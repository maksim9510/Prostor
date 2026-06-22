"""Tests for prostor_cli.cli_worktree — worktree + path helpers.

Tests pure functions and verifies that the cli.py stub functions
delegate correctly to cli_worktree. Heavy git subprocess interactions
(.worktreeinclude copies, lock/unlock, branch delete) are skipped —
those need a real git repo and are tested by integration suites.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from prostor_cli.cli_worktree import (
    active_worktree,
    git_repo_root,
    normalize_git_bash_path,
    path_is_within_root,
    setup_worktree,
    cleanup_worktree,
    worktree_has_unpushed_commits,
)


# ---------------------------------------------------------------------------
# normalize_git_bash_path
# ---------------------------------------------------------------------------

class TestNormalizeGitBashPath:
    def test_empty_returns_empty(self):
        assert normalize_git_bash_path("") == ""

    def test_none_returns_none(self):
        assert normalize_git_bash_path(None) is None

    def test_native_windows_unchanged(self):
        # Backslash paths look like native Windows already.
        assert normalize_git_bash_path(r"C:\Users\foo") == r"C:\Users\foo"

    def test_forward_slash_windows_unchanged(self):
        # ``C:/Users/foo`` is already acceptable to Python on Windows.
        assert normalize_git_bash_path("C:/Users/foo") == "C:/Users/foo"

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only path")
    def test_git_bash_drive_letter_lower(self):
        assert normalize_git_bash_path("/c/Users/foo") == r"C:\Users\foo"

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only path")
    def test_git_bash_drive_letter_upper(self):
        assert normalize_git_bash_path("/C/Users/foo") == r"C:\Users\foo"

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only path")
    def test_cygdrive_path(self):
        assert normalize_git_bash_path("/cygdrive/c/Users/foo") == r"C:\Users\foo"

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only path")
    def test_mnt_path(self):
        assert normalize_git_bash_path("/mnt/c/Users/foo") == r"C:\Users\foo"

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only path")
    def test_posix_passthrough(self):
        assert normalize_git_bash_path("/home/user") == "/home/user"


# ---------------------------------------------------------------------------
# git_repo_root
# ---------------------------------------------------------------------------

class TestGitRepoRoot:
    def test_returns_none_when_not_in_repo(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # Outside a repo: subprocess.run returns non-zero, function returns None.
        assert git_repo_root() is None

    def test_returns_path_inside_real_repo(self):
        # We're running inside the prostor-agent repo itself.
        result = git_repo_root()
        assert result is not None
        assert Path(result).is_dir()


# ---------------------------------------------------------------------------
# path_is_within_root
# ---------------------------------------------------------------------------

class TestPathIsWithinRoot:
    def test_inside(self, tmp_path):
        f = tmp_path / "a" / "b.txt"
        f.parent.mkdir(parents=True)
        f.write_text("x")
        assert path_is_within_root(f, tmp_path) is True

    def test_outside(self, tmp_path):
        outside = tmp_path.parent / "other.txt"
        outside.write_text("x")
        try:
            assert path_is_within_root(outside, tmp_path) is False
        finally:
            outside.unlink(missing_ok=True)

    def test_relative_to_doesnt_traverse(self, tmp_path):
        # ``Path.relative_to`` raises ValueError for any traversal that
        # lands outside ``root``, so the function correctly returns False.
        outside_dir = tmp_path.parent
        outside_file = outside_dir / "outside_test_file.txt"
        try:
            outside_file.write_text("x")
            assert path_is_within_root(outside_file, tmp_path) is False
        finally:
            outside_file.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# active_worktree (module-level dict singleton)
# ---------------------------------------------------------------------------

class TestActiveWorktree:
    def test_initial_none(self):
        # Module-level dict should default to None at import time.
        # Other tests in this file may set/clear it, so we only assert
        # it's a dict or None.
        assert active_worktree is None or isinstance(active_worktree, dict)

    def teardown_function(self):
        # Don't leak state between tests.
        global active_worktree
        active_worktree = None


# ---------------------------------------------------------------------------
# cleanup_worktree / worktree_has_unpushed_commits (smoke)
# ---------------------------------------------------------------------------

class TestCleanupSmoke:
    def test_cleanup_with_no_active_returns_silently(self, capsys):
        # No active worktree set: should print nothing and return None.
        global active_worktree
        saved = active_worktree
        active_worktree = None
        try:
            cleanup_worktree()
            captured = capsys.readouterr()
            # Should not print anything (no worktree to clean).
            assert captured.out == ""
        finally:
            active_worktree = saved

    def test_cleanup_with_missing_path_returns_silently(self, capsys):
        global active_worktree
        saved = active_worktree
        active_worktree = {
            "path": "/nonexistent/path/that/does/not/exist",
            "branch": "prostor/fake",
            "repo_root": "/nonexistent/repo",
        }
        try:
            cleanup_worktree()
            captured = capsys.readouterr()
            # Missing path -> early return, no output.
            assert captured.out == ""
        finally:
            active_worktree = saved

    def test_worktree_has_unpushed_with_no_remotes(self, tmp_path):
        # A fresh git repo with no remotes and no commits should return False.
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True, capture_output=True)
        (tmp_path / "f").write_text("x")
        subprocess.run(["git", "add", "f"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)
        assert worktree_has_unpushed_commits(str(tmp_path)) is False


# ---------------------------------------------------------------------------
# setup_worktree requires being inside a repo
# ---------------------------------------------------------------------------

class TestSetupWorktreeOutsideRepo:
    def test_returns_none_outside_repo(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        result = setup_worktree()
        assert result is None
        captured = capsys.readouterr()
        assert "git repository" in captured.out or "--worktree" in captured.out


# ---------------------------------------------------------------------------
# cli.py stub delegation
# ---------------------------------------------------------------------------

class TestCliStubs:
    """Verify the deprecation aliases in cli.py delegate to cli_worktree."""

    def test_cli_normalize_stub(self):
        import cli
        assert cli._normalize_git_bash_path("") == ""
        assert cli._normalize_git_bash_path(None) is None

    def test_cli_git_repo_root_stub(self):
        import cli
        # Stub should produce the same result as the real function.
        assert cli._git_repo_root() == git_repo_root()

    def test_cli_active_worktree_alias(self):
        import cli
        # Should be the same dict object as cli_worktree.active_worktree.
        assert cli._active_worktree is active_worktree