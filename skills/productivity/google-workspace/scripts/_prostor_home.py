"""Resolve PROSTOR_HOME for standalone skill scripts.

Skill scripts may run outside the Prostor process (e.g. system Python,
nix env, CI) where ``prostor_constants`` is not importable.  This module
provides the same ``get_prostor_home()`` and ``display_prostor_home()``
contracts as ``prostor_constants`` without requiring it on ``sys.path``.

When ``prostor_constants`` IS available it is used directly so that any
future enhancements (profile resolution, Docker detection, etc.) are
picked up automatically.  The fallback path replicates the core logic
from ``prostor_constants.py`` using only the stdlib.

All scripts under ``google-workspace/scripts/`` should import from here
instead of duplicating the ``PROSTOR_HOME = Path(os.getenv(...))`` pattern.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from prostor_constants import display_prostor_home as display_prostor_home
    from prostor_constants import get_prostor_home as get_prostor_home
except (ModuleNotFoundError, ImportError):

    def get_prostor_home() -> Path:
        """Return the Prostor home directory (default: ~/.prostor).

        Mirrors ``prostor_constants.get_prostor_home()``."""
        val = os.environ.get("PROSTOR_HOME", "").strip()
        return Path(val) if val else Path.home() / ".prostor"

    def display_prostor_home() -> str:
        """Return a user-friendly ``~/``-shortened display string.

        Mirrors ``prostor_constants.display_prostor_home()``."""
        home = get_prostor_home()
        try:
            return "~/" + str(home.relative_to(Path.home()))
        except ValueError:
            return str(home)
