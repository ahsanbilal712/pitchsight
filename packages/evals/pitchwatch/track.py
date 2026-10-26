"""Players and ball: detection, tracking, team labels, pitch metres.

    python -m evals.pitchwatch.track data/footage/<slug> --shots 62 [--step 2]

RF-DETR Medium (COCO-pretrained, Apache-2.0) on the Mac GPU finds people (COCO class 1) and the ball (class 37) on
every `step`-th frame of a calibrated shot; trackers.ByteTrackTracker links the people into tracks. Each foot point
(bottom centre of the box) goes through that frame's homography (calib/<shot>.json) to pitch metres; people whose
feet land off the pitch by more than OFF_PITCH_M (staff, fans, the bench) are dropped. Teams: the median non-grass
torso colour of each track (CIE Lab), two clusters by k-means over the tracks seen at least MIN_TEAM_OBS times; a
track much further from both centres than the clusters' own spread (referee, often a keeper) gets team null. Cluster
-> club by the nearest kit colour in <slug>/teams.json. The team is then set per observation (nearest centre, majority
over neighbouring observations), so an identity switch between teams flips the label where it happens. Jersey numbers are not read (no OCR in scope).

Writes <slug>/tracks/<shot>.json in the shared format (track-a-pitchwatch-format.md in the shared notes).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

PERSON, BALL = 1, 37
DET_THRESHOLD, BALL_THRESHOLD = 0.3, 0.2
OFF_PITCH_M = 3.0
MIN_TEAM_OBS = 10
OUTLIER_FACTOR = 2.5
TEAM_WINDOW = 12              # observations either side for the per-observation team majority


def torso_lab(bgr: np.ndarray, box: np.ndarray) -> np.ndarray | None:
    """Median Lab colour of the shirt area (upper body, centre), grass pixels excluded."""
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    crop = bgr[int(y1 + 0.15 * h):int(y1 + 0.5 * h), int(x1 + 0.25 * w):int(x2 - 0.25 * w)]
    if crop.size == 0:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    keep = ~((hsv[..., 0] >= 32) & (hsv[..., 0] <= 90) & (hsv[..., 1] >= 50))
    if keep.sum() < 6:
        return None
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).reshape(-1, 3)[keep.ravel()]
    return np.median(lab, axis=0).astype(np.float32)


def assign_teams(colours: dict[int, list[np.ndarray]], kits: list[dict]) -> tuple[dict[int, int | None], dict]:
    """{track_id: 0 | 1 | None} and the cluster centres (Lab)."""
    med = {t: np.median(np.stack(c), axis=0) for t, c in colours.items() if len(c) >= MIN_TEAM_OBS}
    if len(med) < 2:
        return dict.fromkeys(colours), {}
    X = np.stack(list(med.values())).astype(np.float32)
    _, lab, centres = cv2.kmeans(X, 2, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.5), 10,
                                 cv2.KMEANS_PP_CENTERS)
    lab = lab.ravel()
    d = np.linalg.norm(X[:, None, :] - centres[None], axis=2)
    spread = [np.median(d[lab == k, k]) if (lab == k).any() else 0.0 for k in (0, 1)]
    # cluster -> club by the nearest kit colour
    order = [0, 1]
    if kits:
        kit_lab = [cv2.cvtColor(np.uint8([[k["kit_rgb"][::-1]]]), cv2.COLOR_BGR2LAB)[0, 0].astype(np.float32)
                   for k in kits]
        cost = np.array([[np.linalg.norm(centres[c] - kit_lab[t]) for t in (0, 1)] for c in (0, 1)])
        order = [0, 1] if cost[0, 0] + cost[1, 1] <= cost[0, 1] + cost[1, 0] else [1, 0]
    out: dict[int, int | None] = dict.fromkeys(colours)
    for (t, _), k, dist in zip(med.items(), lab, d, strict=True):
        out[t] = None if dist[k] > OUTLIER_FACTOR * max(spread[k], 4.0) else order[k]
    return out, {"centres_lab": centres.round(1).tolist(), "spread": [round(float(s), 1) for s in spread],
                 "order": order}


def relabel(rows: list[dict], teams: dict, info: dict, window: int = TEAM_WINDOW) -> None:
    """Team per observation: each observation's colour goes to the nearer cluster centre, then a majority over
    the track's neighbouring observations (+-window) smooths it. A track that switches identity between players of
    different teams (ByteTrack does, in a crowd) changes label where it switches. Tracks the clustering left out
    as outliers (referee, keepers) stay None with role "other"."""
    centres = np.asarray(info.get("centres_lab") or [], dtype=np.float32)
    order = info.get("order", [0, 1])
    by_track: dict[int, list[dict]] = {}
    for r in rows:
        for p in r["players"]:
            by_track.setdefault(p["track_id"], []).append(p)
    for tid, obs in by_track.items():
        if teams.get(tid) is None or len(centres) < 2:
            for p in obs:
                p["team"] = None
                if tid in teams and teams[tid] is None:
                    p["role"] = "other"          # referee or goalkeeper: kit unlike either outfield cluster
                p.pop("_lab", None)
            continue
        raw = []
        for p in obs:
            c = p.pop("_lab", None)
            raw.append(None if c is None else order[int(np.argmin(np.linalg.norm(centres - np.asarray(c), axis=1)))])
        for k, p in enumerate(obs):
            near = [x for x in raw[max(0, k - window):k + window + 1] if x is not None]
            p["team"] = max(set(near), key=near.count) if near else teams[tid]


def to_pitch(H: list, uv: tuple[float, float]) -> tuple[float, float]:
    p = np.asarray(H) @ np.array([uv[0], uv[1], 1.0])
    return float(p[0] / p[2]), float(p[1] / p[2])


def nearest_ok(frames: dict, fr: int) -> dict | None:
    for d in range(0, 50):
        for k in (fr - d, fr + d):
            c = frames.get(str(k))
            if c is not None and c["ok"]:
                return c
    return None


def track_shot(slug_dir: Path, shot: dict, step: int = 2, model=None, log=print) -> dict:
    import supervision as sv
    from rfdetr import RFDETRMedium
    from trackers import ByteTrackTracker

    calib = json.loads((slug_dir / "calib" / f"{shot['id']}.json").read_text())
    fps = calib["fps"]
    length, width = calib["pitch"]["length_m"], calib["pitch"]["width_m"]
    kits = json.loads((slug_dir / "teams.json").read_text())["teams"] if (slug_dir / "teams.json").exists() else []
    model = model or RFDETRMedium(device="mps")
    tracker = ByteTrackTracker(frame_rate=fps / step, lost_track_buffer=int(2 * fps / step))
    cap = cv2.VideoCapture(str(slug_dir / "clip.mp4"))
    cap.set(cv2.CAP_PROP_POS_FRAMES, shot["frame_start"])
    rows, colours = [], {}
    fr = shot["frame_start"]
    while fr < shot["frame_end"]:
        ok, bgr = cap.read()
        if not ok:
            break
        if (fr - shot["frame_start"]) % step:
            fr += 1
            continue
        det = model.predict(bgr[:, :, ::-1].copy(), threshold=min(DET_THRESHOLD, BALL_THRESHOLD))
        cal = nearest_ok(calib["frames"], fr)
        people = det[(det.class_id == PERSON) & (det.confidence >= DET_THRESHOLD)]
        if cal is not None and len(people):
            feet = [to_pitch(cal["H"], ((b[0] + b[2]) / 2, b[3])) for b in people.xyxy]
            on = np.array([-OFF_PITCH_M <= x <= length + OFF_PITCH_M and -OFF_PITCH_M <= y <= width + OFF_PITCH_M
                           for x, y in feet], dtype=bool)
            people = people[on]
        tracked = tracker.update(sv.Detections(xyxy=people.xyxy, confidence=people.confidence,
                                               class_id=people.class_id))
        players = []
        for box, tid, conf in zip(tracked.xyxy, tracked.tracker_id, tracked.confidence, strict=True):
            tid = int(tid)
            if tid < 0:
                continue
            foot = ((box[0] + box[2]) / 2, box[3])
            c = torso_lab(bgr, box)
            if c is not None:
                colours.setdefault(tid, []).append(c)
            players.append({"_lab": None if c is None else c.tolist(), "track_id": tid, "team": None, "role": "player",
                            "bbox": [round(float(v), 1) for v in box], "foot_px": [round(float(v), 1) for v in foot],
                            "xy": [round(v, 2) for v in to_pitch(cal["H"], foot)] if cal else None,
                            "conf": round(float(conf), 3) if conf is not None else None})
        balls = det[(det.class_id == BALL) & (det.confidence >= BALL_THRESHOLD)]
        ball = None
        if len(balls):
            k = int(np.argmax(balls.confidence))
            b = balls.xyxy[k]
            px = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
            ball = {"bbox": [round(float(v), 1) for v in b], "px": [round(float(v), 1) for v in px],
                    "xy": [round(v, 2) for v in to_pitch(cal["H"], (px[0], b[3]))] if cal else None,
                    "conf": round(float(balls.confidence[k]), 3)}
        rows.append({"frame": fr, "t": round(fr / fps, 3), "calib_ok": cal is not None, "players": players,
                     "ball": ball})
        if len(rows) % 250 == 0:
            log(f"shot {shot['id']} frame {fr}: {len(players)} players, ball {'yes' if ball else 'no'}")
        fr += 1
    teams, info = assign_teams(colours, kits)
    relabel(rows, teams, info)
    return {"slug": slug_dir.name, "shot_id": shot["id"], "fps": fps, "step": step,
            "teams": {str(i): k for i, k in enumerate(kits)}, "team_clusters": info,
            "detector": "RF-DETR Medium 1.11.2 (COCO), threshold 0.3 people / 0.2 ball",
            "tracker": "trackers.ByteTrackTracker 2.6.1", "frames": rows}


def reproject(doc: dict, calib: dict, source: str) -> dict:
    """Re-map every stored foot and ball pixel through another calibration of the same shot (same format), so a
    better camera needs no new detection run."""
    for r in doc["frames"]:
        cal = nearest_ok(calib["frames"], r["frame"])
        r["calib_ok"] = cal is not None
        for p in r["players"]:
            p["xy"] = [round(v, 2) for v in to_pitch(cal["H"], tuple(p["foot_px"]))] if cal else None
        b = r["ball"]
        if b:
            b["xy"] = [round(v, 2) for v in to_pitch(cal["H"], (b["px"][0], b["bbox"][3]))] if cal else None
    doc["calibration"] = source
    return doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m evals.pitchwatch.track")
    ap.add_argument("slug_dir", type=Path)
    ap.add_argument("--shots", required=True)
    ap.add_argument("--step", type=int, default=2)
    ap.add_argument("--calib", default=None, help="re-project existing tracks through calib/<shot><suffix>.json "
                    "(e.g. _refined) instead of detecting again")
    args = ap.parse_args(argv)
    if args.calib is not None:
        for sid in args.shots.split(","):
            path = args.slug_dir / "tracks" / f"{sid}.json"
            cal_path = args.slug_dir / "calib" / f"{sid}{args.calib}.json"
            doc = reproject(json.loads(path.read_text()), json.loads(cal_path.read_text()), cal_path.name)
            path.write_text(json.dumps(doc, separators=(",", ":")) + "\n")
            print(f"tracks/{sid}.json re-projected through {cal_path.name}")
        return 0
    shots = {s["id"]: s for s in json.loads((args.slug_dir / "shots.json").read_text())["shots"]}
    out = args.slug_dir / "tracks"
    out.mkdir(exist_ok=True)
    from rfdetr import RFDETRMedium
    model = RFDETRMedium(device="mps")
    for sid in (int(s) for s in args.shots.split(",")):
        doc = track_shot(args.slug_dir, shots[sid], step=args.step, model=model)
        (out / f"{sid}.json").write_text(json.dumps(doc, separators=(",", ":")) + "\n")
        n = [len(r["players"]) for r in doc["frames"]]
        teams = [p["team"] for r in doc["frames"] for p in r["players"]]
        print(json.dumps({"shot": sid, "frames": len(n), "players_median": float(np.median(n)) if n else 0,
                          "ball_frames": sum(1 for r in doc["frames"] if r["ball"]),
                          "team_split": {str(k): teams.count(k) for k in (0, 1, None)},
                          "tracks": len({p["track_id"] for r in doc["frames"] for p in r["players"]})}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
