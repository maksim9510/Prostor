"""Shared core utilities for Prostor Agent.

Import-safe module with minimal dependencies — can be imported from
agent/, tools/, prostor_cli/, and gateway/ without circular import risk.
"""
from prostor_core.paths import get_prostor_home, get_skills_dir, is_wsl
from prostor_core.config import cfg_get, DEFAULT_CONFIG
from prostor_core.types import Platform
from prostor_constants import secure_parent_dir

__all__ = [
    "get_prostor_home",
    "get_skills_dir",
    "is_wsl",
    "cfg_get",
    "DEFAULT_CONFIG",
    "Platform",
    "secure_parent_dir",
]
