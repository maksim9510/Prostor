"""Rebrand upstream with smart exclusions.

Strategy: do NOT touch README, CHANGELOG, docs, website, or anything
that mentions a URL pointing to the upstream repo. Those files
preserve the upstream project identity and should be reviewed by
humans before any changes.

Everything else gets the regex rebrand (Hermes → Prostor,
hermes-agent → prostor-agent, etc.).
"""
# Allow direct execution
import re
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from scripts.sync_upstream.rebrand import (  # type: ignore
    apply_rebrand,
    safe_rglob,
)

# Patterns that identify "leave alone" files. These contain upstream's
# marketing/identity and should be reviewed by humans before any change.
SKIP_PATTERNS = [
    "README*",
    "CHANGELOG*",
    "RELEASE*",
    "RELEASE_NOTES*",
    "AUTHORS",
    "CONTRIBUTING*",
    "CODE_OF_CONDUCT*",
    "SECURITY*",
    "LICENSE*",
    "NOTICE*",
    "INSTALL*",
    "docs/**",
    "website/**",
    ".github/ISSUE_TEMPLATE/**",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/dependabot.yml",
    ".github/CODEOWNERS",
    ".github/SECURITY.md",
    "*.md",  # all markdown — too risky, always review manually
]

# Extensions that are pure binary or data, skip
SKIP_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
    ".woff", ".woff2", ".ttf", ".eot",
    ".exe", ".msi", ".asar", ".pak", ".dll",
    ".so", ".dylib", ".pyc", ".pyo", ".blockmap",
    ".icns", ".pdf", ".zip", ".tar", ".gz",
    ".lock",
    ".mp4", ".mov", ".webm", ".mp3", ".wav",
}

# Dirs to skip entirely
SKIP_DIRS = {
    "node_modules", ".git", "dist", "release", "__pycache__",
    ".venv", "venv", "build", ".pytest_cache", ".mypy_cache",
    "node-pty", "winpty",  # vendored native bindings
    ".plans",  # dev-only planning notes
    "build_venv",
}


def should_skip(rel: str) -> bool:
    """Return True if the file matches any SKIP_PATTERN."""
    from fnmatch import fnmatch
    for pat in SKIP_PATTERNS:
        if fnmatch(rel, pat):
            return True
    return False


def main(root: Path) -> int:
    """Walk root and rebrand all non-skipped text files.

    Returns count of rebranded files.
    """
    reb_count = 0
    skipped_count = 0
    error_count = 0
    errors: list[str] = []

    for path in safe_rglob(root):
        if not path.is_file():
            continue
        try:
            rel = str(path.relative_to(root)).replace("\\", "/")
        except ValueError:
            continue

        # Check directory skip
        if any(f"/{d}/" in f"/{rel}" for d in SKIP_DIRS):
            continue
        # Check pattern skip
        if should_skip(rel):
            skipped_count += 1
            continue
        # Check extension skip
        if path.suffix in SKIP_EXTS:
            skipped_count += 1
            continue

        # Try to read as UTF-8
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, IsADirectoryError, PermissionError, OSError):
            skipped_count += 1
            continue
        if not content:
            continue

        # Check if file even has Hermes tokens
        if not re.search(r"hermes|Hermes|HERMES", content):
            skipped_count += 1
            continue

        # Apply rebrand
        new_content = apply_rebrand(content)
        if new_content == content:
            skipped_count += 1
            continue

        try:
            path.write_text(new_content, encoding="utf-8")
            reb_count += 1
        except (PermissionError, OSError) as e:
            error_count += 1
            errors.append(f"{rel}: {e}")

    print("Smart rebrand complete:")
    print(f"  Rebranded: {reb_count}")
    print(f"  Skipped:   {skipped_count}")
    print(f"  Errors:    {error_count}")
    if errors:
        for e in errors[:20]:
            print(f"    {e}")
    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    sys.exit(main(target))
