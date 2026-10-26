"""Frozen-cache guard: unchanged, changed without a VERSION bump (fail), changed with a bump (pass)."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("guard", ROOT / "scripts" / "frozen_cache_guard.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
MANIFEST = guard.MANIFEST


def sh(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def write(repo, frozen=True, sha="a" * 64, version="0"):
    m = {"schema_version": "1.0.0", "match_id": "m_4242", "match_seed": 4242, "events_sha256": "e" * 64,
         "tracking_sha256": "t" * 64, "engine_hash": "0" * 40, "created_at": "2026-10-27T00:00:00Z", "frozen": frozen,
         "entries": [{"key": "m_4242/mo_00077/tactician@3/gemini-4-argon/s4242", "kind": "explanation",
                      "path": "explanations/ex_000077.json", "sha256": sha, "created_at": "2026-10-27T00:00:00Z"}],
         "totals": {"entries": 1, "cost_usd": 0.0}}
    p = repo / MANIFEST
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(m))
    v = repo / guard.VERSION
    v.parent.mkdir(parents=True, exist_ok=True)
    v.write_text(version + "\n")


def commit(repo, msg):
    sh(repo, "add", "-A")
    sh(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", msg)


@pytest.fixture
def repo(tmp_path):
    sh(tmp_path, "init", "-q")
    return tmp_path


def run(repo):
    return guard.check(str(repo), "HEAD^", "HEAD")


def test_unchanged_frozen_manifest_passes(repo):
    write(repo)
    commit(repo, "freeze")
    (repo / "README").write_text("x")
    commit(repo, "unrelated")
    ok, why = run(repo)
    assert ok and "unchanged" in why


def test_changed_without_bump_fails(repo):
    write(repo)
    commit(repo, "freeze")
    write(repo, sha="b" * 64)
    commit(repo, "regenerate")
    ok, why = run(repo)
    assert not ok and "entries" in why
    assert guard.main(["--repo", str(repo), "--base", "HEAD^"]) == 1


def test_changed_with_bump_passes(repo):
    write(repo)
    commit(repo, "freeze")
    write(repo, sha="b" * 64, version="1")
    commit(repo, "regenerate with new video")
    ok, why = run(repo)
    assert ok and "0 -> 1" in why


def test_unfreezing_counts_as_a_change(repo):
    write(repo)
    commit(repo, "freeze")
    write(repo, frozen=False)
    commit(repo, "unfreeze")
    assert not run(repo)[0]


def test_not_frozen_or_absent_passes(repo):
    (repo / "README").write_text("x")
    commit(repo, "start")
    write(repo, frozen=False)
    commit(repo, "manifest")
    assert run(repo)[0]                                  # absent at base
    write(repo, frozen=False, sha="c" * 64)
    commit(repo, "regenerate")
    assert run(repo)[0]                                  # base not frozen


def test_this_repository_passes():
    assert guard.main(["--repo", str(ROOT), "--base", "HEAD^"]) == 0
