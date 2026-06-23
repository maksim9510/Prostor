"""Conftest for sync-upstream tests — adds scripts/sync-upstream to sys.path
so tests can `from sync_upstream.rebrand import ...` directly.

Also reused by build_initial_manifest.py when run as `python -m` from repo root
via the same package-style import path.
"""
import sys
from pathlib import Path

# scripts/sync-upstream/tests/conftest.py
# → tests_dir = .../scripts/sync-upstream/tests
# → package_dir = .../scripts/sync-upstream
_tests_dir = Path(__file__).resolve().parent
_package_dir = _tests_dir.parent
print(f"[conftest] tests_dir={_tests_dir} package_dir={_package_dir} exists={_package_dir.exists()}", file=sys.stderr)
if str(_package_dir) not in sys.path:
    sys.path.insert(0, str(_package_dir))
    print(f"[conftest] added {str(_package_dir)} to sys.path", file=sys.stderr)
