"""Video v9: player boxes on every source frame of each clip window, the window's live states, the decision gap.

    python -m evals.pitchwatch.v9          # cache/v9/window_<start_clip_ms>.json per window, decision_gap_0.json

Boxes: the tracker samples every `step` frames (2: 12.5 Hz at 25 fps, 25 Hz at 50 fps). A sample frame carries the
tracker's own boxes ("measured"); a frame between two samples of the same camera shot carries each track seen on
both, linearly interpolated ("interpolated", never across a cut or a missing sample); a frame of an untracked camera
shot (close-up, replay) or with no tracked player is "lost" with the reason. Team per box: the v6 rule per
observation (track B's hand fix, else keeper by the goal he stands in, else kit colour), then held per identity
stretch of the track so a one-sample kit flicker does not flip a box's colour; a flip that holds three samples or
a jump no player can run is a new stretch (an ID switch), as in v6.identity_span. Carrier: the v6 holder at the
nearest 10 Hz sample, only in state "carry". Names and shirts only within track B's names_live_0 windows.
"""

from __future__ import annotations

import glob
import json
import math
import sys

from evals.pitchwatch.insights import FOOTAGE, keeper_tracks
from evals.pitchwatch.v5 import L
from evals.pitchwatch.v6 import JITTER_M, PLAYER_VMAX, SETTLE, _hand, _label_at, _near

# slug, tracked camera shot, window start / end (clip seconds), what it covers: v8's live windows with v9's ends
WINDOWS = [
    ("liverpool-mancity-2526", 62, 866.0, 880.0, "Liverpool 86': the options re-price, Szoboszlai's strike, the block"),
    ("manutd-mancity-2526", 104, 869.0, 883.2, "Amad's passage, his shot (877.16) and the second shot (880.08)"),
    ("arsenal-chelsea-2526", 177, 1295.0, 1307.0, "Saka finds Eze, Eze's strike (1301.08), saved"),
    ("manutd-mancity-2526", 127, 1074.4, 1086.2, "the move, Mbeumo's shot (1079.36) and goal at normal speed"),
    ("manutd-mancity-2526", 160, 1395.0, 1424.2, "stoppage time: City keep it, Man Utd break, Mount's goal (VAR)"),
    ("arsenal-chelsea-2526", 109, 830.0, 836.9, "Palmer on the byline: the cutback the decision-gap search found"),
]
SHOT_S = 1.0                       # after a reviewed strike: state "shot" until a carrier, a dead ball or this long
LAG_MS = 300                       # the holder rule may still show the shooter on the ball this long after the strike
CLIPS = ("liverpool-mancity-2526", "manutd-mancity-2526", "arsenal-chelsea-2526", "manutd-spurs-2425")
GAP_RULE = {"gap": "xg_receiver (published reference xG from the receiver's spot: the value if the pass reaches him) "
                   "minus the carrier's shot xG from where he stands",
            "eligible": "v6 state carry, receiver onside by more than 0.5 m (offside_risk false), P(complete) >= 0.3, "
                        "receiver outside his own half",
            "passage": "consecutive 10 Hz samples with the same carrier and receiver track; reported at its largest gap"}


def _shot_of(shots: list[dict], t: float) -> dict | None:
    return next((s for s in shots if s["start"] <= t < s["end"]), None)


def _teams(slug: str, tracks: dict) -> dict[tuple[int, int], str | None]:
    """(frame, track_id) -> "home" | "away" | "referee" | None, held per identity stretch of each track."""
    from evals.pitchwatch.clipmeta import clip_meta, home_attacks_plus, period_of
    from footage.tag import side
    F, shot_id = tracks["frames"], tracks["shot_id"]
    team_side = {int(k): side(v.get("name", ""), clip_meta(slug)) for k, v in tracks["teams"].items()}
    home_plus = home_attacks_plus(slug, period_of(slug, shot_id, int(F[0]["t"] * 1000)))
    keepers = keeper_tracks(tracks)
    _, fixes = _hand(slug, shot_id)
    obs: dict[int, list] = {}
    for r in F:
        for p in r["players"]:
            fix, tid = fixes.get(p["track_id"]), p["track_id"]
            if p.get("role") == "referee" or fix == "referee":
                team = "referee"
            elif fix:
                team = fix.partition(":")[0]
            elif tid in keepers and p["xy"]:
                team = "home" if (_near(p["xy"])[0] < L / 2) == home_plus else "away"
            else:
                team = team_side.get(p["team"]) if p["team"] in (0, 1) else None
            obs.setdefault(tid, []).append((r["frame"], r["t"], team, p["xy"]))
    out = {}
    for tid, o in obs.items():
        segs, cur = [[]], None
        for i, (fr, t, team, xy) in enumerate(o):
            prev = o[i - 1] if i else None
            jump = (prev and xy and prev[3] and
                    math.dist(xy, prev[3]) > PLAYER_VMAX * abs(t - prev[1]) + JITTER_M)
            flip = (cur and team and team != cur and len(o[i:i + SETTLE]) == SETTLE
                    and all(x[2] == team for x in o[i:i + SETTLE]))
            if (jump or flip) and segs[-1]:
                segs.append([])
                cur = None
            cur = cur or team
            segs[-1].append(i)
        for seg in segs:
            votes = [o[i][2] for i in seg if o[i][2]]
            held = max(set(votes), key=votes.count) if votes else None
            for i in seg:
                out[(o[i][0], tid)] = held
    return out


def boxes(slug: str, shot_id, t0: float, t1: float) -> dict:
    d = FOOTAGE / slug
    shots = json.loads((d / "shots.json").read_text())["shots"]
    tracks = json.loads((d / "tracks" / f"{shot_id}.json").read_text())
    fps, step = tracks["fps"], tracks["step"]
    team_of = _teams(slug, tracks)
    labels, _ = _hand(slug, shot_id)
    live_p = next(p for p in glob.glob(str(d / "cache" / "v6" / "live_*.json")) if "index" not in p
                  and json.loads(open(p).read())["result"]["shot_id"] == shot_id)
    live = {f["clip_ms"]: f for f in json.loads(open(live_p).read())["result"]["frames"]}
    by_frame = {r["frame"]: r for r in tracks["frames"]}
    names = {int(k): v["name"] for k, v in tracks["teams"].items()}
    tracked = {"start": tracks["frames"][0]["t"], "end": tracks["frames"][-1]["t"]}

    def carrier(ms: int) -> int | None:
        f = live.get(int(round(ms / 100.0)) * 100)
        return f["holder"]["track_id"] if f and f["state"] == "carry" and f["holder"] else None

    def box(p, fr, t, bbox, measured):
        name, shirt = _label_at(labels, p["track_id"], t)
        team = team_of.get((fr, p["track_id"]))
        return {"track_id": p["track_id"], "bbox": [round(v) for v in bbox], "team": team,
                "conf": round(p["conf"], 2) if measured else None, "name": name, "shirt": shirt}

    rows = []
    for fr in range(math.ceil(t0 * fps), math.floor(t1 * fps) + 1):
        t = fr / fps
        ms = int(round(t * 1000))
        cam = _shot_of(shots, t)
        row = {"frame": fr, "clip_ms": ms, "camera_shot": cam and cam["id"], "tracking": "lost", "lost_reason": None,
               "calib_ok": None, "carrier_track_id": None, "boxes": []}
        rows.append(row)
        if cam is None or cam["id"] != shot_id:
            kind = "replay" if cam and cam["replay"] else (cam["kind"] if cam else "none")
            row["lost_reason"] = f"camera cut: shot {cam and cam['id']} ({kind}) is not tracked"
            continue
        if fr in by_frame:
            r, src = by_frame[fr], "measured"
            row["boxes"] = [box(p, fr, t, p["bbox"], True) for p in r["players"]]
        else:
            lo = max((f for f in by_frame if f < fr), default=None)
            hi = min((f for f in by_frame if f > fr), default=None)
            if lo is None or hi is None or hi - lo > step:
                row["lost_reason"] = "outside the tracked samples of the shot"
                continue
            a, b, k = by_frame[lo], by_frame[hi], (fr - lo) / (hi - lo)
            r, src = a, "interpolated"
            nb = {p["track_id"]: p for p in b["players"]}
            for p in a["players"]:
                q = nb.get(p["track_id"])
                if q is None:
                    continue
                bb = [u + k * (v - u) for u, v in zip(p["bbox"], q["bbox"], strict=True)]
                row["boxes"].append(box(p, lo, t, bb, False) | {"team": team_of.get((lo, p["track_id"]))
                                                               if k < 0.5 else team_of.get((hi, p["track_id"]))})
            row["calib_ok"] = bool(a["calib_ok"] and b["calib_ok"])
        if not row["boxes"]:
            row["lost_reason"] = "no player tracked at this frame"
            continue
        row["tracking"] = src
        if row["calib_ok"] is None:
            row["calib_ok"] = bool(r["calib_ok"])
        c = carrier(ms)
        row["carrier_track_id"] = c
        for bx in row["boxes"]:
            bx["carrier"] = bx["track_id"] == c
    n = len(rows)
    count = {k: sum(1 for r in rows if r["tracking"] == k) for k in ("measured", "interpolated", "lost")}
    return {"fps": fps, "tracker_step": step, "frames": rows, "tracked_span_s": tracked, "team_names": names,
            "coverage": {"frames": n, **count,
                         "with_carrier": sum(1 for r in rows if r["carrier_track_id"] is not None)},
            "source": {"tracks": f"{slug}/tracks/{shot_id}.json", "live": live_p.split("/data/footage/")[-1]}}


def live_rows(slug: str, shot_id, t0: float, t1: float, frames: list[dict]) -> dict:
    """The v6 10 Hz rows of the window (players omitted: the boxes carry them) with v7's danger number, and the
    honest state as runs, including the camera cuts where nothing is tracked."""
    d = FOOTAGE / slug
    v6p = next(p for p in glob.glob(str(d / "cache" / "v6" / "live_*.json")) if "index" not in p
               and json.loads(open(p).read())["result"]["shot_id"] == shot_id)
    v6 = json.loads(open(v6p).read())["result"]
    v7p = d / "cache" / "v7" / f"always_{v6['start_clip_ms']}.json"
    v7 = {f["clip_ms"]: f for f in json.loads(v7p.read_text())["result"]["frames"]} if v7p.exists() else {}
    ruled_out = [(r["clip_ms"], r["disallowed"]) for r in json.loads((FOOTAGE / "insights" / "shots_xg.json")
                 .read_text())["shots"] if r["slug"] == slug and r.get("disallowed")]
    out = []
    for f in v6["frames"]:
        if t0 * 1000 <= f["clip_ms"] <= t1 * 1000:
            a = v7.get(f["clip_ms"]) or {}
            row = {k: v for k, v in f.items() if k != "players"} | {"danger": a.get("danger"),
                                                                   "danger_null_reason": a.get("null_reason")}
            gone = [why for ms, why in ruled_out if ms < f["clip_ms"]]
            if gone and f["null_reason"] == "dead ball after the goal":   # v6 says "Goal": this one did not count
                row |= {"state_text": "Goal, ruled out by VAR", "disallowed": gone[-1]}
            out.append(row)
    strikes = [r for r in json.loads((d / "cache" / "v5" / "shots_0.json").read_text())["result"]["shots"]
               if t0 * 1000 <= r["clip_ms"] <= t1 * 1000 and r["outcome"] != "disallowed"]
    for st in strikes:              # v6 knows no shots: the ball leaving the shooter reads as a pass or a loose ball
        s_ms, shot = st["clip_ms"], {"state": "shot", "state_text": f"Shot, {st['outcome']}", "pass": None,
                                     "shot": {k: st.get(k) for k in ("clip_ms", "outcome", "xg", "distance_m")}}
        for row in out:             # a "pass" whose flight spans the strike (its release is the 10 Hz sample before)
            p = row.get("pass")
            if row["state"] == "pass" and p and p["release_clip_ms"] <= s_ms + LAG_MS and p["arrival_clip_ms"] > s_ms:
                row |= shot if row["clip_ms"] >= s_ms - 100 else {  # before the strike: the shooter's own touch
                    "state": "loose", "state_text": "Ball loose", "pass": None}
        started = False
        for row in out:             # then the ball's flight after it, until a carrier or a dead ball
            if not s_ms < row["clip_ms"] <= s_ms + SHOT_S * 1000:
                continue
            if row["state"] in ("carry", "contested") and not started and row["clip_ms"] <= s_ms + LAG_MS:
                continue            # the 10 Hz holder rule still puts the shooter at the ball just after the strike
            if row["state"] in ("carry", "contested", "out_of_play", "no_data"):
                break
            started = True
            row |= shot
    runs = []
    for ms in range(int(math.ceil(t0 * 10)) * 100, int(t1 * 1000) + 1, 100):
        f = next((x for x in out if x["clip_ms"] == ms), None)
        if f:
            key = (f["state"], f["state_text"], f["null_reason"])
        else:
            near = min(frames, key=lambda r: abs(r["clip_ms"] - ms))
            key = ("no_data", None, near["lost_reason"] or "outside the tracked passage")
        if runs and runs[-1]["key"] == key and runs[-1]["to_clip_ms"] == ms - 100:
            runs[-1]["to_clip_ms"] = ms
        else:
            runs.append({"key": key, "from_clip_ms": ms, "to_clip_ms": ms})
    states = [{"from_clip_ms": r["from_clip_ms"], "to_clip_ms": r["to_clip_ms"], "state": r["key"][0],
               "state_text": r["key"][1], "null_reason": r["key"][2]} for r in runs]
    return {"live": out, "states": states, "live_source": v6p.split("/data/footage/")[-1],
            "always_source": str(v7p).split("/data/footage/")[-1] if v7p.exists() else None}


def window(slug: str, shot_id, t0: float, t1: float, what: str) -> dict:
    b = boxes(slug, shot_id, t0, t1)
    lv = live_rows(slug, shot_id, t0, t1, b["frames"])
    return {"shot_id": shot_id, "what": what, "start_clip_ms": int(t0 * 1000), "end_clip_ms": int(t1 * 1000), **b,
            **{k: lv[k] for k in ("states", "live")},
            "box_def": {"bbox": "[x0, y0, x1, y1] image pixels of the clip frame (1920x1080)",
                        "team": "home | away | referee | null (kit matches neither team: unassigned)",
                        "tracking": "measured = the tracker's own boxes at this frame; interpolated = linear between "
                                    "the two neighbouring samples (one tracker step apart, same camera shot), only for "
                                    "tracks seen on both; lost = no box (lost_reason says why)",
                        "carrier": "the v6 holder at the nearest 10 Hz sample, only in state carry",
                        "names": "name/shirt only within track B's names_live_0 windows; track_id never on screen",
                        "team_rule": __doc__.split("Team per box: ")[1].split(" Carrier:")[0].replace("\n", " ")},
            "source": {**b["source"], "live": lv["live_source"], "always": lv["always_source"]}}


def _passages(rows: list[dict]) -> list[dict]:
    rows = sorted(rows, key=lambda r: (r["slug"], r["holder_track"], r["receiver_track"], r["clip_ms"]))
    out = []
    for r in rows:
        last = out[-1] if out else None
        if (last and last["slug"] == r["slug"] and last["holder_track"] == r["holder_track"]
                and last["receiver_track"] == r["receiver_track"] and r["clip_ms"] - last["to_clip_ms"] <= 100):
            last["to_clip_ms"] = r["clip_ms"]
            last["samples"] += 1
            if r["gap"] > last["gap"]:
                last.update({k: v for k, v in r.items() if k not in ("samples",)} | {"from_clip_ms": last["from_clip_ms"],
                                                                                      "to_clip_ms": r["clip_ms"],
                                                                                      "samples": last["samples"]})
        else:
            out.append(r | {"from_clip_ms": r["clip_ms"], "to_clip_ms": r["clip_ms"], "samples": 1})
    return sorted(out, key=lambda r: -r["gap"])


def decision_gap() -> dict:
    """Eze's square option at 79:10, then every eligible (carrier, receiver) moment in the four PL clips."""
    rows, strikes = [], []
    for slug in CLIPS:
        d = FOOTAGE / slug
        shots = [s for s in json.loads((d / "cache" / "v5" / "shots_0.json").read_text())["result"]["shots"]
                 if s.get("xg") is not None]
        for p in sorted(glob.glob(str(d / "cache" / "v6" / "live_*.json"))):
            if "index" in p:
                continue
            lv = json.loads(open(p).read())["result"]
            for f in lv["frames"]:
                if f["state"] != "carry" or f["shot_now_xg"] is None:
                    continue
                me = f["holder"]
                pl = {q["track_id"]: q for q in f["players"]}
                for o in f["options"]:
                    if (o["xg_receiver"] is None or o["offside_risk"] or o["onside_margin_m"] is None
                            or o["onside_margin_m"] <= 0.5 or o["p_pass"] < 0.3):
                        continue
                    opp = [q for q in f["players"] if q["team"] and q["team"] != f["attacking"]]
                    rx = pl[o["track_id"]]
                    rows.append({"slug": slug, "camera_shot": lv["shot_id"], "clip_ms": f["clip_ms"],
                                 "holder_track": me["track_id"], "holder": me["name"],
                                 "shot_xg": f["shot_now_xg"], "receiver_track": o["track_id"], "receiver": o["name"],
                                 "receiver_shirt": o["shirt"], "receiver_xy": [o["x"], o["y"]],
                                 "xg_receiver": o["xg_receiver"], "p_complete": o["p_pass"],
                                 "xg_after_pass": o["xg_after_pass"], "onside_margin_m": o["onside_margin_m"],
                                 "gap": round(o["xg_receiver"] - f["shot_now_xg"], 2),
                                 "nearest_defender_m": round(min((math.hypot(q["x"] - rx["x"], q["y"] - rx["y"])
                                                                  for q in opp), default=99.0), 1),
                                 "next_state": None})
            for s in shots:                              # the moment a measured shot was taken: the options then
                if lv["start_clip_ms"] <= s["clip_ms"] <= lv["end_clip_ms"]:
                    strikes.append((slug, s, lv["shot_id"]))
    by_strike = []
    for slug, s, cam in strikes:
        cand = [r for r in rows if r["slug"] == slug and r["camera_shot"] == cam
                and s["clip_ms"] - 400 <= r["clip_ms"] <= s["clip_ms"] + 50]
        best = max(cand, key=lambda r: r["xg_receiver"] - s["xg"], default=None)
        by_strike.append({"slug": slug, "strike_clip_ms": s["clip_ms"], "outcome": s.get("outcome"),
                          "shot_xg": s["xg"], "distance_m": s.get("distance_m"),
                          "best_option": best and {k: best[k] for k in ("clip_ms", "holder", "receiver_track",
                                                                        "receiver", "xg_receiver", "p_complete",
                                                                        "xg_after_pass", "onside_margin_m",
                                                                        "nearest_defender_m")},
                          "gap": best and round(best["xg_receiver"] - s["xg"], 2)})
    by_strike.sort(key=lambda r: -(r["gap"] if r["gap"] is not None else -9))
    passages = _passages(rows)
    for r in passages[:10]:                              # what happened next (the v6 state after the passage)
        d = FOOTAGE / r["slug"]
        p = next(p for p in glob.glob(str(d / "cache" / "v6" / "live_*.json")) if "index" not in p
                 and json.loads(open(p).read())["result"]["shot_id"] == r["camera_shot"])
        F = json.loads(open(p).read())["result"]["frames"]
        nxt = next((f for f in F if f["clip_ms"] > r["to_clip_ms"]), None)
        r["next_state"] = nxt and {"clip_ms": nxt["clip_ms"], "state": nxt["state"], "state_text": nxt["state_text"],
                                   "null_reason": nxt["null_reason"]}
    eze = next(r for r in by_strike if r["slug"] == "arsenal-chelsea-2526" and r["strike_clip_ms"] == 1301080)
    return {"rule": GAP_RULE, "eze": eze, "by_strike": by_strike, "passages_top": passages[:10],
            "eligible_samples": len(rows), "clips": list(CLIPS),
            "model": {"xg": "evals.pitchwatch.shotxg.reference_xg (Soccermatics' published logistic fit, 8,451 PL "
                            "2017/18 Wyscout shots): distance and angle only, it does not see defenders",
                      "p_complete": "our LightGBM pass model (packages/heads/artifacts/pass), trained on simulated "
                                    "Kickoff matches; it sees the lane, pressure and receiver space"},
            "source": "cache/v6/live_*.json of each clip (built at ee4eda1 on track B's 54e5047 names), "
                      "cache/v5/shots_0.json"}


def main(argv: list[str] | None = None) -> int:
    from evals.pitchwatch.v3 import write
    for slug, shot_id, t0, t1, what in WINDOWS:
        print(write(slug, "window", int(t0 * 1000), window(slug, shot_id, t0, t1, what), version="v9"))
    print(write("arsenal-chelsea-2526", "decision_gap", 0, decision_gap(), version="v9"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
