"""Video v6: live analytics at 10 Hz over every tracked wide shot (shared note track-a-v6-live-format.md).

    python -m evals.pitchwatch.v6 live [slug ...]     # cache/v6/live_<start_clip_ms>.json + live_index_0.json
    python -m evals.pitchwatch.v6 match               # cache/v6/xg_running_0.json + shot_map_0.json (from v5)

Per frame: the ball carrier, his "shot now" xG, every teammate in view as a pass option (P(complete) from our pass
model x the reference xG from the receiver's spot), the best option and threat = max(shot now, best). Same
reference model, own-half rule and onside margin as v5. Where the camera fit is not trusted, the ball is not
detected or loose, or possession is unsettled, the analytics are null with the reason: never a guess.
"""

from __future__ import annotations

import json
import math
import sys

import numpy as np

from evals.pitchwatch.insights import FOOTAGE, keeper_tracks
from evals.pitchwatch.v5 import GOAL_Y, SOURCE, L, W, options_xg, shot_xg, team_frame

HZ = 10
HOLD_M = 2.5                       # holder: the tracked player nearest the ball, within this
FLIGHT_MS = 12.0                   # ball ground speed above this (m/s, over ~0.2 s): a pass or in the air, no holder
SETTLE = 3                         # possession switches after this many consecutive samples (0.3 s)
CLIPS = ("liverpool-mancity-2526", "manutd-mancity-2526", "arsenal-chelsea-2526", "manutd-spurs-2425")
RULES = {"holder": f"tracked player nearest the ball within {HOLD_M} m, else 'ball loose'",
         "possession": f"the holder's team must hold for {SETTLE} samples ({SETTLE / HZ:.1f} s) before possession "
                       "switches; a holder of the other team before then is 'possession unsettled'",
         "own_half": "no xG while the holder or the receiver is in his own half (the model has no shots there)",
         "onside": "offside_risk = within 0.5 m of the line (second-last defender, ball or halfway); never best",
         "keepers": "by position, one per goal, plus track B's hand corrections (moments/overrides.json, same "
                    "camera shot, which also remove referees): opponents for control, never pass options",
         "trusted": "false where the camera fit is not trusted at the frame or the ball is not detected",
         "in_flight": f"no holder while the ball's ground speed exceeds {FLIGHT_MS:.0f} m/s over ~0.2 s (a pass or a "
                      "ball in the air, whose ground position a single camera cannot place), or where it cannot be "
                      "measured (fewer than two ball detections within 0.12 s)",
         "dead_ball": "null once the ball is past a line, and from a goal's reviewed strike to the end of the shot",
         "goal_line": "positions on or behind the goal line are valued 0.5 m out (the model has no shots there)"}


def _period(slug: str, clip_ms: int) -> int:
    ev = [json.loads(x) for x in (FOOTAGE / slug / "events.jsonl").read_text().splitlines()]
    return min(ev, key=lambda e: abs(e["attrs"]["clip_ms"] - clip_ms))["period"]


def _goal_strikes(slug: str) -> list[int]:
    """Reviewed strike times (clip_ms) of the clip's goals: after one, the ball is dead until the restart."""
    rows = json.loads((FOOTAGE / "insights" / "shots_xg.json").read_text())["shots"]
    return [r["release_clip_ms"] for r in rows if r["slug"] == slug and r.get("goal") and r.get("release_clip_ms")]


def _hand(slug: str, shot_id) -> tuple[dict[int, str], dict[int, str]]:
    """track id -> name and track id -> fix ("referee" | "home" | "away" | "<side>:goalkeeper"), from track B's
    moment files and moments/overrides.json for moments in the same camera shot (track ids are unique per shot)."""
    from footage.freeze import load
    from footage.from_tracks import overrides
    names, fixes = {}, {}
    for p in (FOOTAGE / slug / "moments").glob("[0-9]*.json"):
        m = load(slug, int(p.stem))
        if (m.get("tracking") or {}).get("shot_id") == shot_id:
            names.update({q["track_id"]: q["name"] for q in m["players"] if q.get("name") and "track_id" in q})
            fixes.update({int(k): v for k, v in overrides(FOOTAGE / slug, int(p.stem)).items()})
    return names, fixes


def _near(xy) -> tuple[float, float]:
    return round(float(xy[0]), 2), round(W - float(xy[1]), 2)


def live_shot(slug: str, shot_id) -> dict:
    from evals.pitchwatch.shotxg import HOME_ATTACKS_P2
    from footage.clips import CLIPS as META
    from footage.from_tracks import _good_ball
    from footage.tag import side

    tracks = json.loads((FOOTAGE / slug / "tracks" / f"{shot_id}.json").read_text())
    fps, F = tracks["fps"], tracks["frames"]
    team_side = {int(k): side(v.get("name", ""), META[slug]) for k, v in tracks["teams"].items()}
    keepers = keeper_tracks(tracks)
    names, fixes = _hand(slug, shot_id)
    start, end = F[0]["t"], F[-1]["t"]
    period = _period(slug, int(start * 1000))
    home_plus = HOME_ATTACKS_P2[slug] * (1 if period == 2 else -1) > 0
    by_frame = {r["frame"]: r for r in F}
    goals = _goal_strikes(slug)
    balls = np.array([(r["t"], *_near(r["ball"]["xy"])) for r in F if _good_ball(r["ball"])]).reshape(-1, 3)
    dead_from = min((g for g in goals if start * 1000 <= g <= end * 1000), default=None)
    frames, possession, cand, cand_n = [], None, None, 0
    for t in np.arange(math.ceil(start * HZ) / HZ, end + 1e-9, 1 / HZ):
        r = by_frame.get(min(by_frame, key=lambda f: abs(f - t * fps)))
        clip_ms = int(round(t * 1000))
        if abs(r["frame"] / fps - t) > 0.5 / HZ:
            continue
        players = []
        for p in r["players"]:
            fix = fixes.get(p["track_id"])
            if not p["xy"] or p.get("role") == "referee" or fix == "referee":
                continue
            x, y = _near(p["xy"])
            keeper = p["track_id"] in keepers or (fix or "").endswith(":goalkeeper")
            if fix:                                  # track B's hand correction for this camera shot
                team = fix.partition(":")[0]
            elif keeper:                             # the goal he stands in: the team defending it
                team = "home" if (x < L / 2) == home_plus else "away"
            else:
                team = team_side.get(p["team"]) if p["team"] in (0, 1) else None
            players.append({"label": f"t{p['track_id']}", "name": names.get(p["track_id"]), "team": team,
                            "keeper": keeper, "x": x, "y": y,
                            "px": [round(v) for v in p["foot_px"]]})
        row = {"clip_ms": clip_ms, "trusted": False, "null_reason": None, "ball": None, "attacking": None,
               "attacks": None, "holder": None, "in_opponent_half": None, "shot_now_xg": None, "options": [],
               "best": None, "threat": None, "threat_from": None, "players": players}
        frames.append(row)
        if dead_from is not None and clip_ms > dead_from:
            row["null_reason"] = "dead ball after the goal"
            continue
        if not r["calib_ok"]:
            row["null_reason"] = "camera fit not trusted"
            continue
        if not _good_ball(r["ball"]):
            row["null_reason"] = "ball not detected"
            continue
        bx, by = _near(r["ball"]["xy"])
        row["ball"] = {"x": bx, "y": by, "px": [round(v) for v in r["ball"]["px"]]}
        row["trusted"] = True
        if not (0 <= bx <= L and 0 <= by <= W):
            row["null_reason"] = "ball out of play"
            continue
        win = balls[np.abs(balls[:, 0] - t) <= 0.12]
        if len(win) >= 2 and win[-1, 0] - win[0, 0] >= 0.08:
            speed = math.hypot(*(win[-1, 1:] - win[0, 1:])) / (win[-1, 0] - win[0, 0])
            row["ball"]["speed_ms"] = round(speed, 1)
            if speed > FLIGHT_MS:
                row["null_reason"] = "ball in flight"
                continue
        else:                                        # one detection only: cannot tell a held ball from one in the air
            row["null_reason"] = "ball speed not measurable"
            continue
        out = [p for p in players if p["team"] and not p["keeper"]]
        near = min(out, key=lambda p: math.hypot(p["x"] - bx, p["y"] - by), default=None)
        if near is None or math.hypot(near["x"] - bx, near["y"] - by) > HOLD_M:
            row["null_reason"] = "ball loose"
            continue
        team = near["team"]                          # possession debounce on the holder's team
        if team == possession:
            cand, cand_n = None, 0
        else:
            cand_n = cand_n + 1 if team == cand else 1
            cand = team
            if cand_n >= SETTLE:
                possession, cand, cand_n = team, None, 0
        if team != possession:
            row["null_reason"] = "possession unsettled"
            continue
        attacks_plus = home_plus == (team == "home")
        u0, v0 = team_frame((near["x"], near["y"]), attacks_plus)
        row.update({"attacking": team, "attacks": "+x" if attacks_plus else "-x",
                    "holder": {k: near[k] for k in ("label", "name", "x", "y", "px")},
                    "in_opponent_half": bool(u0 >= L / 2)})
        if u0 < L / 2:
            row["null_reason"] = "own half"
            continue
        mates = [p for p in out if p["team"] == team and p is not near]
        opps = [p for p in players if p["team"] and p["team"] != team]
        shot = shot_xg(min(u0, L - 0.5), v0)              # same goal-line clamp as the receivers
        opts = options_xg(near, mates, opps, attacks_plus) if mates else []
        px = {p["label"]: p["px"] for p in mates}
        row["options"] = [{k: o[k] for k in ("label", "name", "x", "y", "p_pass", "xg_receiver", "xg_after_pass",
                                             "onside_margin_m", "offside_risk")} | {"px": px[o["label"]]}
                          for o in opts]
        best = next((o for o in opts if not o["offside_risk"] and o["xg_after_pass"] is not None), None)
        row["shot_now_xg"] = round(shot, 2)
        row["best"] = best and {"label": best["label"], "xg_after_pass": best["xg_after_pass"]}
        bxg = best["xg_after_pass_exact"] if best else -1.0
        row["threat"] = round(max(shot, bxg), 2)
        row["threat_from"] = "pass" if bxg > shot else "shot"
    return {"shot_id": shot_id, "period": period, "home_attacks": "+x" if home_plus else "-x", "hz": HZ,
            "step_ms": 1000 // HZ, "start_clip_ms": frames[0]["clip_ms"], "end_clip_ms": frames[-1]["clip_ms"],
            "image_size": _image_size(slug, shot_id), "formula": SOURCE, "rules": RULES,
            "coordinates": "pitch metres, x from the left goal line, y from the NEAR touchline (moment-file frame); "
                           "px = image pixel (feet / ball centre)",
            "frames": frames,
            "source": {"tracks": f"{slug}/tracks/{shot_id}.json", "calib": f"{slug}/calib/{shot_id}.json",
                       "pass_model": "packages/heads/artifacts/pass", "shot_model": "evals.pitchwatch.shotxg.reference_xg",
                       "names": "track B's moment files for this camera shot"}}


def _image_size(slug: str, shot_id) -> list[int] | None:
    p = FOOTAGE / slug / "calib" / f"{shot_id}.json"
    return json.loads(p.read_text()).get("image_size") if p.exists() else None


def _spans(slug: str) -> dict:
    out = {}
    for p in sorted((FOOTAGE / slug / "tracks").glob("*.json")):
        F = json.loads(p.read_text())["frames"]
        out[p.stem] = (F[0]["t"], F[-1]["t"])
    return out


def live(slug: str) -> list[str]:
    from evals.pitchwatch.v3 import write
    spans = _spans(slug)
    main = {k: v for k, v in spans.items() if not k.startswith("x")}
    index, paths = [], []
    for sid, (a, b) in spans.items():
        cover = next((k for k, (c, d) in main.items() if k != sid and c <= a and b <= d), None)
        if sid.startswith("x") and cover:            # a strike window inside a tracked passage: that one covers it
            index.append({"shot_id": sid, "covered_by": int(cover)})
            continue
        shot_id = int(sid) if sid.isdigit() else sid
        res = live_shot(slug, shot_id)
        path = write(slug, "live", res["start_clip_ms"], res, version="v6")
        paths.append(str(path))
        fr = res["frames"]
        index.append({"shot_id": shot_id, "path": f"v6/live_{res['start_clip_ms']}.json",
                      "start_clip_ms": res["start_clip_ms"], "end_clip_ms": res["end_clip_ms"], "frames": len(fr),
                      "trusted_frames": sum(f["trusted"] for f in fr),
                      "valued_frames": sum(f["threat"] is not None for f in fr),
                      "max_threat": max((f["threat"] for f in fr if f["threat"] is not None), default=None)})
    paths.append(str(write(slug, "live_index", 0, {"shots": index, "hz": HZ, "rules": RULES}, version="v6")))
    return paths


def match_beats() -> list[str]:
    """Score-bug series and shot map per clip: v5's shots_0 / xg_race_0 (same rules), in v6."""
    from evals.pitchwatch.v3 import write
    out = []
    for slug in CLIPS:
        v5 = FOOTAGE / slug / "cache" / "v5"
        shots = json.loads((v5 / "shots_0.json").read_text())["result"]
        race = json.loads((v5 / "xg_race_0.json").read_text())["result"]
        keep = {k: race[k] for k in race if k not in ("beat", "slug", "match_id")}
        out.append(str(write(slug, "xg_running", 0, {**keep, "source": {"v5": f"{slug}/cache/v5/xg_race_0.json"}},
                             version="v6")))
        rows = [{k: s.get(k) for k in ("event_id", "clock", "clip_ms", "team", "team_name", "shooter", "x", "y",
                                       "distance_m", "xg", "outcome", "goal", "penalty", "header", "set_piece",
                                       "disallowed", "reviewed", "reason", "camera_ok")}
                for s in shots["shots"]]
        out.append(str(write(slug, "shot_map", 0, {"shots": rows, "formula": SOURCE,
                                                   "coordinates": "moment-file frame (y from the near touchline), "
                                                                  "the shooter's spot at the strike frame",
                                                   "goal_y": GOAL_Y, "source": {"v5": f"{slug}/cache/v5/shots_0.json"}},
                             version="v6")))
    return out


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    if args[0] == "live":
        for slug in args[1:] or CLIPS:
            print(*live(slug), sep="\n")
    elif args[0] == "match":
        print(*match_beats(), sep="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
