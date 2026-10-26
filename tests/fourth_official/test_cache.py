"""Every offside, foul and card of the golden match has a cached referee_line cue with lines and its margin,
verified by construction."""

import json
from pathlib import Path

import pytest

from cache.manifest import CacheManifest
from newsroom.executors.fourth_official import REFEREE, rule_event
from physics import TrackingWindow

GOLDEN = Path(__file__).resolve().parents[2] / "data" / "matches" / "4242"


@pytest.fixture(scope="module")
def golden():
    events = [json.loads(line) for line in (GOLDEN / "events.jsonl").read_text().splitlines()]
    return events, TrackingWindow.load(GOLDEN)


def test_cached_cue_for_every_referee_event(golden):
    events, _ = golden
    manifest = CacheManifest.load(GOLDEN / "cache")
    entries = {e["key"].split("/")[1]: e for e in manifest.find(producer="fourth_official")}
    referee = [e for e in events if e["type"] in REFEREE]
    assert referee and {e["id"] for e in referee} == set(entries)
    for ev in referee:
        cue = manifest.read(entries[ev["id"]])
        assert cue["layer"] == "referee_line" and cue["kind"] == "fourth_official" and cue["verified"]
        assert cue["graphics"]["lines"] and all(c["evidence_ids"] == [ev["id"]] for c in cue["explain"]["claims"])
        if ev["type"] == "offside":
            margin = f"{abs(ev['attrs']['margin_m']):.1f} m"
            assert margin in cue["text"]["body"] and cue["explain"]["claims"][0]["value"] == pytest.approx(
                round(abs(ev["attrs"]["margin_m"]), 1))
    assert manifest.verify_hashes(GOLDEN)


def test_cache_matches_a_fresh_ruling(golden):
    events, window = golden
    manifest = CacheManifest.load(GOLDEN / "cache")
    for entry in manifest.find(producer="fourth_official")[:6]:
        ev = next(e for e in events if e["id"] == entry["key"].split("/")[1])
        assert manifest.read(entry) == json.loads(json.dumps(rule_event(ev, events, window, "m_4242")))
