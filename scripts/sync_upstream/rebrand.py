"""Idempotent Hermes→Prostor rebrander.

Rewrites identifiers in any file state (hermes-form, prostor-form, or mixed)
deterministically. Uses SHA-256 manifest for skip-detection — safe to run
repeatedly on the same tree.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Allow running this script directly via `python scripts/sync_upstream/rebrand.py`
# without requiring `pip install -e .` — adds the scripts/ dir to sys.path so
# `from sync_upstream.X import Y` resolves.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# Rebrand rules — case-sensitive, longest match first. Python's `\b` treats
# `_` as a word char, so for UPPER_SNAKE_CASE identifiers (HERMES_HOME) we use
# `(?![a-z])` instead of `\b` to match HERMES when followed by `_` or end-of-token.
REBRAND_RULES: list[tuple[re.Pattern[str], str]] = [
    # Compound CamelCase / snake_case forms first (longest match wins)
    (re.compile(r"\bHermesAgent\b"), "ProstorAgent"),
    (re.compile(r"\bhermes_agent\b"), "prostor_agent"),
    # PascalCase: `Hermes` not followed by identifier char (so HermesAgent
    # is consumed by the rule above; bare `Hermes` falls through here)
    (re.compile(r"\bHermes(?![A-Za-z0-9_])"), "Prostor"),
    # snake_case: same boundary handling
    (re.compile(r"\bhermes(?![A-Za-z0-9_])"), "prostor"),
    # UPPER_SNAKE: HERMES_HOME, HERMES_AGENT. `(?![a-z])` means HERMES not
    # followed by lowercase (which would be part of a longer identifier).
    # Followed by `_` is fine and falls through to plain `HERMES\b`.
    (re.compile(r"\bHERMES(?![a-z])"), "PROSTOR"),
]


def _strip_marker(content: str) -> str:
    """No-op placeholder kept for backward-compat in case external callers
    depended on the symbol. Currently unused."""
    return content


@dataclass(frozen=True)
class FileState:
    """Result of rebranding one file."""
    path: Path
    action: str  # "skipped_post" | "skipped_protected" | "reb" | "added_to_manifest" | "error"
    old_hash: str | None
    new_hash: str | None
    error: str | None = None


def sha256(content: str | bytes) -> str:
    """SHA-256 hex digest of string or bytes."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def apply_rebrand(content: str) -> str:
    """Apply all rebrand rules in order. Idempotent: prostor-form is unchanged."""
    for pattern, replacement in REBRAND_RULES:
        content = pattern.sub(replacement, content)
    return content


@dataclass
class Manifest:
    """Per-file rebrand manifest: maps path → {pre_hash, post_hash}.

    pre_hash = SHA-256 of upstream (hermes-form) file content.
    post_hash = SHA-256 of rebranded (prostor-form) file content.
    If current file hash == post_hash, file is already rebranded → skip.
    If current file hash == pre_hash, file is fresh from upstream → apply rebrand.
    """
    by_path: dict[str, dict[str, str]]
    protected: set[str]

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        if not path.exists():
            return cls(by_path={}, protected=set())
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            by_path=data.get("files", {}),
            protected=set(data.get("protected_files", [])),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "files": self.by_path,
            "protected_files": sorted(self.protected),
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def is_protected(self, file_path: Path) -> bool:
        """Check whether a file is protected from rebrand.

        Matches against both the full relative path (`tools/hashline.py`)
        and the basename (`hashline.py`) so callers can use either form
        in their protected set — convenient for tests that pass tmp_paths.
        """
        rel = str(file_path).replace("\\", "/")
        return rel in self.protected or file_path.name in self.protected

    def lookup_pre_hash(self, file_path: Path) -> str | None:
        """Look up pre_hash by file path. Tries full path, then basename.

        Full path uses forward slashes (Windows path normalization).
        Basename match is the fallback for callers that pass tmp_paths or
        absolute paths where the manifest key is the repo-relative path.
        """
        rel = str(file_path).replace("\\", "/")
        entry = self.by_path.get(rel)
        if entry is None and file_path.name in self.by_path:
            entry = self.by_path[file_path.name]
        return entry.get("pre_hash") if entry else None

    def lookup_post_hash(self, file_path: Path) -> str | None:
        rel = str(file_path).replace("\\", "/")
        entry = self.by_path.get(rel)
        if entry is None and file_path.name in self.by_path:
            entry = self.by_path[file_path.name]
        return entry.get("post_hash") if entry else None

    def update(self, file_path: Path, pre_hash: str, post_hash: str) -> None:
        rel = str(file_path).replace("\\", "/")
        self.by_path[rel] = {"pre_hash": pre_hash, "post_hash": post_hash}


def rebrand_file(
    file_path: Path,
    manifest: Manifest,
    *,
    add_if_missing: bool = False,
    lookup_key: Path | None = None,
) -> FileState:
    """Rebrand a single file using manifest for idempotency.

    Args:
        file_path: Path to file (relative to repo root or absolute).
        manifest: Manifest instance for skip/protected checks.
        add_if_missing: If True, auto-register the file in the manifest when
            it has no entry yet. Use this for new upstream files. Default False
            (require explicit pre-registration for safety).
        lookup_key: Optional Path used as the manifest lookup key. Defaults to
            file_path. Use this when file_path is absolute but the manifest
            key is repo-relative — pass the relative path explicitly so
            is_protected/lookup_* resolve correctly.
    """
    # Resolve lookup key once. Defaults to file_path.
    lookup = lookup_key if lookup_key is not None else file_path
    if manifest.is_protected(lookup):
        current_hash = sha256(file_path.read_bytes()) if file_path.exists() else None
        return FileState(
            path=file_path,
            action="skipped_protected",
            old_hash=current_hash,
            new_hash=current_hash,
        )

    if not file_path.exists():
        return FileState(
            path=file_path,
            action="error",
            old_hash=None,
            new_hash=None,
            error="file does not exist",
        )

    content = file_path.read_text(encoding="utf-8")
    current_hash = sha256(content)

    post_hash = manifest.lookup_post_hash(lookup)
    if current_hash == post_hash:
        return FileState(
            path=file_path,
            action="skipped_post",
            old_hash=current_hash,
            new_hash=current_hash,
        )

    pre_hash = manifest.lookup_pre_hash(lookup)
    if pre_hash is None:
        if not add_if_missing:
            return FileState(
                path=file_path,
                action="error",
                old_hash=current_hash,
                new_hash=None,
                error="not in manifest (pass add_if_missing=True for new files)",
            )
        # New file: reverse-engineer pre_hash by applying rebrand and
        # computing post_hash. pre_hash becomes current_hash (the upstream
        # content is what we just downloaded).
        new_content = apply_rebrand(content)
        new_hash = sha256(new_content)
        # Update using the manifest key (rel path) so future lookups match.
        manifest.update(lookup, pre_hash=current_hash, post_hash=new_hash)
        file_path.write_text(new_content, encoding="utf-8")
        return FileState(
            path=file_path,
            action="added_to_manifest",
            old_hash=current_hash,
            new_hash=new_hash,
        )

    # File in pre-state: apply rebrand
    new_content = apply_rebrand(content)
    new_hash = sha256(new_content)
    file_path.write_text(new_content, encoding="utf-8")
    # Verify post_hash matches manifest (sanity)
    expected_post = manifest.lookup_post_hash(lookup)
    if expected_post and expected_post != new_hash:
        return FileState(
            path=file_path,
            action="error",
            old_hash=current_hash,
            new_hash=new_hash,
            error=f"post_hash mismatch: expected {expected_post[:8]}, got {new_hash[:8]}",
        )
    return FileState(
        path=file_path,
        action="reb",
        old_hash=current_hash,
        new_hash=new_hash,
    )


def main() -> int:
    """CLI: rebrand entire repo using manifest.

    Usage:
        python -m sync_upstream.rebrand [ROOT] [--add-missing]

    Idempotent: running on already-rebranded repo is a no-op (all files
    skipped as post-state). Exit 0 if no errors, 1 otherwise.
    """
    import argparse
    parser = argparse.ArgumentParser(description="Idempotent Hermes→Prostor rebrander")
    parser.add_argument("root", nargs="?", default=".", help="Repo root")
    parser.add_argument("--add-missing", action="store_true",
                        help="Auto-register new files in manifest")
    parser.add_argument("--manifest", default="scripts/sync_upstream/manifest.json",
                        help="Path to manifest JSON (relative to root)")
    parser.add_argument("--skip-glob", action="append", default=None,
                        help="Glob to skip (can be passed multiple times)")
    parser.add_argument("--auto-skip-manifest", action="store_true", default=True,
                        help="Skip the manifest JSON file itself (default: True)")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    manifest_path = root / args.manifest
    manifest = Manifest.load(manifest_path)

    skip_globs = list(args.skip_glob or [])
    if args.auto_skip_manifest:
        # The manifest.json file itself is auto-generated and its contents
        # shift whenever we rebrand other files. Skip it by default.
        skip_globs.append(args.manifest)

    def should_skip(rel: str) -> bool:
        from fnmatch import fnmatch
        return any(fnmatch(rel, g) for g in skip_globs)

    reb_count = skipped_count = protected_count = added_count = error_count = 0
    errors: list[FileState] = []

    # Walk manifest keys (relative paths), resolving to absolute for IO.
    # Pass the relative path as lookup_key so Manifest.is_protected/lookup_*
    # resolve against the manifest's relative path keys.
    #
    # With --add-missing, ALSO walk the filesystem to discover new files
    # that aren't in the manifest yet (added by upstream sync).
    processed: set[str] = set()

    for rel in list(manifest.by_path.keys()):
        if should_skip(rel):
            continue
        p = root / rel
        if not p.exists():
            continue
        state = rebrand_file(p, manifest, add_if_missing=args.add_missing, lookup_key=Path(rel))
        processed.add(rel)
        if state.action == "reb":
            reb_count += 1
        elif state.action == "skipped_post":
            skipped_count += 1
        elif state.action == "skipped_protected":
            protected_count += 1
        elif state.action == "added_to_manifest":
            added_count += 1
        else:
            error_count += 1
            errors.append(state)

    if args.add_missing:
        # Walk filesystem for files NOT in manifest. These are new files
        # from upstream that we haven't seen before. Skip dirs and
        # binary extensions same way build_initial_manifest does.
        skip_dirs = {"node_modules", ".git", "dist", "release", "__pycache__",
                     ".venv", "venv", "build", ".pytest_cache", ".mypy_cache"}
        skip_exts = {".png", ".jpg", ".ico", ".woff", ".woff2", ".ttf",
                     ".exe", ".msi", ".asar", ".pak", ".dll",
                     ".so", ".dylib", ".pyc", ".pyo", ".blockmap",
                     ".icns", ".pdf"}
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            try:
                rel = str(path.relative_to(root)).replace("\\", "/")
            except ValueError:
                continue
            if rel in processed:
                continue
            if should_skip(rel):
                continue
            if any(f"/{d}/" in f"/{rel}" for d in skip_dirs):
                continue
            if path.suffix in skip_exts:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, IsADirectoryError, PermissionError):
                continue
            if not content:
                continue
            state = rebrand_file(path, manifest, add_if_missing=True, lookup_key=Path(rel))
            processed.add(rel)
            if state.action == "reb":
                reb_count += 1
            elif state.action == "skipped_post":
                skipped_count += 1
            elif state.action == "skipped_protected":
                protected_count += 1
            elif state.action == "added_to_manifest":
                added_count += 1
            else:
                error_count += 1
                errors.append(state)

    manifest.save(manifest_path)

    print(f"Rebrand complete:")
    print(f"  Rebranded:       {reb_count}")
    print(f"  Skipped (post):  {skipped_count}")
    print(f"  Skipped (protected): {protected_count}")
    print(f"  Added to manifest:   {added_count}")
    print(f"  Errors:          {error_count}")
    for e in errors[:20]:
        print(f"    {e.path}: {e.error}")

    return 1 if error_count > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
