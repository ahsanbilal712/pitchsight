"""Ghost defender on a real goal (video v3): which defender's position mattered most, and how much the goal chance
falls if he had reached the best spot he could in the time available.

The engine values a shot as FINISH * xg(distance, angle, cone) (kickoff `_kick_shot`), where `cone` counts the
opponents inside the triangle between the shooter and the posts. So a defender changes the chance by being in that
cone. For every defender not in it, the nearest point inside the cone (a margin in from its edge) is how far he had
to move from where he was `t_avail_s` before the shot; he could get there at TOP_SPEED_MS. The defender who could
make it with the least ground to cover is the one whose position mattered most; the shot is re-valued with him there
(the formula, and n forced-shot rollouts of the engine as a check).
"""

from __future__ import annotations

import math

import numpy as np

from footage.freeze import PITCH_L, PITCH_W

TOP_SPEED_MS = 7.0
MARGIN_M = 0.4
GRID_M = 0.25


def _frame(moment: dict, team: str) -> tuple[bool, callable]:
    """(team attacks +x in the file, mapping (x, y) -> team frame (u, v) with the attacked goal at u = 105)."""
    plus = (moment["home_attacks"] == "+x") == (team == "home")
    return plus, (lambda x, y: (x, y) if plus else (PITCH_L - x, PITCH_W - y))


def shot_value(moment: dict, shooter_label: str, override: dict[str, tuple[float, float]] | None = None) -> dict:
    """p_goal of a shot by `shooter_label` from where he stands, with optional moved opponents {label: (x, y)}."""
    from kickoff.engine import FINISH
    from kickoff.physics_prior import cone_count, goal_angle, goal_distance, xg

    players = {p["label"]: p for p in moment["players"] if p.get("label")}
    s = players[shooter_label]
    _, tf = _frame(moment, s["team"])
    u, v = tf(s["x"], s["y"])
    opp = [p for p in moment["players"] if p["team"] != s["team"]]
    pos = [(override or {}).get(p.get("label"), (p["x"], p["y"])) for p in opp]
    ou, ov = np.array([tf(x, y)[0] for x, y in pos]), np.array([tf(x, y)[1] for x, y in pos])
    cone = cone_count(u, v, ou, ov)
    dist, ang = float(goal_distance(u, v)), float(goal_angle(u, v))
    return {"p_goal": round(FINISH * float(xg(dist, ang, cone)), 4), "cone": int(cone), "distance_m": round(dist, 1)}


def cone_points(moment: dict, shooter_label: str) -> np.ndarray:
    """Grid points (file coordinates) inside the shooting cone, MARGIN_M in from its edges."""
    from kickoff.physics_prior import GOAL_HALF, GOAL_Y

    s = next(p for p in moment["players"] if p.get("label") == shooter_label)
    plus, tf = _frame(moment, s["team"])
    u0, v0 = tf(s["x"], s["y"])
    us, vs = np.meshgrid(np.arange(0, PITCH_L, GRID_M), np.arange(0, PITCH_W, GRID_M))
    a = np.arctan2(GOAL_Y + GOAL_HALF - v0, PITCH_L - u0)
    b = np.arctan2(GOAL_Y - GOAL_HALF - v0, PITCH_L - u0)
    ang = np.arctan2(vs - v0, us - u0)
    d = np.hypot(us - u0, vs - v0)
    lo, hi = min(a, b), max(a, b)
    margin = MARGIN_M / np.maximum(d, 1e-6)
    inside = (us > u0) & (d < math.hypot(PITCH_L - u0, GOAL_Y - v0)) & (ang >= lo + margin) & (ang <= hi - margin)
    pts = np.c_[us[inside], vs[inside]]
    return pts if plus else np.c_[PITCH_L - pts[:, 0], PITCH_W - pts[:, 1]]


def ghost(moment: dict, shooter_label: str, earlier: dict[str, tuple[float, float]], t_avail_s: float) -> dict:
    """The defender who needed the least ground to get into the cone, the metres, whether he could in t_avail_s,
    and the shot value before and after. `earlier` = {label: (x, y)} of the defenders t_avail_s before the shot."""
    before = shot_value(moment, shooter_label)
    s = next(p for p in moment["players"] if p.get("label") == shooter_label)
    pts = cone_points(moment, shooter_label)
    options = []
    for p in moment["players"]:
        if p["team"] == s["team"] or not p.get("label") or p.get("slot") == "GK" or p["label"] not in earlier:
            continue
        if _in_cone(pts, (p["x"], p["y"])):
            continue                                  # already in the cone
        ex, ey = earlier[p["label"]]
        d = np.hypot(pts[:, 0] - ex, pts[:, 1] - ey)
        k = int(np.argmin(d))
        options.append({"label": p["label"], "name": p.get("name"), "from": [round(ex, 2), round(ey, 2)],
                        "to": [round(float(pts[k, 0]), 2), round(float(pts[k, 1]), 2)], "metres": round(float(d[k]), 1),
                        "reach_m": round(TOP_SPEED_MS * t_avail_s, 1)})
    options.sort(key=lambda o: o["metres"])
    if not options:
        return {"before": before, "ghost": None}
    g = options[0]
    after = shot_value(moment, shooter_label, {g["label"]: tuple(g["to"])})
    return {"before": before, "after": after, "ghost": {**g, "reachable": g["metres"] <= g["reach_m"]},
            "drop_p_goal": round(before["p_goal"] - after["p_goal"], 4), "alternatives": options[1:4],
            "t_avail_s": t_avail_s, "top_speed_ms": TOP_SPEED_MS}


def _in_cone(pts: np.ndarray, xy: tuple[float, float]) -> bool:
    return bool(len(pts)) and float(np.min(np.hypot(pts[:, 0] - xy[0], pts[:, 1] - xy[1]))) <= GRID_M


def rollout_check(moment: dict, shooter_label: str, moved: dict[str, tuple[float, float]] | None, n: int = 200,
                  seed: int = 9002) -> float:
    """p_goal of the shooter's team from n forced-shot engine rollouts (2 s), with opponents optionally moved."""
    from footage.freeze import to_state
    from kickoff import Override
    from kickoff.rules import Action
    from rollout.core import rollout

    m = {**moment, "players": [dict(p, **({"x": moved[p["label"]][0], "y": moved[p["label"]][1]}
                                          if moved and p.get("label") in moved else {}))
                               for p in moment["players"]]}
    m["ball"] = {**m["ball"], "holder": shooter_label}
    team = next(p["team"] for p in m["players"] if p.get("label") == shooter_label)
    fut = rollout(to_state(m, seed=seed), Override(first_action=Action(kind="shoot")), n, 2.0, seed, events=[])
    return round(float(fut.outcome()[f"p_goal_{team}"]), 4)
