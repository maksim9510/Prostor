"""Path utilities — import-safe, no heavy deps."""
from __future__ import annotations

from pathlib import Path

# Re-export from prostor_constants for convenience
from prostor_constants import get_prostor_home

__all__ = ["get_prostor_home"]
