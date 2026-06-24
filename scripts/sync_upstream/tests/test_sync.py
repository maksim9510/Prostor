"""Tests for sync orchestrator. Uses ephemeral git repos with subprocess.

Windows quirk: `git init` defaults to branch `master`, not `main`. Every
fixture below explicitly passes `-b main` to `git init`/`git clone`.
"""
import subprocess
import sys
from pathlib import Path

import pytest

_PYTHON = sys.executable


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run command, fail loudly if non-zero exit (unless check=False)."""
    result = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", shell=False
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)} (cwd={cwd})\n"
            f"  stdout: {result.stdout}\n  stderr: {result.stderr}"
        )
    return result


@pytest.fixture
def fake_upstream(tmp_path: Path) -> Path:
    """Create a bare upstream repo with one initial commit on `main`."""
    upstream = tmp_path / "upstream.git"
    upstream.mkdir()
    run(["git", "init", "--bare", "-b", "main"], cwd=upstream)

    # Working repo to push the initial commit
    work = tmp_path / "upstream-work"
    work.mkdir()
    run(["git", "init", "-b", "main"], cwd=work)
    run(["git", "config", "user.email", "test@test"], cwd=work)
    run(["git", "config", "user.name", "Test"], cwd=work)
    (work / "README.md").write_text("# hermes-agent upstream\n")
    (work / "tools").mkdir()
    (work / "tools" / "fuzzy_match.py").write_text("# Hermes fuzzy match\nimport hermes\n")
    run(["git", "add", "-A"], cwd=work)
    run(["git", "commit", "-m", "init"], cwd=work)
    run(["git", "remote", "add", "origin", str(upstream)], cwd=work)
    run(["git", "push", "-u", "origin", "main"], cwd=work)
    return upstream


@pytest.fixture
def fake_prostor(tmp_path: Path, fake_upstream: Path) -> Path:
    """Clone fake_upstream, rebrand in place. Ready for rebrand orchestrator."""
    work = tmp_path / "prostor"
    work.mkdir()
    run(["git", "clone", "-b", "main", str(fake_upstream), "."], cwd=work)
    run(["git", "config", "user.email", "test@test"], cwd=work)
    run(["git", "config", "user.name", "Test"], cwd=work)
    run(["git", "remote", "rename", "origin", "fork"], cwd=work)
    run(["git", "remote", "add", "upstream", str(fake_upstream)], cwd=work)

    # Apply rebrand to the working tree to simulate a Prostor fork post-rebrand.
    (work / "README.md").write_text("# prostor-agent fork\n")
    (work / "tools" / "fuzzy_match.py").write_text("# Prostor fuzzy match\nimport prostor\n")
    run(["git", "commit", "-am", "rebrand upstream to prostor"], cwd=work)
    return work


def _run_rebrand_subprocess(work: Path, *extra_args: str) -> subprocess.CompletedProcess:
    """Run rebrand.main() against a fake worktree.

    Run from the main repo (where scripts/sync_upstream/ is installed) and
    pass the fake worktree path as positional argument. The manifest is
    written inside the fake worktree at scripts/sync_upstream/manifest.json.
    """
    main_repo = Path(__file__).resolve().parents[3]
    manifest_rel = "scripts/sync_upstream/manifest.json"
    cmd = [
        _PYTHON, "-m", "scripts.sync_upstream.rebrand",
        str(work),
        "--manifest", manifest_rel,
        *extra_args,
    ]
    return run(cmd, cwd=main_repo, check=False)


def test_rebrand_no_manifest_noop(fake_prostor: Path):
    """No manifest exists → rebrand errors on every file (add_if_missing=False default)."""
    result = _run_rebrand_subprocess(fake_prostor)
    # Errors expected because manifest is empty
    assert "not in manifest" in result.stdout or "Rebrand complete" in result.stdout


def test_rebrand_add_missing_creates_manifest(fake_prostor: Path):
    """With --add-missing, rebrand auto-populates manifest and rebrand files."""
    result = _run_rebrand_subprocess(fake_prostor, "--add-missing")
    assert result.returncode == 0, f"rebrand failed: {result.stdout[-500:]}"
    # Manifest should exist now and have entries
    manifest_path = fake_prostor / "scripts" / "sync_upstream" / "manifest.json"
    assert manifest_path.exists(), "manifest should be created by --add-missing"
    import json
    m = json.loads(manifest_path.read_text())
    assert len(m["files"]) > 0, f"manifest should have entries, got: {m}"


def test_rebrand_idempotent_after_manifest(fake_prostor: Path):
    """Run twice — second run is a no-op (all skipped as post-state)."""
    # First run: populates manifest
    r1 = _run_rebrand_subprocess(fake_prostor, "--add-missing")
    assert r1.returncode == 0

    # Second run: should be no-op
    r2 = _run_rebrand_subprocess(fake_prostor, "--add-missing")
    assert r2.returncode == 0, f"second rebrand should be no-op, got: {r2.stdout[-500:]}"
    # Should have 0 errors
    assert "Errors:          0" in r2.stdout or "Errors: 0" in r2.stdout, \
        f"Expected 0 errors, got: {r2.stdout[-1000:]}"


def test_rebrand_handles_new_upstream_file(fake_prostor: Path):
    """A new file with Hermes tokens gets rebranded and added to manifest."""
    # Populate manifest from current state
    r0 = _run_rebrand_subprocess(fake_prostor, "--add-missing")
    assert r0.returncode == 0

    # Drop a new file with hermes tokens (simulating upstream merge)
    (fake_prostor / "new_feature.py").write_text("# New hermes feature\nimport hermes_agent\n")
    run(["git", "add", "new_feature.py"], cwd=fake_prostor)
    run(["git", "commit", "-m", "merge new feature from upstream"], cwd=fake_prostor)

    # Run rebrand with --add-missing
    r = _run_rebrand_subprocess(fake_prostor, "--add-missing")
    assert r.returncode == 0, f"rebrand failed: {r.stdout[-500:]}"
    content = (fake_prostor / "new_feature.py").read_text()
    assert "prostor" in content.lower() or "Prostor" in content, \
        f"Expected prostor tokens in rebranded content, got: {content!r}"
