"""The agent pipeline record (video v6): every node, every timing labelled by its source, none invented."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_amad_pipeline_record_is_honest_about_timings():
    r = json.loads((ROOT / "data/footage/manutd-mancity-2526/cache/v6/pipeline_877000.json").read_text())["result"]
    nodes = {n["node"]: n for n in r["nodes"]}
    assert list(nodes) == ["Freeze", "Scout", "Proposer", "Model", "Tactician", "Fact Checker", "Producer review",
                           "Director", "On air"]
    for n in r["nodes"]:
        t = n["timing"]
        assert t["source"] in r["timing_sources"] and (t["ms"] is None) == (t["source"] == "not recorded")
    assert nodes["Tactician"]["timing"]["source"] == "recorded live" and nodes["Tactician"]["timing"]["ms"] == 13819
    assert nodes["Model"]["outputs"]["rerun_matches_stored"] is True
    assert nodes["Fact Checker"]["outputs"]["verified"] and all(c["verified"] for c in nodes["Fact Checker"]["outputs"]["claims"])
    assert nodes["On air"]["outputs"]["headline"] == "Amad: shot from here 0.06 xG, pass 0.11 xG"
