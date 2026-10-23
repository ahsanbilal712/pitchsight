"""Grounded-claims count (video v3 and v4 metrics cards): every on-screen number bound, and the check bites."""

from footage.clips import CLIPS
from footage.grounding import _check, latest_edit, run, version_of
from footage.insights import evidence_board

FACT = {"fact_id": "f_799901", "match_id": "m_9002", "label": "ghost goal chance", "value": 0.2581, "unit": "p_goal"}


def test_all_v3_on_screen_numbers_are_bound():
    r = run()
    assert r["numbers"] > 0 and r["numbers_bound"] == r["numbers"] and r["claims_verified"] == r["claims"]
    assert set(r["groups"]) == {"studio cue", "beat caption", "video caption"}


def test_a_wrong_number_is_caught():
    bb = evidence_board("manutd-mancity-2526", [FACT])
    claim = {"text": "26%", "kind": "number", "value": 0.2581, "unit": "p_goal", "evidence_ids": ["f_799901"]}
    ok = _check(CLIPS["manutd-mancity-2526"]["match_id"], [claim], bb, {"caption": "it falls from 26%"})
    bad = _check(CLIPS["manutd-mancity-2526"]["match_id"], [{**claim, "text": "28%"}], bb, {"caption": "from 28%"})
    unclaimed = _check(CLIPS["manutd-mancity-2526"]["match_id"], [claim], bb, {"caption": "26% and then 7 more"})
    bb.close()
    assert ok["numbers_bound"] == ok["numbers"] == 1 and ok["claims_verified"] == 1
    assert bad["claims_verified"] == 0 and bad["numbers_bound"] == 0
    assert unclaimed["numbers"] == 2 and unclaimed["numbers_bound"] == 1


def test_v4_lines_studio_and_captions_are_bound_and_the_overlay_is_checked():
    edit = latest_edit().with_name("edit_v4.yaml")
    assert version_of(edit) == "v4" and version_of(latest_edit()) >= "v4"
    r = run("v4", edit)
    for g in ("studio cue", "v4 line", "video caption"):
        x = r["groups"][g]
        assert x["numbers_bound"] == x["numbers"] > 0 and x["claims_verified"] == x["claims"], (g, x)
    assert r["groups"]["v4 overlay"]["items"] == 8      # six decision cards, the Oracle card, the ghost footer
    assert "win" not in " ".join(row["item"] for row in r["rows"]).lower()


def test_v5_lines_studio_and_captions_are_bound():
    from footage.grounding import ROOT

    r = run("v5", ROOT / "packages" / "demo" / "edit_v5.yaml")
    for g in ("studio cue", "v5 line"):
        x = r["groups"][g]
        assert x["numbers_bound"] == x["numbers"] > 0 and x["claims_verified"] == x["claims"], (g, x)
    # whatever is not bound yet is listed with the change that binds it; nothing unexplained
    assert all(u["owner"] != "open" for u in r["unbound"]), r["unbound"]
    assert r["numbers"] - r["numbers_bound"] == sum(
        row["numbers"] - row["numbers_bound"] for row in r["rows"] if row["item"] in {u["item"] for u in r["unbound"]})
    assert "win" not in " ".join(row["item"] for row in r["rows"]).lower()


def test_v5_from_here_binds_the_freeze_and_any_other_shot_the_strike():
    from footage.grounding import v5_caption_sources

    src = v5_caption_sources()
    (amad,) = src["Man Utd v Man City. Amad shoots from here: 0.06 xG."]
    assert amad[3] == 0.0635 and "freeze" in amad[4][1]                    # strike would be 0.07
    eze = src["Arsenal v Chelsea. Eze from 16 m: 0.08 xG. Saved."][1]
    assert eze[3] == 0.08 and "shots_0 e_0046" in eze[4][1]                # strike; the freeze was 0.05


def test_v6_all_bound_and_the_live_product_check_bites(tmp_path):
    import json as _json

    from footage.grounding import ROOT, v6_live

    r = run("v6", ROOT / "packages" / "demo" / "edit_v6.yaml")
    assert r["numbers_bound"] == r["numbers"] > 400 and r["claims_verified"] == r["claims"]
    frame = {"clip_ms": 1000, "shot_now_xg": 0.04, "options": [
        {"label": "t4", "p_pass": 0.5, "xg_receiver": 0.2, "xg_after_pass": 0.15}]}      # 0.5 x 0.2 is 0.10
    path = tmp_path / "live.json"
    path.write_text(_json.dumps({"result": {"frames": [frame]}}))
    (row,) = v6_live({"x": {"kind": "live_hud", "data": str(path), "t0": 0.0, "t1": 2.0}})
    assert row["numbers_bound"] < row["numbers"] and "is not 0.5 x 0.2" in row["diff"][0]


def test_v6_pipeline_compact_phrases_are_checked():
    import yaml

    from footage.grounding import ROOT, v6_pipeline

    beat = yaml.safe_load((ROOT / "packages/demo/footage_moments.yaml").read_text())["moments"]["mci_pipeline_v6"]
    (ok,) = v6_pipeline({"p": beat})
    assert ok["numbers_bound"] == ok["numbers"]
    (bad,) = v6_pipeline({"p": {**beat, "compact": {**beat["compact"], "proposer": "Shot + 9 passes priced"}}})
    assert bad["numbers_bound"] == bad["numbers"] - 1 and any("9" in d for d in bad["diff"])


def test_v7_always_on_checks_the_share_and_the_shape():
    import json as _json

    from footage.grounding import v7_always

    lines = [{"x": 43.73}, {"x": 50.39}, {"x": 59.4}]
    fr = {"clip_ms": 1000, "danger": {"team": "home", "share": 0.28, "text": "Man Utd control 28% of the danger zone"},
          "danger_zone": {"attacked_by": "home"}, "shape": {"away": {
              "width_m": 28.96, "width_y_min": 6.82, "width_y_max": 35.78, "depth_m": 15.67, "line_gap_m": 6.67,
              "lines": lines, "n_players_seen": 9}}}
    bad = {**fr, "clip_ms": 1100, "danger": {**fr["danger"], "text": "Man Utd control 30% of the danger zone"},
           "shape": {"away": {**fr["shape"]["away"], "depth_m": 19.0}}}

    def run_on(frames, tmp):
        path = tmp / "always.json"
        path.write_text(_json.dumps({"result": {"frames": frames}}))
        (row,) = v7_always({"x": {"kind": "always_on", "always": str(path), "t0": 0.0, "t1": 2.0}})
        return row

    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp())
    assert run_on([fr], tmp)["numbers_bound"] == run_on([fr], tmp)["numbers"] == 4
    row = run_on([bad], tmp)
    assert row["numbers"] - row["numbers_bound"] == 2 and any("28%" in d for d in row["diff"])
