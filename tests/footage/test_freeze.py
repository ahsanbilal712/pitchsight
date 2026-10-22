"""Moment freeze (T-107): homography, role-prior fill, a frozen frame becomes a branchable engine state. Synthetic
moments only: CI has no footage."""

import numpy as np
import pytest

from footage.freeze import SLOT_NAMES, apply_h, fill, fit_homography, slot_of, to_state
from kickoff import Override
from kickoff.rules import Action
from rollout.core import rollout

LANDMARKS = [(88.5, 54.16), (105, 54.16), (88.5, 13.84), (99.5, 43.16), (99.5, 24.84), (105, 43.16), (105, 37.66),
             (105, 30.34)]


def camera():
    """A made-up broadcast camera: pitch -> image."""
    return np.array([[18.0, -6.0, 300.0], [2.0, 9.0, 120.0], [0.002, -0.004, 1.0]])


def moment(home_attacks="+x", period=2, n_home=8, n_away=11):
    rng = np.random.default_rng(1)
    players = [{"team": "home", "label": "#8", "slot": None, "x": 78.0, "y": 19.0, "vx": 3.0, "vy": 0.5,
                "source": "hand"},
               {"team": "home", "label": "#11", "slot": None, "x": 87.5, "y": 9.0, "vx": 0.0, "vy": 0.0,
                "source": "hand"}]
    players += [{"team": "home", "label": f"L{i}", "slot": None, "x": float(rng.uniform(70, 90)),
                 "y": float(rng.uniform(25, 55)), "vx": 0.0, "vy": 0.0, "source": "hand"} for i in range(n_home - 2)]
    players += [{"team": "away", "label": "GK", "slot": "GK", "x": 102.0, "y": 32.0, "vx": 0.0, "vy": 0.0,
                 "source": "hand"}]
    players += [{"team": "away", "label": f"C{i}", "slot": None, "x": float(rng.uniform(78, 92)),
                 "y": float(rng.uniform(15, 50)), "vx": 0.0, "vy": 0.0, "source": "hand"} for i in range(n_away - 1)]
    if home_attacks == "-x":
        for p in players:
            p["x"], p["y"], p["vx"], p["vy"] = 105 - p["x"], 68 - p["y"], -p["vx"], -p["vy"]
    ball = {"x": players[0]["x"], "y": players[0]["y"], "holder": "#8"}
    return {"slug": "liverpool-mancity-2526", "match_id": "m_9001", "clip_ms": 875000, "t_ms": 5_183_000,
            "period": period, "clock": "86:23", "score": [1, 1], "home_attacks": home_attacks, "players": players,
            "ball": ball}


def test_homography_recovers_pitch_points():
    pitch_to_image = camera()
    image = apply_h(pitch_to_image, LANDMARKS)
    H, rms = fit_homography(image, LANDMARKS)
    assert rms < 1e-6
    assert np.allclose(apply_h(H, apply_h(pitch_to_image, [(80.0, 20.0)])), [(80.0, 20.0)], atol=1e-6)


def test_fill_gives_eleven_per_team_with_distinct_slots():
    out = fill(moment())
    for team in ("home", "away"):
        mine = [p for p in out["players"] if p["team"] == team]
        assert len(mine) == 11 and sorted(p["slot"] for p in mine) == sorted(SLOT_NAMES)
    prior = [p for p in out["players"] if p["source"] == "prior"]
    assert len(prior) == 3 and {p["slot"] for p in prior if p["team"] == "home"} >= {"GK"}
    gk = next(p for p in out["players"] if p["team"] == "home" and p["slot"] == "GK")
    assert gk["x"] < 10                                     # home attacks +x: its keeper is at its own goal
    assert next(p for p in out["players"] if p["label"] == "#11")["slot"] in ("RW", "RB")   # wide on the right


def test_fill_keeps_hand_set_slots_and_refuses_twelve():
    m = moment()
    m["players"][0]["slot"] = "CF"
    assert next(p for p in fill(m)["players"] if p.get("label") == "#8")["slot"] == "CF"
    with pytest.raises(ValueError):
        fill(moment(n_away=12))


@pytest.mark.parametrize("home_attacks", ["+x", "-x"])
def test_state_puts_the_frame_into_the_engine_convention(home_attacks):
    """Period 2: the engine's home side attacks -x, so a frame with home attacking +x is mirrored."""
    st = to_state(moment(home_attacks))
    assert st.mirrored == (home_attacks == "+x")
    row = st.labels["#8"]
    assert int(st.holder[0]) == row and int(st.possession[0]) == 0
    x = float(st.S[0, row, 0])
    assert x == pytest.approx(105 - 78.0 if home_attacks == "+x" else 105 - 78.0, abs=1e-6)   # 27 m from goal at x=0
    assert np.allclose(st.S[0, 22, 0:2], st.S[0, row, 0:2])
    assert st.t_ms == 5_183_000 and st.period == 2 and list(st.score[0]) == [1, 1]


def test_frozen_state_branches_deterministically():
    st = to_state(moment())
    salah = slot_of(st, "#11")
    a = rollout(st, Override(first_action=Action(kind="pass", target=salah)), 40, 4.0, 7, events=[])
    b = rollout(to_state(moment()), Override(first_action=Action(kind="pass", target=salah)), 40, 4.0, 7, events=[])
    assert a.invalid_reason is None and a.digest() == b.digest()
    base = rollout(st, None, 40, 4.0, 7, decide_now=True, events=[])
    assert 0.0 <= base.outcome()["p_goal_home"] <= 1.0
