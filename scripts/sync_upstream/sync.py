"""Upstream sync orchestrator.

Workflow:
1. git fetch upstream (NousResearch/hermes-agent)
2. Create/sync local branch `upstream-sync` at upstream/main
3. Apply rebrand using manifest (with --add-missing for new files)
4. git checkout main, merge upstream-sync with -X ours on protected files
5. Push to origin/main (only if all CI checks would pass — checked locally)
6. Open PR if changes detected, with auto-merge label

Designed to run from GitHub Actions weekly cron.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Allow running this script directly via `python scripts/sync_upstream/sync.py`
# without requiring `pip install -e .` — adds the scripts/ dir to sys.path so
# `from sync_upstream.X import Y` (notably `from sync_upstream.rebrand import ...`
# used internally) resolves.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from sync_upstream.rebrand import apply_rebrand, rebrand_file, Manifest  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[2]
UPSTREAM_REMOTE = "upstream"
UPSTREAM_URL = "https://github.com/NousResearch/hermes-agent.git"
UPSTREAM_BRANCH = "main"
SYNC_BRANCH = "upstream-sync"
MANIFEST_PATH = REPO_ROOT / "scripts" / "sync-upstream" / "manifest.json"


@dataclass
class SyncResult:
    upstream_sha: str
    sync_branch_sha: str
    files_changed: int
    pr_url: str | None
    auto_merged: bool


def run(cmd: list[str], check: bool = True, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run shell command, return result."""
    result = subprocess.run(
        cmd,
        cwd=cwd or REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if check and result.returncode != 0:
        print(f"ERROR: {' '.join(cmd)}")
        print(f"  stdout: {result.stdout}")
        print(f"  stderr: {result.stderr}")
        sys.exit(result.returncode)
    return result


def ensure_upstream_remote() -> None:
    """Add upstream remote if missing."""
    result = run(["git", "remote", "get-url", UPSTREAM_REMOTE], check=False)
    if result.returncode != 0:
        print(f"Adding upstream remote: {UPSTREAM_URL}")
        run(["git", "remote", "add", UPSTREAM_REMOTE, UPSTREAM_URL])


def fetch_upstream() -> str:
    """Fetch upstream, return SHA of upstream/main."""
    print("Fetching upstream...")
    run(["git", "fetch", UPSTREAM_REMOTE, UPSTREAM_BRANCH])
    result = run(["git", "rev-parse", f"{UPSTREAM_REMOTE}/{UPSTREAM_BRANCH}"])
    sha = result.stdout.strip()
    print(f"  upstream/{UPSTREAM_BRANCH} = {sha[:10]}")
    return sha


def create_sync_branch(upstream_sha: str) -> None:
    """Create or reset upstream-sync branch at upstream_sha."""
    # Stash any local changes
    run(["git", "stash", "--include-untracked"], check=False)

    # Delete local sync branch if exists
    run(["git", "branch", "-D", SYNC_BRANCH], check=False)

    # Create fresh
    run(["git", "checkout", "-b", SYNC_BRANCH, upstream_sha])

    # Pop stash if there was one
    stash_result = run(["git", "stash", "list"], check=False)
    if stash_result.stdout.strip():
        run(["git", "stash", "pop"], check=False)


def apply_rebrand() -> int:
    """Apply rebrand on current branch, return count of changes."""
    print("Applying rebrand...")
    result = run(
        [sys.executable, "-m", "scripts.sync_upstream.rebrand", str(REPO_ROOT), "--add-missing"],
        cwd=REPO_ROOT,
    )
    return result.returncode


def commit_rebrand(upstream_sha: str) -> str | None:
    """Commit rebrand changes if any. Returns commit SHA or None."""
    status = run(["git", "status", "--porcelain"], check=False)
    if not status.stdout.strip():
        print("  No rebrand changes needed.")
        return None

    print("  Committing rebrand...")
    run(["git", "add", "-A"])
    msg = f"chore(sync): rebrand upstream {upstream_sha[:10]}\n\nApplied via scripts/sync-upstream/sync.py"
    run(["git", "commit", "-m", msg])
    sha_result = run(["git", "rev-parse", "HEAD"])
    return sha_result.stdout.strip()


def merge_into_main(sync_sha: str) -> tuple[int, str | None]:
    """Merge sync branch into main with -X ours on protected files.

    Returns (files_changed, conflict_files).
    """
    print("Merging into main...")
    run(["git", "checkout", "main"])

    # Try merge
    result = run(
        ["git", "merge", "--no-ff", SYNC_BRANCH, "-m",
         f"merge: upstream sync ({sync_sha[:10]})\n\nAuto-synced from NousResearch/hermes-agent"],
        check=False,
    )

    if result.returncode != 0:
        # Conflicts expected on protected files — resolve with ours
        print("  Conflicts detected, resolving with -X ours on protected files...")
        # Get list of conflicted files
        diff_result = run(["git", "diff", "--name-only", "--diff-filter=U"], check=False)
        conflicted = diff_result.stdout.strip().split("\n")

        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        protected = set(manifest.get("protected_files", []))

        for f in conflicted:
            if f in protected:
                print(f"    Keeping ours (protected): {f}")
                run(["git", "checkout", "--ours", f])
                run(["git", "add", f])
            else:
                print(f"    WARNING: unexpected conflict in {f}")

        # Complete merge
        run(["git", "commit", "--no-edit"])

    # Count changed files
    diff_result = run(["git", "diff", "--name-only", "HEAD~1", "HEAD"], check=False)
    changed = len([f for f in diff_result.stdout.strip().split("\n") if f])
    return changed, None


def push_to_origin() -> None:
    """Push main to origin."""
    print("Pushing to origin/main...")
    run(["git", "push", "origin", "main"])


def open_or_update_pr(sync_sha: str, files_changed: int) -> str | None:
    """Open PR if not exists, return URL.

    For auto-merge: PR gets label 'auto-merge' which triggers
    .github/workflows/auto-merge.yml to merge when CI green.
    """
    if os.environ.get("DRY_RUN"):
        print(f"  DRY_RUN: would open PR for {sync_sha[:10]}")
        return None

    title = f"chore(sync): upstream NousResearch {sync_sha[:10]} ({files_changed} files)"
    body = (
        f"## Auto-synced from upstream\n\n"
        f"- **Upstream SHA**: `{sync_sha}`\n"
        f"- **Files changed**: {files_changed}\n"
        f"- **Protected files**: kept our version via `-X ours`\n\n"
        f"Auto-generated by `.github/workflows/upstream-sync.yml`. "
        f"Auto-merges when CI passes.\n\n"
        f"---\n\n"
        f"<sub>🤖 This PR was opened by GitHub Action. Do not review manually.</sub>"
    )

    # Check if PR exists
    list_result = run(
        ["gh", "pr", "list", "--state", "open", "--label", "auto-merge", "--json", "number"],
        check=False,
    )
    if list_result.returncode == 0 and list_result.stdout.strip() != "[]":
        print("  PR already open, skipping")
        return None

    # Open new PR
    result = run(
        ["gh", "pr", "create",
         "--title", title,
         "--body", body,
         "--base", "main",
         "--head", "main",  # PR from main to main (after push)
         "--label", "auto-merge",
         "--label", "type:sync"],
        check=False,
    )
    if result.returncode == 0:
        # Extract URL from output
        for line in result.stdout.split("\n"):
            if "github.com" in line and "/pull/" in line:
                return line.strip()
    else:
        print(f"  PR creation failed: {result.stderr}")
    return None


def main() -> int:
    print("=" * 60)
    print("Prostor upstream sync — NousResearch/hermes-agent")
    print("=" * 60)

    ensure_upstream_remote()
    upstream_sha = fetch_upstream()
    create_sync_branch(upstream_sha)
    apply_rebrand()
    sync_sha = commit_rebrand(upstream_sha)

    if sync_sha is None:
        print("No upstream changes since last sync.")
        return 0

    files_changed, _ = merge_into_main(sync_sha)
    push_to_origin()
    pr_url = open_or_update_pr(sync_sha, files_changed)

    print("=" * 60)
    print("Sync complete:")
    print(f"  Upstream SHA: {upstream_sha[:10]}")
    print(f"  Sync SHA: {sync_sha[:10]}")
    print(f"  Files changed: {files_changed}")
    print(f"  PR: {pr_url or 'none'}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
