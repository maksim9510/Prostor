#!/usr/bin/env python3
"""
HashLine — hash-based line matching for fast, deterministic code replacement.

Multi-level index for O(1) lookup instead of O(n) sequential scan.
Designed for files up to 20,000+ lines.

Architecture:
    - Line index: hash(normalized line) → list of line positions
    - Block index: hash(normalized block of 5/10/20 lines) → list of block positions
    - Token index: hash(token) → list of (line, char_offset) for substring search
    - Bloom filter: instant reject when pattern definitely not in file
    - Indentation fingerprint: relative indent pattern for structural matching
    - Index cache: reuse between sequential patches (mtime + size based)
    - Parallel build: ThreadPoolExecutor for files >5000 lines

API:
    hashline_find_and_replace(content, old_string, new_string, replace_all, file_path, file_mtime)
        → (new_content, match_count, strategy_name, error_message)

Integration:
    Drop-in fast path before fuzzy_match.py's 9 strategies.
    If hashline finds a match → returns immediately.
    If not → caller falls back to fuzzy_match.
"""

import hashlib
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Optional dependencies — graceful fallback to stdlib
# ---------------------------------------------------------------------------

try:
    import xxhash
    _HASH_FUNC = lambda s: xxhash.xxh64(s).hexdigest()
    _HASH_NAME = "xxhash64"
except ImportError:
    _HASH_FUNC = lambda s: hashlib.blake2b(s.encode("utf-8"), digest_size=8).hexdigest()
    _HASH_NAME = "blake2b8"

try:
    from pybloom_live import ScalableBloomFilter as _PyBloom
    _BLOOM_AVAILABLE = True
except ImportError:
    _BLOOM_AVAILABLE = False

# ---------------------------------------------------------------------------
# Unicode normalization (shared with fuzzy_match)
# ---------------------------------------------------------------------------

UNICODE_MAP = {
    "\u201c": '"', "\u201d": '"',    # smart double quotes
    "\u2018": "'", "\u2019": "'",    # smart single quotes
    "\u2014": "--", "\u2013": "-",   # em/en dashes
    "\u2026": "...", "\u00a0": " ",  # ellipsis and non-breaking space
}

def _unicode_normalize(text: str) -> str:
    for char, repl in UNICODE_MAP.items():
        text = text.replace(char, repl)
    return text

# ---------------------------------------------------------------------------
# Line key — normalized hash of a single line
# ---------------------------------------------------------------------------

_WS_RE = re.compile(r'[ \t]+')


def _normalize_line(line: str) -> str:
    """Normalize a line for hashing: unicode + strip + collapse whitespace."""
    line = _unicode_normalize(line)
    line = line.strip()
    line = _WS_RE.sub(" ", line)
    return line


def _line_key(line: str) -> str:
    """Hash a normalized line. Returns hex string."""
    return _HASH_FUNC(_normalize_line(line))


def _block_key(lines: List[str]) -> str:
    """Hash a block of lines (normalized). Returns hex string."""
    normalized = "\n".join(_normalize_line(l) for l in lines)
    return _HASH_FUNC(normalized)


# ---------------------------------------------------------------------------
# Token key — for inverted token index (substring/phrase search)
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r'[\w\u0410-\u044f\u0451]+')


def _tokenize(line: str) -> List[Tuple[str, int]]:
    """Tokenize a line into (normalized_token, char_offset) pairs."""
    normalized = _unicode_normalize(line)
    tokens = []
    for m in _TOKEN_RE.finditer(normalized):
        token = m.group().lower()
        tokens.append((token, m.start()))
    return tokens


def _token_key(token: str) -> str:
    """Hash a token for the inverted index."""
    return _HASH_FUNC(token)

# ---------------------------------------------------------------------------
# Indentation fingerprint — relative indent pattern
# ---------------------------------------------------------------------------


def _leading_whitespace(line: str) -> str:
    i = 0
    while i < len(line) and line[i] in (" ", "\t"):
        i += 1
    return line[:i]


def _indent_fingerprint(lines: List[str]) -> str:
    """Relative indentation pattern, not absolute.

    ['    if x:', '        y()']  → '0|+4'
    ['  if x:', '      y()']     → '0|+4'  (same fingerprint!)

    Blank lines get '=' marker.
    """
    if not lines:
        return ""
    fingerprints = ["0"]
    prev_indent = len(_leading_whitespace(lines[0]))
    for line in lines[1:]:
        if not line.strip():
            fingerprints.append("=")
            continue
        curr = len(_leading_whitespace(line))
        delta = curr - prev_indent
        if delta == 0:
            fingerprints.append("=")
        else:
            fingerprints.append(f"{delta:+d}")
        prev_indent = curr
    return "|".join(fingerprints)

# ---------------------------------------------------------------------------
# Bloom filter — instant reject
# ---------------------------------------------------------------------------


class _BloomSet:
    """Simple set-based bloom filter fallback (no false negatives)."""

    def __init__(self, capacity: int = 0):
        self._set: set = set()

    def add(self, item: str):
        self._set.add(item)

    def __contains__(self, item: str) -> bool:
        return item in self._set

    def add_many(self, items):
        self._set.update(items)


class BloomFilter:
    """Bloom filter with fallback to set if pybloom_live not available."""

    def __init__(self, capacity: int = 20000):
        if _BLOOM_AVAILABLE:
            self._bf = _PyBloom(
                initial_capacity=capacity,
                error_rate=0.001,
            )
            self._is_set = False
        else:
            self._bf = _BloomSet(capacity)
            self._is_set = True

    def add(self, item: str):
        self._bf.add(item)

    def add_many(self, items):
        if self._is_set:
            self._bf.add_many(items)
        else:
            for item in items:
                self._bf.add(item)

    def __contains__(self, item: str) -> bool:
        return item in self._bf

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class LineRef:
    """Reference to a line in the original content."""
    line_idx: int
    start_pos: int
    end_pos: int
    indent: str
    stripped: str

@dataclass
class BlockRef:
    """Reference to a block of lines."""
    start_line: int
    line_count: int
    start_pos: int
    end_pos: int

@dataclass
class TokenRef:
    """Reference to a token occurrence in the original content."""
    line_idx: int
    char_offset: int
    token: str


@dataclass
class CachedIndex:
    """Cached index with validation metadata."""
    index: "HashLineIndex"
    mtime: Optional[float]
    size: int

# ---------------------------------------------------------------------------
# HashLineIndex — multi-level index
# ---------------------------------------------------------------------------


class HashLineIndex:
    """Multi-level hash index for fast line/block/token matching."""

    # Block sizes for pre-hashing
    BLOCK_SIZES = [5, 10, 20]

    # Threshold for parallel build
    PARALLEL_THRESHOLD = 5000

    def __init__(self, content: str, file_path: Optional[str] = None,
                 file_mtime: Optional[float] = None):
        self.content = content
        self.lines = content.split("\n")
        self.line_count = len(self.lines)
        self.file_path = file_path
        self.file_mtime = file_mtime

        # Line positions (precomputed for O(1) lookup)
        self._line_starts: List[int] = []
        self._compute_line_starts()

        # Indexes
        self.line_index: Dict[str, List[LineRef]] = {}
        self.block_indexes: Dict[int, Dict[str, List[BlockRef]]] = {
            size: {} for size in self.BLOCK_SIZES
        }
        self.token_index: Dict[str, List[TokenRef]] = {}
        self.bloom: BloomFilter = BloomFilter(max(self.line_count * 2, 20000))

        # Build
        self._build()

    def _compute_line_starts(self):
        """Precompute character offset of each line start."""
        pos = 0
        for line in self.lines:
            self._line_starts.append(pos)
            pos += len(line) + 1  # +1 for \n

    def _line_end(self, idx: int) -> int:
        """Character offset of the end of line idx (exclusive)."""
        if idx + 1 < len(self._line_starts):
            return self._line_starts[idx + 1] - 1  # -1 for \n
        return len(self.content)

    def _build(self):
        """Build all indexes."""
        if self.line_count > self.PARALLEL_THRESHOLD:
            self._build_parallel()
        else:
            self._build_sequential()

    def _build_sequential(self):
        """Build indexes in a single thread."""
        # Line index + token index
        for i, line in enumerate(self.lines):
            key = _line_key(line)
            ref = LineRef(
                line_idx=i,
                start_pos=self._line_starts[i],
                end_pos=self._line_end(i),
                indent=_leading_whitespace(line),
                stripped=line.strip(),
            )
            self.line_index.setdefault(key, []).append(ref)

            # Token index
            for token, offset in _tokenize(line):
                tkey = _token_key(token)
                self.token_index.setdefault(tkey, []).append(
                    TokenRef(line_idx=i, char_offset=offset, token=token)
                )

        # Block indexes
        for size in self.BLOCK_SIZES:
            for i in range(self.line_count - size + 1):
                block = self.lines[i:i + size]
                bkey = _block_key(block)
                self.block_indexes[size].setdefault(bkey, []).append(
                    BlockRef(
                        start_line=i,
                        line_count=size,
                        start_pos=self._line_starts[i],
                        end_pos=self._line_end(i + size - 1),
                    )
                )

        # Bloom filter — add all line keys, block keys, AND token keys
        bloom_items = list(self.line_index.keys())
        for size in self.BLOCK_SIZES:
            bloom_items.extend(self.block_indexes[size].keys())
        # Add token keys so bloom_check passes for substring patterns
        bloom_items.extend(self.token_index.keys())
        self.bloom.add_many(bloom_items)

    def _build_parallel(self):
        """Build indexes using multiple threads (for large files)."""
        num_workers = min(4, os.cpu_count() or 2)

        # Split lines into chunks
        chunk_size = max(1, self.line_count // num_workers)
        chunks = []
        for start in range(0, self.line_count, chunk_size):
            end = min(start + chunk_size, self.line_count)
            chunks.append((start, end))

        # Build line + token index in parallel
        def build_chunk(start_end):
            start, end = start_end
            local_line_idx: Dict[str, List[LineRef]] = {}
            local_token_idx: Dict[str, List[TokenRef]] = {}
            for i in range(start, end):
                line = self.lines[i]
                key = _line_key(line)
                ref = LineRef(
                    line_idx=i,
                    start_pos=self._line_starts[i],
                    end_pos=self._line_end(i),
                    indent=_leading_whitespace(line),
                    stripped=line.strip(),
                )
                local_line_idx.setdefault(key, []).append(ref)
                for token, offset in _tokenize(line):
                    tkey = _token_key(token)
                    local_token_idx.setdefault(tkey, []).append(
                        TokenRef(line_idx=i, char_offset=offset, token=token)
                    )
            return local_line_idx, local_token_idx

        with ThreadPoolExecutor(max_workers=num_workers) as pool:
            results = list(pool.map(build_chunk, chunks))

        # Merge results
        for local_line_idx, local_token_idx in results:
            for key, refs in local_line_idx.items():
                self.line_index.setdefault(key, []).extend(refs)
            for key, refs in local_token_idx.items():
                self.token_index.setdefault(key, []).extend(refs)

        # Block indexes (sequential — blocks span chunk boundaries)
        for size in self.BLOCK_SIZES:
            for i in range(self.line_count - size + 1):
                block = self.lines[i:i + size]
                bkey = _block_key(block)
                self.block_indexes[size].setdefault(bkey, []).append(
                    BlockRef(
                        start_line=i,
                        line_count=size,
                        start_pos=self._line_starts[i],
                        end_pos=self._line_end(i + size - 1),
                    )
                )

        # Bloom filter
        bloom_items = list(self.line_index.keys())
        for size in self.BLOCK_SIZES:
            bloom_items.extend(self.block_indexes[size].keys())
        self.bloom.add_many(bloom_items)

    # -------------------------------------------------------------------
    # Search methods
    # -------------------------------------------------------------------

    def bloom_check(self, pattern: str) -> bool:
        """Quick check: pattern might be in the file? (no false negatives).

        Checks both line keys (for full-line patterns) and token keys
        (for substring/phrase patterns). If neither is found, the pattern
        is definitely not in the file.
        """
        pattern_lines = pattern.split("\n")
        first_key = _line_key(pattern_lines[0])
        if first_key in self.bloom:
            return True
        # Check if pattern is a substring (token-based)
        tokens = _tokenize(pattern_lines[0])
        if tokens:
            tkey = _token_key(tokens[0][0])
            if tkey in self.bloom:
                return True
            # Check remaining pattern lines tokens
            for pline in pattern_lines[1:]:
                for token, _ in _tokenize(pline):
                    tkey = _token_key(token)
                    if tkey in self.bloom:
                        return True
        return False

    def find_line_matches(self, pattern: str) -> List[Tuple[int, int]]:
        """Find matches using line index (for full-line / multi-line patterns)."""
        pattern_lines = pattern.split("\n")
        pcount = len(pattern_lines)

        if pcount == 0:
            return []

        # Single-line pattern
        if pcount == 1:
            key = _line_key(pattern_lines[0])
            candidates = self.line_index.get(key, [])
            matches = []
            for cand in candidates:
                if _verify_match(self.lines, cand.line_idx, pattern_lines):
                    matches.append((cand.start_pos, cand.end_pos))
            return matches

        # Multi-line pattern — use first line as anchor
        first_key = _line_key(pattern_lines[0])
        candidates = self.line_index.get(first_key, [])
        matches = []
        for cand in candidates:
            if cand.line_idx + pcount > self.line_count:
                continue
            # Check all pattern lines match
            all_ok = True
            for j in range(pcount):
                file_key = _line_key(self.lines[cand.line_idx + j])
                pat_key = _line_key(pattern_lines[j])
                if file_key != pat_key:
                    all_ok = False
                    break
            if not all_ok:
                continue
            # Verify (collision protection)
            if not _verify_match(self.lines, cand.line_idx, pattern_lines):
                continue
            start_pos = self._line_starts[cand.line_idx]
            end_pos = self._line_end(cand.line_idx + pcount - 1)
            matches.append((start_pos, end_pos))
        return matches

    def find_block_matches(self, pattern: str) -> List[Tuple[int, int]]:
        """Find matches using block index (for patterns matching block sizes)."""
        pattern_lines = pattern.split("\n")
        pcount = len(pattern_lines)

        # Select best block size
        best_size = None
        for size in self.BLOCK_SIZES:
            if pcount >= size:
                best_size = size
        if best_size is None:
            return []

        # Use first block as anchor
        first_block = pattern_lines[:best_size]
        bkey = _block_key(first_block)
        candidates = self.block_indexes[best_size].get(bkey, [])
        matches = []
        for cand in candidates:
            if cand.start_line + pcount > self.line_count:
                continue
            # Verify full pattern
            if not _verify_match(self.lines, cand.start_line, pattern_lines):
                continue
            start_pos = self._line_starts[cand.start_line]
            end_pos = self._line_end(cand.start_line + pcount - 1)
            matches.append((start_pos, end_pos))
        return matches

    def find_token_matches(self, pattern: str) -> List[Tuple[int, int]]:
        """Find substring/phrase matches using token index."""
        pattern_lines = pattern.split("\n")

        # Tokenize the pattern
        all_tokens = []
        for pline in pattern_lines:
            for token, _ in _tokenize(pline):
                all_tokens.append(token)

        if not all_tokens:
            return []

        # Find lines containing all tokens (intersection)
        # Start with rarest token (fewest occurrences)
        token_refs = []
        for token in all_tokens:
            tkey = _token_key(token)
            refs = self.token_index.get(tkey, [])
            if not refs:
                return []  # token not in file → no match
            token_refs.append((token, refs))

        # Sort by frequency (rarest first)
        token_refs.sort(key=lambda x: len(x[1]))

        # Get candidate lines from rarest token
        rarest_token, rarest_refs = token_refs[0]
        candidate_lines = set(ref.line_idx for ref in rarest_refs)

        # Filter: lines must contain all tokens
        for token, refs in token_refs[1:]:
            lines_with_token = set(ref.line_idx for ref in refs)
            candidate_lines &= lines_with_token
            if not candidate_lines:
                return []

        # For each candidate line, find the pattern substring
        matches = []
        pattern_text = pattern.strip()

        for line_idx in sorted(candidate_lines):
            line = self.lines[line_idx]
            # Check if pattern appears in the line (normalized)
            norm_line = _normalize_line(line)
            norm_pattern = _normalize_line(pattern)

            if norm_pattern in norm_line:
                # Find exact position
                idx = norm_line.find(norm_pattern)
                if idx >= 0:
                    # Map back to original position (approximate)
                    start_pos = self._line_starts[line_idx]
                    end_pos = self._line_end(line_idx)
                    matches.append((start_pos, end_pos))

        return matches

    def find_matches(self, pattern: str) -> List[Tuple[int, int]]:
        """Find all matches using the best strategy.

        Tries: bloom reject → block index → line index → token index.
        """
        # Bloom check
        if not self.bloom_check(pattern):
            return []

        pattern_lines = pattern.split("\n")
        pcount = len(pattern_lines)

        # Select strategy based on pattern size
        if pcount >= 5:
            # Try block index first (for large patterns)
            matches = self.find_block_matches(pattern)
            if matches:
                return matches
            # Fall through to line index

        # Line index (works for any pattern size)
        matches = self.find_line_matches(pattern)
        if matches:
            return matches

        # Token index (for substrings within lines)
        matches = self.find_token_matches(pattern)
        if matches:
            return matches

        return []

# ---------------------------------------------------------------------------
# Verification — collision protection
# ---------------------------------------------------------------------------


def _verify_match(lines: List[str], start_idx: int, pattern_lines: List[str]) -> bool:
    """Verify that lines[start_idx:start_idx+len(pattern_lines)] matches pattern.

    Compares normalized content (strip + whitespace collapse) to catch
    hash collisions. This is the safety net that makes hash collisions
    harmless — a collision would need identical normalized content, which
    for practical purposes means the content IS the same.
    """
    pcount = len(pattern_lines)
    if start_idx + pcount > len(lines):
        return False

    for j in range(pcount):
        file_line = _normalize_line(lines[start_idx + j])
        pat_line = _normalize_line(pattern_lines[j])
        if file_line != pat_line:
            return False
    return True

# ---------------------------------------------------------------------------
# Reindent replacement — adjust new_string to match file's indentation
# ---------------------------------------------------------------------------


def _first_meaningful_line(text: str) -> Optional[str]:
    for line in text.split("\n"):
        if line.strip():
            return line
    return None


def _first_indented_line(text: str) -> Optional[str]:
    """Return the first line of ``text`` that has indentation (leading whitespace)."""
    for line in text.split("\n"):
        if line.strip() and _leading_whitespace(line):
            return line
    # Fall back to first meaningful line
    return _first_meaningful_line(text)


def _reindent_replacement(file_region: str, old_string: str, new_string: str) -> str:
    """Adjust new_string indentation to match file_region's actual indent.

    If LLM sent 2-space indent but file has 4-space, this shifts new_string
    to use the file's base indent while preserving relative nesting.
    """
    if not new_string:
        return new_string

    old_first = _first_indented_line(old_string)
    file_first = _first_indented_line(file_region)
    if old_first is None or file_first is None:
        return new_string

    old_indent = _leading_whitespace(old_first)
    file_indent = _leading_whitespace(file_first)

    if old_indent == file_indent:
        return new_string

    out_lines: List[str] = []
    for line in new_string.split("\n"):
        if not line.strip():
            out_lines.append(line)
            continue
        line_indent = _leading_whitespace(line)
        if line_indent.startswith(old_indent):
            remainder = line[len(old_indent):]
            out_lines.append(file_indent + remainder)
        else:
            out_lines.append(file_indent + line.lstrip(" \t"))
    return "\n".join(out_lines)

# ---------------------------------------------------------------------------
# Apply replacements
# ---------------------------------------------------------------------------


def _apply_replacements(content: str, matches: List[Tuple[int, int]],
                        new_string: str, old_string: Optional[str] = None) -> str:
    """Apply replacements at given positions."""
    sorted_matches = sorted(matches, key=lambda x: x[0], reverse=True)
    result = content
    for start, end in sorted_matches:
        if old_string is not None:
            file_region = content[start:end]
            adjusted = _reindent_replacement(file_region, old_string, new_string)
        else:
            adjusted = new_string
        result = result[:start] + adjusted + result[end:]
    return result

# ---------------------------------------------------------------------------
# Index cache — reuse between sequential patches
# ---------------------------------------------------------------------------

_INDEX_CACHE: Dict[str, CachedIndex] = {}
_CACHE_LOCK = threading.Lock()


def get_index(content: str, file_path: Optional[str] = None,
              file_mtime: Optional[float] = None) -> HashLineIndex:
    """Get a HashLineIndex, from cache if valid, or build new."""
    if file_path:
        cache_key = os.path.abspath(file_path)
        with _CACHE_LOCK:
            cached = _INDEX_CACHE.get(cache_key)
            if cached:
                # Validate: mtime + size must match
                if (cached.mtime == file_mtime and cached.size == len(content)):
                    return cached.index
            # Build new
            index = HashLineIndex(content, file_path, file_mtime)
            _INDEX_CACHE[cache_key] = CachedIndex(index, file_mtime, len(content))
            return index
    else:
        # No file_path → no caching
        return HashLineIndex(content)

# ---------------------------------------------------------------------------
# Main API — hashline_find_and_replace
# ---------------------------------------------------------------------------


def hashline_find_and_replace(
    content: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
    file_path: Optional[str] = None,
    file_mtime: Optional[float] = None,
) -> Tuple[str, int, Optional[str], Optional[str]]:
    """Find and replace text using hash-based line matching.

    Args:
        content: File content to search in.
        old_string: Text to find.
        new_string: Replacement text.
        replace_all: If True, replace all occurrences; if False, require uniqueness.
        file_path: Optional file path for index caching.
        file_mtime: Optional file modification time for cache validation.

    Returns:
        Tuple of (new_content, match_count, strategy_name, error_message).
        - If successful: (modified_content, N, "hashline", None)
        - If failed: (original_content, 0, None, error_description)
    """
    if not old_string:
        return content, 0, None, "old_string cannot be empty"

    if old_string == new_string:
        return content, 0, None, "old_string and new_string are identical"

    # Fast path 0: exact string match (before building any index)
    # This is the most common case — pattern is literally in the file.
    # Costs O(n) but with C-level str.find, much faster than building a hash index.
    exact_matches = []
    search_start = 0
    while True:
        pos = content.find(old_string, search_start)
        if pos == -1:
            break
        exact_matches.append((pos, pos + len(old_string)))
        search_start = pos + 1
        if not replace_all and len(exact_matches) > 1:
            break

    if exact_matches:
        if len(exact_matches) > 1 and not replace_all:
            return content, 0, None, (
                f"Found {len(exact_matches)} matches for old_string. "
                f"Provide more context to make it unique, or use replace_all=True."
            )
        if not replace_all:
            # Single exact match — apply directly
            start, end = exact_matches[0]
            new_content = content[:start] + new_string + content[end:]
            return new_content, 1, "hashline", None
        # replace_all — apply all exact matches
        sorted_matches = sorted(exact_matches, key=lambda x: x[0], reverse=True)
        result = content
        for start, end in sorted_matches:
            result = result[:start] + new_string + result[end:]
        return result, len(exact_matches), "hashline", None

    # Fast path 0.5: quick negative check — if first line of pattern
    # is not anywhere in content, no strategy will find it.
    first_line = old_string.split("\n")[0].strip()
    if first_line and first_line not in content:
        return content, 0, None, "Could not find a match for old_string in the file"

    # Get index (cached or new)
    index = get_index(content, file_path, file_mtime)

    # Find matches
    matches = index.find_matches(old_string)

    if not matches:
        return content, 0, None, "Could not find a match for old_string in the file"

    if len(matches) > 1 and not replace_all:
        return content, 0, None, (
            f"Found {len(matches)} matches for old_string. "
            f"Provide more context to make it unique, or use replace_all=True."
        )

    # Apply replacements
    new_content = _apply_replacements(
        content, matches, new_string,
        old_string=old_string,  # triggers reindent
    )

    return new_content, len(matches), "hashline", None

# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------

__all__ = [
    "HashLineIndex",
    "hashline_find_and_replace",
    "get_index",
    "BloomFilter",
    "LineRef",
    "BlockRef",
    "TokenRef",
]

# ---------------------------------------------------------------------------
# Auto-apply monkey-patch to fuzzy_match on import
# ---------------------------------------------------------------------------

try:
    from tools.fuzzy_match_patch import apply_patch as _apply_fuzzy_patch
    _apply_fuzzy_patch()
except ImportError:
    pass  # fuzzy_match_patch not available — hashline works standalone