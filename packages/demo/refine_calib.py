"""Refine track A's per-frame calibration against the paint (track A asked for it on 23 Oct).

    python -m demo.refine_calib <slug> <shot_id> [--workers N] [--frames A:B]

Reads data/footage/<slug>/calib/<shot>.json (Pitchwatch format v1: H maps pixels to pitch metres, y from the far
touchline) and writes calib/<shot>_refined.json in the same format. Every frame track A marks ok is seeded with its H
and refined by demo.footage.fit_from_lines against the centres of the painted lines it sees (players masked; the far
touchline and everything above it left out, since the boards sit on it). Per frame:

    "H"      the best plain homography (a drop-in for the original)
    "k1", "H_k1"  the camera with one radial lens term about the picture centre, r normalised by half the width:
             undistort pixels u = c + (v - c) / (1 + k1 r^2) (solve by iteration), then pitch = H_k1 @ u
    "drift_median_px", "drift_p95_px", "drift_lines"  demo.footage.drift_px of the lens camera
    "seed_drift_p95_px"  the same measure for track A's H
    "refined"  true when the refinement measured better than the seed (else the seed is kept as it was)

Frames track A marks not ok are copied unchanged. Media is only decoded, never written.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from multiprocessing import Pool

import numpy as np

from demo.composite import FOOTAGE as ROOT_FOOTAGE
from demo.footage import (
    Camera,
    board_top,
    drift_px,
    fit_from_lines,
    from_pitchwatch,
    model_lines,
    to_pitchwatch,
)

LINES = [n for n in model_lines() if n != "touchline_far"]


def decode(slug: str, first: int, count: int, fps: float, size=(1920, 1080)):
    w, h = size
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{first / fps:.4f}", "-i",
                          str(ROOT_FOOTAGE / slug / "clip.mp4"), "-frames:v", str(count), "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    n = len(raw) // (w * h * 3)
    return np.frombuffer(raw[: n * w * h * 3], np.uint8).reshape(n, h, w, 3)


def refine(frame: np.ndarray, seed: Camera) -> dict:
    top = board_top(seed, frame.shape[1])
    before = drift_px(seed, frame, LINES, top=top)
    lens = fit_from_lines(frame, None, None, LINES, top=top, seed=seed)
    plain = fit_from_lines(frame, None, None, LINES, top=top, seed=Camera(lens.camera.h, size=seed.size),
                           search=(8, 8, 8), lens=False)
    out = {"seed_drift_p95_px": before.p95, "seed_drift_median_px": before.median}
    if lens.drift.lines and lens.drift.p95 < before.p95:
        out.update({"H": to_pitchwatch(plain.camera), "H_k1": to_pitchwatch(lens.camera), "k1": lens.camera.k1,
                    "drift_median_px": lens.drift.median, "drift_p95_px": lens.drift.p95,
                    "drift_plain_p95_px": plain.drift.p95, "drift_lines": lens.drift.lines, "refined": True})
    else:
        out["refined"] = False
    return out


def work(job):
    slug, first, count, fps, calib_frames = job
    frames = decode(slug, first, count, fps)
    out = {}
    for i, img in enumerate(frames):
        key = str(first + i)
        entry = calib_frames.get(key)
        if not entry or not entry.get("ok"):
            continue
        seed = from_pitchwatch({"frames": {key: entry}, "image_size": [img.shape[1], img.shape[0]]}, first + i)
        try:
            out[key] = {**entry, **refine(img, seed)}
        except Exception as exc:                         # a frame that will not fit keeps track A's H
            out[key] = {**entry, "refined": False, "error": f"{type(exc).__name__}: {exc}"[:200]}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("slug")
    ap.add_argument("shot", type=int)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--frames", help="A:B, a sub-range of frame indices (for checking)")
    ap.add_argument("--chunk", type=int, default=50)
    args = ap.parse_args(argv)
    src = ROOT_FOOTAGE / args.slug / "calib" / f"{args.shot}.json"
    calib = json.loads(src.read_text())
    fps = float(calib.get("fps", 50.0))
    keys = sorted(int(k) for k in calib["frames"])
    if args.frames:
        a, b = (int(x) for x in args.frames.split(":"))
        keys = [k for k in keys if a <= k < b]
    jobs = [(args.slug, k, min(args.chunk, keys[-1] + 1 - k), fps, calib["frames"])
            for k in range(keys[0], keys[-1] + 1, args.chunk)]
    t0 = time.time()
    refined = {}
    with Pool(args.workers) as pool:
        for i, part in enumerate(pool.imap_unordered(work, jobs), 1):
            refined.update(part)
            print(f"\r{i}/{len(jobs)} chunks, {time.time() - t0:.0f} s", end="", file=sys.stderr)
    print(file=sys.stderr)
    frames = {k: refined.get(k, v) for k, v in calib["frames"].items() if int(k) in set(keys)}
    done = [v for v in frames.values() if v.get("refined")]
    seeds = [v["seed_drift_p95_px"] for v in frames.values() if "seed_drift_p95_px" in v]
    summary = {"frames": len(frames), "ok": sum(bool(v.get("ok")) for v in frames.values()), "refined": len(done),
               "seed_p95_median_px": round(float(np.median(seeds)), 2) if seeds else None,
               "refined_p95_median_px": round(float(np.median([v["drift_p95_px"] for v in done])), 2) if done else None,
               "refined_p95_max_px": round(float(np.max([v["drift_p95_px"] for v in done])), 2) if done else None,
               "k1_median": round(float(np.median([v["k1"] for v in done])), 4) if done else None,
               "seconds": round(time.time() - t0)}
    doc = {**{k: v for k, v in calib.items() if k != "frames"}, "refined_from": src.name,
           "refined_by": "demo.refine_calib (track C): seeded with H, ICP against painted line centres",
           "refine_summary": summary, "frames": frames}
    suffix = "_refined" if not args.frames else f"_refined_{keys[0]}_{keys[-1]}"
    dst = src.with_name(f"{args.shot}{suffix}.json")
    dst.write_text(json.dumps(doc))
    print(json.dumps(summary))
    print(f"wrote {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
