"""Real-footage insights for video v3 (track A): per-frame data from Pitchwatch tracks.

    python -m evals.pitchwatch.insights speed   <slug> --shots 23,25 --player-at 250.0:holder [--out ...]
    python -m evals.pitchwatch.insights line    <slug> --shot 62
    python -m evals.pitchwatch.insights xray    <slug> --shot 62
    python -m evals.pitchwatch.insights metrics

Pitch frame as in the shared format note: x in [0, 105] from the left goal line, y in [0, 68] from the far
touchline, metres. Every number comes from tracks/<shot>.json (positions through the calibration) and is smoothed
before it is differentiated; frames whose calibration is not trusted are flagged, never filled silently.

speed: one player's run across shots (a gap between shots, a close camera, is reported as a gap: its distance is the
straight line between the two ends, a lower bound). Positions are smoothed with a Savitzky-Golay filter (0.6 s,
cubic), speed from the smoothed derivative; any speed above MAX_KMH is flagged as measurement error, not reported.
line: per frame, each team's last-defender line (second-deepest outfield-or-keeper x toward its own goal) and the gap
to the opponent's most advanced player, plus pass moments (the ball's nearest player changes to a team-mate).
xray: per frame, for every visible team-mate of the ball carrier, P(pass completes) x xG(shot from there), from the
outcome heads (PassHead, XGHead) on features computed from the tracked positions; pitch control re-implemented for
the players in view.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
FOOTAGE = ROOT / "data" / "footage"
L, W, GOAL_Y, GOAL_HALF = 105.0, 68.0, 34.0, 3.66
MAX_KMH = 37.5                 # fastest sprints measured in the Premier League are ~37 km/h
SMOOTH_S = 0.6
MIN_LINE_PLAYERS = 4
HOLD_S = 0.3


def load(slug: str, shot: int) -> tuple[dict, dict]:
    d = FOOTAGE / slug
    tracks = json.loads((d / "tracks" / f"{shot}.json").read_text())
    cal_path = d / "calib" / f"{shot}_refined.json"
    cal = json.loads((cal_path if cal_path.exists() else d / "calib" / f"{shot}.json").read_text())
    return tracks, cal


def calib_ok(cal: dict, frame: int, slack: int = 3) -> bool:
    return any(cal["frames"].get(str(f), {}).get("ok") for f in range(frame - slack, frame + slack + 1))


# ---------------------------------------------------------------------------------------------------- speed gun
def holder_track(tracks: dict, frame: int) -> int | None:
    """Track id nearest the ball (pixels, feet to ball) at a frame."""
    r = min(tracks["frames"], key=lambda x: abs(x["frame"] - frame))
    if not r["ball"] or not r["players"]:
        return None
    bx, by = r["ball"]["px"]
    return min(r["players"], key=lambda p: math.hypot(p["foot_px"][0] - bx, p["foot_px"][1] - by))["track_id"]


def follow(tracks: dict, tid: int, max_jump_m: float = 2.5) -> dict[int, list[float]]:
    """{frame: xy} for one player, continued across ID switches: when the track ends, take the track whose first
    point is nearest the last one (within max_jump_m and 0.5 s)."""
    by: dict[int, dict[int, list[float]]] = {}
    for r in tracks["frames"]:
        for p in r["players"]:
            if p["xy"]:
                by.setdefault(p["track_id"], {})[r["frame"]] = p["xy"]
    out, cur = {}, tid
    used = {tid}
    while cur is not None:
        pts = by.get(cur, {})
        start = max(out) if out else -1
        out.update({f: xy for f, xy in pts.items() if f > start})
        last_f = max(out)
        last = out[last_f]
        fps = tracks["fps"]
        nxt, best = None, max_jump_m
        for t, q in by.items():
            if t in used:
                continue
            f0 = min(q)
            if 0 < f0 - last_f <= fps / 2:
                d = math.dist(q[f0], last)
                if d < best:
                    nxt, best = t, d
        if nxt is not None:
            used.add(nxt)
        cur = nxt
    return out


def smooth_series(frames: np.ndarray, xy: np.ndarray, fps: float) -> tuple[np.ndarray, np.ndarray]:
    """Savitzky-Golay smoothed positions and velocities (m/s) on a regular frame grid (gaps interpolated first)."""
    from scipy.signal import savgol_filter

    grid = np.arange(frames[0], frames[-1] + 1)
    P = np.stack([np.interp(grid, frames, xy[:, k]) for k in (0, 1)], axis=1)
    win = max(5, int(round(SMOOTH_S * fps)) | 1)
    if len(grid) < win:
        return grid, P, np.zeros_like(P)
    S = savgol_filter(P, win, 3, axis=0)
    V = savgol_filter(P, win, 3, deriv=1, delta=1.0 / fps, axis=0)
    return grid, S, V


def speed_gun(slug: str, shots: list[int], player_at: list[tuple[float, int | str]]) -> dict:
    """player_at: per shot, (time_s, track_id or "holder") identifying the player in that shot."""
    segs = []
    for shot, (t_s, who) in zip(shots, player_at, strict=True):
        tracks, cal = load(slug, shot)
        fps = tracks["fps"]
        frame = int(round(t_s * fps))
        tid = holder_track(tracks, frame) if who == "holder" else int(who)
        path = follow(tracks, tid)
        fr = np.array(sorted(path))
        xy = np.array([path[f] for f in fr])
        grid, S, V = smooth_series(fr, xy, fps)
        kmh = np.hypot(V[:, 0], V[:, 1]) * 3.6
        ok = np.array([calib_ok(cal, int(f)) for f in grid])
        bad = ok & (kmh > MAX_KMH)
        rows = [{"frame": int(f), "t": round(f / fps, 3), "xy": [round(float(a), 2) for a in s],
                 "kmh": round(float(k), 1) if o and not b else None, "calib_ok": bool(o),
                 "flag": None if o and not b else ("calibration" if not o else "speed_above_limit")}
                for f, s, k, o, b in zip(grid, S, kmh, ok, bad, strict=True)]
        step = np.hypot(*np.diff(S, axis=0).T)
        segs.append({"shot": shot, "track_ids": sorted({tid}), "fps": fps, "frames": rows,
                     "distance_m": round(float(step[ok[1:]].sum()), 1),
                     "top_kmh": round(float(np.max(kmh[ok & ~bad])), 1) if (ok & ~bad).any() else None,
                     "trusted_share": round(float(ok.mean()), 3)})
    gaps = []
    for a, b in zip(segs, segs[1:], strict=False):        # between the last and first trusted positions
        e = next(r for r in reversed(a["frames"]) if r["calib_ok"])
        s = next(r for r in b["frames"] if r["calib_ok"])
        gaps.append({"from_t": e["t"], "to_t": s["t"], "straight_line_m": round(math.dist(e["xy"], s["xy"]), 1),
                     "note": "not on the wide camera; straight-line distance is a lower bound"})
    return {"slug": slug, "segments": segs, "gaps": gaps,
            "distance_m": round(sum(s["distance_m"] for s in segs) + sum(g["straight_line_m"] for g in gaps), 1),
            "top_kmh": max((s["top_kmh"] for s in segs if s["top_kmh"]), default=None),
            "method": f"Savitzky-Golay {SMOOTH_S} s cubic on positions; speeds above {MAX_KMH} km/h or on untrusted "
                      "calibration are flagged, not shown"}


# ---------------------------------------------------------------------------------------------------- line
def keeper_tracks(tracks: dict, depth_m: float = 12.0, half_width_m: float = 12.0) -> set[int]:
    """Tracks that behave like goalkeepers: median position over the shot within depth_m of a goal line and within
    half_width_m of the centre line, at most one per goal (the one nearest the line; attackers parked in the box
    are further out). Kit clustering puts some keepers in an outfield team (their kit matches
    neither), which would make the opposing keeper a "pass option"; position over the shot does not lie."""
    pts: dict[int, list] = {}
    for r in tracks["frames"]:
        for p in r["players"]:
            if p["xy"]:
                pts.setdefault(p["track_id"], []).append(p["xy"])
    best: dict[int, tuple[float, int]] = {}                # goal side -> (distance to its line, track)
    for tid, xy in pts.items():
        if len(xy) < 10:
            continue
        x, y = np.median(np.array(xy), axis=0)
        if abs(y - GOAL_Y) >= half_width_m:
            continue
        for side, dist in ((0, x), (1, L - x)):
            if dist < depth_m and (side not in best or dist < best[side][0]):
                best[side] = (dist, tid)
    return {tid for _, tid in best.values()}          # at most one keeper per goal


def team_directions(tracks: dict) -> dict[int, int]:
    """+1 when the team attacks +x. From the clip's reviewed directions.json when it lists the shot (the reliable
    source: a side under sustained pressure sits in its own half, which fools the fallback); otherwise the team
    whose players sit further left on average defends the left goal."""
    path = FOOTAGE / tracks["slug"] / "directions.json"
    if path.exists():
        by = json.loads(path.read_text())["by_shot"].get(str(tracks["shot_id"]))
        if by:
            return {int(k): int(v) for k, v in by.items()}
    xs = {0: [], 1: []}
    for r in tracks["frames"]:
        for p in r["players"]:
            if p["xy"] and p["team"] in (0, 1):
                xs[p["team"]].append(p["xy"][0])
    m0, m1 = np.mean(xs[0]), np.mean(xs[1])
    return {0: 1 if m0 < m1 else -1, 1: -1 if m0 < m1 else 1}


def nearest_player(r: dict) -> dict | None:
    if not r["ball"] or not r["players"]:
        return None
    bx, by = r["ball"]["px"]
    p = min(r["players"], key=lambda p: math.hypot(p["foot_px"][0] - bx, p["foot_px"][1] - by))
    h = p["bbox"][3] - p["bbox"][1]
    return p if math.hypot(p["foot_px"][0] - bx, p["foot_px"][1] - by) < 0.8 * h else None


def defensive_line(slug: str, shot: int) -> dict:
    tracks, cal = load(slug, shot)
    dirs = team_directions(tracks)
    rows, last_holder, cand, cand_n = [], None, None, 0
    hold = max(2, int(round(HOLD_S * tracks["fps"] / tracks.get("step", 1))))
    for r in tracks["frames"]:
        f = r["frame"]
        row = {"frame": f, "t": round(f / tracks["fps"], 3), "calib_ok": calib_ok(cal, f)}
        h = nearest_player(r)
        if h and h["team"] in (0, 1):                     # a holder counts after HOLD_S of keeping the ball
            if cand and cand["track_id"] == h["track_id"]:
                cand_n += 1
            else:
                cand, cand_n = h, 1
            if cand_n == hold and (last_holder is None or last_holder["track_id"] != h["track_id"]):
                if last_holder and last_holder["team"] == h["team"]:
                    row["pass"] = {"from": last_holder["track_id"], "to": h["track_id"], "team": h["team"]}
                last_holder = h
        row["defending"] = None
        if last_holder is not None:
            team = 1 - last_holder["team"]                  # the team out of possession holds the line
            d = dirs[team]                                   # +1: attacks +x, so defends the left goal
            mine = [p["xy"][0] for p in r["players"] if p["team"] == team and p["xy"]]
            mine += [p["xy"][0] for p in r["players"] if p["team"] is None and p["xy"]
                     and (p["xy"][0] < 20 if d > 0 else p["xy"][0] > L - 20)]          # its keeper, by the goal
            opp = [p["xy"][0] for p in r["players"] if p["team"] == 1 - team and p["xy"]]
            keeper_seen = any(p["team"] is None and p["xy"] and (p["xy"][0] < 20 if d > 0 else p["xy"][0] > L - 20)
                              for p in r["players"])
            depth = sorted(mine) if d > 0 else sorted(mine, reverse=True)          # nearest own goal first
            own_half = len(depth) > 1 and (depth[1] < L / 2 if d > 0 else depth[1] > L / 2)
            if len(mine) >= MIN_LINE_PLAYERS and opp and (keeper_seen or own_half):
                line = depth[1]
                adv = min(opp) if d > 0 else max(opp)
                row["defending"] = {"team": team, "line_x": round(line, 2), "most_advanced_attacker_x": round(adv, 2),
                                    "beyond_m": round((line - adv) if d > 0 else (adv - line), 2),
                                    "players_seen": len(mine)}
        rows.append(row)
    return {"slug": slug, "shot": shot, "directions": {str(k): v for k, v in dirs.items()},
            "teams": tracks.get("teams"), "frames": rows,
            "note": "defending = the team out of possession (last ball carrier's opponents). beyond_m > 0: the most "
                    "advanced attacker is past the line (offside position if the ball is played then); < 0: onside "
                    "by that much. Only players in view count; reported when at least MIN_LINE_PLAYERS defenders "
                    "(keeper included) are seen and the line is in the defending team's half or its keeper is in "
                    "view (otherwise the real back line may be off-camera). A holder counts after HOLD_S with the "
                    "ball; a pass is a change of holder within a team."}


def offside_checks(slug: str, shot: int) -> list[dict]:
    """For every detected pass: the receiver's position against the offside line at the moment the ball was played
    (the last frame the passer was nearest the ball). Law 11: offside position = in the opponents' half and nearer
    their goal line than both the ball and the second-last opponent. margin_m = receiver's distance past the deepest
    of (second-last defender, ball, halfway line), in the attacking direction; > 0 offside position, < 0 onside."""
    res = defensive_line(slug, shot)
    tracks, cal = load(slug, shot)
    dirs = team_directions(tracks)
    keepers = keeper_tracks(tracks)
    frames = tracks["frames"]
    nearest = [(nearest_player(r) or {}).get("track_id") for r in frames]
    index = {r["frame"]: i for i, r in enumerate(frames)}
    out = []
    for row in res["frames"]:
        if "pass" not in row:
            continue
        att_team, passer, receiver = row["pass"]["team"], row["pass"]["from"], row["pass"]["to"]
        i = index[row["frame"]]
        j = next((k for k in range(i, max(-1, i - 60), -1) if nearest[k] == passer), None)
        if j is None:
            continue
        r = frames[j]
        pos = {p["track_id"]: p for p in r["players"] if p["xy"]}
        if passer not in pos or receiver not in pos or not calib_ok(cal, r["frame"]):
            continue
        d = dirs[att_team]                                           # attacking direction of the passing team

        def u(xy, d=d):
            return xy[0] if d > 0 else L - xy[0]
        defenders = sorted((u(p["xy"]) for p in r["players"] if p["xy"] and (p["team"] == 1 - att_team
                            or (p["track_id"] in keepers and u(p["xy"]) > L / 2))), reverse=True)
        if len(defenders) < MIN_LINE_PLAYERS:
            continue
        keeper_seen = any(p["track_id"] in keepers and p["xy"] and u(p["xy"]) > L / 2 for p in r["players"])
        # the keeper is the last defender; off-screen, assume he is behind everyone in view
        second_last = defenders[1] if keeper_seen else defenders[0]
        ball_u, recv_u = u(pos[passer]["xy"]), u(pos[receiver]["xy"])
        line_u = max(second_last, ball_u, L / 2)
        out.append({"pass_frame": r["frame"], "pass_t": round(r["frame"] / tracks["fps"], 3),
                    "received_t": row["t"], "team": att_team, "passer": passer, "receiver": receiver,
                    "second_last_x": round(second_last if d > 0 else L - second_last, 2),
                    "ball_x": pos[passer]["xy"][0], "line_x": round(line_u if d > 0 else L - line_u, 2),
                    "receiver_xy": pos[receiver]["xy"], "margin_m": round(recv_u - line_u, 2),
                    "decided_by": "defender" if line_u == second_last else ("ball" if line_u == ball_u else "halfway"),
                    "defenders_seen": len(defenders), "keeper_seen": keeper_seen,
                    "attacking_dir": "+x" if d > 0 else "-x"})
    return out


# ---------------------------------------------------------------------------------------------------- xray
def control(players: list[tuple[float, float, int]], pts: np.ndarray, team: int) -> np.ndarray:
    """Team's share of control at points (the pitch-control model of physics.pitch_control, players in view)."""
    from physics.pitch_control import REACTION_S, SCALE, VMAX
    P = np.array([[x, y] for x, y, _ in players])
    t = REACTION_S + np.hypot(pts[None, :, 0] - P[:, 0, None], pts[None, :, 1] - P[:, 1, None]) / VMAX
    w = np.exp(-(t - t.min(axis=0, keepdims=True)) / SCALE)
    mine = np.array([tm == team for _, _, tm in players])
    return w[mine].sum(axis=0) / w.sum(axis=0)


def xray(slug: str, shot: int) -> dict:
    import pandas as pd

    from heads.models import PassHead, XGHead
    from kickoff.physics_prior import cone_count, goal_angle, goal_distance

    tracks, cal = load(slug, shot)
    dirs = team_directions(tracks)
    ph, xh = PassHead(), XGHead()
    excl_path = FOOTAGE / slug / "exclude.json"           # reviewed: referees and others kit clustering misplaced
    excluded = set(json.loads(excl_path.read_text()).get(str(shot), [])) if excl_path.exists() else set()
    keepers = keeper_tracks(tracks)
    for r in tracks["frames"]:
        r["players"] = [p for p in r["players"] if p["track_id"] not in excluded and p["xy"]
                        and -1.0 <= p["xy"][0] <= L + 1.0 and -0.5 <= p["xy"][1] <= W + 0.5]    # off-pitch: bench
        for p in r["players"]:
            if p["track_id"] in keepers:              # keepers: never a pass option, counted as keepers
                p["team"], p["role"] = None, "keeper"
    out = []
    for r in tracks["frames"]:
        h = nearest_player(r)
        if not h or h["team"] not in (0, 1) or not h["xy"]:
            continue
        team, d = h["team"], dirs[h["team"]]

        def uv(xy, d=d):
            return (xy[0], xy[1]) if d > 0 else (L - xy[0], W - xy[1])
        mates = [p for p in r["players"] if p["team"] == team and p["xy"] and p["track_id"] != h["track_id"]]
        opps = [p for p in r["players"] if p["team"] == 1 - team and p["xy"]]
        if not mates or not opps:
            continue
        u0, v0 = uv(h["xy"])
        ou = np.array([uv(p["xy"])[0] for p in opps])
        ov = np.array([uv(p["xy"])[1] for p in opps])
        players = [(*uv(p["xy"]), p["team"]) for p in r["players"] if p["team"] in (0, 1) and p["xy"]]
        prows, srows = [], []
        for m in mates:
            u, v = uv(m["xy"])
            length = math.hypot(u - u0, v - v0)
            seg = np.array([u - u0, v - v0])
            L2 = max(float(seg @ seg), 1e-9)
            s = np.clip(((np.stack([ou, ov], 1) - [u0, v0]) @ seg) / L2, 0, 1)
            lane = np.hypot(ou - (u0 + s * seg[0]), ov - (v0 + s * seg[1]))
            prows.append({"length_m": length, "angle_rad": math.atan2(v - v0, u - u0), "lofted": int(length > 32),
                          "under_pressure": int(np.min(np.hypot(ou - u0, ov - v0)) < 2.5),
                          "receiver_space": float(control(players, np.array([[u, v]]), team)[0]),
                          "progressive_m": u - u0, "opponents_in_lane": int(np.sum(lane < 2.0)), "start_u": u0,
                          "nearest_opp_m": float(np.min(np.hypot(ou - u0, ov - v0)))})
            keepers = [uv(p["xy"])[0] for p in r["players"] if p["team"] is None and p["xy"] and uv(p["xy"])[0] > L - 20]
            keeper_u = max(keepers) if keepers else L - 1.0
            srows.append({"distance_m": float(goal_distance(u, v)), "angle_rad": float(goal_angle(u, v)),
                          "body_part": 0, "defenders_in_cone": cone_count(u, v, ou, ov),
                          "keeper_line_m": L - keeper_u, "under_pressure": int(np.min(np.hypot(ou - u, ov - v)) < 2.5),
                          "control_at_shot": float(control(players, np.array([[u, v]]), team)[0]), "penalty": 0})
        keepers = [uv(p["xy"])[0] for p in r["players"] if p["team"] is None and p["xy"] and uv(p["xy"])[0] > L - 20]
        srows.append({"distance_m": float(goal_distance(u0, v0)), "angle_rad": float(goal_angle(u0, v0)), "body_part": 0,
                      "defenders_in_cone": cone_count(u0, v0, ou, ov),
                      "keeper_line_m": L - (max(keepers) if keepers else L - 1.0),
                      "under_pressure": int(np.min(np.hypot(ou - u0, ov - v0)) < 2.5),
                      "control_at_shot": float(control(players, np.array([[u0, v0]]), team)[0]), "penalty": 0})
        pc = ph.predict(pd.DataFrame(prows))
        xg_all = xh.predict(pd.DataFrame(srows))
        xg, shot_now = xg_all[:-1], float(xg_all[-1])
        out.append({"frame": r["frame"], "t": round(r["frame"] / tracks["fps"], 3), "calib_ok": calib_ok(cal, r["frame"]),
                    "carrier": h["track_id"], "team": team, "carrier_xy": h["xy"], "shoot_now_xg": round(shot_now, 4),
                    "options": sorted([{"track_id": m["track_id"], "xy": m["xy"], "p_pass": round(float(a), 3),
                                        "xg_if_shot": round(float(b), 3), "value": round(float(a * b), 4)}
                                       for m, a, b in zip(mates, pc, xg, strict=True)], key=lambda o: -o["value"])})
    return {"slug": slug, "shot": shot, "frames": out,
            "method": "value = PassHead P(complete) x XGHead xG(shot from the receiver's spot), heads trained on the "
                      "synthetic league; features from tracked positions (players in view only)",
            "teams": tracks.get("teams")}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m evals.pitchwatch.insights")
    ap.add_argument("kind", choices=("speed", "line", "xray", "metrics"))
    ap.add_argument("slug", nargs="?")
    ap.add_argument("--shots", default="")
    ap.add_argument("--shot", type=int)
    ap.add_argument("--player-at", default="", help="speed: per shot time_s:track_id|holder, comma separated")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    if args.kind == "speed":
        pa = [(float(a), b if b == "holder" else int(b)) for a, b in (x.split(":") for x in args.player_at.split(","))]
        res = speed_gun(args.slug, [int(s) for s in args.shots.split(",")], pa)
        name = f"speed_{'_'.join(args.shots.split(','))}"
    elif args.kind == "line":
        res, name = defensive_line(args.slug, args.shot), f"line_{args.shot}"
    elif args.kind == "xray":
        res, name = xray(args.slug, args.shot), f"xray_{args.shot}"
    else:
        from evals.pitchwatch.metrics import footage_metrics
        res, name = footage_metrics(), "metrics"
    out = args.out or (FOOTAGE / (args.slug or "") / "insights" / f"{name}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, separators=(",", ":")) + "\n")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
