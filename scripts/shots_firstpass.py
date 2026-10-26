"""First-pass shot segmentation for broadcast football clips.

Usage: python -I shots.py <clip.mp4> <out_dir>
Writes <out_dir>/shots.json and one review thumbnail per wide shot in <out_dir>/frames/.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

SAMPLE_FPS = 5
W, H = 320, 180
CUT_CORR = 0.55          # HSV-histogram correlation below this between samples = cut
WIDE_GREEN = 0.42        # pitch-green share of the frame for a wide shot
WIDE_BLOB = 0.025        # largest non-green blob (lower 3/4 of frame) must be smaller than this
MIN_WIDE_S = 4.0
MIN_PLAYERS = 4          # player-sized blobs needed; close-ups have one or two


def frame_features(bgr):
    small = cv2.resize(bgr, (W, H), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, (32, 50, 35), (90, 255, 255))
    green_frac = float(green.mean() / 255)
    hist = cv2.calcHist([hsv], [0, 1], None, [30, 16], [0, 180, 0, 256])
    cv2.normalize(hist, hist)
    # largest non-green blob inside the pitch area: a close-up has one big person
    lower = 255 - green[H // 4:, :]
    lower = cv2.morphologyEx(lower, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(lower, connectivity=8)
    areas = stats[1:, cv2.CC_STAT_AREA] if n > 1 else np.array([0])
    # ignore only blobs touching the top of the region (crowd, boards); a close-up
    # player touches the bottom or sides and must count
    # count only tall blobs: a close-up person is tall, stands and boards are wide and short
    players, blob = 0, 0.0
    if n > 1:
        y, h = stats[1:, cv2.CC_STAT_TOP], stats[1:, cv2.CC_STAT_HEIGHT]
        keep = y > 0
        players = int(((areas >= 8) & (areas <= 700) & keep).sum())
        tall = keep & (h >= 0.3 * lower.shape[0])
        blob = float(areas[tall].max() / (W * H)) if tall.any() else 0.0
    return green_frac, blob, players, hist, small


def analyse(clip, out_dir):
    cap = cv2.VideoCapture(str(clip))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step = max(1, round(fps / SAMPLE_FPS))
    samples, prev_hist, idx = [], None, 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        if idx % step == 0:
            ok, bgr = cap.retrieve()
            if not ok:
                break
            g, b, players, hist, small = frame_features(bgr)
            corr = 1.0 if prev_hist is None else float(cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL))
            wide = g >= WIDE_GREEN and b < WIDE_BLOB and players >= MIN_PLAYERS
            samples.append({"t": idx / fps, "green": g, "blob": b, "corr": corr, "wide": wide, "img": small})
            prev_hist = hist
        idx += 1
    cap.release()

    # split into shots at cuts
    shots, cur = [], [samples[0]]
    for s in samples[1:]:
        if s["corr"] < CUT_CORR:
            shots.append(cur)
            cur = []
        cur.append(s)
    shots.append(cur)

    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for i, sh in enumerate(shots):
        start, end = sh[0]["t"], sh[-1]["t"] + 1 / SAMPLE_FPS
        wide_share = sum(s["wide"] for s in sh) / len(sh)
        kind = "wide" if wide_share >= 0.7 else "other"
        rec = {
            "id": i, "start": round(start, 2), "end": round(end, 2), "duration": round(end - start, 2),
            "kind": kind, "wide_share": round(wide_share, 2),
            "green_mean": round(float(np.mean([s["green"] for s in sh])), 3),
            "usable": kind == "wide" and end - start >= MIN_WIDE_S,
        }
        if rec["usable"]:
            mid = sh[len(sh) // 2]["img"]
            cv2.imwrite(str(frames_dir / f"shot_{i:03d}_{int(start)//60:02d}m{int(start)%60:02d}s.jpg"), mid)
        out.append(rec)

    duration = n_frames / fps
    usable = [s for s in out if s["usable"]]
    summary = {
        "clip": clip.name, "fps": round(fps, 2), "duration_s": round(duration, 1),
        "n_shots": len(out), "n_usable_wide": len(usable),
        "usable_wide_s": round(sum(s["duration"] for s in usable), 1),
        "usable_wide_share": round(sum(s["duration"] for s in usable) / duration, 3),
        "longest_wide_s": max((s["duration"] for s in usable), default=0),
        "params": {"sample_fps": SAMPLE_FPS, "cut_corr": CUT_CORR, "wide_green": WIDE_GREEN,
                   "wide_blob": WIDE_BLOB, "min_players": MIN_PLAYERS, "min_wide_s": MIN_WIDE_S},
        "note": "heuristic first pass; replays and slow-motion are not yet flagged, review frames/ by hand",
    }
    (out_dir / "shots.json").write_text(json.dumps({"summary": summary, "shots": out}, indent=1))
    return summary


if __name__ == "__main__":
    print(json.dumps(analyse(Path(sys.argv[1]), Path(sys.argv[2])), indent=1))
