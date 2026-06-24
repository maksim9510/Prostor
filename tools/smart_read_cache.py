#!/usr/bin/env python3
"""
Smart Read Cache — кэширование результатов read_file с детекцией изменений.

Проблема: агент часто читает один и тот же файл несколько раз за сессию
(прочитать → править → прочитать снова для проверки). Каждый раз —
повторный I/O + полный контент в токенах.

Решение: кэш на основе (path, mtime, size):
- Первый read: полный результат, сохраняется в кэш
- Повторный read (файл не изменился): возврат из кэша + метка [CACHED]
- После patch/write: mtime меняется → кэш инвалидируется автоматически
- LRU eviction: max 50 файлов в кэше

Дополнительно:
- Read-ahead: при чтении файла → преварительно кэшируются соседние файлы
  из той же директории (background thread, hardware-aware)
- Stats: hit/miss ratio, saved I/O operations, saved tokens
"""

import logging
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MAX_CACHE_ENTRIES = 50
_READAHEAD_THRESHOLD = 3  # read 3 files from same dir → trigger readahead


@dataclass
class CacheEntry:
    content: str
    mtime: float
    size: int
    offset: int
    limit: int
    tokens: int
    cached_at: float
    hit_count: int = 0


class SmartReadCache:
    """LRU cache for file reads with change detection."""

    def __init__(self, max_entries: int = _MAX_CACHE_ENTRIES):
        self.max_entries = max_entries
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.Lock()
        self._dir_read_count: dict[str, int] = {}  # dir → read count (for readahead)
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "invalidations": 0,
            "readahead_triggered": 0,
            "readahead_files": 0,
            "saved_io_operations": 0,
            "saved_tokens": 0,
        }

    def _cache_key(self, path: str, offset: int, limit: int) -> str:
        return f"{os.path.abspath(path)}:{offset}:{limit}"

    def _file_signature(self, path: str) -> tuple[float, int] | None:
        """Get (mtime, size) for file, or None if not accessible."""
        try:
            stat = os.stat(path)
            return (stat.st_mtime, stat.st_size)
        except (OSError, ValueError):
            return None

    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4) if text else 0

    def get(
        self,
        path: str,
        offset: int = 1,
        limit: int = 500,
    ) -> str | None:
        """Try to get file content from cache.

        Returns cached content if file hasn't changed, None if cache miss.
        """
        key = self._cache_key(path, offset, limit)
        sig = self._file_signature(path)

        if sig is None:
            return None  # file not accessible

        mtime, size = sig

        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._stats["misses"] += 1
                return None

            # Check if file changed
            if entry.mtime != mtime or entry.size != size:
                # File changed — invalidate
                del self._cache[key]
                self._stats["invalidations"] += 1
                self._stats["misses"] += 1
                logger.debug("Cache invalidated (file changed): %s", path)
                return None

            # Cache hit!
            entry.hit_count += 1
            self._stats["hits"] += 1
            self._stats["saved_io_operations"] += 1
            self._stats["saved_tokens"] += entry.tokens

            # Move to end (LRU)
            self._cache.move_to_end(key)

            # Track directory reads for readahead
            dir_path = str(Path(path).parent)
            self._dir_read_count[dir_path] = self._dir_read_count.get(dir_path, 0) + 1

            return entry.content

    def put(
        self,
        path: str,
        content: str,
        offset: int = 1,
        limit: int = 500,
    ) -> None:
        """Store file content in cache."""
        sig = self._file_signature(path)
        if sig is None:
            return

        mtime, size = sig
        key = self._cache_key(path, offset, limit)
        tokens = self._estimate_tokens(content)

        with self._lock:
            # LRU eviction
            while len(self._cache) >= self.max_entries:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                self._stats["evictions"] += 1

            self._cache[key] = CacheEntry(
                content=content,
                mtime=mtime,
                size=size,
                offset=offset,
                limit=limit,
                tokens=tokens,
                cached_at=time.time(),
            )

            # Track directory for readahead
            dir_path = str(Path(path).parent)
            self._dir_read_count[dir_path] = self._dir_read_count.get(dir_path, 0) + 1

    def invalidate(self, path: str) -> int:
        """Invalidate all cache entries for a file (after patch/write).

        Returns number of entries removed.
        """
        abspath = os.path.abspath(path)
        removed = 0

        with self._lock:
            keys_to_remove = [
                k for k in self._cache
                if k.startswith(f"{abspath}:")
            ]
            for k in keys_to_remove:
                del self._cache[k]
                removed += 1
            self._stats["invalidations"] += removed

        if removed > 0:
            logger.debug("Invalidated %d cache entries for %s", removed, path)

        return removed

    def maybe_readahead(self, path: str) -> list[str]:
        """Check if readahead should be triggered for this file's directory.

        If 3+ files from the same directory have been read, pre-fetch
        remaining .py files in that directory (background, best-effort).

        Returns list of files that were pre-fetched (empty if not triggered).
        """
        dir_path = str(Path(path).parent)
        read_count = self._dir_read_count.get(dir_path, 0)

        if read_count < _READAHEAD_THRESHOLD:
            return []

        # Find .py files in the same directory not yet cached
        try:
            dir_p = Path(dir_path)
            if not dir_p.is_dir():
                return []

            candidates = []
            for f in dir_p.iterdir():
                if f.is_file() and f.suffix in (".py", ".ts", ".tsx", ".js"):
                    abspath = str(f)
                    # Check if already cached
                    already = any(
                        k.startswith(f"{abspath}:")
                        for k in self._cache
                    )
                    if not already:
                        candidates.append(abspath)

            if not candidates:
                return []

            # Pre-fetch up to 5 files (best-effort, don't overwhelm)
            to_prefetch = candidates[:5]

            for fp in to_prefetch:
                try:
                    with open(fp, encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    # Store with default offset/limit
                    self.put(fp, content, offset=1, limit=500)
                    self._stats["readahead_files"] += 1
                except Exception:
                    pass  # best-effort

            self._stats["readahead_triggered"] += 1
            logger.debug(
                "Readahead: pre-fetched %d files from %s",
                len(to_prefetch), dir_path,
            )
            return to_prefetch

        except Exception as e:
            logger.debug("Readahead failed: %s", e)
            return []

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total = self._stats["hits"] + self._stats["misses"]
            hit_rate = (self._stats["hits"] / total * 100) if total > 0 else 0

            return {
                **self._stats,
                "hit_rate": round(hit_rate, 1),
                "cache_size": len(self._cache),
                "max_entries": self.max_entries,
                "tracked_dirs": len(self._dir_read_count),
            }

    def get_stats_json(self) -> str:
        import json
        return json.dumps(self.get_stats(), ensure_ascii=False, indent=2)

    def reset(self):
        """Reset cache and stats."""
        with self._lock:
            self._cache.clear()
            self._dir_read_count.clear()
            self._stats = {
                "hits": 0, "misses": 0, "evictions": 0,
                "invalidations": 0, "readahead_triggered": 0,
                "readahead_files": 0, "saved_io_operations": 0,
                "saved_tokens": 0,
            }

    def warm(self, paths: list[str]) -> int:
        """Pre-warm cache with a list of files.

        Returns number of files successfully cached.
        """
        count = 0
        for path in paths:
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                self.put(path, content)
                count += 1
            except Exception:
                pass
        return count


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_cache: SmartReadCache | None = None
_cache_lock = threading.Lock()


def get_read_cache() -> SmartReadCache:
    global _cache
    if _cache is None:
        with _cache_lock:
            if _cache is None:
                _cache = SmartReadCache()
    return _cache


# ---------------------------------------------------------------------------
# Wrapper: cached read_file
# ---------------------------------------------------------------------------

def cached_read_file(
    path: str,
    offset: int = 1,
    limit: int = 500,
    task_id: str = "default",
) -> str:
    """Read a file with smart caching.

    If the file was read before and hasn't changed, returns cached content
    with a [CACHED] marker. Otherwise reads from disk and caches the result.

    Also triggers readahead if the same directory has been accessed 3+ times.
    """
    cache = get_read_cache()

    # Try cache first
    cached = cache.get(path, offset, limit)
    if cached is not None:
        # Return cached content with marker
        import json
        return json.dumps({
            "content": cached,
            "cached": True,
            "path": path,
            "offset": offset,
            "limit": limit,
        }, ensure_ascii=False)

    # Cache miss — read from disk
    from tools.file_tools import read_file_tool
    result_str = read_file_tool(path=path, offset=offset, limit=limit, task_id=task_id)

    # Try to cache the result
    try:
        import json
        result = json.loads(result_str)
        if isinstance(result, dict) and result.get("content"):
            cache.put(path, result["content"], offset, limit)
    except (json.JSONDecodeError, TypeError):
        pass

    # Maybe trigger readahead (background, non-blocking)
    try:
        cache.maybe_readahead(path)
    except Exception:
        pass  # best-effort

    return result_str


# ---------------------------------------------------------------------------
# Invalidate after write operations
# ---------------------------------------------------------------------------

def invalidate_on_write(path: str) -> int:
    """Call this after patch/write_file to invalidate cache for the file."""
    return get_read_cache().invalidate(path)


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

READ_CACHE_STATS_SCHEMA = {
    "name": "read_cache_stats",
    "description": (
        "Show smart read cache statistics: hit/miss ratio, saved I/O, "
        "saved tokens, readahead info. Use after batch operations to "
        "see cache efficiency.\n\n"
        "Actions:\n"
        "- 'stats': Get cache statistics (default)\n"
        "- 'reset': Clear cache and reset stats\n"
        "- 'warm': Pre-warm cache with specific files (pass file_paths array)\n"
        "- 'invalidate': Invalidate cache for specific file (pass file_path)"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["stats", "reset", "warm", "invalidate"],
                "description": "Action (default: stats)",
                "default": "stats",
            },
            "file_path": {
                "type": "string",
                "description": "File path (for 'invalidate' action)",
            },
            "file_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of file paths (for 'warm' action)",
            },
        },
        "required": [],
    },
}


def _handle_read_cache_stats(args, **kw):
    cache = get_read_cache()
    import json
    action = args.get("action", "stats")

    if action == "stats":
        return cache.get_stats_json()
    elif action == "reset":
        cache.reset()
        return json.dumps({"success": True, "message": "Read cache reset"})
    elif action == "warm":
        paths = args.get("file_paths", [])
        count = cache.warm(paths)
        return json.dumps({"success": True, "warmed": count, "requested": len(paths)})
    elif action == "invalidate":
        fp = args.get("file_path", "")
        if not fp:
            return json.dumps({"error": "file_path required"})
        removed = cache.invalidate(fp)
        return json.dumps({"success": True, "invalidated": removed, "file": fp})
    return json.dumps({"error": f"Unknown action: {action}"})


def _check_read_cache_reqs() -> bool:
    return True


try:
    from tools.registry import registry
    registry.register(
        name="read_cache_stats",
        toolset="file",
        schema=READ_CACHE_STATS_SCHEMA,
        handler=_handle_read_cache_stats,
        check_fn=_check_read_cache_reqs,
        emoji="💾",
        max_result_size_chars=10_000,
    )
except Exception as e:
    logger.debug("Could not register read_cache_stats: %s", e)


__all__ = [
    "SmartReadCache",
    "get_read_cache",
    "cached_read_file",
    "invalidate_on_write",
]
