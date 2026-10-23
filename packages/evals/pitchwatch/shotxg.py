"""xG at every real shot (video v4, track A): our head on tracked positions vs a published reference model.

    python -m evals.pitchwatch.shotxg track      # calibrate + track a window around each tagged shot
    python -m evals.pitchwatch.shotxg xg         # release frame, features, xG; writes data/footage/insights/shots_xg.json
    python -m evals.pitchwatch.shotxg sheet      # review sheet of every release frame (git-ignored)

Shots: the Gemini-tagged events (T-106, <slug>/events.jsonl, type shot; times are whole seconds of the clip). A shot
is measurable when its time falls in a usable wide main-camera shot (shots.json); replays and close-ups have no pitch
geometry and are listed as not measured.

Release: within [t - 3 s, t + 2 s], the frame before the ball (RF-DETR, pixels) starts moving fastest away from the
attacking player nearest it. Reviewed corrections (frame, shooter track) in <slug>/shot_overrides.json win.

Ours: heads.models.XGHead on SHOT_FEATURES from the tracked frame (distance, goal-mouth angle, header from the tag
note, opponents in the shooting cone, keeper's distance off his line, pressure within 2.5 m, pitch control at the
shooter). Reference: Soccermatics' combined logistic model fitted on 8,451 non-penalty Premier League 2017/18 shots
(Wyscout): logit = 0.5103 + 0.6338 A - 0.2798 D + 0.1243 X - 0.0300 C + 0.0014 X^2 + 0.0041 C^2 - 0.1251 A X, with
X metres from the goal line, C metres from the centre line, D = sqrt(X^2 + C^2), A the goal-mouth angle in radians
(https://soccermatics.readthedocs.io/en/latest/gallery/lesson2/plot_xGModelFit.html).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

from evals.pitchwatch.insights import FOOTAGE, GOAL_Y, L, W, keeper_tracks

CLIPS = ("liverpool-mancity-2526", "manutd-mancity-2526", "arsenal-chelsea-2526", "manutd-spurs-2425")
HOME_ATTACKS_P2 = {"liverpool-mancity-2526": 1, "manutd-mancity-2526": -1, "arsenal-chelsea-2526": 1,
                   "manutd-spurs-2425": 1}          # +1: home attacks +x (x from the left goal line) in the 2nd half
PRE_S, POST_S = 3.0, 2.0
HEADER_WORDS = ("header", "headed", "heads", "head")


def reference_xg(x_m: float, c_m: float) -> float:
    d = math.hypot(x_m, c_m)
    a = math.atan2(7.32 * x_m, x_m * x_m + c_m * c_m - (7.32 / 2) ** 2)
    a = a if a >= 0 else a + math.pi
    z = 0.5103 + 0.6338 * a - 0.2798 * d + 0.1243 * x_m - 0.0300 * c_m + 0.0014 * x_m ** 2 + 0.0041 * c_m ** 2 \
        - 0.1251 * a * x_m
    return 1.0 / (1.0 + math.exp(-z))


def tagged_shots(slug: str) -> list[dict]:
    shots = json.loads((FOOTAGE / slug / "shots.json").read_text())["shots"]
    out = []
    for line in (FOOTAGE / slug / "events.jsonl").read_text().splitlines():
        e = json.loads(line)
        if e["type"] != "shot":
            continue
        t = e["attrs"]["clip_ms"] / 1000
        s = next((x for x in shots if x["start"] <= t < x["end"]), None)
        out.append({"event": e, "t": t, "camera_shot": s["id"] if s else None,
                    "measurable": bool(s and s["usable"])})
    return out


def window(slug: str, shot: dict) -> dict:
    shots = {s["id"]: s for s in json.loads((FOOTAGE / slug / "shots.json").read_text())["shots"]}
    s = shots[shot["camera_shot"]]
    fps = json.loads((FOOTAGE / slug / "shots.json").read_text())["summary"]["fps"]
    a = max(s["frame_start"], int((shot["t"] - PRE_S) * fps))
    b = min(s["frame_end"], int((shot["t"] + POST_S) * fps))
    return {"id": f"x{shot['event']['id']}", "frame_start": a, "frame_end": b, "camera_shot": s["id"]}


def track_all() -> None:
    import cv2
    from rfdetr import RFDETRMedium

    from evals.pitchwatch.calibrate import calibrate_shot, pitch_model
    from evals.pitchwatch.track import track_shot

    model, det = pitch_model(), RFDETRMedium(device="mps")
    for slug in CLIPS:
        d = FOOTAGE / slug
        cap = cv2.VideoCapture(str(d / "clip.mp4"))
        fps = cap.get(cv2.CAP_PROP_FPS)
        for shot in tagged_shots(slug):
            if not shot["measurable"]:
                continue
            w = window(slug, shot)
            if (d / "tracks" / f"{w['id']}.json").exists():
                continue
            cam_path = d / "calib" / f"camera_{w['camera_shot']}.json"
            cam = json.loads((cam_path if cam_path.exists() else d / "calib" / "camera.json").read_text())
            frames = calibrate_shot(cap, w, cam, model, log=lambda *_: None)
            (d / "calib" / f"{w['id']}.json").write_text(json.dumps(
                {"slug": slug, "shot_id": w["id"], "fps": fps, "image_size": cam["size"],
                 "pitch": {"length_m": L, "width_m": W, "frame": "x from left goal line, y from far touchline"},
                 "frames": frames}, separators=(",", ":")) + "\n")
            doc = track_shot(d, w, step=1, model=det, log=lambda *_: None)
            (d / "tracks").mkdir(exist_ok=True)
            (d / "tracks" / f"{w['id']}.json").write_text(json.dumps(doc, separators=(",", ":")) + "\n")
            print(slug, w["id"], sum(f["ok"] for f in frames.values()), "/", len(frames), "frames ok", flush=True)


def attack_dir(slug: str, period: int, team: str) -> int:
    home = HOME_ATTACKS_P2[slug] * (1 if period == 2 else -1)
    return home if team == "home" else -home


def release(tracks: dict, cal: dict, team_idx: int, override: dict | None) -> tuple[int, dict] | None:
    """(frame, shooter) at release."""
    F = tracks["frames"]
    if override:
        r = next(x for x in F if x["frame"] == override["frame"])
        return r["frame"], next(p for p in r["players"] if p["track_id"] == override["shooter"])
    best, out = 0.0, None
    for i in range(len(F) - 3):
        r = F[i]
        b0 = r["ball"]
        if not b0 or not cal["frames"].get(str(r["frame"]), {}).get("ok"):
            continue
        mates = [p for p in r["players"] if p["team"] == team_idx]
        if not mates:
            continue
        near = min(mates, key=lambda p: math.dist(p["foot_px"], b0["px"]))
        h = near["bbox"][3] - near["bbox"][1]
        if math.dist(near["foot_px"], b0["px"]) > 0.9 * h:
            continue
        nxt = [x["ball"]["px"] for x in F[i + 1:i + 4] if x["ball"]]
        if not nxt:
            continue
        speed = max(math.dist(q, b0["px"]) / (k + 1) for k, q in enumerate(nxt)) / max(h, 1)
        if speed > best:
            best, out = speed, (r["frame"], near)
    return out


def features(r: dict, shooter: dict, d: int, team_idx: int, keepers: set[int], header: bool) -> dict:
    from evals.pitchwatch.insights import control
    from kickoff.physics_prior import cone_count, goal_angle, goal_distance

    def uv(xy):
        return (xy[0], xy[1]) if d > 0 else (L - xy[0], W - xy[1])
    u0, v0 = uv(shooter["xy"])
    opp = [p for p in r["players"] if p["xy"] and (p["team"] == 1 - team_idx or p["track_id"] in keepers)
           and p["track_id"] != shooter["track_id"]]
    ou = np.array([uv(p["xy"])[0] for p in opp]) if opp else np.zeros(0)
    ov = np.array([uv(p["xy"])[1] for p in opp]) if opp else np.zeros(0)
    gk = [uv(p["xy"])[0] for p in r["players"] if p["track_id"] in keepers and p["xy"] and uv(p["xy"])[0] > L / 2]
    players = [(*uv(p["xy"]), p["team"]) for p in r["players"] if p["team"] in (0, 1) and p["xy"]]
    return {"distance_m": float(goal_distance(u0, v0)), "angle_rad": float(goal_angle(u0, v0)),
            "body_part": 2 if header else 0, "defenders_in_cone": int(cone_count(u0, v0, ou, ov)) if len(ou) else 0,
            "keeper_line_m": (L - max(gk)) if gk else 1.0,
            "under_pressure": int(len(ou) > 0 and float(np.min(np.hypot(ou - u0, ov - v0))) < 2.5),
            "control_at_shot": float(control(players, np.array([[u0, v0]]), team_idx)[0]) if players else 0.5,
            "penalty": 0, "_u": u0, "_v": v0, "_keeper_seen": bool(gk)}


def xg_all() -> dict:
    import pandas as pd

    from heads.models import XGHead

    head = XGHead()
    rows = []
    for slug in CLIPS:
        d = FOOTAGE / slug
        ov_path = d / "shot_overrides.json"
        ovs = json.loads(ov_path.read_text()) if ov_path.exists() else {}
        for shot in tagged_shots(slug):
            e = shot["event"]
            base = {"slug": slug, "event_id": e["id"], "clip_ms": e["attrs"]["clip_ms"], "clock": e["clock"],
                    "team": e["team"], "player": e["attrs"].get("player_name"), "outcome": e["outcome"],
                    "goal": e["outcome"] == "goal", "note": e["attrs"].get("note"), "camera_shot": shot["camera_shot"]}
            ov = ovs.get(e["id"], {})
            if not shot["measurable"] or ov.get("exclude"):
                rows.append({**base, "measured": False,
                             "reason": ov.get("exclude") or "no wide main-camera view (replay, close-up or graphic)"})
                continue
            w = window(slug, shot)
            tracks = json.loads((d / "tracks" / f"{w['id']}.json").read_text())
            cal = json.loads((d / "calib" / f"{w['id']}.json").read_text())
            team_idx = 0 if e["team"] == "home" else 1
            rel = release(tracks, cal, team_idx, ov if "frame" in ov else None)
            if rel is None:
                rows.append({**base, "measured": False, "reason": "no release frame found (ball not detected)"})
                continue
            frame, shooter = rel
            r = next(x for x in tracks["frames"] if x["frame"] == frame)
            dirn = attack_dir(slug, e["period"], e["team"])
            header = any(wd in (e["attrs"].get("note") or "").lower().split() for wd in HEADER_WORDS)
            f = features(r, shooter, dirn, team_idx, keeper_tracks(tracks), header)
            ours = float(head.predict(pd.DataFrame([{k: v for k, v in f.items() if not k.startswith("_")}]))[0])
            ref = reference_xg(L - f["_u"], abs(f["_v"] - GOAL_Y))
            rows.append({**base, "measured": True, "release_frame": frame,
                         "release_clip_ms": int(round(frame / tracks["fps"] * 1000)), "shooter_track": shooter["track_id"],
                         "shooter_xy_near": [round(shooter["xy"][0], 2), round(W - shooter["xy"][1], 2)],
                         "features": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in f.items()
                                      if not k.startswith("_")},
                         "keeper_in_view": f["_keeper_seen"], "header": header,
                         "xg_ours": round(ours, 3), "xg_reference": round(ref, 3),
                         "reviewed": "frame" in ov, "calib_ok": bool(cal["frames"].get(str(frame), {}).get("ok"))})
    return {"shots": rows}


def summary(doc: dict) -> dict:
    m = [r for r in doc["shots"] if r["measured"] and not r["header"]]
    a, b = np.array([r["xg_ours"] for r in m]), np.array([r["xg_reference"] for r in m])
    goals = np.array([r["goal"] for r in m], dtype=float)
    out = {"measured": len([r for r in doc["shots"] if r["measured"]]), "total": len(doc["shots"]),
           "compared_non_headers": len(m)}
    if len(m) >= 3:
        from scipy.stats import spearmanr
        out.update({"mean_abs_diff": round(float(np.mean(np.abs(a - b))), 3),
                    "spearman": round(float(spearmanr(a, b).statistic), 3),
                    "sum_ours": round(float(a.sum()), 2), "sum_reference": round(float(b.sum()), 2),
                    "goals": int(goals.sum()),
                    "outliers": [r["event_id"] for r in m if abs(r["xg_ours"] - r["xg_reference"]) > 0.15]})
    return out


def sheet() -> Path:
    import cv2
    tiles = []
    doc = json.loads((FOOTAGE / "insights" / "shots_xg.json").read_text())
    for r in doc["shots"]:
        if not r["measured"]:
            continue
        d = FOOTAGE / r["slug"]
        cap = cv2.VideoCapture(str(d / "clip.mp4"))
        cap.set(cv2.CAP_PROP_POS_FRAMES, r["release_frame"])
        ok, img = cap.read()
        tr = json.loads((d / "tracks" / f"x{r['event_id']}.json").read_text())
        fr = next(x for x in tr["frames"] if x["frame"] == r["release_frame"])
        for p in fr["players"]:
            if p["track_id"] == r["shooter_track"]:
                x1, y1, x2, y2 = map(int, p["bbox"])
                cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 255), 4)
        if fr["ball"]:
            cv2.circle(img, tuple(int(v) for v in fr["ball"]["px"]), 14, (0, 0, 255), 3)
        cv2.putText(img, f"{r['event_id']} {r['player']} ours {r['xg_ours']} ref {r['xg_reference']} "
                    f"{'GOAL' if r['goal'] else r['outcome']}", (20, 1050), 0, 1.3, (0, 255, 255), 3)
        tiles.append(cv2.resize(img, (640, 360)))
    while len(tiles) % 3:
        tiles.append(np.zeros_like(tiles[0]))
    out = FOOTAGE / "insights" / "shots_review.jpg"
    rows = [np.hstack(tiles[k:k + 3]) for k in range(0, len(tiles), 3)]
    for k in range(0, len(rows), 4):
        cv2.imwrite(str(out.with_name(f"shots_review_{k // 4}.jpg")), np.vstack(rows[k:k + 4]))
    return out


def main(argv: list[str] | None = None) -> int:
    kind = (argv or sys.argv[1:])[0]
    if kind == "track":
        track_all()
    elif kind == "xg":
        doc = xg_all()
        doc["summary"] = summary(doc)
        doc["reference_model"] = __doc__.split("Reference: ")[1].strip()
        (FOOTAGE / "insights").mkdir(exist_ok=True)
        (FOOTAGE / "insights" / "shots_xg.json").write_text(json.dumps(doc, indent=1) + "\n")
        print(json.dumps(doc["summary"]))
    else:
        print(sheet())
    return 0


if __name__ == "__main__":
    sys.exit(main())
