"""Track A's v3 insight files -> the beat formats demo.live draws (shared notes: track-a-v3-insights.md in,
track-c-v3-overlay-formats.md out).

Track A writes per-frame files in the Pitchwatch frame (y from the far touchline, players as track ids); the beats
want the moment-file frame (y from the near touchline), sampled for the screen, with names where the moment file
knows them. A moment spec names its adapter (`adapter: xray | line`) and the adapter writes the beat's JSON under
packages/demo/out/footage/data/ (derived, git-ignored), which the spec's `data` then points at.
"""

from __future__ import annotations

import json
from pathlib import Path

from demo.footage import PITCH_W

ROOT = Path(__file__).resolve().parents[2]
FOOTAGE = ROOT / "data" / "footage"
DATA_OUT = ROOT / "packages" / "demo" / "out" / "footage" / "data"
METRICS = FOOTAGE / "insights" / "metrics.json"


def names(slug: str, moment_ms: int | None) -> dict[int, dict]:
    """track_id -> {label, name} from a moment file of the clip (T-107), where it knows them."""
    if moment_ms is None:
        return {}
    doc = json.loads((FOOTAGE / slug / "moments" / f"{moment_ms}.json").read_text())
    return {p["track_id"]: {"label": p["label"], "name": p.get("name")} for p in doc["players"]
            if p.get("track_id") is not None}


def positions(slug: str, shot: int) -> dict[int, dict[int, list[float]]]:
    """frame -> track_id -> [x, y] (moment-file frame) from tracks/<shot>.json."""
    tr = json.loads((FOOTAGE / slug / "tracks" / f"{shot}.json").read_text())
    return {f["frame"]: {p["track_id"]: [p["xy"][0], PITCH_W - p["xy"][1]] for p in f["players"] if p.get("xy")}
            for f in tr["frames"]}


def xray(spec: dict) -> dict:
    """xray_<shot>.json (per frame: carrier, options ranked by value = P(pass completes) x xG from the receiver's
    spot) -> pass_xray samples every `step_s` over [t0, t1], frames with trusted calibration only."""
    slug, shot = spec["clip"], int(spec["shot_id"])
    src = json.loads((FOOTAGE / slug / "insights" / f"xray_{shot}.json").read_text())
    who = names(slug, spec.get("names_from"))
    pos = positions(slug, shot)
    t0, t1, step = spec["t0"], spec["t1"], float(spec.get("step_s", 0.5))
    frames = [f for f in src["frames"] if t0 <= f["t"] <= t1 and f["calib_ok"] and f["options"]]
    samples, next_t = [], -1.0
    for f in frames:
        if f["t"] < next_t:
            continue
        next_t = f["t"] + step
        holder = pos.get(f["frame"], {}).get(f["carrier"])
        samples.append({"clip_ms": int(round(f["t"] * 1000)), "holder": str(f["carrier"]), "holder_xy": holder,
                        "options": [{"label": str(o["track_id"]),
                                     "name": (who.get(o["track_id"]) or {}).get("name"),
                                     "x": o["xy"][0], "y": PITCH_W - o["xy"][1], "p_goal": o["value"],
                                     "p_pass": o["p_pass"], "xg_if_shot": o["xg_if_shot"]} for o in f["options"]]})
    return {"team": "home", "shot_id": shot, "samples": samples, "method": src["method"],
            "source": f"data/footage/{slug}/insights/xray_{shot}.json"}


def line(spec: dict) -> dict:
    """line_<shot>.json (per frame: the defending team's line and the most advanced attacker, beyond_m at passes)
    -> an offside-line beat over [t0, pass] holding at the pass; the uncertainty is track A's calibration check
    (mean error of 20 hand-checked points, metrics.json)."""
    slug, shot = spec["clip"], int(spec["shot_id"])
    src = json.loads((FOOTAGE / slug / "insights" / f"line_{shot}.json").read_text())
    t0, t_pass = spec["t0"], spec["pass_t"]
    rows = [f for f in src["frames"] if t0 <= f["t"] <= t_pass + 1e-6 and f.get("defending") and f["calib_ok"]]
    at = min(rows, key=lambda f: abs(f["t"] - t_pass))
    check = json.loads(METRICS.read_text())["clips"][slug]["calibration"]["check_points_m"]
    return {"shot_id": shot, "pass_clip_ms": int(round(at["t"] * 1000)),
            "attacking_dir": "+x" if src["directions"][str(1 - at["defending"]["team"])] > 0 else "-x",
            "samples": [{"clip_ms": int(round(f["t"] * 1000)), "line_x": f["defending"]["line_x"],
                         "attacker_x": f["defending"]["most_advanced_attacker_x"]} for f in rows],
            "gap_m": at["defending"]["beyond_m"], "uncertainty_m": check["mean"],
            "uncertainty_source": f"metrics.json {slug} calibration.check_points_m (n = {check['n']})",
            "source": f"data/footage/{slug}/insights/line_{shot}.json"}


def xray_goal10(spec: dict) -> dict:
    """pass_xray_goal10_<ms>.json (track A, v4: each option's goal chance in the next 10 s, Wilson 95%) -> the
    pass_xray beat: pass options as tagged players, the shot as the 'shooting now' row; within [t0, t1]."""
    src = json.loads((ROOT / spec["source_file"]).read_text())["result"]
    t0, t1 = spec.get("t0", 0), spec.get("t1", 1e9)
    samples = []
    for x in src["samples"]:
        if not t0 <= x["clip_ms"] / 1000 <= t1 or not x.get("options"):   # a sample with a note and no options
            continue
        passes = [o for o in x["options"] if o["kind"] == "pass" and o.get("x") is not None]
        shoot = next((o for o in x["options"] if o["kind"] == "shoot"), None)
        samples.append({"clip_ms": x["clip_ms"], "holder": x["holder"], "holder_xy": x.get("holder_xy"),
                        "shoot_now_p_goal": shoot["p_goal_10s"] if shoot else None,
                        "options": [{"label": o["label"], "name": o.get("name"), "x": o["x"], "y": o["y"],
                                     "p_goal": o["p_goal_10s"], "ci95": o["ci95"]} for o in passes]})
    return {"team": src.get("team"), "shot_id": spec.get("shot_id"), "samples": samples, "n": None,
            "source": spec["source_file"]}


def xray_xg(spec: dict) -> dict:
    """pass_xray_xg_<ms>.json (track A, v5: each pass option's xG after the pass, P(complete) x xG at the
    receiver's spot) -> the pass_xray beat, valued in xG; the holder's own shot as 'shooting now'. Only the
    after-pass value is ever printed (never the receiver component)."""
    src = json.loads((ROOT / spec["source_file"]).read_text())
    src = src.get("result", src)
    t0, t1 = spec.get("t0", 0), spec.get("t1", 1e9)
    samples = []
    for x in src["samples"]:
        if not t0 <= x["clip_ms"] / 1000 <= t1 or not x.get("options"):
            continue
        samples.append({"clip_ms": x["clip_ms"], "holder": x["holder"], "holder_xy": x.get("holder_xy"),
                        "shoot_now_p_goal": x.get("shoot_now_xg"),
                        "options": [{"label": o["label"], "name": o.get("name"), "x": o["x"], "y": o["y"],
                                     "p_goal": o["xg_after_pass"]} for o in x["options"]
                                    if o.get("x") is not None and o.get("xg_after_pass") is not None]})
    return {"shot_id": spec.get("shot_id"), "samples": samples, "n": None, "source": spec["source_file"]}


ADAPTERS = {"xray": xray, "line": line, "xray_goal10": xray_goal10, "xray_xg": xray_xg}


def build(m: dict) -> str:
    """Write the beat's data for a moment with an `adapter` and return its repo-relative path."""
    DATA_OUT.mkdir(parents=True, exist_ok=True)
    path = DATA_OUT / f"{m['name']}.json"
    path.write_text(json.dumps({"record": "tool_result", "result": ADAPTERS[m["adapter"]](m)}))
    return str(path.relative_to(ROOT))


def metrics_rows(slug: str) -> list[tuple[str, str]]:
    """The measurement card's rows for one clip, from track A's metrics.json (real footage only)."""
    c = json.loads(METRICS.read_text())["clips"][slug]
    rows = []
    if "detection" in c:
        d = c["detection"]
        rows.append((f"Players found ({d['frames']} hand-checked frames)", f"{d['recall'] * 100:.1f}%"))
    cal = c["calibration"]
    if "paint_drift_p95_px_refined" in cal:
        rows.append(("Graphics on the painted lines (p95)", f"{cal['paint_drift_p95_px_refined']['median']:.1f} px"))
    if "check_points_m" in cal:
        rows.append((f"Position error ({cal['check_points_m']['n']} checked points)",
                     f"{cal['check_points_m']['mean']:.2f} m"))
    t = c["tracking"]
    rows.append(("Track breaks per player-minute (at most)", f"{t['per_player_minute']:.2f}"))
    return rows

