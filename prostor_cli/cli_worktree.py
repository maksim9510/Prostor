"""Git worktree management for the ``-w`` / ``--worktree`` CLI flag.

Extracted from cli.py (#29 Phase 3). Pure functions plus a single
module-level dict (``active_worktree``) that the ProstorCLI class
references via the ``_active_worktree`` alias re-exported from cli.py.

Why a module-level dict instead of a class:
  - The original code uses ``global _active_worktree`` to pass the
    worktree info between setup and cleanup. Preserving that shape keeps
    the refactor mechanical and zero-risk for callers.
  - Migration to a class would be a separate refactor (Phase 4 of #29).

Side effects (preserved as-is):
  - Prints to stdout (creation success, cleanup warnings)
  - Mutates ``active_worktree`` module global
  - Runs ``git worktree add/lock/unlock/remove`` and ``git branch -D``
  - Touches ``.gitignore`` to add ``.worktrees/``
  - Creates symlinks or recursive copies of ``.worktreeinclude`` entries
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Module-level singleton tracking the active worktree (set by
# setup_worktree, read+cleared by cleanup_worktree). Same shape as
# cli.py's original ``_active_worktree`` global — the cli.py re-export
# below keeps callers in cli.py reading this dict unchanged.
active_worktree: Optional[dict] = None


# ---------------------------------------------------------------------------
# Path normalization (Windows MSYS / Git Bash → native Windows path)
# ---------------------------------------------------------------------------

def normalize_git_bash_path(p: str) -> str:
    """Translate ``/c/Users/...`` (git-bash) or ``/mnt/c/...`` to ``C:\\…``.

    No-op on non-Windows or on paths that aren't in the recognized shapes.
    """
    if not p:
        return p
    if sys.platform != "win32":
        return p
    import re as _re
    # /c/Users/... or /C/Users/...
    m = _re.match(r"^/([a-zA-Z])/(.*)$", p)
    if m:
        drive, rest = m.group(1), m.group(2)
        return f"{drive.upper()}:\\{rest.replace('/', chr(92))}"
    # /cygdrive/c/... or /mnt/c/...
    m = _re.match(r"^/(?:cygdrive|mnt)/([a-zA-Z])/(.*)$", p)
    if m:
        drive, rest = m.group(1), m.group(2)
        return f"{drive.upper()}:\\{rest.replace('/', chr(92))}"
    return p


def git_repo_root() -> Optional[str]:
    """Return the git repo root for CWD, or None if not in a repo.

    Runs through :func:`normalize_git_bash_path` so callers can pass
    the result directly to ``Path``/``subprocess.Popen(cwd=...)`` on
    Windows without hitting ``C:\\c\\Users\\...`` style resolution
    mistakes.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return normalize_git_bash_path(result.stdout.strip())
    except Exception:
        pass
    return None


def path_is_within_root(path: Path, root: Path) -> bool:
    """Return True when a resolved path stays within the expected root."""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Worktree lifecycle
# ---------------------------------------------------------------------------

def setup_worktree(repo_root: str = None) -> Optional[dict]:
    """Create an isolated git worktree for this CLI session.

    Returns a dict with worktree metadata on success, None on failure.
    The dict contains: path, branch, repo_root.
    """
    repo_root = repo_root or git_repo_root()
    if not repo_root:
        print("\033[31m✗ --worktree requires being inside a git repository.\033[0m")
        print("  cd into your project repo first, then run prostor -w")
        return None

    short_id = uuid.uuid4().hex[:8]
    wt_name = f"prostor-{short_id}"
    branch_name = f"prostor/{wt_name}"

    worktrees_dir = Path(repo_root) / ".worktrees"
    worktrees_dir.mkdir(parents=True, exist_ok=True)

    wt_path = worktrees_dir / wt_name

    # Ensure .worktrees/ is in .gitignore
    gitignore = Path(repo_root) / ".gitignore"
    _ignore_entry = ".worktrees/"
    try:
        existing = gitignore.read_text() if gitignore.exists() else ""
        if _ignore_entry not in existing.splitlines():
            with open(gitignore, "a", encoding="utf-8") as f:
                if existing and not existing.endswith("\n"):
                    f.write("\n")
                f.write(f"{_ignore_entry}\n")
    except Exception as e:
        logger.debug("Could not update .gitignore: %s", e)

    # Create the worktree
    try:
        result = subprocess.run(
            ["git", "worktree", "add", str(wt_path), "-b", branch_name, "HEAD"],
            capture_output=True, text=True, timeout=30, cwd=repo_root,
        )
        if result.returncode != 0:
            print(f"\033[31m✗ Failed to create worktree: {result.stderr.strip()}\033[0m")
            return None
    except Exception as e:
        print(f"\033[31m✗ Failed to create worktree: {e}\033[0m")
        return None

    # Copy files listed in .worktreeinclude (gitignored files the agent needs)
    include_file = Path(repo_root) / ".worktreeinclude"
    if include_file.exists():
        try:
            repo_root_resolved = Path(repo_root).resolve()
            wt_path_resolved = wt_path.resolve()
            for line in include_file.read_text().splitlines():
                entry = line.strip()
                if not entry or entry.startswith("#"):
                    continue
                src = Path(repo_root) / entry
                dst = wt_path / entry
                # Prevent path traversal and symlink escapes: both the resolved
                # source and the resolved destination must stay inside their
                # expected roots before any file or symlink operation happens.
                try:
                    src_resolved = src.resolve(strict=False)
                    dst_resolved = dst.resolve(strict=False)
                except (OSError, ValueError):
                    logger.debug("Skipping invalid .worktreeinclude entry: %s", entry)
                    continue
                if not path_is_within_root(src_resolved, repo_root_resolved):
                    logger.warning("Skipping .worktreeinclude entry outside repo root: %s", entry)
                    continue
                if not path_is_within_root(dst_resolved, wt_path_resolved):
                    logger.warning("Skipping .worktreeinclude entry that escapes worktree: %s", entry)
                    continue
                if src.is_file():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src), str(dst))
                elif src.is_dir():
                    # Symlink directories (faster, saves disk).  On Windows,
                    # symlink creation requires Developer Mode or elevation,
                    # and fails with OSError otherwise — fall back to a
                    # recursive copy so the worktree is still usable.  The
                    # copy is slower and uses disk, but it doesn't require
                    # admin and matches the Linux/macOS symlink outcome
                    # functionally.
                    if not dst.exists():
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        try:
                            os.symlink(str(src_resolved), str(dst))
                        except (OSError, NotImplementedError) as _sym_err:
                            if sys.platform == "win32":
                                logger.info(
                                    ".worktreeinclude: symlink failed (%s) — "
                                    "falling back to copytree on Windows.",
                                    _sym_err,
                                )
                                try:
                                    shutil.copytree(
                                        str(src_resolved),
                                        str(dst),
                                        symlinks=True,
                                        dirs_exist_ok=False,
                                    )
                                except Exception as _copy_err:
                                    logger.warning(
                                        ".worktreeinclude: copy fallback "
                                        "also failed for %s -> %s: %s",
                                        src, dst, _copy_err,
                                    )
                            else:
                                raise
        except Exception as e:
            logger.debug("Error copying .worktreeinclude entries: %s", e)

    # Lock the worktree so other processes (and `git worktree remove`) can see
    # it is actively in use.  Fail-soft: a lock failure never blocks the session.
    try:
        subprocess.run(
            ["git", "worktree", "lock", "--reason", f"prostor pid={os.getpid()}", str(wt_path)],
            capture_output=True, text=True, timeout=10, cwd=repo_root,
        )
        logger.debug("Worktree locked: %s (pid=%s)", wt_path, os.getpid())
    except Exception as e:
        logger.debug("git worktree lock failed (non-fatal): %s", e)

    info = {
        "path": str(wt_path),
        "branch": branch_name,
        "repo_root": repo_root,
    }

    print(f"\033[32m✓ Worktree created:\033[0m {wt_path}")
    print(f"  Branch: {branch_name}")

    return info


def worktree_has_unpushed_commits(worktree_path: str, timeout: int = 10) -> bool:
    """Return whether a worktree has commits not reachable from any remote branch.

    ``git log HEAD --not --remotes`` compares against remote-tracking refs under
    ``refs/remotes/*``. If a repo has no remote-tracking refs yet, there is no
    usable remote baseline to compare against, so treat it as having no
    "unpushed" commits.
    """
    try:
        remote_refs = subprocess.run(
            ["git", "for-each-ref", "--format=%(refname)", "refs/remotes"],
            capture_output=True, text=True, timeout=timeout, cwd=worktree_path,
        )
        if remote_refs.returncode != 0:
            return True
        if not remote_refs.stdout.strip():
            return False

        result = subprocess.run(
            ["git", "log", "--oneline", "HEAD", "--not", "--remotes"],
            capture_output=True, text=True, timeout=timeout, cwd=worktree_path,
        )
        if result.returncode != 0:
            return True
        return bool(result.stdout.strip())
    except Exception:
        return True


def cleanup_worktree(info: dict = None) -> None:
    """Remove a worktree and its branch on exit.

    Preserves the worktree only if it has unpushed commits (real work
    that hasn't been pushed to any remote).  Uncommitted changes alone
    (untracked files, test artifacts) are not enough to keep it — agent
    work lives in commits/PRs, not the working tree.
    """
    global active_worktree
    info = info or active_worktree
    if not info:
        return

    wt_path = info["path"]
    branch = info["branch"]
    repo_root = info["repo_root"]

    if not Path(wt_path).exists():
        return

    has_unpushed = worktree_has_unpushed_commits(wt_path, timeout=10)

    if has_unpushed:
        print(f"\n\033[33m⚠ Worktree has unpushed commits, keeping: {wt_path}\033[0m")
        print(f"  To clean up manually: git worktree remove --force {wt_path}")
        active_worktree = None
        return

    # Remove worktree (even if working tree is dirty — uncommitted
    # changes without unpushed commits are just artifacts)
    # Unlock first so `git worktree remove` isn't blocked by the lock we
    # placed at creation time.  Fail-soft — never block cleanup.
    try:
        subprocess.run(
            ["git", "worktree", "unlock", wt_path],
            capture_output=True, text=True, timeout=10, cwd=repo_root,
        )
    except Exception as e:
        logger.debug("git worktree unlock failed (non-fatal): %s", e)

    try:
        subprocess.run(
            ["git", "worktree", "remove", wt_path, "--force"],
            capture_output=True, text=True, timeout=15, cwd=repo_root,
        )
    except Exception as e:
        logger.debug("Failed to remove worktree: %s", e)

    # Delete the branch
    try:
        subprocess.run(
            ["git", "branch", "-D", branch],
            capture_output=True, text=True, timeout=10, cwd=repo_root,
        )
    except Exception as e:
        logger.debug("Failed to delete branch %s: %s", branch, e)

    active_worktree = None
    print(f"\033[32m✓ Worktree cleaned up: {wt_path}\033[0m")


__all__ = [
    "active_worktree",
    "normalize_git_bash_path",
    "git_repo_root",
    "path_is_within_root",
    "setup_worktree",
    "worktree_has_unpushed_commits",
    "cleanup_worktree",
]
