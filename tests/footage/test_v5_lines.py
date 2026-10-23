"""Video v5 lines (real-data xG): the comparison is on the shown values, offside receivers are no option, a goal
gets the xG of the shot he scored. Committed files only, no model call."""

from footage.v4_lines import BETTER, CLOSE, FINISH, SHOT_ONLY
from footage.v5_lines import compare, facts_for, offside, xg


def test_shown_values_and_the_close_call_margin():
    assert (xg(0.0199), xg(0.3014), xg(0.1)) == ("0.02", "0.30", "0.10")
    assert compare(0.0635, 0.1137) == BETTER and compare(0.0199, 0.0327) == CLOSE and compare(0.05, 0.06) == CLOSE


def test_offside_receiver_is_left_out():
    facts, view = facts_for("liverpool-mancity-2526", 875000)
    assert view["excluded_offside"] == ["L5"] and view["alternative"]["label"] == "L4"
    assert view["verdict"] == CLOSE and {f["role"]: f["display"] for f in facts}["alternative"] == "0.03"
    m = {"home_attacks": "+x", "ball": {"x": 79.27}, "players": [
        {"team": "away", "x": 101.8, "source": "tracking"}, {"team": "away", "x": 89.99, "source": "tracking"}]}
    assert offside(m, "home", 90.42) == 0.43 and offside(m, "home", 86.32) < 0


def test_a_goal_gets_the_xg_of_the_shot_he_scored():
    facts, view = facts_for("manutd-mancity-2526", 1189840)
    assert view["verdict"] == FINISH and view["alternative"] is None
    assert facts[0]["display"] == "0.48" and "strike" in facts[0]["label"]       # 0.30 where he stood at the freeze
    facts, view = facts_for("manutd-spurs-2425", 682800)
    assert view["verdict"] == SHOT_ONLY and facts[0]["display"] == "0.08"         # the reviewed strike, not 0.04
