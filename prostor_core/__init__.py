"""Shared core utilities for Prostor Agent.

Import-safe module with minimal dependencies — can be imported from
agent/, tools/, prostor_cli/, and gateway/ without circular import risk.
"""
from prostor_core.paths import get_prostor_home
from prostor_core.config import cfg_get, DEFAULT_CONFIG
from prostor_core.types import Platform

__all__ = [
    "get_prostor_home",
    "cfg_get",
    "DEFAULT_CONFIG",
    "Platform",
]
