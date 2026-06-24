"""Path utilities — import-safe, no heavy deps."""
from __future__ import annotations

# Re-export from prostor_constants for convenience
from prostor_constants import get_prostor_home, get_skills_dir, is_wsl

__all__ = ["get_prostor_home", "get_skills_dir", "is_wsl"]
