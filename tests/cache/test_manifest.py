"""CacheManifest: key format, schema validation, one flipped byte detected, freeze (T-038)."""

import json
import shutil
from pathlib import Path

import pytest

from cache import CacheCorrupt, CacheFrozen, CacheManifest
from cache.manifest import SCHEMA, VALIDATOR

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "data" / "matches" / "4242"


def test_keys_match_the_schema_examples():
    ex = SCHEMA["examples"][0]["entries"]
    assert CacheManifest.key("m_4242", "mo_00077", "rollout", "scripted_v1", "scripted", 4242) == ex[0]["key"]
    assert CacheManifest.key("m_4242", "mo_00077", "tactician", "tactician@3", "claude-opus-5-5", 4242) == ex[1]["key"]
    assert CacheManifest.key("m_4242", None, "timeline", "1", None, 4242) == "m_4242/match/timeline@1/none/s4242"


def test_schema_example_validates():
    assert not list(VALIDATOR.iter_errors(SCHEMA["examples"][0]))


@pytest.fixture
def match_copy(tmp_path):
    d = tmp_path / "4242"
    d.mkdir()
    for name in ("events.jsonl", "tracking.npz"):
        shutil.copy(GOLDEN / name, d / name)
    return d


def build(match_copy, engine_hash="0" * 40):
    m = CacheManifest.new(match_copy, engine_hash=engine_hash)
    key = m.key("m_4242", "mo_00077", "tactician", "tactician@3", "gemini-4-argon", 4242)
    m.add(key, "explanation", {"json": {"why": "x"}}, "explanations/ex_000077.json", moment_id="mo_00077",
          producer="tactician", version="tactician@3", model="gemini-4-argon", seed=4242, simulated_latency_ms=6200,
          tokens_in=4120, tokens_out=790, cost_usd=0.0161)
    return m, key


def test_save_load_validates_and_totals(match_copy):
    m, key = build(match_copy)
    path = m.save()
    loaded = CacheManifest.load(path.parent)
    assert not list(VALIDATOR.iter_errors(loaded.data))
    assert loaded.get(key)["path"] == "explanations/ex_000077.json"
    assert loaded.data["totals"] == {"entries": 1, "cost_usd": 0.0161, "tokens_in": 4120, "tokens_out": 790}
    assert loaded.data["match_seed"] == 4242 and loaded.verify_hashes()
    assert loaded.read(loaded.get(key)) == {"json": {"why": "x"}}


def test_invalid_manifest_is_refused(match_copy):
    m, _ = build(match_copy)
    m.data["entries"][0]["kind"] = "narration"
    with pytest.raises(CacheCorrupt):
        m.save()


@pytest.mark.parametrize("target", ["entry", "events"])
def test_one_flipped_byte_is_detected(match_copy, target):
    m, key = build(match_copy)
    m.save()
    path = (m.cache_dir / m.get(key)["path"]) if target == "entry" else match_copy / "events.jsonl"
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 0x01
    path.write_bytes(bytes(data))
    assert not m.verify_hashes()
    assert len(m.problems()) == 1


def test_frozen_manifest_takes_no_entries(match_copy):
    m, _ = build(match_copy)
    m.data["frozen"] = True
    with pytest.raises(CacheFrozen):
        m.add("k", "cue", {}, "cues/c.json")
    assert json.loads(json.dumps(m.data))["frozen"] is True
