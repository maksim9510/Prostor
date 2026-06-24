#!/usr/bin/env python3
"""Compatibility shim: hermes_cli.main → prostor_cli.main

The Electron desktop app still references ``hermes_cli.main`` for
``python -m hermes_cli.main`` spawning.  This thin re-export lets
that work while the real code lives in ``prostor_cli``.
"""

from prostor_cli.main import *  # noqa: F401,F403
from prostor_cli.main import main as __main__  # noqa: F401

if __name__ == "__main__":
    __main__()
