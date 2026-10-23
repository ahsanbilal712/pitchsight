"""Video v7: the always-on layer from player positions alone, 10 Hz, over every tracked wide passage
(track C's format, shared notes track-c-v7-formats.md; definitions in track-a-v7-space-format.md).

    python -m evals.pitchwatch.v7 always      # cache/v7/always_<start_clip_ms>.json + always_index_0.json

Per frame, from the v6 live frames' players (same tracking, teams, keepers) and the shot's camera fit, over the part
of the pitch the camera shows (the lead's gate (b)):
- pitch control: P(home controls) on a 2.5 m grid (the repo's time-to-intercept model, insights.control);
- dangerous space in view: each team's xG-weighted share of the dangerous zone in front of the goal in view
  (DANGER_DEF), printed only when that zone is at least 70% in view;
- team shape: the back line whenever the team's four deepest outfield players are provably in view, and the lines,
  width, depth and line gap when at least 9 of its 10 outfield players are.
No ball is needed. Where a gate fails the value is null with the reason: never a guess.
"""

from __future__ import annotations

import base64
import json
import sys

import numpy as np

from evals.pitchwatch.insights import FOOTAGE, control
from evals.pitchwatch.shotxg import reference_xg
from evals.pitchwatch.track import nearest_ok
from evals.pitchwatch.v5 import GOAL_Y, L, W

CLIPS = ("liverpool-mancity-2526", "manutd-mancity-2526", "arsenal-chelsea-2526", "manutd-spurs-2425")
NX, NY = 42, 27                    # control grid: 2.5 m x 2.52 m cells
ZONE_XG = 0.05                     # the dangerous zone: cells where a shot is worth at least this (reference xG)
ZONE_IN_VIEW = 0.70                # the zone must be at least this share in view (by cell count) to print a share
BEHIND_IN_VIEW = 0.85              # back line: the strip behind the deepest outfielder in view must be this visible
BEHIND_HALF_W = 20.16              # m either side of the goal centre: the penalty area's width
OUTFIELD_MIN = 9                   # lines, width, depth, gap: at least this many of a team's 10 outfield players
RUN_GAP = 3                        # always_index runs: bridge gaps of up to this many samples
RUN_MIN_S = 2.0                    # and keep runs at least this long
RUN_PCT = 0.90
CONTROL_MODEL = ("time-to-intercept pitch control (insights.control, from physics.pitch_control; simplified Spearman "
                 "2018): each player in view reaches a point after a 0.7 s reaction then at 5 m/s; a team's control "
                 "is its softmin share of the arrival times; positions only, no ball travel time")
DANGER_DEF = ("Dangerous space in view: the dangerous zone is every cell in front of the goal in view from which a "
              f"shot is worth at least {ZONE_XG} xG (Soccermatics' logistic fit on 8,451 PL 2017/18 Wyscout shots, as "
              "in v5/v6). Each team's share = sum over the zone's cells in view of its pitch control x that cell's xG, "
              "divided by the sum of the xG; home + away = 1. Printed only when at least "
              f"{ZONE_IN_VIEW:.0%} of the zone's cells are in view; 2 dp")


def _grid() -> np.ndarray:
    xs = (np.arange(NX) + 0.5) * L / NX
    ys = (np.arange(NY) + 0.5) * W / NY
    return np.array([(x, y) for y in ys for x in xs])        # row-major: y then x


PTS = _grid()


def _xg_toward(goal_x: float) -> np.ndarray:
    """Reference xG of a shot from each cell at the goal on x = goal_x (0 in the other half: own-half rule)."""
    out = np.zeros(len(PTS))
    for i, (x, y) in enumerate(PTS):
        d = abs(goal_x - x)
        if d <= L / 2:
            out[i] = reference_xg(max(d, 0.5), abs(y - GOAL_Y))
    return out


XG = {0.0: _xg_toward(0.0), L: _xg_toward(L)}
ZONE = {g: XG[g] >= ZONE_XG for g in XG}


def _visible(H: list, size: list[int], pts: np.ndarray) -> np.ndarray:
    """Cells whose centre the camera shows: pitch (near frame) -> far frame -> image through the inverse fit."""
    Hi = np.linalg.inv(np.asarray(H))
    P = np.c_[pts[:, 0], W - pts[:, 1], np.ones(len(pts))] @ Hi.T
    z = np.where(P[:, 2] == 0, 1e-9, P[:, 2])
    u, v = P[:, 0] / z, P[:, 1] / z
    return (P[:, 2] > 0) & (u >= 0) & (u < size[0]) & (v >= 0) & (v < size[1])


def _depth(p: dict, attacks_plus: bool) -> float:
    return p["x"] if attacks_plus else L - p["x"]


def shape(players: list[dict], attacks_plus: bool, vis: np.ndarray) -> dict:
    """Back line = the 4 deepest outfield players (by depth from the team's own goal line), drawn when the strip from
    the deepest of them back to the goal line is in view (nobody deeper can be hidden); the remaining lines split
    the rest (front = the 3 most advanced, midfield = between) and need OUTFIELD_MIN in view."""
    out = sorted((p for p in players if not p["keeper"]), key=lambda p: _depth(p, attacks_plus))
    res = {"n_players_seen": len(out), "back_line": None, "lines": None, "width_m": None, "depth_m": None,
           "line_gap_m": None, "null_reason": None}
    if len(out) < 4:
        res["null_reason"] = f"{len(out)} outfield players in view (back line needs 4)"
        return res
    deepest = _depth(out[0], attacks_plus)
    behind = np.array([(x if attacks_plus else L - x) <= deepest and abs(y - GOAL_Y) <= BEHIND_HALF_W
                       for x, y in PTS])
    if behind.any() and vis[behind].mean() < BEHIND_IN_VIEW:
        res["null_reason"] = "the space behind the back line is not in view (a deeper player could be hidden)"
        return res
    pts = lambda ps: [[p["x"], p["y"]] for p in sorted(ps, key=lambda p: p["y"])]   # noqa: E731  touchline to touchline
    res["back_line"] = pts(out[:4])
    if len(out) < OUTFIELD_MIN:
        res["null_reason"] = f"{len(out)} of 10 outfield players in view (lines, width, depth need {OUTFIELD_MIN})"
        return res
    d = [_depth(p, attacks_plus) for p in out]
    back, mid, front = np.mean(d[:4]), np.mean(d[4:-3]), np.mean(d[-3:])
    res.update({"lines": [pts(out[:4]), pts(out[4:-3]), pts(out[-3:])],
                "width_m": round(float(max(p["y"] for p in out) - min(p["y"] for p in out)), 2),
                "depth_m": round(float(front - back), 2), "line_gap_m": round(float(mid - back), 2)})
    return res


def always_shot(slug: str, live_path: str) -> dict:
    from footage.clips import CLIPS as META
    live = json.loads((FOOTAGE / slug / "cache" / live_path).read_text())["result"]
    shot_id = live["shot_id"]
    tracks = json.loads((FOOTAGE / slug / "tracks" / f"{shot_id}.json").read_text())
    calib = json.loads((FOOTAGE / slug / "calib" / f"{shot_id}.json").read_text())
    fps, size = tracks["fps"], calib["image_size"]
    home_plus = live["home_attacks"] == "+x"
    by_frame = {r["frame"]: r for r in tracks["frames"]}
    frames = []
    for fr in live["frames"]:
        frame = min(by_frame, key=lambda f: abs(f - fr["clip_ms"] / 1000 * fps))
        players = [p for p in fr["players"] if p["team"] in ("home", "away")]
        row = {"clip_ms": fr["clip_ms"], "trusted": False, "null_reason": None, "control": None, "danger": None,
               "danger_zone": None, "shape": None, "ball_layer": fr["threat"] is not None}
        frames.append(row)
        cal = nearest_ok(calib["frames"], frame) if by_frame[frame]["calib_ok"] else None   # as the tracking used
        if cal is None:
            row["null_reason"] = "camera fit not trusted"
            continue
        if fr["null_reason"] == "dead ball after the goal":
            row["null_reason"] = "dead ball after the goal"
            continue
        teams = {t: [p for p in players if p["team"] == t] for t in ("home", "away")}
        if not teams["home"] or not teams["away"]:
            row["null_reason"] = "one team not in view"
            continue
        row["trusted"] = True
        vis = _visible(cal["H"], size, PTS)
        ctrl = control([(p["x"], p["y"], 0 if p["team"] == "home" else 1) for p in players], PTS, 0)
        row["control"] = base64.b64encode(np.where(vis, np.round(ctrl * 254), 255).astype(np.uint8).tobytes()).decode()
        row["shape"] = {t: shape(teams[t], home_plus == (t == "home"), vis) for t in ("home", "away")}
        seen = {g: float(vis[ZONE[g]].mean()) for g in ZONE}
        g = max(seen, key=seen.get)                   # the goal whose zone the camera shows (one end at a time)
        attacker = "home" if (g == L) == home_plus else "away"
        row["danger_zone"] = {"goal_x": g, "attacked_by": attacker, "in_view": round(seen[g], 2)}
        if seen[g] < ZONE_IN_VIEW:
            row["null_reason"] = f"dangerous zone {seen[g]:.0%} in view (needs {ZONE_IN_VIEW:.0%})"
            continue
        z = ZONE[g] & vis
        s_home = float((ctrl[z] * XG[g][z]).sum() / XG[g][z].sum())
        row["danger"] = {"home": round(s_home, 2), "away": round(1 - s_home, 2)}
    return {"slug": slug, "shot_id": shot_id, "live": live_path, "hz": live["hz"], "step_ms": live["step_ms"],
            "start_clip_ms": live["start_clip_ms"], "end_clip_ms": live["end_clip_ms"], "period": live["period"],
            "home_attacks": live["home_attacks"],
            "team_names": {"home": META[slug]["home"], "away": META[slug]["away"]},
            "control_model": CONTROL_MODEL, "danger_def": DANGER_DEF,
            "grid": {"x0": 0.0, "y0": 0.0, "dx": round(L / NX, 3), "dy": round(W / NY, 3), "nx": NX, "ny": NY,
                     "encoding": "base64 uint8, row-major y then x (y from the NEAR touchline): P(home controls) x 254 "
                                 "rounded; 255 = cell not in view"},
            "shape_def": ("by depth from the team's own goal line, outfield players in view: back_line = the 4 deepest, "
                          f"drawn only when >= {BEHIND_IN_VIEW:.0%} of the strip behind the deepest (to the goal line, the "
                          "penalty area's width) is in view; lines "
                          "= back 4 / the rest / the 3 most advanced; width_m = touchline-to-touchline spread; depth_m "
                          f"= front line - back line (mean depths); line_gap_m = midfield line - back line; lines, "
                          f"width, depth and gap need >= {OUTFIELD_MIN} of 10 outfield players; metres, 2 dp; points "
                          "listed touchline to touchline (y ascending)"),
            "gates": {"trusted": "the tracking's camera fit is trusted at the frame, both teams in view, not after a "
                                 "goal (dead ball)",
                      "scope": "visible region only: control and danger use the cells the camera shows"},
            "frames": frames,
            "source": {"players": f"{slug}/cache/{live_path}", "calib": f"{slug}/calib/{shot_id}.json",
                       "xg_model": "evals.pitchwatch.shotxg.reference_xg"}}


def runs(frames: list[dict], hz: int) -> list[dict]:
    """Stretches of always-on frames (control and danger), gaps up to RUN_GAP bridged, at least RUN_MIN_S long, with
    their always-on and ball-layer shares; only those at >= RUN_PCT always-on are kept."""
    on = [f["control"] is not None and f["danger"] is not None for f in frames]
    out, i = [], 0
    while i < len(on):
        if not on[i]:
            i += 1
            continue
        j, last = i, i
        while j + 1 < len(on) and (on[j + 1] or any(on[j + 1:j + 2 + RUN_GAP]) and j + 1 - last <= RUN_GAP):
            j += 1
            if on[j]:
                last = j
        seg = frames[i:last + 1]
        if (last - i + 1) / hz >= RUN_MIN_S:
            pct = sum(on[i:last + 1]) / len(seg)
            if pct >= RUN_PCT:
                out.append({"start_clip_ms": seg[0]["clip_ms"], "end_clip_ms": seg[-1]["clip_ms"],
                            "always_on_pct": round(pct, 3),
                            "ball_pct": round(sum(f["ball_layer"] for f in seg) / len(seg), 3)})
        i = last + 1
    return sorted(out, key=lambda r: r["start_clip_ms"] - r["end_clip_ms"])


def always(slug: str) -> list[str]:
    from evals.pitchwatch.v3 import write
    ix = json.loads((FOOTAGE / slug / "cache" / "v6" / "live_index_0.json").read_text())["result"]["shots"]
    index, paths = [], []
    for s in ix:
        if "path" not in s:
            continue
        res = always_shot(slug, s["path"])
        paths.append(str(write(slug, "always", res["start_clip_ms"], res, version="v7")))
        fr = res["frames"]
        on = sum(f["control"] is not None and f["danger"] is not None for f in fr)
        index.append({"shot_id": s["shot_id"], "path": f"v7/always_{res['start_clip_ms']}.json",
                      "start_clip_ms": res["start_clip_ms"], "end_clip_ms": res["end_clip_ms"], "frames": len(fr),
                      "trusted": sum(f["trusted"] for f in fr), "control": sum(f["control"] is not None for f in fr),
                      "always_on": on, "always_on_pct": round(on / len(fr), 3) if fr else 0.0,
                      "ball_layer": sum(f["ball_layer"] for f in fr),
                      "back_line": {t: sum(bool(f["shape"] and f["shape"][t]["back_line"]) for f in fr)
                                    for t in ("home", "away")},
                      "runs": runs(fr, res["hz"])})
    paths.append(str(write(slug, "always_index", 0, {"shots": index, "run_rule": (
        f"stretches of always-on frames (control and danger not null), gaps up to {RUN_GAP} samples bridged, at "
        f"least {RUN_MIN_S:.0f} s long, kept when >= {RUN_PCT:.0%} always-on; ball_pct = share with a v6 value")},
        version="v7")))
    return paths


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    if args[0] == "always":
        for slug in args[1:] or CLIPS:
            print(*always(slug), sep="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
