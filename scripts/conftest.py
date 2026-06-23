"""Top-level conftest for scripts/ — adds scripts/sync_upstream to sys.path.

pytest's rootdir is the project root. When collecting tests under
scripts/sync_upstream/tests/, the import system needs to find the
`sync_upstream` package. Two options:
1. Make scripts/ a proper package (it now has __init__.py)
2. Add scripts/sync_upstream to sys.path

Option 1 alone is enough on POSIX but Windows/MSYS sometimes resolves
the underscored directory to its dashed alias, breaking imports.
Adding scripts/sync_upstream to sys.path explicitly fixes this on all
platforms.
"""
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SYNC_UPSTREAM = _HERE / "sync_upstream"

if _SYNC_UPSTREAM.exists() and str(_SYNC_UPSTREAM) not in sys.path:
    sys.path.insert(0, str(_SYNC_UPSTREAM))
