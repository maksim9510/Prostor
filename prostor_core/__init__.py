"""Shared core utilities for Prostor Agent.

Import-safe module with minimal dependencies — can be imported from
agent/, tools/, prostor_cli/, and gateway/ without circular import risk.

Issue #25: progressively extracting leaf utilities from prostor_cli/ into
prostor_core/ to break the 4 cyclic dependency pairs.
"""
from prostor_constants import secure_parent_dir
from prostor_core.config import cfg_get
from prostor_core.paths import get_prostor_home, get_skills_dir, is_wsl
from prostor_core.types import Platform

__all__ = [
    "get_prostor_home",
    "get_skills_dir",
    "is_wsl",
    "cfg_get",
    "Platform",
    "secure_parent_dir",
]