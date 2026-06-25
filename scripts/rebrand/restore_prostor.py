#!/usr/bin/env python3
"""
Restore Prostor rebrand after `prostor update`.

The official update mechanism downloads a ZIP from NousResearch/hermes-agent
which overwrites our rebrand. This script re-applies it.

Usage:
    python scripts/rebrand/restore_prostor.py
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INSTALL_DIR = Path.home() / "AppData/Local/prostor/prostor-agent"
REBRAND_APPLY = ROOT / "scripts/rebrand/apply_rebrand.py"


def copy_file(src, dst):
    """Copy a file, creating parent dirs if needed."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def main():
    if not INSTALL_DIR.exists():
        print(f"Install directory not found: {INSTALL_DIR}")
        return 1

    print(f"Restoring Prostor rebrand to: {INSTALL_DIR}")
    print()

    # 1. Restore PROTECTED files from dev repo
    protected = [
        "tools/hashline.py",
        "tools/batch_patch_tool.py",
        "tools/batch_read_tool.py",
        "tools/token_budget.py",
        "tools/context_optimizer.py",
        "tools/adaptive_router.py",
        "tools/result_compression.py",
        "toolsets.py",
        "prostor_constants.py",
        "hermes_cli/main.py",
        "prostor_cli/main.py",
    ]

    print("Step 1: Restoring protected files...")
    for f in protected:
        src = ROOT / f
        dst = INSTALL_DIR / f
        if src.exists():
            copy_file(src, dst)
            print(f"  ✅ {f}")
        else:
            print(f"  ⚠️  {f} not found in dev repo")

    # 2. Restore all mixins
    print("\nStep 2: Restoring mixins...")
    for pattern in ["prostor_cli/cli_*_mixin.py", "gateway/*_mixin.py"]:
        for src in ROOT.glob(pattern):
            dst = INSTALL_DIR / src.relative_to(ROOT)
            copy_file(src, dst)
            print(f"  ✅ {src.name}")

    # 3. Apply rebrand to installed copy
    print("\nStep 3: Applying rebrand to installed copy...")
    # prostor_cli imports
    for f in (INSTALL_DIR / "prostor_cli").rglob("*.py"):
        try:
            content = f.read_text(encoding="utf-8")
            new = content.replace("from hermes_cli.", "from prostor_cli.").replace("import hermes_cli.", "import prostor_cli.")
            if new != content:
                f.write_text(new, encoding="utf-8")
        except Exception:
            pass

    # Electron files
    preload = INSTALL_DIR / "apps/desktop/electron/preload.cjs"
    if preload.exists():
        content = preload.read_text(encoding="utf-8")
        content = content.replace("hermesDesktop", "prostorDesktop")
        preload.write_text(content, encoding="utf-8")
        print("  ✅ preload.cjs")

    main_cjs = INSTALL_DIR / "apps/desktop/electron/main.cjs"
    if main_cjs.exists():
        content = main_cjs.read_text(encoding="utf-8")
        content = content.replace("normalizeHermesHomeRoot", "normalizeProstorHomeRoot")
        content = content.replace("hermesDesktop", "prostorDesktop")
        main_cjs.write_text(content, encoding="utf-8")
        print("  ✅ main.cjs")

    print("\n✅ Done! Try: stor update  or  stor --version")
    return 0


if __name__ == "__main__":
    sys.exit(main())
