"""Tests for rebrand idempotency and protected-file behavior."""
import sys
from pathlib import Path

# Path setup: pytest's rootdir is the project root (prostor-agent), and
# `scripts/__init__.py` makes `scripts` a real package. We import via the
# fully-qualified `scripts.sync_upstream.rebrand` path so pytest's import
# resolver finds the module regardless of sys.path tricks or rootdir drift.
_ROOT = Path(__file__).resolve().parents[3]  # prostor-agent/
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.sync_upstream.rebrand import (  # noqa: E402
    Manifest,
    apply_rebrand,
    rebrand_file,
    sha256,
)


def test_apply_rebrand_basic():
    assert apply_rebrand("hermes-agent") == "prostor-agent"
    assert apply_rebrand("Hermes Agent") == "Prostor Agent"
    assert apply_rebrand("PROSTOR_HOME") == "PROSTOR_HOME"
    assert apply_rebrand("HermesAgent.run()") == "ProstorAgent.run()"


def test_apply_rebrand_idempotent_on_prostor():
    """Running rebrand on already-prostor content is a no-op."""
    prostor_content = "prostor-agent and Prostor Agent and PROSTOR_HOME"
    assert apply_rebrand(prostor_content) == prostor_content


def test_apply_rebrand_mixed_state():
    """Mixed: should still produce consistent prostor-form."""
    assert apply_rebrand("hermes and Hermes and HERMES") == "prostor and Prostor and PROSTOR"


def test_sha256_deterministic():
    assert sha256("hello") == sha256("hello")
    assert sha256("hello") != sha256("world")


def test_manifest_load_save(tmp_path: Path):
    m_path = tmp_path / "manifest.json"
    m = Manifest(by_path={"foo.py": {"pre_hash": "a", "post_hash": "b"}}, protected={"x.py"})
    m.save(m_path)
    loaded = Manifest.load(m_path)
    assert loaded.by_path == m.by_path
    assert loaded.protected == m.protected


def test_manifest_load_missing_file(tmp_path: Path):
    m = Manifest.load(tmp_path / "nonexistent.json")
    assert m.by_path == {}
    assert m.protected == set()


def test_rebrand_file_skips_when_already_post(tmp_path: Path):
    """If file content matches post_hash in manifest, do nothing."""
    f = tmp_path / "test.py"
    content = "prostor is great"
    f.write_text(content, encoding="utf-8")
    m = Manifest(
        by_path={"test.py": {"pre_hash": "deadbeef" * 8, "post_hash": sha256(content)}},
        protected=set(),
    )
    state = rebrand_file(f, m)
    assert state.action == "skipped_post"
    assert f.read_text(encoding="utf-8") == content  # unchanged


def test_rebrand_file_rebrands_when_pre(tmp_path: Path):
    """If file content matches pre_hash, apply rebrand."""
    f = tmp_path / "test.py"
    content = "hermes-agent"
    f.write_text(content, encoding="utf-8")
    expected_post = sha256("prostor-agent")
    m = Manifest(
        by_path={"test.py": {"pre_hash": sha256(content), "post_hash": expected_post}},
        protected=set(),
    )
    state = rebrand_file(f, m)
    assert state.action == "reb"
    assert f.read_text(encoding="utf-8") == "prostor-agent"


def test_rebrand_file_skips_protected(tmp_path: Path):
    """Protected files are never modified."""
    f = tmp_path / "hashline.py"
    content = "hermes CONTENT"  # would be rebranded normally
    f.write_text(content, encoding="utf-8")
    m = Manifest(by_path={}, protected={"hashline.py"})
    state = rebrand_file(f, m)
    assert state.action == "skipped_protected"
    assert f.read_text(encoding="utf-8") == content  # untouched


def test_rebrand_file_errors_when_not_in_manifest(tmp_path: Path):
    """Unknown files error unless add_if_missing=True."""
    f = tmp_path / "new.py"
    f.write_text("hermes", encoding="utf-8")
    m = Manifest(by_path={}, protected=set())
    state = rebrand_file(f, m)
    assert state.action == "error"
    assert "not in manifest" in (state.error or "")


def test_rebrand_file_adds_to_manifest_when_missing(tmp_path: Path):
    """With add_if_missing=True, new files are rebranded + registered."""
    f = tmp_path / "new.py"
    content = "from hermes_agent import run"
    f.write_text(content, encoding="utf-8")
    m = Manifest(by_path={}, protected=set())
    state = rebrand_file(f, m, add_if_missing=True)
    assert state.action == "added_to_manifest"
    assert f.read_text(encoding="utf-8") == "from prostor_agent import run"
    assert m.lookup_pre_hash(f) == sha256(content)
    assert m.lookup_post_hash(f) == sha256("from prostor_agent import run")
