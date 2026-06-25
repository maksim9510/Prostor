#!/usr/bin/env python3
"""
Post-upstream-merge script. Replaces manual rebrand work.

Usage:
    python scripts/rebrand/post_merge.py              # merge + rebrand
    python scripts/rebrand/post_merge.py --dry-run     # preview only
    python scripts/rebrand/post_merge.py --rebrand-only # rebrand only (skip merge)

Steps:
    1. git merge upstream/main (abort if conflicts)
    2. Apply rebrand patterns from rebrand_manifest.json
    3. Syntax-check all modified Python files
    4. Report results
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REBRAND_SCRIPT = Path(__file__).resolve().parent / "apply_rebrand.py"


def run(cmd, **kwargs):
    """Run a shell command and return (exit_code, stdout)."""
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        cwd=str(ROOT), **kwargs
    )
    return result.returncode, result.stdout.strip()


def main():
    dry_run = "--dry-run" in sys.argv
    rebrand_only = "--rebrand-only" in sys.argv

    print("=" * 60)
    print("Post-merge: upstream sync + rebrand")
    print("=" * 60)
    print()

    # Step 1: Merge (unless rebrand-only)
    if not rebrand_only:
        print("Step 1: Fetching upstream...")
        rc, out = run("git fetch upstream main")
        print(f"  fetch: {'OK' if rc == 0 else 'FAILED'}")
        if rc != 0:
            print(out)
            return 1

        print("Step 2: Merging upstream/main...")
        rc, out = run("git merge upstream/main --no-edit")
        if rc != 0:
            print(f"  {RED}Merge conflicts detected!{RESET}")
            print("  Resolve conflicts manually, then run:")
            print(f"    python scripts/rebrand/post_merge.py --rebrand-only")
            run("git merge --abort")
            return 1
        print("  merge: OK")

    # Step 3: Apply rebrand
    print()
    print(f"Step {'2' if rebrand_only else '3'}: Applying rebrand...")
    rc = run(f"{sys.executable} {REBRAND_SCRIPT} {'--dry-run' if dry_run else ''}")[0]
    if rc != 0:
        print(f"  Rebrand had errors — check output above")
        return 1

    # Step 4: Syntax check
    if not dry_run:
        print()
        print("Step 4: Syntax checking modified files...")
        rc, out = run("git diff --name-only --diff-filter=M | grep '\\.py$' | xargs -r python -m py_compile")
        if rc == 0:
            print("  All Python files pass syntax check")
        else:
            print(f"  {YELLOW}Some files have syntax errors:{RESET}")
            print(out[:500])

    print()
    print("=" * 60)
    print(f"{'[DRY RUN] ' if dry_run else ''}Done! Review changes with: git diff")
    print("=" * 60)
    return 0


RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


if __name__ == "__main__":
    sys.exit(main())
