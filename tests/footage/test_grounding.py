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
    assert r["groups"]["v4 overlay"]["items"] == 9      # six decision cards, the X-ray tags, the Oracle card, ghost footer
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
