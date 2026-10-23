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


def test_track_c_view_binds_every_number_and_labels_only_verified_names():
    import re

    r = json.loads((ROOT / "data/footage/manutd-mancity-2526/cache/v6/pipeline_manutd-mancity-2526_877000.json")
                   .read_text())["result"]
    assert [n["agent"] for n in r["nodes"]] == ["scout", "proposer", "rollout", "tactician", "factcheck", "director",
                                               "cuebus"]
    shown = {f["display"] for f in r["facts"]}
    for n in r["nodes"]:
        for text in [n.get("says", ""), n.get("line", "")]:
            for tok in re.findall(r"\d+(?::\d+)?(?:\.\d+)?(?:%| m| s)?", text):
                assert tok in shown, (n["agent"], tok)
        for o in n.get("options", []):
            assert o["label"] in ("Shot", "Pass") or o["label"].startswith("Pass to ") and "#" not in o["label"]
    assert r["nodes"][1]["options"][1]["label"] == "Pass to Mbeumo"


def test_live_names_hold_only_inside_their_window():
    r = json.loads((ROOT / "data/footage/liverpool-mancity-2526/cache/v6/names_live_0.json").read_text())["result"]
    wirtz = next(p for p in r["players"] if p["name"] == "Florian Wirtz")
    assert (wirtz["track_id"], wirtz["from_clip_ms"], wirtz["to_clip_ms"]) == (69, 867200, 870900)   # t69 is City later
    assert all(p["name"] is None or p["shirt"] is not None for p in r["players"])
