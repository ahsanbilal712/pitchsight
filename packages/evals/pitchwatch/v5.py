"""Video v5 beats (track A): real-data xG on screen, one formula everywhere.

    python -m evals.pitchwatch.v5 gate          # benchmark check of the reference model
    python -m evals.pitchwatch.v5 decisions     # featured freezes: the shot taken vs xG after each pass
    python -m evals.pitchwatch.v5 xray          # Man Utd v Spurs 240-242.5 s, every 0.5 s
    python -m evals.pitchwatch.v5 shots         # shots_<slug> + xg_race_<slug>

Shot xG = the published reference model (Soccermatics' combined logistic fit on 8,451 non-penalty Premier League
2017/18 shots, Wyscout; evals.pitchwatch.shotxg.reference_xg) at the shooter's spot from tracking. Penalties: 0.76,
Wyscout's fixed value (https://dataglossary.wyscout.com/xg/), consistent with the reference's data source.

xG after a pass = P(pass completes) x reference xG of a shot from the receiver's spot when the pass is played:
P(complete) from our pass model (heads.models.PassHead) on the tracked positions. Projecting the receiver along his
run for the ball's flight time was tried and dropped: it carried runners to the goal line (0.8+ xG, outside the
six-yard benchmark) and once off the pitch, so it adds extrapolation error, not accuracy. Deterministic: no
rollouts, no n or seed.

Coordinates: the moment-file frame (x 0-105 from the left goal line, y from the near touchline). Only players seen
in the frame count (role-prior fills are guesses and are left out), so an opponent off-camera does not block a lane.
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import numpy as np

from evals.pitchwatch.shotxg import CLIPS, reference_xg

L, W, GOAL_Y = 105.0, 68.0, 34.0
PENALTY_XG = 0.76
OFFSIDE_ERROR_M = 0.5          # tracking error: a receiver within this of the line may be offside
CLOSE_CALL_XG = 0.02           # display rule: gaps under two display steps are a close call (no interval exists)
RUN_S = 1.0                    # run arrows: the receiver's tracked spot this long after the freeze
BENCH = [("six-yard box, central (6 m)", 6.0, 0.0, 0.30, 0.50), ("penalty spot, open play (11 m)", 11.0, 0.0, 0.12, 0.30),
         ("edge of the box, central (16.5 m)", 16.5, 0.0, 0.06, 0.12), ("30 m, central", 30.0, 0.0, 0.02, 0.04)]
SOURCE = ("xG = Soccermatics' logistic fit on 8,451 PL 2017/18 shots (Wyscout); after a pass = P(complete, our pass "
          "model) x that xG from the receiver's spot when the pass is played")


def gate() -> dict:
    rows = [{"where": n, "x_m": x, "c_m": c, "xg": round(reference_xg(x, c), 3), "range": [lo, hi],
             "ok": lo <= reference_xg(x, c) <= hi} for n, x, c, lo, hi in BENCH]
    rows.append({"where": "penalty kick", "xg": PENALTY_XG, "range": [0.70, 0.80], "ok": True,
                 "note": "fixed value (Wyscout), not the open-play model"})
    return {"benchmarks": rows, "passed": all(r["ok"] for r in rows)}


def team_frame(xy, attacks_plus: bool) -> tuple[float, float]:
    return (xy[0], xy[1]) if attacks_plus else (L - xy[0], W - xy[1])


def shot_xg(u: float, v: float) -> float | None:
    """None in the team's own half: the fit has no shots there and its quadratic term turns the curve back up (0.05
    at 91 m), so no value is shown rather than an extrapolated one."""
    return reference_xg(L - u, abs(v - GOAL_Y)) if u >= L / 2 else None


def options_xg(holder: dict, mates: list[dict], opps: list[dict], attacks_plus: bool) -> list[dict]:
    """holder/mates/opps: {label, x, y, vx, vy} in the moment frame. Returns per mate the formula's pieces."""
    import pandas as pd

    from evals.pitchwatch.insights import control
    from heads.models import PassHead

    def tf(p):
        return team_frame((p["x"], p["y"]), attacks_plus)
    u0, v0 = tf(holder)
    ou = np.array([tf(p)[0] for p in opps]) if opps else np.zeros(0)
    ov = np.array([tf(p)[1] for p in opps]) if opps else np.zeros(0)
    players = [(*tf(p), 0) for p in [holder, *mates]] + [(*tf(p), 1) for p in opps]
    rows, meta = [], []
    for m in mates:
        u, v = tf(m)
        length = math.hypot(u - u0, v - v0)
        seg = np.array([u - u0, v - v0])
        s = np.clip(((np.stack([ou, ov], 1) - [u0, v0]) @ seg) / max(float(seg @ seg), 1e-9), 0, 1) if len(ou) else []
        lane = np.hypot(ou - (u0 + s * seg[0]), ov - (v0 + s * seg[1])) if len(ou) else np.zeros(0)
        rows.append({"length_m": length, "angle_rad": math.atan2(v - v0, u - u0), "lofted": int(length > 32),
                     "under_pressure": int(len(ou) > 0 and float(np.min(np.hypot(ou - u0, ov - v0))) < 2.5),
                     "receiver_space": float(control(players, np.array([[u, v]]), 0)[0]),
                     "progressive_m": u - u0, "opponents_in_lane": int(np.sum(lane < 2.0)), "start_u": u0,
                     "nearest_opp_m": float(np.min(np.hypot(ou - u0, ov - v0))) if len(ou) else 30.0})
        meta.append((m, 0.0, u, v))           # his spot when the pass is played (no run projection, see docstring)
    p = PassHead().predict(pd.DataFrame(rows)) if rows else []
    deep = sorted(ou, reverse=True)
    line_u = max(deep[1] if len(deep) > 1 else (deep[0] if len(deep) else L / 2), u0, L / 2)
    out = []
    for (m, _t, ua, va), pc in zip(meta, p, strict=True):
        xa = shot_xg(min(ua, L - 0.5), va)
        if xa is None:
            out.append({"label": m.get("label"), "name": m.get("name"), "x": m["x"], "y": m["y"],
                        "p_pass": round(float(pc), 2), "xg_receiver": None, "gate": None,
                        "onside_margin_m": None, "offside_risk": False, "xg_after_pass": None,
                        "xg_after_pass_exact": None, "xg_note": "receiver in his own half: outside the model's range"})
            continue
        out.append({"label": m.get("label"), "name": m.get("name"), "x": m["x"], "y": m["y"],
                    "p_pass": round(float(pc), 2), "xg_receiver": round(xa, 2),
                    "gate": gate_value(xa, L - min(ua, L - 0.5), abs(va - GOAL_Y)),
                    "onside_margin_m": round(line_u - ua, 2),
                    "offside_risk": bool(line_u - ua < OFFSIDE_ERROR_M),
                    "xg_after_pass": round(float(pc) * xa, 2), "xg_after_pass_exact": round(float(pc) * xa, 4)})
    return sorted(out, key=lambda o: -(o["xg_after_pass_exact"] if o["xg_after_pass_exact"] is not None else -1))


def linked_shot(slug: str, clip_ms: int, team: str) -> dict:
    """The tagged shot this freeze leads to (same team, within 4 s after): its event, reviewed strike time and
    outcome, from data/footage/insights/shots_xg.json. Empty when none is linked."""
    from evals.pitchwatch.insights import FOOTAGE
    path = FOOTAGE / "insights" / "shots_xg.json"
    if not path.exists():
        return {}
    cand = [r for r in json.loads(path.read_text())["shots"] if r["slug"] == slug and r["team"] == team
            and -1000 <= r["clip_ms"] - clip_ms <= 4000]
    if not cand:
        return {}
    r = min(cand, key=lambda r: abs(r["clip_ms"] - clip_ms))
    strike_xg = None
    if r.get("measured") and not r.get("header") and r.get("xg_reference") is not None:
        strike_xg = round(r["xg_reference"], 2)
    return {"event_id": r["event_id"], "outcome": r["outcome"], "strike_xg": strike_xg,
            "strike_distance_m": r.get("features", {}).get("distance_m"),
            "strike_clip_ms": r.get("release_clip_ms") if r.get("measured") else None,
            "strike_reviewed": bool(r.get("reviewed")) if r.get("measured") else False}


def run_to(slug: str, m: dict, track_id: int | None) -> list[float] | None:
    """The player's tracked spot RUN_S after the freeze (same camera shot, moment-file frame), for the run arrow
    only; None where the track breaks or switches to another man, the camera fit is not trusted there, or the shot
    ends first."""
    from evals.pitchwatch.insights import FOOTAGE
    if track_id is None or not m.get("tracking"):
        return None
    tracks = json.loads((FOOTAGE / slug / "tracks" / f"{m['tracking']['shot_id']}.json").read_text())
    target = m["tracking"]["frame"] + round(RUN_S * tracks["fps"])
    r = min(tracks["frames"], key=lambda f: abs(f["frame"] - target))
    if abs(r["frame"] - target) > tracks["step"] or not r["calib_ok"]:
        return None
    p = next((p for p in r["players"] if p["track_id"] == track_id and p.get("xy")), None)
    from evals.pitchwatch.v6 import identity_span
    span = identity_span(tracks["frames"], track_id, m["tracking"]["frame"] / tracks["fps"])
    if p is None or span is None or not span[0] <= r["t"] <= span[1]:   # the id switched to another man
        return None
    return [round(p["xy"][0], 2), round(W - p["xy"][1], 2)]


def decision(slug: str, clip_ms: int) -> dict:
    from footage.freeze import load
    m = load(slug, clip_ms)
    holder_label = m["ball"]["holder"]
    seen = [p for p in m["players"] if p.get("source") != "prior"]
    holder = next(p for p in seen if p.get("label") == holder_label)
    team = holder["team"]
    attacks_plus = (m["home_attacks"] == "+x") == (team == "home")
    mates = [p for p in seen if p["team"] == team and p is not holder and p.get("slot") != "GK"]
    opps = [p for p in seen if p["team"] != team]
    u0, v0 = team_frame((holder["x"], holder["y"]), attacks_plus)
    shot = shot_xg(u0, v0)
    opts = options_xg(holder, mates, opps, attacks_plus)
    by_label = {p.get("label"): p for p in mates}
    for o in opts:
        o["run_to"] = run_to(slug, m, by_label[o["label"]].get("track_id"))
    best = next((o for o in opts if not o["offside_risk"] and o["xg_after_pass"] is not None), None)
    strike = linked_shot(slug, clip_ms, team)
    return {"clip_ms": clip_ms, "clock": m["clock"], "team": team, "holder": holder_label,
            "holder_name": holder.get("name"),
            "actual": {"kind": m["actual"]["kind"], "label": "Shot" if m["actual"]["kind"] == "shoot" else m["actual"]["kind"],
                       "xg": round(shot, 2) if m["actual"]["kind"] == "shoot" else None,
                       "xg_exact": round(shot, 4) if m["actual"]["kind"] == "shoot" else None,
                       "distance_m": round(math.hypot(L - u0, v0 - GOAL_Y), 1), "x": holder["x"], "y": holder["y"],
                       **strike},
            "alternatives": opts, "best_alternative": best,
            "comparison": None if not best or m["actual"]["kind"] != "shoot" else
            ("close call" if abs(best["xg_after_pass_exact"] - shot) < CLOSE_CALL_XG else
             "pass higher" if best["xg_after_pass_exact"] > shot else "shot higher"),
            "comparison_rule": f"no statistical interval exists for these deterministic models; a gap under "
                               f"{CLOSE_CALL_XG} xG (two display steps) is reported as a close call",
            "frame_role": "freeze: the decision moment (track B's moment file), before the strike",
            "run_s": RUN_S, "run_rule": f"run_to = the receiver's tracked spot {RUN_S} s after the freeze (same camera "
                                        "shot); drawn as an arrow only, not part of any number; null where the track breaks",
            "best_rule": f"highest xg_after_pass among receivers at least {OFFSIDE_ERROR_M} m onside of the line "
                         "(second-last defender, ball or halfway, players in view)",
            "formula": SOURCE, "deterministic": True, "players_seen": len(seen),
            "source": {"moment": f"{slug}/moments/{clip_ms}.json", "pass_model": "packages/heads/artifacts/pass",
                       "shot_model": "evals.pitchwatch.shotxg.reference_xg"}}


def xray(slug: str = "manutd-spurs-2425", t0: float = 240.0, t1: float = 242.0) -> dict:
    from evals.pitchwatch.shotxg import HOME_ATTACKS_P2
    from evals.pitchwatch.v4 import tracked_moment

    samples = []
    for t in np.arange(t0, t1 + 1e-9, 0.5):
        clip_ms = int(round(t * 1000))
        m = tracked_moment(slug, clip_ms, "02:13", 1, [0, 0])
        if m is None:
            samples.append({"clip_ms": clip_ms, "holder": None, "note": "ball loose (no player within 2.5 m)"})
            continue
        holder = next(p for p in m["players"] if p.get("label") == m["ball"]["holder"])
        team = holder["team"]
        home_plus = HOME_ATTACKS_P2[slug] * (1 if m["period"] == 2 else -1) > 0
        attacks_plus = home_plus == (team == "home")
        seen = [p for p in m["players"] if p.get("source") != "prior"]
        mates = [p for p in seen if p["team"] == team and p is not holder]
        opps = [p for p in seen if p["team"] != team]
        u0, v0 = team_frame((holder["x"], holder["y"]), attacks_plus)
        samples.append({"clip_ms": clip_ms, "holder": holder["label"], "team": team,
                        "holder_xy": [holder["x"], holder["y"]], "shoot_now_xg": None if shot_xg(u0, v0) is None else round(shot_xg(u0, v0), 2),
                        "options": options_xg(holder, mates, opps, attacks_plus)})
    return {"slug": slug, "samples": samples, "formula": SOURCE, "deterministic": True,
            "source": {"tracks": f"{slug}/tracks/23.json", "calib": f"{slug}/calib/23.json"}}


def gate_value(xg: float, x_m: float, c_m: float) -> str | None:
    """Benchmark check of one on-screen shot value by where it is taken (None = within or no band). The six-yard
    band applies to central shots (within 5.5 m of the goal's centre line): a tight-angle shot from the byline is
    in the six-yard box but is not the shot the benchmark describes."""
    d = math.hypot(x_m, c_m)
    for name, lo, hi, cond in (("six-yard box, central", 0.30, 0.50, x_m <= 5.5 and c_m <= 5.5),
                               ("edge of the box", 0.06, 0.12, 15.0 <= d <= 18.0 and c_m <= 8.0),
                               ("30 m+", 0.0, 0.04, d >= 30.0)):
        if cond and not lo <= xg <= hi:
            return f"{xg:.2f} outside the {name} band {lo:.2f}-{hi:.2f} at {d:.1f} m"
    return None


def shots_beats() -> list[Path]:
    from evals.pitchwatch.insights import FOOTAGE
    from evals.pitchwatch.v3 import write
    doc = json.loads((FOOTAGE / "insights" / "shots_xg.json").read_text())
    model = {"xg": "Soccermatics combined logistic model, 8,451 non-penalty PL 2017/18 shots (Wyscout), at the strike "
                   "point from tracking", "penalty": f"{PENALTY_XG} (Wyscout's fixed penalty value)",
             "url": "https://soccermatics.readthedocs.io/en/latest/gallery/lesson2/plot_xGModelFit.html"}
    outs = []
    for slug in CLIPS:
        names = json.loads((FOOTAGE / slug / "names_verified.json").read_text()).get("shots", {})
        teams = json.loads((FOOTAGE / slug / "teams.json").read_text())["teams"]
        shots = []
        for r in (x for x in doc["shots"] if x["slug"] == slug):
            nm = names.get(r["event_id"], {})
            penalty = bool(re.search(r"\bpenalt(y|ies)\b(?!\s+(area|box))", (r.get("note") or "").lower()))
            row = {"event_id": r["event_id"], "clock": r["clock"], "team": r["team"],
                   "team_name": teams[0 if r["team"] == "home" else 1]["name"],
                   "shooter": {"label": r.get("shooter_label") or (f"t{r['shooter_track']}" if r.get("shooter_track")
                                                                  is not None else None),
                               "name": nm.get("name"), "name_source": nm.get("source")},
                   "outcome": r["outcome"] if r["outcome"] != "off_target" else "wide", "goal": r["goal"],
                   "disallowed": r.get("disallowed"), "penalty": penalty}
            if penalty:
                row.update({"clip_ms": r["clip_ms"], "xg": PENALTY_XG, "camera_ok": False, "x": None, "y": None,
                            "source": {"event": r["event_id"], "xg": "penalty constant"}})
            elif r.get("measured") and r["header"]:
                row.update({"clip_ms": r["release_clip_ms"], "xg": None, "camera_ok": True, "header": True,
                            "x": r["shooter_xy_near"][0], "y": r["shooter_xy_near"][1],
                            "reason": "header: the published model has no body-part term and overstates headers "
                                      "(a 3.8 m header came out 0.55, above the six-yard benchmark), so no xG is shown",
                            "source": {"event": r["event_id"]}})
            elif r.get("measured"):
                x_m = L - (r["shooter_xy_near"][0] if (r["team"] == "home") == _home_plus(slug, r) else
                           L - r["shooter_xy_near"][0])
                c_m = abs(r["shooter_xy_near"][1] - GOAL_Y)
                xg = round(r["xg_reference"], 2)
                row.update({"clip_ms": r["release_clip_ms"], "frame": r.get("release_frame"), "camera_ok": True,
                            "shot_id": r["camera_shot"], "x": r["shooter_xy_near"][0], "y": r["shooter_xy_near"][1],
                            "distance_m": round(math.hypot(x_m, c_m), 1), "xg": xg, "header": r["header"],
                            "set_piece": r.get("set_piece"), "reviewed": r["reviewed"],
                            "gate": gate_value(r["xg_reference"], x_m, c_m),
                            "source": {"event": r["event_id"],
                                       "position": r.get("spot_source") or f"{slug}/tracks/x{r['event_id']}.json",
                                       "calib": None if r.get("spot_source") else f"{slug}/calib/x{r['event_id']}.json"}})
            else:
                row.update({"clip_ms": r["clip_ms"], "xg": None, "camera_ok": False, "reason": r.get("reason"),
                            "source": {"event": r["event_id"]}})
            shots.append(row)
        shots.sort(key=lambda x: x["clip_ms"])
        outs.append(write(slug, "shots", 0, {"shots": shots, "model": model, "decimals": 2,
                                             "frame_role": "strike: the reviewed frame the ball is struck (or the "
                                                           "named moment file where stated in source.position)",
                                             "note": "xg null where the strike has no trusted wide view (and it is not "
                                                     "a penalty); names only from names_verified.json"}, version="v5"))
        cum = {"home": 0.0, "away": 0.0}
        series, events = [], []
        for r in shots:
            if r["xg"] is not None:
                cum[r["team"]] += r["xg"]
            series.append({"clip_ms": r["clip_ms"], "clock": r["clock"], "home_xg": round(cum["home"], 2),
                           "away_xg": round(cum["away"], 2)})
            events.append({"clip_ms": r["clip_ms"], "clock": r["clock"], "team": r["team"],
                           "kind": "goal" if r["goal"] else ("disallowed" if r.get("disallowed") else "shot"),
                           "label": r["shooter"]["name"], "xg": r["xg"], "measured": r["xg"] is not None})
        un = [e for e in events if not e["measured"]]
        outs.append(write(slug, "xg_race", 0, {"home": teams[0]["name"], "away": teams[1]["name"], "series": series,
                                               "events": events, "model": model,
                                               "unmeasured": {"shots": len(un), "goals": sum(e["kind"] == "goal" for e in un)},
                                               "note": "cumulative xG of measured shots and penalties; shots without a "
                                                       "trusted wide view are listed with xg null and add nothing"},
                          version="v5"))
    return outs


def _home_plus(slug: str, r: dict) -> bool:
    from evals.pitchwatch.shotxg import HOME_ATTACKS_P2
    period = 2 if int(r["clock"].split(":")[0]) >= 45 else 1
    return HOME_ATTACKS_P2[slug] * (1 if period == 2 else -1) > 0


def ghost(slug: str, clip_ms: int) -> dict:
    """Track C's ghost_future for the v5 decision's better pass: the medoid (by ball path) of v4's N rollouts after
    that pass, every player and the ball each engine tick (10 Hz), moment-file frame. Same seeds as v4, so it is
    v4's world when v4 chose the same pass."""
    from evals.pitchwatch.insights import FOOTAGE
    from evals.pitchwatch.v4 import HORIZON_S, SEED, N, _branch, wilson
    from footage.freeze import load, to_state
    from kickoff.engine import TICK_MS

    dec = json.loads((FOOTAGE / slug / "cache" / "v5" / f"xg_decision_{clip_ms}.json").read_text())["result"]
    assert dec["comparison"] == "pass higher", "a ghost is drawn only for a better pass"
    best = dec["best_alternative"]
    spec = {"kind": "pass", "target": best["label"]}
    moment = load(slug, clip_ms)
    state = to_state(moment, seed=SEED)
    names = {p.get("label"): p.get("name") for p in moment["players"] if p.get("label")}
    b = _branch(state, moment, spec, N, SEED)
    inv = {row: lab for lab, row in state.labels.items()}
    P = b["paths"]
    frames = [{"t_ms": i * TICK_MS, "ball": [round(float(P[i, 22, 0]), 2), round(float(P[i, 22, 1]), 2)],
               "players": [{"label": inv.get(r), "name": names.get(inv.get(r)), "team": "home" if r < 11 else "away",
                            "x": round(float(P[i, r, 0]), 2), "y": round(float(P[i, r, 1]), 2)} for r in range(22)]}
              for i in range(P.shape[0])]
    scored = bool(b["goals"][b["world"]])
    k = int(b["goals"].sum())
    return {"clip_ms": clip_ms, "clock": dec["clock"], "branch": "alternative", "option": spec,
            "label": f"Pass to {best.get('name') or best['label']}", "xg_after_pass": best["xg_after_pass"],
            "step_ms": TICK_MS, "horizon_s": HORIZON_S, "frames": frames,
            "outcome": {"label": "goal" if scored else "no goal within 10 s", "at_ms": None}, "scored": scored,
            "share_of_worlds_scoring": round(k / N, 4), "share_ci95": wilson(k, N),
            "n": N, "seed": SEED, "engine": "scripted_v1", "attack": moment["home_attacks"] + " (home)",
            "representative": {"which": "medoid", "world": b["world"], "world_seed": SEED + b["world"]},
            "note": "The most typical of the n simulated futures (medoid by ball path), not the likeliest outcome; "
                    "players without a label were placed by role prior at the freeze. The on-screen number for "
                    "this pass stays the xG after the pass (xg_decision); the ghost is a picture of one future.",
            "source": {"decision": f"{slug}/cache/v5/xg_decision_{clip_ms}.json",
                       "moment": f"{slug}/moments/{clip_ms}.json"}}


def main(argv: list[str] | None = None) -> int:
    from evals.pitchwatch.v3 import write
    from evals.pitchwatch.v4 import DECISION_MOMENTS
    kind = (argv or sys.argv[1:])[0]
    if kind == "gate":
        print(json.dumps(gate(), indent=1))
    elif kind == "decisions":
        for slug, moments in DECISION_MOMENTS.items():
            for clip_ms in moments:
                print(write(slug, "xg_decision", clip_ms, decision(slug, clip_ms), version="v5"))
    elif kind == "shots":
        print(*shots_beats(), sep="\n")
    elif kind == "ghost":
        slug, clip_ms = (argv or sys.argv[1:])[1], int((argv or sys.argv[1:])[2])
        print(write(slug, "ghost_future", clip_ms, ghost(slug, clip_ms), version="v5"))
    elif kind == "xray":
        print(write("manutd-spurs-2425", "pass_xray_xg", 240000, xray(), version="v5"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
