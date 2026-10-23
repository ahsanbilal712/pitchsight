"""Real-footage measurement card (track A, video v3): detection recall, calibration quality, tracking continuity.

    python -m evals.pitchwatch.insights metrics      # writes data/footage/insights/metrics.json

- Detection recall: from <slug>/recall.json (200 frames labelled by eye, T-105); only clips that have labels.
- Calibration, per clip and over every calibrated shot: share of frames whose fit is trusted (ok) and the median and
  p95 line residual of those frames, in pixels (distance from the projected pitch model to the detected line
  segments; includes about half a line width of edge bias). Where track C refined a shot against the paint
  (calib/<shot>_refined.json) its drift to the paint centre is reported too, and the 20 check points of T-104 give
  metres.
- Tracking continuity: interior track starts per player-minute. A track that starts mid-shot with its box at least
  EDGE_PX from the picture border is a player the tracker lost and picked up again under a new id (an ID switch or
  a re-identification after occlusion); a player walking into the picture starts at the edge and does not count.
  This is an upper bound on true ID switches (ids are not hand-labelled).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
FOOTAGE = ROOT / "data" / "footage"
EDGE_PX = 40
W, H = 1920, 1080


def calib_stats(slug_dir: Path) -> dict | None:
    rms, ok_n, n, refined_p95, shots = [], 0, 0, [], []
    for p in sorted((slug_dir / "calib").glob("[0-9]*.json")):
        doc = json.loads(p.read_text())
        frames = doc["frames"].values()
        if p.stem.endswith("_refined"):
            refined_p95 += [f["drift_p95_px"] for f in frames if f.get("drift_p95_px") is not None]
            continue
        shots.append(int(p.stem))
        n += len(doc["frames"])
        good = [f for f in frames if f["ok"]]
        ok_n += len(good)
        rms += [f["rms_px"] for f in good]
    if not n:
        return None
    out = {"shots": shots, "frames": n, "ok_share": round(ok_n / n, 3),
           "line_residual_px": {"median": round(float(np.median(rms)), 2), "p95": round(float(np.percentile(rms, 95)), 2)}}
    if refined_p95:
        out["paint_drift_p95_px_refined"] = {"median": round(float(np.median(refined_p95)), 2),
                                             "shots": "track C refinement"}
    ev = slug_dir / "calib" / "eval_refined.json"
    if not ev.exists():
        ev = slug_dir / "calib" / "eval.json"
    if ev.exists():
        e = json.loads(ev.read_text())
        out["check_points_m"] = {"n": e["n"], "mean": e["mean_m"], "max": e["max_m"], "source": ev.name}
    return out


def track_stats(slug_dir: Path) -> dict | None:
    starts, player_s, shots = 0, 0.0, []
    for p in sorted((slug_dir / "tracks").glob("[0-9]*.json")):
        doc = json.loads(p.read_text())
        frames = doc["frames"]
        if len(frames) < 2:
            continue
        shots.append(int(p.stem))
        dt = doc["step"] / doc["fps"]
        first: dict[int, dict] = {}
        for r in frames:
            player_s += len(r["players"]) * dt
            for q in r["players"]:
                first.setdefault(q["track_id"], {"frame": r["frame"], "bbox": q["bbox"]})
        f0 = frames[0]["frame"]
        for t in first.values():
            x1, y1, x2, y2 = t["bbox"]
            interior = x1 > EDGE_PX and y1 > EDGE_PX and x2 < W - EDGE_PX and y2 < H - EDGE_PX
            if t["frame"] > f0 + doc["step"] * 2 and interior:
                starts += 1
    if not player_s:
        return None
    return {"shots": shots, "player_minutes": round(player_s / 60, 1), "interior_track_starts": starts,
            "per_player_minute": round(starts / (player_s / 60), 2)}


def footage_metrics() -> dict:
    clips = {}
    for d in sorted(p for p in FOOTAGE.iterdir() if p.is_dir()):
        row = {}
        if (d / "recall.json").exists():
            r = json.loads((d / "recall.json").read_text())
            row["detection"] = {k: r[k] for k in ("frames", "recall", "precision", "missed", "true_boxes")}
        if (d / "calib").exists() and (c := calib_stats(d)):
            row["calibration"] = c
        if (d / "tracks").exists() and (t := track_stats(d)):
            row["tracking"] = t
        if row:
            clips[d.name] = row
    return {"clips": clips, "definitions": __doc__}
