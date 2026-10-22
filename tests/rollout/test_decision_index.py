"""Decision Index (T-048): every on-ball decision of the golden match has a cached value, the per-player index is in
[0, 100], the formula is documented, and the live head-swing approximation ranks players like the rollout index
(Spearman >= 0.5)."""

import json
from pathlib import Path

import pytest

import rollout.decision_index as di
from rollout.decision_index import player_index

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "matches" / "4242" / "cache" / "analytics" / "decision_index.json"


def test_formula_documented():
    assert "value = p(actual) - max(p(alternative_1..3))" in di.__doc__


def test_player_index_percentiles():
    vals = [("a", 0.01)] * 5 + [("b", 0.0)] * 5 + [("c", -0.01)] * 5 + [("d", 0.5)] * 2
    idx = player_index(vals)
    assert idx["a"]["index"] == 100.0 and idx["c"]["index"] == 0.0 and idx["b"]["index"] == 50.0
    assert idx["d"]["index"] is None and idx["d"]["decisions"] == 2


@pytest.fixture(scope="module")
def doc():
    if not CACHE.exists():
        pytest.skip("decision_index stage not run yet")
    return json.loads(CACHE.read_text())


def test_every_decision_cached(doc):
    events = [json.loads(line) for line in (ROOT / "data" / "matches" / "4242" / "events.jsonl").read_text().splitlines()]
    decisions = {e["id"] for e in events if e["type"] in di.DECISIONS and e.get("player")}
    valued = {d["event_id"] for d in doc["decisions"]}
    print(f"\n{len(valued)} of {len(decisions)} decisions valued; Spearman live vs rollout "
          f"{doc['spearman_live_vs_rollout']}")
    assert valued == decisions
    assert all(p["index"] is None or 0 <= p["index"] <= 100 for p in doc["players"].values())
    assert doc["n"] == 50 and doc["horizon_s"] == 8 and doc["engine"] == "scripted_v1"


def test_live_approximation_correlates(doc):
    assert doc["spearman_live_vs_rollout"] >= 0.5
