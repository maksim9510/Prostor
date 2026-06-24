"""Lightweight config utilities — import-safe."""
from __future__ import annotations

from typing import Any

# Minimal DEFAULT_CONFIG for shared use
DEFAULT_CONFIG: dict[str, Any] = {}


def cfg_get(cfg: dict[str, Any] | None, *keys: str, default: Any = None) -> Any:
    """Nested dict getter — safe for missing keys."""
    if cfg is None:
        return default
    current = cfg
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return default
    return current if current is not None else default


__all__ = ["cfg_get", "DEFAULT_CONFIG"]
