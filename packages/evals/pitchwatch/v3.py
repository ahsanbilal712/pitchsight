"""Video v3 beats in track C's overlay format (shared note track-c-v3-overlay-formats.md), from Pitchwatch insights.

    python -m evals.pitchwatch.v3 speed_gun | pass_xray | offside_line | card

Each beat goes to data/footage/<slug>/cache/v3/<beat>_<clip_ms>.json as {"record": "tool_result", "result": {...}}.
Pitch metres in the moment-file frame (y from the NEAR touchline: y_near = 68 - y_far); times as clip_ms. Every
number carries its source; tracking numbers carry the window and the stated error.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from evals.pitchwatch.insights import FOOTAGE, defensive_line, load, speed_gun, xray

W = 68.0


def near(xy):
    return [round(float(xy[0]), 2), round(W - float(xy[1]), 2)]


def ms(t: float) -> int:
    return int(round(t * 1000))


def write(slug: str, beat: str, clip_ms: int, result: dict) -> Path:
    """Through track B's footage.v3.write_beat: the model_cache envelope ($schema, schema_version, record) and an
    entry in the clip's cache manifest, so validate_schemas and the replay index see it."""
    from footage.v3 import write_beat
    return Path(write_beat(slug, beat, clip_ms, result))


def speed_gun_beat() -> Path:
    slug = "manutd-spurs-2425"
    res = speed_gun(slug, [23, 25], [(250.0, "holder"), (260.0, "holder")])
    samples, top = [], (None, None)
    for seg in res["segments"]:
        for r in seg["frames"][::2]:                       # 15 Hz
            samples.append({"clip_ms": ms(r["t"]), "x": near(r["xy"])[0], "y": near(r["xy"])[1],
                            "speed_kmh": r["kmh"], "shot_id": seg["shot"]})
        for r in seg["frames"]:
            if r["kmh"] is not None and (top[0] is None or r["kmh"] > top[0]):
                top = (r["kmh"], ms(r["t"]))
    return write(slug, "speed_gun", samples[0]["clip_ms"], {
        "player": {"label": "VdV", "name": "Micky van de Ven", "team": "Tottenham Hotspur",
                   "track_ids": {str(s["shot"]): s["track_ids"] for s in res["segments"]}},
        "shot_id": [23, 25], "samples": samples, "top_speed_kmh": top[0], "top_speed_clip_ms": top[1],
        "distance_m": res["distance_m"], "start_clip_ms": samples[0]["clip_ms"], "end_clip_ms": samples[-1]["clip_ms"],
        "gaps": [{"from_clip_ms": ms(g["from_t"]), "to_clip_ms": ms(g["to_t"]), "straight_line_m": g["straight_line_m"]}
                 for g in res["gaps"]],
        "error_note": "Positions from RF-DETR + ByteTrack through the per-frame camera fit (main camera shot 23, reverse "
                      "angle shot 25 with its own camera); about 0.5 m per position, smoothed with a 0.6 s Savitzky-Golay "
                      "filter before differentiating. Speeds are null where the camera fit is not trusted or above 37.5 km/h. "
                      "Distance = the trusted path in both shots plus the straight line across the close-up gap "
                      f"({res['gaps'][0]['from_t']:.1f}-{res['gaps'][0]['to_t']:.1f} s), so it is a lower bound.",
        "source": {"tracks": [f"{slug}/tracks/23.json", f"{slug}/tracks/25.json"],
                   "calib": [f"{slug}/calib/23.json", f"{slug}/calib/25.json"], "method": res["method"]}})


def pass_xray_beat(slug: str = "manutd-spurs-2425", shot: int = 23, t0: float = 238.0,
                   t1: float = 243.0) -> Path:
    res = xray(slug, shot)
    by = {r["t"]: r for r in res["frames"] if r["calib_ok"]}
    ts = sorted(by)
    samples = []
    for t in np.arange(t0, t1 + 1e-9, 0.5):
        near_t = min(ts, key=lambda x: abs(x - t))
        if abs(near_t - t) > 0.25:
            continue
        r = by[near_t]
        samples.append({"clip_ms": ms(near_t), "holder": f"t{r['carrier']}", "team": r["team"],
                        "shoot_now_p_goal": r["shoot_now_xg"],
                        "options": [{"label": f"t{o['track_id']}", "name": None, "x": near(o["xy"])[0],
                                     "y": near(o["xy"])[1], "p_goal": o["value"], "p_pass": o["p_pass"],
                                     "xg_if_shot": o["xg_if_shot"]} for o in r["options"]]})
    teams = res.get("teams") or {}
    return write(slug, "pass_xray", samples[0]["clip_ms"], {
        "team": {k: v.get("name") for k, v in teams.items()}, "shot_id": shot, "samples": samples,
        "n": None, "horizon_s": None, "seed": None, "engine": "heads: PassHead x XGHead (lightgbm, feature f1)",
        "note": "p_goal = P(pass completes) x xG(shot from the receiver's spot), not a rollout (no n or seed): the "
                "outcome heads on features from the tracked positions, players in view only. Labels are track ids; "
                "names come from track B's moment labels, unnamed where not identified. shoot_now_p_goal = the holder's "
                "own xG from where he stands. Keepers (one per goal, by position) and reviewed exclusions are not "
                "options.",
        "source": {"tracks": f"{slug}/tracks/{shot}.json", "calib": f"{slug}/calib/{shot}_refined.json",
                   "heads": "packages/heads/artifacts/{pass,xg}"}})


def offside_beat(slug: str = "liverpool-mancity-2526", shot: int = 62, uncertainty_m: float = 0.3) -> list[Path]:
    res = defensive_line(slug, shot)
    tracks, _ = load(slug, shot)
    F = {r["frame"]: r for r in tracks["frames"]}
    fps = tracks["fps"]
    out = []
    for i, r in enumerate(res["frames"]):
        if "pass" not in r or not r["defending"] or not r["calib_ok"]:
            continue
        team = r["defending"]["team"]
        d = res["directions"][str(team)]
        samples = []
        for q in res["frames"][max(0, i - int(2 * fps / tracks["step"])):i + 1]:
            if not q["defending"] or q["defending"]["team"] != team:
                continue
            fr = F[q["frame"]]
            dfn = [p for p in fr["players"] if p["xy"] and (p["team"] == team or p["team"] is None)]
            att = [p for p in fr["players"] if p["xy"] and p["team"] == 1 - team]
            dl = min(dfn, key=lambda p: abs(p["xy"][0] - q["defending"]["line_x"]))
            ad = (max if d < 0 else min)(att, key=lambda p: p["xy"][0])
            samples.append({"clip_ms": ms(q["t"]), "line_x": q["defending"]["line_x"], "defender": f"t{dl['track_id']}",
                            "attacker": f"t{ad['track_id']}", "attacker_x": q["defending"]["most_advanced_attacker_x"]})
        if not samples:
            continue
        last = samples[-1]
        out.append(write(slug, "offside_line", ms(r["t"]), {
            "shot_id": shot, "attacking_dir": "+x" if d < 0 else "-x", "pass_clip_ms": ms(r["t"]),
            "pass": {"from": f"t{r['pass']['from']}", "to": f"t{r['pass']['to']}"}, "samples": samples,
            "gap_m": r["defending"]["beyond_m"], "uncertainty_m": uncertainty_m,
            "defender": last["defender"], "attacker": last["attacker"],
            "note": "gap_m > 0: the attacker is past the second-last defender when the pass is played (offside "
                    "position); < 0 onside. Line from tracked feet through the paint-refined camera; uncertainty = the "
                    "camera's check-point error near this box. Only players in view count.",
            "source": {"tracks": f"{slug}/tracks/{shot}.json", "calib": f"{slug}/calib/{shot}_refined.json"}}))
    return out


def card() -> Path:
    from evals.pitchwatch.metrics import footage_metrics
    m = footage_metrics()
    ball = {}
    for slug in m["clips"]:
        n = hit = 0
        for p in (FOOTAGE / slug / "tracks").glob("[0-9]*.json"):
            frames = json.loads(p.read_text())["frames"]
            n += len(frames)
            hit += sum(1 for r in frames if r["ball"])
        if n:
            ball[slug] = {"frames": n, "ball_detected_share": round(hit / n, 3)}
    res = {"clips": m["clips"], "ball": ball,
           "ball_note": "share of tracked wide frames with a ball detection (RF-DETR sports-ball class, conf >= 0.2): "
                        "a detection rate, not recall (balls are not hand-labelled); includes false detections",
           "definitions": m["definitions"]}
    out = Path(__file__).with_name("results.json")
    out.write_text(json.dumps(res, indent=1) + "\n")
    return out


def main(argv: list[str] | None = None) -> int:
    kind = (argv or sys.argv[1:])[0]
    out = {"speed_gun": speed_gun_beat, "pass_xray": pass_xray_beat, "offside_line": offside_beat, "card": card}[kind]()
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
