"""Tiled ball detection (SAHI-style) at full resolution for the v6 live data.

    python -m evals.pitchwatch.ball_tiles <slug> <shot_id> [...]

The broadcast ball is a few pixels wide; RF-DETR sees the whole 1920x1080 frame at its input size and misses it.
Here the same model (RF-DETR Medium, COCO "sports ball", threshold 0.2) runs on overlapping 640 px tiles of every
10 Hz sample frame; detections are merged across tiles, those that do not land on the pitch through the frame's
camera fit are dropped, and the most confident one is kept with its runners-up. Output (git-ignored):
data/footage/<slug>/tracks/<shot_id>.ball_tiled.json {frame: [{px, bbox, xy, conf}, ...]} (all candidates, most
confident first; the live data picks among them by continuity).
"""

from __future__ import annotations

import json
import sys
import time

import cv2
import numpy as np

from evals.pitchwatch.insights import FOOTAGE
from evals.pitchwatch.track import BALL, BALL_THRESHOLD, nearest_ok, to_pitch

TILE, OVERLAP = 640, 0.25
HZ = 10
OFF_PITCH_M = 1.0


def tiles(w: int, h: int) -> list[tuple[int, int]]:
    stride = int(TILE * (1 - OVERLAP))
    xs = sorted({min(x, w - TILE) for x in range(0, w - TILE + stride, stride)})
    ys = sorted({min(y, h - TILE) for y in range(0, h - TILE + stride, stride)})
    return [(x, y) for y in ys for x in xs]


def detect(model, bgr: np.ndarray) -> list[tuple[np.ndarray, float]]:
    h, w = bgr.shape[:2]
    out = []
    rgb = bgr[:, :, ::-1]
    for x0, y0 in tiles(w, h):
        det = model.predict(rgb[y0:y0 + TILE, x0:x0 + TILE].copy(), threshold=BALL_THRESHOLD)
        for b, c, k in zip(det.xyxy, det.confidence, det.class_id, strict=True):
            if k == BALL:
                out.append((b + np.array([x0, y0, x0, y0]), float(c)))
    keep = []                                      # merge the same ball seen in two overlapping tiles
    for b, c in sorted(out, key=lambda x: -x[1]):
        centre = (b[:2] + b[2:]) / 2
        if all(np.linalg.norm(centre - (k[:2] + k[2:]) / 2) > 8 for k, _ in keep):
            keep.append((b, c))
    return keep


def run(slug: str, shot_id: str, model=None) -> dict:
    from rfdetr import RFDETRMedium
    d = FOOTAGE / slug
    tracks = json.loads((d / "tracks" / f"{shot_id}.json").read_text())
    calib = json.loads((d / "calib" / f"{shot_id}.json").read_text())
    length, width = calib["pitch"]["length_m"], calib["pitch"]["width_m"]
    fps = tracks["fps"]
    F = tracks["frames"]
    want = sorted({min(F, key=lambda r: abs(r["t"] - t))["frame"]
                   for t in np.arange(np.ceil(F[0]["t"] * HZ) / HZ, F[-1]["t"] + 1e-9, 1 / HZ)})
    model = model or RFDETRMedium(device="mps")
    cap = cv2.VideoCapture(str(d / "clip.mp4"))
    cap.set(cv2.CAP_PROP_POS_FRAMES, want[0])
    fr, out, todo = want[0], {}, set(want)
    t0 = time.time()
    while fr <= want[-1]:
        ok, bgr = cap.read()
        if not ok:
            break
        if fr in todo:
            cal = nearest_ok(calib["frames"], fr)
            cands = []
            for b, c in detect(model, bgr) if cal else []:
                px = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
                x, y = to_pitch(cal["H"], (px[0], b[3]))
                if -OFF_PITCH_M <= x <= length + OFF_PITCH_M and -OFF_PITCH_M <= y <= width + OFF_PITCH_M:
                    cands.append({"px": [round(float(v), 1) for v in px], "bbox": [round(float(v), 1) for v in b],
                                  "xy": [round(x, 2), round(y, 2)], "conf": round(c, 3)})
            out[str(fr)] = cands                     # all on-pitch candidates, most confident first
        fr += 1
    doc = {"slug": slug, "shot_id": shot_id, "fps": fps, "hz": HZ, "tile": TILE, "overlap": OVERLAP,
           "detector": f"RF-DETR Medium 1.11.2 (COCO sports ball), {TILE} px tiles, {OVERLAP:.0%} overlap, "
                       f"threshold {BALL_THRESHOLD}, on-pitch through the frame's camera fit",
           "seconds": round(time.time() - t0, 1), "frames": out}
    (d / "tracks" / f"{shot_id}.ball_tiled.json").write_text(json.dumps(doc, separators=(",", ":")) + "\n")
    return doc


def main(argv: list[str] | None = None) -> int:
    from rfdetr import RFDETRMedium
    args = argv or sys.argv[1:]
    model = RFDETRMedium(device="mps")
    for shot_id in args[1:]:
        doc = run(args[0], shot_id, model)
        n = len(doc["frames"])
        print(args[0], shot_id, sum(bool(v) for v in doc["frames"].values()), "/", n, "frames with a ball,",
              doc["seconds"], "s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
