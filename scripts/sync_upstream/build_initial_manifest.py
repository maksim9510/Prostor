"""Build initial rebrand manifest by reverse-engineering from current main.

For each file in current main (which is post-rebrand, i.e. prostor-form), we
compute:
- post_hash = SHA-256(file content as-is, prostor-form)
- pre_hash = SHA-256(reverse_rebrand(file content), hermes-form)
- protected flag = whether the file is one of our 10 competitive-advantage files

Run once at plan adoption to bootstrap the manifest. Subsequent upstream syncs
use `sync_upstream.rebrand` to maintain it.

Usage:
    python scripts/sync_upstream/build_initial_manifest.py [REPO_ROOT]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Allow direct execution: python scripts/sync_upstream/build_initial_manifest.py
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from sync_upstream.rebrand import (  # noqa: E402
    Manifest,
    apply_rebrand,
    sha256,
)

# Reverse of rebrand rules — used to compute pre_hash from current post-form.
# Order matters: longest patterns first to avoid partial matches.
REVERSE_REBRAND_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bProstorAgent\b"), "HermesAgent"),
    (re.compile(r"\bprostor_agent\b"), "hermes_agent"),
    (re.compile(r"\bProstor(?![A-Za-z0-9_])"), "Hermes"),
    (re.compile(r"\bprostor(?![A-Za-z0-9_])"), "hermes"),
    (re.compile(r"\bPROSTOR(?![a-z])"), "HERMES"),
]


def reverse_rebrand(content: str) -> str:
    """Reverse the prostor→hermes rebrand to compute pre-form content."""
    for pattern, replacement in REVERSE_REBRAND_RULES:
        content = pattern.sub(replacement, content)
    return content


# 10 наших файлов + AGENTS.md (наш architectural bible, не upstream's)
PROTECTED = {
    "tools/hashline.py",
    "tools/hashline_persistent_cache.py",
    "tools/batch_patch_tool.py",
    "tools/batch_read_tool.py",
    "tools/result_compression.py",
    "tools/token_budget.py",
    "tools/context_optimizer.py",
    "tools/smart_read_cache.py",
    "tools/adaptive_router.py",
    "skills/devops/ssh-paramiko-connector/SKILL.md",
    "skills/devops/ssh-paramiko-connector/ssh_connector.py",
    "AGENTS.md",  # our architectural choices, not upstream's
}


def build_manifest(repo_root: Path, *, verbose: bool = True) -> Manifest:
    """Walk repo, build manifest. Skip protected files (their pre_hash is fake).

    Skip dirs that don't need rebrand: build artifacts, deps, venvs.
    Skip binary files (try UTF-8 read; fall back to skip).
    """
    m = Manifest(by_path={}, protected=PROTECTED)

    skip_dirs = {
        "node_modules", ".git", "dist", "release", "__pycache__",
        ".venv", "venv", "build", ".pytest_cache", ".mypy_cache",
        "node-pty", "winpty",  # vendored C extensions
    }

    skipped = 0
    errors: list[tuple[str, str]] = []

    for path in sorted(repo_root.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(repo_root)).replace("\\", "/")
        if any(f"/{d}/" in f"/{rel}" for d in skip_dirs):
            continue
        if rel in PROTECTED:
            continue
        # Skip obvious binaries by extension
        if path.suffix in {".png", ".jpg", ".ico", ".woff", ".woff2", ".ttf",
                            ".exe", ".msi", ".asar", ".pak", ".dll",
                            ".so", ".dylib", ".pyc", ".pyo", ".blockmap"}:
            continue

        # Try to read as UTF-8 text
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, IsADirectoryError, PermissionError) as e:
            skipped += 1
            if verbose and skipped <= 5:
                print(f"  SKIP binary/unreadable: {rel} ({e})")
            continue
        if content == "":
            continue  # empty file, nothing to rebrand

        post_hash = sha256(content)
        pre_content = reverse_rebrand(content)
        pre_hash = sha256(pre_content)

        # Sanity check: re-applying rebrand should yield same post_hash.
        # If it doesn't, the file is in an unusual state (mixed, partial rebrand,
        # or has Hermes identifiers that survive the rebrand pass — e.g. inside
        # a string that the rules don't match).
        verify_post = sha256(apply_rebrand(pre_content))
        if verify_post != post_hash:
            errors.append((rel, "non-monorebrandable"))
            if verbose and len(errors) <= 5:
                print(f"  WARN non-monorebrandable: {rel}")
            continue

        m.by_path[rel] = {"pre_hash": pre_hash, "post_hash": post_hash}

    if verbose:
        print(f"  Files registered: {len(m.by_path)}")
        print(f"  Protected:        {len(m.protected)}")
        print(f"  Skipped (binary): {skipped}")
        print(f"  Errors:           {len(errors)}")
        if errors:
            print(f"  Error files: {[e[0] for e in errors[:10]]}")

    return m


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Build initial rebrand manifest")
    parser.add_argument("root", nargs="?", default=".", help="Repo root")
    parser.add_argument("--out", default="scripts/sync_upstream/manifest.json",
                        help="Output manifest path (relative to root)")
    args = parser.parse_args()

    repo_root = Path(args.root).resolve()
    out_path = repo_root / args.out

    print(f"Building manifest from {repo_root}...")
    manifest = build_manifest(repo_root)

    manifest.save(out_path)
    size_kb = out_path.stat().st_size / 1024
    print(f"  Saved to {out_path} ({size_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
