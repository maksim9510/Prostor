#!/usr/bin/env python3
"""
HashLine Persistent Index Cache — сохранение индекса на диск между сессиями.

Если файл не изменился (mtime + size match), индекс загружается с диска
вместо перестроения с нуля. Это экономит ~50-200ms на больших файлах.

Кэш хранится в ~/.prostor/cache/hashline-index/ как pickle-файлы.
Имя файла: hash(<abspath>) + mtime + size → обеспечивает уникальность.

Cache invalidation: mtime + size. Если файл изменился — индекс перестраивается.
LRU eviction: при превышении max_entries (по умолчанию 100) самые старые удаляются.
"""

import hashlib
import logging
import os
import pickle
import threading
import time
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_CACHE_DIR: Optional[Path] = None
_CACHE_LOCK = threading.Lock()
_MAX_ENTRIES = 100  # max cached indexes on disk
_MAX_CACHE_SIZE_MB = 200  # max total cache size on disk


def _get_cache_dir() -> Path:
    """Get or create the persistent cache directory."""
    global _CACHE_DIR
    if _CACHE_DIR is not None:
        return _CACHE_DIR

    try:
        from prostor_constants import get_prostor_home
        home = Path(get_prostor_home())
    except ImportError:
        home = Path.home() / ".prostor"

    cache_dir = home / "cache" / "hashline-index"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.debug("Could not create hashline cache dir: %s", e)

    _CACHE_DIR = cache_dir
    return cache_dir


def _cache_key(file_path: str, mtime: float, size: int) -> str:
    """Generate cache key from file path + mtime + size."""
    abspath = os.path.abspath(file_path)
    key_str = f"{abspath}|{mtime}|{size}"
    return hashlib.blake2b(key_str.encode(), digest_size=16).hexdigest()


def _cache_path(key: str) -> Path:
    """Get the disk path for a cache key."""
    return _get_cache_dir() / f"{key}.pkl"


def save_index(index, file_path: str, mtime: Optional[float], size: int) -> bool:
    """Save a HashLineIndex to disk cache.

    Args:
        index: HashLineIndex instance
        file_path: Original file path
        mtime: File modification time
        size: File content size in bytes

    Returns:
        True if saved successfully, False otherwise.
    """
    if not file_path or mtime is None:
        return False

    # Don't cache small files — index build is < 1ms for < 100 lines
    if index.line_count < 100:
        return False

    key = _cache_key(file_path, mtime, size)
    path = _cache_path(key)

    try:
        # Serialize only the index data (not the full content — it's redundant)
        # Content can be re-read from the file on load if needed
        data = {
            "line_index": index.line_index,
            "block_indexes": index.block_indexes,
            "token_index": index.token_index,
            "line_starts": index._line_starts,
            "line_count": index.line_count,
            "bloom_items": list(index.bloom._set) if hasattr(index.bloom, '_set') else [],
            "file_path": os.path.abspath(file_path),
            "mtime": mtime,
            "size": size,
            "saved_at": time.time(),
        }

        with _CACHE_LOCK:
            with open(path, "wb") as f:
                pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)

        # LRU eviction — check cache size
        _maybe_evict()
        return True

    except Exception as e:
        logger.debug("Failed to save hashline index cache: %s", e)
        return False


def load_index(file_path: str, mtime: Optional[float], size: int):
    """Load a HashLineIndex from disk cache if valid.

    Args:
        file_path: Original file path
        mtime: Current file modification time
        size: Current file content size

    Returns:
        HashLineIndex instance if cache hit, None if miss.
    """
    if not file_path or mtime is None:
        return None

    key = _cache_key(file_path, mtime, size)
    path = _cache_path(key)

    if not path.exists():
        return None

    try:
        with _CACHE_LOCK:
            with open(path, "rb") as f:
                data = pickle.load(f)

        # Validate cache entry
        if data["mtime"] != mtime or data["size"] != size:
            return None  # stale

        # Reconstruct HashLineIndex without rebuilding from scratch
        from tools.hashline import HashLineIndex, BloomFilter, LineRef, BlockRef, TokenRef

        # Need to read the file content to reconstruct lines
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception:
            return None

        # Quick sanity check — size should match
        if len(content) != size:
            return None

        index = HashLineIndex.__new__(HashLineIndex)
        index.content = content
        index.lines = content.split("\n")
        index.line_count = data["line_count"]
        index.file_path = os.path.abspath(file_path)
        index.file_mtime = mtime
        index._line_starts = data["line_starts"]
        index.line_index = data["line_index"]
        index.block_indexes = data["block_indexes"]
        index.token_index = data["token_index"]

        # Reconstruct bloom filter
        index.bloom = BloomFilter(max(index.line_count * 2, 20000))
        if data.get("bloom_items"):
            try:
                index.bloom._set.update(data["bloom_items"])
            except Exception:
                pass

        logger.debug(
            "hashline cache HIT: %s (%d lines, %d tokens)",
            file_path, index.line_count, len(index.token_index),
        )
        return index

    except Exception as e:
        logger.debug("Failed to load hashline index cache: %s", e)
        # Corrupt cache file — remove it
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
        return None


def _maybe_evict():
    """Evict old cache entries if cache exceeds limits."""
    try:
        cache_dir = _get_cache_dir()
        entries = []
        total_size = 0

        for f in cache_dir.glob("*.pkl"):
            stat = f.stat()
            entries.append((f, stat.st_mtime, stat.st_size))
            total_size += stat.st_size

        # Check if we need to evict
        total_mb = total_size / (1024 * 1024)
        if len(entries) <= _MAX_ENTRIES and total_mb <= _MAX_CACHE_SIZE_MB:
            return

        # Sort by mtime (oldest first)
        entries.sort(key=lambda x: x[1])

        # Evict oldest until under limits
        for path, _, size in entries:
            if len(entries) <= _MAX_ENTRIES and total_mb <= _MAX_CACHE_SIZE_MB:
                break
            try:
                path.unlink()
                total_mb -= size / (1024 * 1024)
                entries.remove((path, _, size))
            except Exception:
                pass

    except Exception as e:
        logger.debug("hashline cache eviction failed: %s", e)


def clear_cache():
    """Clear all cached indexes."""
    try:
        cache_dir = _get_cache_dir()
        for f in cache_dir.glob("*.pkl"):
            f.unlink(missing_ok=True)
        logger.info("hashline cache cleared")
    except Exception as e:
        logger.debug("hashline cache clear failed: %s", e)


def cache_stats() -> Dict[str, any]:
    """Get cache statistics."""
    try:
        cache_dir = _get_cache_dir()
        entries = list(cache_dir.glob("*.pkl"))
        total_size = sum(f.stat().st_size for f in entries)
        return {
            "entries": len(entries),
            "total_mb": round(total_size / (1024 * 1024), 2),
            "cache_dir": str(cache_dir),
            "max_entries": _MAX_ENTRIES,
            "max_mb": _MAX_CACHE_SIZE_MB,
        }
    except Exception:
        return {"entries": 0, "total_mb": 0, "cache_dir": "unknown"}