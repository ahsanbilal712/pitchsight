"""Video v5 lines (real-data xG), lead's rules: every shot at its reviewed strike; a pass only when it is worth at
least 0.04 xG more and the receiver is more than 0.5 m onside, else the beat is shot-only. Committed files only."""

from footage.v4_lines import BETTER, FINISH, SHOT_ONLY
from footage.v5_lines import compare, facts_for, metres, offside, xg


def test_shown_values_and_the_lead_margin():
    assert (xg(0.0199), xg(0.3014), xg(0.1)) == ("0.02", "0.30", "0.10")
    assert (metres(28.82), metres(4.482), metres(16.4)) == ("29 m", "4.5 m", "16 m")
    assert compare(0.07, {"xg_after_pass": 0.11, "onside_margin_m": 0.75}) == BETTER
    assert compare(0.07, {"xg_after_pass": 0.11, "onside_margin_m": 0.4}) == SHOT_ONLY      # not clearly onside
    assert compare(0.02, {"xg_after_pass": 0.03, "onside_margin_m": 3.7}) == SHOT_ONLY      # 0.01: no pass shown


def test_liverpool_and_arsenal_are_shot_only_at_the_strike():
    facts, view = facts_for("liverpool-mancity-2526", 875000)
    assert view["verdict"] == SHOT_ONLY and view["alternative"] is None and "L5" in view["excluded_offside"]
    assert {f["role"]: f["display"] for f in facts} == {"actual": "0.02", "distance": "29 m"}
    facts, view = facts_for("arsenal-chelsea-2526", 1300500)
    assert view["verdict"] == SHOT_ONLY and facts[0]["display"] == "0.08"         # 0.05 where he stood at the freeze


def test_amad_pass_and_the_goals():
    facts, view = facts_for("manutd-mancity-2526", 877000)
    assert view["verdict"] == BETTER and view["alternative"]["label"] == "#19"
    assert [f["display"] for f in facts if f["role"] in ("actual", "alternative")] == ["0.07", "0.11"]
    facts, view = facts_for("manutd-mancity-2526", 1189840)
    assert view["verdict"] == FINISH and facts[0]["display"] == "0.48"             # 0.30 at the freeze
    m = {"home_attacks": "+x", "ball": {"x": 79.27}, "players": [
        {"team": "away", "x": 101.8, "source": "tracking"}, {"team": "away", "x": 89.99, "source": "tracking"}]}
    assert offside(m, "home", 90.42) == 0.43 and offside(m, "home", 86.32) < 0
