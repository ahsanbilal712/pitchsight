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
THREAT_DEF = ("Threat = the higher of the ball carrier's shot-now xG and the best pass's xG after the pass (pass "
              "completion x the reference xG from the receiver's spot); null when the ball is not held in the "
              "opponents' half")
HOLD_M = 2.5                       # holder: the tracked player nearest the ball, within this
FLIGHT_MS = 12.0                   # ball ground speed above this (m/s, over ~0.2 s): a pass or in the air, no holder
SPOTS = ((11.0, GOAL_Y), (L - 11.0, GOAL_Y), (L / 2, GOAL_Y))   # penalty and centre spots: not a ball
SPOT_M = 1.0
ANCHOR_CONF, LONE_CONF, VMAX = 0.5, 0.4, 35.0   # ball choice: a confident detection, or one a ball could reach
GAP_S, TOUCH_M = 1.5, 1.5          # possession carrier: same player either side of a gap this short, nobody this near
STATES = {"carry": "a player has the ball (carrier_source ball: detected at his feet; possession: same player either "
                   "side of a short gap, see rules)", "contested": "carrier known, possession not settled",
          "pass": "ball in flight between two different carriers within 3 s (receiver known on arrival; complete "
                  "false = the other team received it)",
          "loose": "ball loose or not seen", "out_of_play": "ball past a line, or dead after a goal",
          "no_data": "camera fit not trusted"}
PASS_MAX_S = 3.0                   # a longer run between two carriers is not shown as one pass
PLAYER_VMAX = 12.0                 # m/s: a faster jump of one track id is an ID switch, not a player
JITTER_M = 2.5                     # per-frame camera-fit jitter of a foot position, allowed on top of PLAYER_VMAX
SETTLE = 3                         # possession switches after this many consecutive samples (0.3 s)
CLIPS = ("liverpool-mancity-2526", "manutd-mancity-2526", "arsenal-chelsea-2526", "manutd-spurs-2425")
RULES = {"holder": f"tracked player nearest the ball within {HOLD_M} m, else 'ball loose'",
         "possession": f"the holder's team must hold for {SETTLE} samples ({SETTLE / HZ:.1f} s) before possession "
                       "switches; a holder of the other team before then is 'possession unsettled'",
         "own_half": "no xG while the holder or the receiver is in his own half (the model has no shots there)",
         "onside": "offside_risk = within 0.5 m of the line (second-last defender, ball or halfway); never best",
         "keepers": "by position, one per goal, plus track B's hand corrections (moments/overrides.json, same "
                    "camera shot, which also remove referees): opponents for control, never pass options",
         "trusted": "false where the camera fit is not trusted at the frame, or no ball and no possession carrier",
         "ball": f"tiled full-resolution detection plus the full-frame one, minus the penalty and centre spots; conf >= "
                 f"{ANCHOR_CONF} stands alone, weaker only within {VMAX:.0f} m/s of the nearest confident one (1 s) "
                 f"or at conf >= {LONE_CONF} with none near",
         "possession_carrier": f"the same player at the ball before and after a gap of <= {GAP_S} s with the ball "
                               f"unseen and no other player within {TOUCH_M} m of him keeps it through the gap "
                               "(carrier_source 'possession'); never across a ball seen elsewhere",
         "in_flight": f"no holder while the ball's ground speed exceeds {FLIGHT_MS:.0f} m/s over ~0.2 s (a pass or a "
                      "ball in the air, whose ground position a single camera cannot place), or where it cannot be "
                      "measured (fewer than two ball detections within 0.12 s)",
         "dead_ball": "null once the ball is past a line, and from a goal's reviewed strike (a disallowed goal: its "
                      "tagged second) to the end of the shot",
         "goal_line": "positions on or behind the goal line are valued 0.5 m out (the model has no shots there)"}


def _period(slug: str, clip_ms: int) -> int:
    ev = [json.loads(x) for x in (FOOTAGE / slug / "events.jsonl").read_text().splitlines()]
    return min(ev, key=lambda e: abs(e["attrs"]["clip_ms"] - clip_ms))["period"]


def _goal_strikes(slug: str) -> list[int]:
    """When the clip's goals, counted or disallowed, kill the ball: the reviewed strike, else (a disallowed goal
    without one) the tagged second. After one, the ball is dead until the restart."""
    rows = json.loads((FOOTAGE / "insights" / "shots_xg.json").read_text())["shots"]
    return [r.get("release_clip_ms") or r["clip_ms"] for r in rows
            if r["slug"] == slug and (r.get("goal") or r.get("disallowed")) and (r.get("release_clip_ms") or r.get("disallowed"))]


def identity_span(F: list[dict], tid: int, t_link: float) -> tuple[float, float] | None:
    """The stretch of a track around t_link that is still the same man: it ends where the track's kit team changes
    and holds for three observations, or it jumps further than PLAYER_VMAX allows plus JITTER_M (an ID switch, e.g.
    manutd-mancity 104 track 4 at 878.1 s)."""
    obs = [(r["t"], p["team"], p["xy"]) for r in F for p in r["players"] if p["track_id"] == tid and p["xy"]]
    if not obs:
        return None
    k = min(range(len(obs)), key=lambda i: abs(obs[i][0] - t_link))
    if abs(obs[k][0] - t_link) > 0.3:
        return None
    team = obs[k][1]

    def same(i, j):                                  # j steps on from i (either direction)
        if math.dist(obs[i][2], obs[j][2]) > PLAYER_VMAX * abs(obs[j][0] - obs[i][0]) + JITTER_M:
            return False
        step = 1 if j > i else -1
        run = [obs[x][1] for x in range(j, j + 3 * step, step) if 0 <= x < len(obs)]
        return not (len(run) == 3 and all(tm is not None and tm != team for tm in run))   # a kit flip that holds
    lo = hi = k
    while lo > 0 and same(lo, lo - 1):
        lo -= 1
    while hi < len(obs) - 1 and same(hi, hi + 1):
        hi += 1
    return obs[lo][0], obs[hi][0]


def _hand(slug: str, shot_id, F: list[dict]) -> tuple[dict[int, list], dict[int, str]]:
    """track id -> [(t0, t1, name, shirt)] and track id -> fix ("referee" | "home" | "away" | "<side>:goalkeeper").
    First track B's names_live_0.json (crop reads per track and window, used exactly within its window); then
    names_verified.json ("names" links and verified "shots"), each within the linked track's identity span: a link
    to a moment in this camera shot names that moment's track (with its "#NN" shirt), an event link names the
    shooter at that shot's reviewed strike (his strike-window track, or the player within 1.5 m of his spot at the
    strike frame). Fixes from moments/overrides.json."""
    import re

    from footage.freeze import load
    from footage.from_tracks import overrides
    nv = json.loads((FOOTAGE / slug / "names_verified.json").read_text())
    links = [(name, link) for name, v in nv["names"].items() for link in v["links"]]
    links += [(v["name"], {"event": ev}) for ev, v in (nv.get("shots") or {}).items() if v.get("name")]
    moments, fixes = {}, {}
    for p in (FOOTAGE / slug / "moments").glob("[0-9]*.json"):
        m = load(slug, int(p.stem))
        if (m.get("tracking") or {}).get("shot_id") == shot_id:
            moments[int(p.stem)] = m
            fixes.update({int(k): v for k, v in overrides(FOOTAGE / slug, int(p.stem)).items()})
    rows = {r["event_id"]: r for r in json.loads((FOOTAGE / "insights" / "shots_xg.json").read_text())["shots"]
            if r["slug"] == slug and r.get("release_clip_ms")}
    labels: dict[int, list] = {}
    live = FOOTAGE / slug / "cache" / "v6" / "names_live_0.json"   # track B's per-window reads come first
    for q in (json.loads(live.read_text())["result"]["players"] if live.exists() else []):
        if q["tracks"] == f"tracks/{shot_id}.json" and (q.get("name") or q.get("shirt")):
            labels.setdefault(q["track_id"], []).append((q["from_clip_ms"] / 1000, q["to_clip_ms"] / 1000,
                                                         q.get("name"), q.get("shirt")))
    tagged = []                                       # (track id, link time, name, shirt)
    for name, link in links:
        if "event" not in link:
            m = moments.get(link.get("clip_ms"))
            q = m and next((q for q in m["players"] if q.get("label") == link.get("label") and "track_id" in q), None)
            if q:
                shirt = int(q["label"][1:]) if re.fullmatch(r"#\d+", q["label"]) else None
                tagged.append((q["track_id"], link["clip_ms"] / 1000, name, shirt))
            continue
        r = rows.get(link["event"])
        if not r:
            continue
        t = r["release_clip_ms"] / 1000
        if f"x{r['event_id']}" == str(shot_id):       # the strike window's own track ids
            tid = r.get("shooter_track")
            if tid is None and re.fullmatch(r"t\d+", link.get("label") or ""):
                tid = int(link["label"][1:])
            if tid is not None:
                tagged.append((tid, t, name, None))
            continue
        fr = min(F, key=lambda f: abs(f["t"] - t))
        if abs(fr["t"] - t) > 0.1 or not fr["calib_ok"]:
            continue
        sx, sy = r["shooter_xy_near"]
        near = [(math.hypot(q["xy"][0] - sx, (W - q["xy"][1]) - sy), q["track_id"]) for q in fr["players"] if q["xy"]]
        if near and min(near)[0] <= 1.5:
            tagged.append((min(near)[1], t, name, None))
    read = set(labels)                               # a track with a window read is labelled by it alone
    for tid, t, name, shirt in tagged:
        if tid in read:
            continue
        span = identity_span(F, tid, t)
        if span:
            labels.setdefault(tid, []).append((*span, name, shirt))
    return labels, fixes


def _label_at(labels: dict[int, list], tid: int, t: float) -> tuple[str | None, int | None]:
    name = shirt = None
    for t0, t1, n, sh in labels.get(tid, []):
        if t0 - 1e-6 <= t <= t1 + 1e-6:
            name, shirt = name or n, shirt or sh
    return name, shirt


def _near(xy) -> tuple[float, float]:
    return round(float(xy[0]), 2), round(W - float(xy[1]), 2)


def _ball_series(slug: str, shot_id, samples: list[tuple[float, dict]]) -> list[dict | None]:
    """The ball at each sample: candidates from the tiled pass (ball_tiles) and the full-frame detection, minus the
    penalty and centre spots (the full-frame detector's commonest false ball); a candidate with conf >= ANCHOR_CONF
    stands on its own, a weaker one only within VMAX of the nearest anchor (within 1 s) or, with no anchor near,
    at conf >= LONE_CONF."""
    path = FOOTAGE / slug / "tracks" / f"{shot_id}.ball_tiled.json"
    tiled = json.loads(path.read_text())["frames"] if path.exists() else {}
    cands = []
    for _, r in samples:
        c = [{**b, "source": "tiled"} for b in tiled.get(str(r["frame"]), [])]
        if r["ball"] and r["ball"].get("xy"):
            c.append({**r["ball"], "source": "full"})
        keep = []
        for b in c:
            x, y = _near(b["xy"])
            if not any(math.hypot(x - sx, y - sy) < SPOT_M for sx, sy in SPOTS):
                keep.append({"x": x, "y": y, "px": [round(v) for v in b["px"]], "conf": b["conf"],
                             "source": b["source"]})
        cands.append(sorted(keep, key=lambda b: -b["conf"]))
    anchors = [(t, b) for (t, _), c in zip(samples, cands, strict=True) for b in c[:1] if b["conf"] >= ANCHOR_CONF]
    out = []
    for (t, _), c in zip(samples, cands, strict=True):
        near = min(((abs(ta - t), a) for ta, a in anchors if 0 < abs(ta - t) <= 1.0), key=lambda x: x[0],
                   default=None)
        pick = None
        for b in c:
            if b["conf"] >= ANCHOR_CONF or (near and math.hypot(b["x"] - near[1]["x"], b["y"] - near[1]["y"])
                                            <= VMAX * near[0]) or (near is None and b["conf"] >= LONE_CONF):
                pick = b
                break
        out.append(pick)
    return out


def _who(p: dict) -> dict:
    return {k: p[k] for k in ("label", "track_id", "name", "shirt")}


def _say(p: dict) -> str:
    return p["name"] or (f"#{p['shirt']}" if p["shirt"] else "")


def live_shot(slug: str, shot_id) -> dict:
    from evals.pitchwatch.shotxg import HOME_ATTACKS_P2
    from footage.clips import CLIPS as META
    from footage.tag import side

    tracks = json.loads((FOOTAGE / slug / "tracks" / f"{shot_id}.json").read_text())
    fps, F = tracks["fps"], tracks["frames"]
    team_side = {int(k): side(v.get("name", ""), META[slug]) for k, v in tracks["teams"].items()}
    keepers = keeper_tracks(tracks)
    labels, fixes = _hand(slug, shot_id, F)
    start, end = F[0]["t"], F[-1]["t"]
    period = _period(slug, int(start * 1000))
    home_plus = HOME_ATTACKS_P2[slug] * (1 if period == 2 else -1) > 0
    by_frame = {r["frame"]: r for r in F}
    dead_from = min((g for g in _goal_strikes(slug) if start * 1000 <= g <= end * 1000), default=None)
    samples = []
    for t in np.arange(math.ceil(start * HZ) / HZ, end + 1e-9, 1 / HZ):
        r = by_frame[min(by_frame, key=lambda f: abs(f - t * fps))]
        if abs(r["frame"] / fps - t) <= 0.5 / HZ:
            samples.append((float(t), r))
    balls = _ball_series(slug, shot_id, samples)

    # pass 1: players, ball, reason and the ball-based carrier at each sample
    frames = []
    for i, (t, r) in enumerate(samples):
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
            name, shirt = _label_at(labels, p["track_id"], r["t"])
            players.append({"label": f"t{p['track_id']}", "track_id": p["track_id"], "name": name,
                            "shirt": shirt, "team": team,
                            "keeper": keeper, "x": x, "y": y,
                            "px": [round(v) for v in p["foot_px"]]})
        row = {"clip_ms": int(round(t * 1000)), "trusted": False, "state": None, "state_text": None,
               "null_reason": None, "ball": None, "carrier_source": None, "attacking": None, "attacks": None,
               "holder": None, "in_opponent_half": None, "shot_now_xg": None, "options": [], "best": None,
               "threat": None, "threat_from": None, "pass": None, "players": players, "_carrier": None}
        frames.append(row)
        b = balls[i]
        if b:
            ends = [j for j in (i - 1, i + 1) if 0 <= j < len(balls) and balls[j]]
            if ends:                                 # the faster of the two steps through this sample
                b = {**b, "speed_ms": round(max(math.hypot(balls[j]["x"] - b["x"], balls[j]["y"] - b["y"])
                                                / abs(samples[j][0] - t) for j in ends), 1)}
            row["ball"] = b
        if dead_from is not None and row["clip_ms"] > dead_from:
            row["null_reason"] = "dead ball after the goal"
        elif not r["calib_ok"]:
            row["null_reason"] = "camera fit not trusted"
        elif b is None:
            row["null_reason"] = "ball not detected"
        elif not (0 <= b["x"] <= L and 0 <= b["y"] <= W):
            row["null_reason"] = "ball out of play"
        elif "speed_ms" not in b:                    # one detection only: cannot tell a held ball from one in the air
            row["null_reason"] = "ball speed not measurable"
        elif b["speed_ms"] > FLIGHT_MS:
            row["null_reason"] = "ball in flight"
        else:
            out = [p for p in players if p["team"] and not p["keeper"]]
            near = min(out, key=lambda p: math.hypot(p["x"] - b["x"], p["y"] - b["y"]), default=None)
            if near is None or math.hypot(near["x"] - b["x"], near["y"] - b["y"]) > HOLD_M:
                row["null_reason"] = "ball loose"
            else:
                row["_carrier"], row["carrier_source"] = near, "ball"
        row["trusted"] = bool(r["calib_ok"]) and b is not None

    # pass 2: the same player at the ball before and after a short gap with no ball seen and nobody within touching
    # distance of him keeps it through the gap
    fill = {"ball not detected", "ball speed not measurable"}
    i = 0
    while i < len(frames):
        if frames[i]["_carrier"] is None:
            i += 1
            continue
        j = i + 1
        while j < len(frames) and frames[j]["_carrier"] is None and frames[j]["null_reason"] in fill:
            j += 1
        tid = frames[i]["_carrier"]["track_id"]
        if (j < len(frames) and j > i + 1 and frames[j]["_carrier"] is not None
                and frames[j]["_carrier"]["track_id"] == tid and (j - i - 1) / HZ <= GAP_S):
            run = []
            for k in range(i + 1, j):
                me = next((p for p in frames[k]["players"] if p["track_id"] == tid), None)
                if me is None or any(math.hypot(p["x"] - me["x"], p["y"] - me["y"]) <= TOUCH_M
                                     for p in frames[k]["players"] if p is not me):
                    run = None
                    break
                run.append((k, me))
            for k, me in run or []:
                frames[k].update({"_carrier": me, "carrier_source": "possession", "null_reason": None,
                                  "trusted": True})
        i = j

    # pass 3: possession debounce, then the carrier's values
    possession, cand, cand_n = None, None, 0
    for row in frames:
        near = row["_carrier"]
        if near is None:
            continue
        team = near["team"]
        if team == possession:
            cand, cand_n = None, 0
        else:
            cand_n = cand_n + 1 if team == cand else 1
            cand = team
            if cand_n >= SETTLE:
                possession, cand, cand_n = team, None, 0
        row["holder"] = {k: near[k] for k in ("label", "track_id", "name", "shirt", "x", "y", "px")}
        if team != possession:
            row["null_reason"] = "possession unsettled"
            continue
        attacks_plus = home_plus == (team == "home")
        u0, v0 = team_frame((near["x"], near["y"]), attacks_plus)
        row.update({"attacking": team, "attacks": "+x" if attacks_plus else "-x", "in_opponent_half": bool(u0 >= L / 2)})
        if u0 < L / 2:
            row["null_reason"] = "own half"
            continue
        out = [p for p in row["players"] if p["team"] and not p["keeper"]]
        mates = [p for p in out if p["team"] == team and p is not near]
        opps = [p for p in row["players"] if p["team"] and p["team"] != team]
        shot = shot_xg(min(u0, L - 0.5), v0)              # same goal-line clamp as the receivers
        opts = options_xg(near, mates, opps, attacks_plus) if mates else []
        who = {p["label"]: p for p in mates}
        row["options"] = [{k: o[k] for k in ("label", "name", "x", "y", "p_pass", "xg_receiver", "xg_after_pass",
                                             "onside_margin_m", "offside_risk")}
                          | {k: who[o["label"]][k] for k in ("track_id", "shirt", "px")} for o in opts]
        best = next((o for o in opts if not o["offside_risk"] and o["xg_after_pass"] is not None), None)
        row["shot_now_xg"] = round(shot, 2)
        row["best"] = best and {"label": best["label"], "track_id": who[best["label"]]["track_id"],
                                "name": best["name"], "shirt": who[best["label"]]["shirt"],
                                "xg_after_pass": best["xg_after_pass"]}
        bxg = best["xg_after_pass_exact"] if best else -1.0
        row["threat"] = round(max(shot, bxg), 2)
        row["threat_from"] = "pass" if bxg > shot else "shot"

    # pass 4: an explicit state for every sample, so the HUD is never blank
    for row in frames:
        reason = row["null_reason"]
        if row["holder"]:
            row["state"] = "carry" if reason != "possession unsettled" else "contested"
            row["state_text"] = (f"{_say(row['holder'])} on the ball" if _say(row["holder"]) else "On the ball") \
                if row["state"] == "carry" else "Contested"
        elif reason in ("ball out of play", "dead ball after the goal"):
            row["state"], row["state_text"] = "out_of_play", "Out of play" if reason == "ball out of play" else "Goal"
        elif reason == "camera fit not trusted":
            row["state"], row["state_text"] = "no_data", None
        else:
            row["state"], row["state_text"] = "loose", "Ball loose"
    i = 0
    while i < len(frames):                           # a run between two carriers with the ball in flight: a pass
        if frames[i]["state"] != "loose":
            i += 1
            continue
        j = i
        while j < len(frames) and frames[j]["state"] == "loose":
            j += 1
        a, b = (frames[i - 1] if i > 0 else None), (frames[j] if j < len(frames) else None)
        flight = any(frames[k]["null_reason"] == "ball in flight" for k in range(i, j))
        if (flight and a and b and (j - i) / HZ <= PASS_MAX_S and a["state"] in ("carry", "contested")
                and b["state"] in ("carry", "contested")
                and a["holder"]["track_id"] != b["holder"]["track_id"]):
            frm, to = a["_carrier"], b["_carrier"]
            complete = frm["team"] == to["team"]
            at_release = next((o["xg_after_pass"] for o in a["options"] if o["track_id"] == to["track_id"]), None)
            info = {"from": _who(frm), "to": _who(to), "complete": complete, "release_clip_ms": a["clip_ms"],
                    "arrival_clip_ms": b["clip_ms"], "xg_after_pass_at_release": at_release}
            text = (f"Pass in flight → {_say(to)}" if _say(to) else "Pass in flight") if complete else \
                (f"Pass intercepted by {_say(to)}" if _say(to) else "Pass intercepted")
            for k in range(i, j):
                frames[k].update({"state": "pass", "state_text": text, "pass": info})
        i = j
    for row in frames:
        del row["_carrier"]
    return {"shot_id": shot_id, "period": period, "home_attacks": "+x" if home_plus else "-x", "hz": HZ,
            "step_ms": 1000 // HZ, "start_clip_ms": frames[0]["clip_ms"], "end_clip_ms": frames[-1]["clip_ms"],
            "image_size": _image_size(slug, shot_id), "formula": SOURCE, "rules": RULES, "threat_def": THREAT_DEF,
            "states": STATES,
            "labels": "on screen: name (track B's names_verified.json), else shirt (hand-read #NN), else nothing; "
                      "each only within the linked track's identity span (same kit team, no jump over "
                      f"{PLAYER_VMAX:.0f} m/s); label/track_id are internal ids, never shown",
            "coordinates": "pitch metres, x from the left goal line, y from the NEAR touchline (moment-file frame); "
                           "px = image pixel (feet / ball centre)",
            "frames": frames,
            "source": {"tracks": f"{slug}/tracks/{shot_id}.json", "calib": f"{slug}/calib/{shot_id}.json",
                       "ball": f"{slug}/tracks/{shot_id}.ball_tiled.json (tiled) + the full-frame detection",
                       "pass_model": "packages/heads/artifacts/pass", "shot_model": "evals.pitchwatch.shotxg.reference_xg",
                       "names": "track B's names_live_0.json and names_verified.json"}}


def _image_size(slug: str, shot_id) -> list[int] | None:
    p = FOOTAGE / slug / "calib" / f"{shot_id}.json"
    return json.loads(p.read_text()).get("image_size") if p.exists() else None


def _spans(slug: str) -> dict:
    out = {}
    for p in sorted((FOOTAGE / slug / "tracks").glob("*.json")):
        if "." in p.stem:                            # <shot>.ball_tiled.json
            continue
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
                      "valued_by_possession": sum(f["threat"] is not None and f["carrier_source"] == "possession"
                                                  for f in fr),
                      "state_frames": sum(f["state"] != "no_data" for f in fr),
                      "states": {k: sum(f["state"] == k for f in fr) for k in STATES},
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
        verified = json.loads((FOOTAGE / slug / "names_verified.json").read_text()).get("shots") or {}
        rows = [{k: s.get(k) for k in ("event_id", "clock", "clip_ms", "team", "team_name", "shooter", "x", "y",
                                       "distance_m", "xg", "outcome", "goal", "penalty", "header", "set_piece",
                                       "disallowed", "reviewed", "reason", "camera_ok")}
                for s in shots["shots"]]
        for r in rows:                               # track B's verified shooters (shirt reads at the strike)
            v = verified.get(r["event_id"]) or {}
            if v.get("name") and not r["shooter"].get("name"):
                r["shooter"] = {**r["shooter"], "name": v["name"],
                                "name_source": f"names_verified.json shots: {v.get('source')}"}
        named = {(r["clip_ms"], r["team"]): r["shooter"].get("name") for r in rows}
        keep = {k: race[k] for k in race if k not in ("beat", "slug", "match_id")}
        keep["events"] = [{**e, "label": e.get("label") or named.get((e["clip_ms"], e["team"]))}
                          for e in keep["events"]]
        out.append(str(write(slug, "xg_running", 0, {**keep, "source": {"v5": f"{slug}/cache/v5/xg_race_0.json",
                                                                        "names": f"{slug}/names_verified.json"}},
                             version="v6")))
        out.append(str(write(slug, "shot_map", 0, {"shots": rows, "formula": SOURCE,
                                                   "coordinates": "moment-file frame (y from the near touchline), "
                                                                  "the shooter's spot at the strike frame",
                                                   "goal_y": GOAL_Y, "source": {"v5": f"{slug}/cache/v5/shots_0.json",
                                                                              "names": f"{slug}/names_verified.json"}},
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
