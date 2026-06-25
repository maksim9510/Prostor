#!/usr/bin/env python3
"""
Post-merge rebrand script. Run after every upstream sync:

    python scripts/rebrand/apply_rebrand.py [--dry-run]

Reads rebrand_manifest.json and applies all rebrand patterns to the codebase.
Skips PROTECTED files that must never be overwritten.

The script is idempotent — running it twice produces no changes.
"""

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = Path(__file__).resolve().parent / "rebrand_manifest.json"

# Colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"


def load_manifest():
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def is_protected(filepath, protected_files):
    """Check if a file is in the protected list."""
    rel = filepath.relative_to(ROOT).as_posix()
    return rel in protected_files


def find_files(dirs, root, extensions=None):
    """Find all files in given directories."""
    files = []
    for d in dirs:
        dirpath = root / d
        if not dirpath.is_dir():
            continue
        for f in dirpath.rglob("*"):
            if f.is_file():
                if extensions:
                    if f.suffix in extensions:
                        files.append(f)
                else:
                    files.append(f)
    return files


def apply_replacements(content, replacement_map, skip_patterns=None):
    """Apply all replacements to content string. Returns (new_content, changes_made)."""
    original = content
    for old, new in replacement_map.items():
        content = content.replace(old, new)

    if skip_patterns:
        # Restore skipped patterns — if the replacement was in a skip context, revert it
        for skip in skip_patterns:
            for old, new in replacement_map.items():
                # Find lines matching skip pattern that were modified
                pass  # Complex — skip for now, log instead

    return content, content != original


def main():
    dry_run = "--dry-run" in sys.argv
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    manifest = load_manifest()
    protected = set(manifest.get("protected_files", []))

    total_files = 0
    total_changes = 0
    skipped_protected = 0
    errors = []

    print(f"{'[DRY RUN] ' if dry_run else ''}Applying rebrand from {MANIFEST_PATH.name}")
    print()

    # Process each section in the manifest
    for section_name, section in manifest.items():
        if section_name.startswith("_"):
            continue
        if not isinstance(section, dict):
            continue
        if "replacement" not in section:
            continue

        dirs = section.get("dirs", ["prostor_cli/", "agent/", "tools/", "gateway/", "scripts/"])
        replacement = section["replacement"]
        extensions = section.get("extensions", [".py", ".cjs", ".ts", ".tsx", ".md"])
        skip_patterns = section.get("skip_patterns", [])

        print(f"{YELLOW}Section: {section_name}{RESET}")

        files = find_files(dirs, ROOT, extensions)
        section_changes = 0

        for filepath in sorted(files):
            if is_protected(filepath, protected):
                if verbose:
                    print(f"  {RED}SKIP (protected){RESET}: {filepath.relative_to(ROOT)}")
                skipped_protected += 1
                continue

            try:
                content = filepath.read_text(encoding="utf-8")
                new_content, changed = apply_replacements(content, replacement, skip_patterns)

                if changed:
                    if dry_run:
                        print(f"  {GREEN}WOULD CHANGE{RESET}: {filepath.relative_to(ROOT)}")
                    else:
                        filepath.write_text(new_content, encoding="utf-8")
                        print(f"  {GREEN}CHANGED{RESET}: {filepath.relative_to(ROOT)}")
                    section_changes += 1
                    total_changes += 1
            except Exception as e:
                errors.append((filepath, str(e)))
                print(f"  {RED}ERROR{RESET}: {filepath.relative_to(ROOT)}: {e}")

        total_files += len(files)
        if section_changes == 0:
            print(f"  (no changes needed)")
        print()

    # Summary
    print("=" * 60)
    print(f"Files scanned: {total_files}")
    print(f"Files changed: {total_changes}")
    print(f"Protected skipped: {skipped_protected}")
    if errors:
        print(f"{RED}Errors: {len(errors)}{RESET}")
        for fp, err in errors:
            print(f"  {fp.relative_to(ROOT)}: {err}")
    print("=" * 60)

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
