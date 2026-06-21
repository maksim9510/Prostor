#!/usr/bin/env python3
"""
Tool Result Compression — сжатие результатов tool calls перед отправкой в LLM.

Экономия токенов на больших выводах:
- Удаление повторяющихся строк (дедупликация с сохранением порядка)
- Сжатие whitespace (несколько пустых строк → одна)
- Обрезка длинных hex/binary строк
- Truncation с smart boundary detection
- Summary для очень больших результатов (>50K chars)

Стратегии применяются последовательно, каждая пропускает только если результат
превышает порог. Маленькие результаты проходят без изменений.
"""

import logging
import re
import textwrap
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Thresholds (in characters)
COMPRESS_THRESHOLD = 5_000      # start compressing at 5K chars
HARD_LIMIT = 100_000            # hard truncation at 100K chars
LARGE_SUMMARY_THRESHOLD = 50_000  # summarize instead of truncate at 50K

# Patterns for binary/hex noise
_HEX_LINE_RE = re.compile(r'^[0-9a-fA-F]{40,}\s*$', re.MULTILINE)
_LONG_HEX_RE = re.compile(r'[0-9a-fA-F]{80,}')
_REPEAT_WS_RE = re.compile(r'\n{4,}')  # 4+ consecutive newlines → 2
_TRAILING_WS_RE = re.compile(r'[ \t]+\n')


def _dedup_consecutive_lines(text: str) -> str:
    """Remove consecutive duplicate lines (keep first occurrence)."""
    lines = text.split("\n")
    result = []
    prev = None
    dup_count = 0

    for line in lines:
        stripped = line.strip()
        if stripped == prev and stripped:
            dup_count += 1
            continue
        if dup_count > 3:
            # Insert a marker showing how many were skipped
            result.append(f"  ... [{dup_count} repeated lines omitted]")
        dup_count = 0
        result.append(line)
        prev = stripped

    if dup_count > 3:
        result.append(f"  ... [{dup_count} repeated lines omitted]")

    return "\n".join(result)


def _compress_whitespace(text: str) -> str:
    """Compress multiple blank lines into one, strip trailing whitespace."""
    # Strip trailing whitespace on each line
    text = _TRAILING_WS_RE.sub("\n", text)
    # 4+ consecutive newlines → 2
    text = _REPEAT_WS_RE.sub("\n\n", text)
    return text


def _clean_hex_noise(text: str) -> str:
    """Replace long hex strings with placeholder."""
    # Full lines of hex (like hash dumps)
    text = _HEX_LINE_RE.sub("[hex line]", text)
    # Inline long hex strings
    text = _LONG_HEX_RE.sub("[hex:80+chars]", text)
    return text


def _smart_truncate(text: str, limit: int) -> str:
    """Truncate at limit, but try to break at a line boundary."""
    if len(text) <= limit:
        return text

    # Try to find a line break near the limit
    break_point = text.rfind("\n", 0, limit)
    if break_point > limit * 0.8:  # found a good break point
        return text[:break_point] + f"\n... [truncated: {len(text) - break_point} more chars]"
    else:
        # No good line break — truncate at limit
        return text[:limit] + f"\n... [truncated: {len(text) - limit} more chars]"


def _summarize_large(text: str) -> str:
    """Create a summary for very large outputs instead of truncating blindly."""
    lines = text.split("\n")
    total = len(lines)

    # Take first 20 + last 20 lines, count middle
    head = lines[:20]
    tail = lines[-20:]

    summary = (
        f"[LARGE OUTPUT SUMMARY — {total} lines, {len(text)} chars]\n"
        + "=== FIRST 20 LINES ===\n"
        + "\n".join(head)
        + f"\n\n... [{total - 40} lines omitted] ...\n"
        + "\n=== LAST 20 LINES ===\n"
        + "\n".join(tail)
        + f"\n[/SUMMARY]"
    )
    return summary


def compress_result(
    content: str,
    tool_name: str = "",
    max_chars: int = HARD_LIMIT,
) -> Tuple[str, Dict[str, Any]]:
    """Compress a tool result before sending to LLM.

    Args:
        content: Raw tool output string
        tool_name: Name of the tool (for logging)
        max_chars: Hard character limit

    Returns:
        (compressed_content, stats_dict)
    """
    original_len = len(content)
    original_lines = content.count("\n") + 1

    if original_len < COMPRESS_THRESHOLD:
        # Too small to bother compressing
        return content, {
            "original_chars": original_len,
            "original_lines": original_lines,
            "compressed_chars": original_len,
            "saved_chars": 0,
            "saved_pct": 0,
            "strategies": [],
        }

    strategies_applied = []
    result = content

    # Strategy 1: Clean hex/binary noise
    if len(result) > COMPRESS_THRESHOLD:
        before = len(result)
        result = _clean_hex_noise(result)
        if len(result) < before:
            strategies_applied.append("hex_noise")

    # Strategy 2: Deduplicate consecutive lines
    if len(result) > COMPRESS_THRESHOLD:
        before = len(result)
        result = _dedup_consecutive_lines(result)
        if len(result) < before:
            strategies_applied.append("dedup_lines")

    # Strategy 3: Compress whitespace
    if len(result) > COMPRESS_THRESHOLD:
        before = len(result)
        result = _compress_whitespace(result)
        if len(result) < before:
            strategies_applied.append("whitespace")

    # Strategy 4: Summarize or truncate
    if len(result) > LARGE_SUMMARY_THRESHOLD:
        result = _summarize_large(result)
        strategies_applied.append("summarize")
    elif len(result) > max_chars:
        result = _smart_truncate(result, max_chars)
        strategies_applied.append("truncate")

    compressed_len = len(result)
    saved = original_len - compressed_len
    saved_pct = (saved / original_len * 100) if original_len > 0 else 0

    stats = {
        "original_chars": original_len,
        "original_lines": original_lines,
        "compressed_chars": compressed_len,
        "saved_chars": saved,
        "saved_pct": round(saved_pct, 1),
        "strategies": strategies_applied,
    }

    if saved > 1000:
        logger.info(
            "compress_result [%s]: %d → %d chars (saved %d, %.1f%%, %s)",
            tool_name, original_len, compressed_len, saved, saved_pct,
            strategies_applied,
        )

    return result, stats


def compress_json_result(
    json_str: str,
    tool_name: str = "",
    max_chars: int = HARD_LIMIT,
) -> str:
    """Compress a JSON tool result, preserving JSON validity.

    If the JSON contains large string fields, compress those fields
    individually and return valid JSON.
    """
    import json

    try:
        data = json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        # Not JSON — compress as plain text
        compressed, _ = compress_result(json_str, tool_name, max_chars)
        return compressed

    # Recursively compress long string values in the JSON
    def _compress_strings(obj, depth=0):
        if depth > 10:  # prevent infinite recursion
            return obj
        if isinstance(obj, str):
            if len(obj) > COMPRESS_THRESHOLD:
                compressed, stats = compress_result(obj, tool_name, max_chars)
                return compressed
            return obj
        elif isinstance(obj, dict):
            return {k: _compress_strings(v, depth + 1) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [_compress_strings(v, depth + 1) for v in obj]
        return obj

    compressed_data = _compress_strings(data)

    # Check if compression happened
    result = json.dumps(compressed_data, ensure_ascii=False, indent=2)
    if len(result) > max_chars:
        # Still too large — truncate the JSON string itself
        result = result[:max_chars] + '\n... [JSON truncated]'

    return result


__all__ = [
    "compress_result",
    "compress_json_result",
    "COMPRESS_THRESHOLD",
    "HARD_LIMIT",
]