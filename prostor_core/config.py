"""Lightweight config utilities — import-safe.

This module is importable from agent/, tools/, gateway/, and prostor_cli/
without circular dependency risk. It contains only the leaf-level helpers
that the narrow-waist core needs.

``cfg_get`` was extracted from prostor_cli/config.py (Issue #25) so that
agent/ and tools/ can use it without pulling in the full 7000-LOC config
module (which imports yaml, ruamel, pathlib, and dozens of CLI-specific
helpers). The prostor_cli.config module re-exports this for back-compat.
"""
from __future__ import annotations

from typing import Any

__all__ = ["cfg_get"]


def cfg_get(cfg: dict[str, Any] | None, *keys: str, default: Any = None) -> Any:
    """Traverse nested dict keys safely, returning ``default`` on any miss.

    Canonical helper for the ``cfg.get("X", {}).get("Y", default)`` pattern
    that appears 50+ times across the codebase. Handles three common gotchas
    in one place:

      1. Missing intermediate keys (returns ``default``, no KeyError).
      2. An intermediate value that's not a dict (e.g. a user wrote a string
         where a section was expected). Returns ``default`` instead of
         AttributeError on ``.get()``.
      3. ``cfg is None`` (callers sometimes pass ``load_config() or None``).

    Named ``cfg_get`` rather than ``cfg_path`` to avoid shadowing the
    ubiquitous ``cfg_path = _prostor_home / "config.yaml"`` local variable
    that appears in gateway/run.py, cron/scheduler.py, main.py, etc.

    Explicit ``None`` values are returned as-is (matches ``dict.get(key,
    default)`` semantics — ``default`` is only returned when the key is
    *absent*, not when it's present but set to ``None``).

    Examples:
        >>> cfg_get({"agent": {"reasoning_effort": "high"}}, "agent", "reasoning_effort")
        'high'
        >>> cfg_get({}, "agent", "reasoning_effort", default="medium")
        'medium'
        >>> cfg_get({"agent": "oops_a_string"}, "agent", "reasoning_effort", default="low")
        'low'
        >>> cfg_get(None, "anything", default=42)
        42
        >>> cfg_get({"a": {"b": None}}, "a", "b", default="def")  # explicit None preserved
        >>> cfg_get({"a": {"b": False}}, "a", "b", default=True)  # falsy values preserved
        False
    """
    if not isinstance(cfg, dict):
        return default
    node: Any = cfg
    for key in keys:
        if not isinstance(node, dict):
            return default
        if key not in node:
            return default
        node = node[key]
    return node