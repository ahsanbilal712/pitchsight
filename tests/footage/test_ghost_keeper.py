"""Ghost defender and keeper coverage (video v3) on synthetic positions."""

import pytest

from footage.ghost import ghost, rollout_check, shot_value
from footage.keeper import assess, best_on_bisector, bisector_point, coverage


def moment():
    players = [{"team": "home", "label": "#19", "slot": None, "x": 92.0, "y": 30.0, "vx": 0, "vy": 0},
               {"team": "away", "label": "GK", "slot": "GK", "x": 103.0, "y": 34.0, "vx": 0, "vy": 0},
               {"team": "away", "label": "#3", "slot": None, "x": 92.0, "y": 24.0, "vx": 0, "vy": 0},
               {"team": "away", "label": "#5", "slot": None, "x": 80.0, "y": 45.0, "vx": 0, "vy": 0}]
    return {"slug": "manutd-mancity-2526", "match_id": "m_9002", "clip_ms": 1, "t_ms": 3_880_000, "period": 2,
            "clock": "64:40", "score": [0, 0], "home_attacks": "+x", "players": players,
            "ball": {"x": 92.0, "y": 30.0, "holder": "#19"}}


def test_shot_value_drops_with_a_defender_in_the_cone():
    m = moment()
    open_ = shot_value(m, "#19")
    blocked = shot_value(m, "#19", {"#3": (97.0, 32.0)})
    assert blocked["cone"] == open_["cone"] + 1 and blocked["p_goal"] < open_["p_goal"]


def test_ghost_picks_the_defender_with_least_ground_and_checks_the_reach():
    m = moment()
    g = ghost(m, "#19", {"#3": (92.0, 24.0), "#5": (80.0, 45.0)}, t_avail_s=1.0)
    assert g["ghost"]["label"] == "#3" and g["ghost"]["metres"] < 8 and g["drop_p_goal"] > 0
    assert g["ghost"]["reachable"] == (g["ghost"]["metres"] <= 7.0)
    assert g["after"]["cone"] == g["before"]["cone"] + 1


def test_rollout_check_agrees_in_direction():
    m = moment()
    g = ghost(m, "#19", {"#3": (92.0, 24.0), "#5": (80.0, 45.0)}, t_avail_s=1.0)
    assert rollout_check(m, "#19", {g["ghost"]["label"]: tuple(g["ghost"]["to"])}, n=200) <= \
        rollout_check(m, "#19", None, n=200)


def test_keeper_on_the_bisector_covers_more_than_off_it():
    shooter, gx = (88.0, 40.0), 105.0
    on = bisector_point(shooter, gx, 2.0)
    assert coverage(shooter, on, gx) > coverage(shooter, (104.5, 30.0), gx)
    best = best_on_bisector(shooter, gx)
    assert 0 < best["coverage"] <= 1 and 0.3 <= best["depth_m"] <= 8
    a = assess(shooter, (104.5, 30.0), gx)
    assert a["best"]["coverage"] >= a["actual_coverage"] and a["move_m"] > 0
    assert a["assumptions"]["shot_speed_ms"] == pytest.approx(26.0)
