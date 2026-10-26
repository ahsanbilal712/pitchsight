"""Player recall of the detector on labelled frames.

    python -m evals.pitchwatch.recall data/footage/<slug> sheets --shots 43,48,49,62,135 --per-shot 40
    python -m evals.pitchwatch.recall data/footage/<slug> score

`sheets` samples frames evenly across the shots, runs RF-DETR (people, threshold 0.3) and writes review sheets to
<slug>/frames/recall/ (git-ignored): four frames per sheet, each person box drawn and numbered, with a box count per
frame. The labeller (labelled by eye, 23 Oct 2026) records for every frame how many
people on the pitch have no box (`missed`) and how many boxes are not a person on the pitch (`false`), in
<slug>/recall_labels.json. `score` computes recall = (boxes - false) / (boxes - false + missed) pooled over frames,
and precision = (boxes - false) / boxes; writes <slug>/recall.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

PERSON = 1
THRESHOLD = 0.3
TILE_W, TILE_H = 960, 540


def sample_frames(shots: list[dict], per_shot: int) -> list[int]:
    out = []
    for s in shots:
        a, b = s["frame_start"] + 10, s["frame_end"] - 10
        out += [int(x) for x in np.linspace(a, b, per_shot)]
    return out


def sheets(slug_dir: Path, shot_ids: list[int], per_shot: int) -> dict:
    from rfdetr import RFDETRMedium

    shots = {s["id"]: s for s in json.loads((slug_dir / "shots.json").read_text())["shots"]}
    frames = sample_frames([shots[i] for i in shot_ids], per_shot)
    model = RFDETRMedium(device="mps")
    cap = cv2.VideoCapture(str(slug_dir / "clip.mp4"))
    out_dir = slug_dir / "frames" / "recall"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, tiles = [], []
    for k, fr in enumerate(frames):
        cap.set(cv2.CAP_PROP_POS_FRAMES, fr)
        ok, bgr = cap.read()
        if not ok:
            continue
        det = model.predict(bgr[:, :, ::-1].copy(), threshold=THRESHOLD)
        boxes = det.xyxy[det.class_id == PERSON]
        img = bgr.copy()
        for j, (x1, y1, x2, y2) in enumerate(boxes):
            cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 255), 2)
            cv2.putText(img, str(j), (int(x1), int(y1) - 3), 0, 0.7, (0, 255, 255), 2)
        tile = cv2.resize(img, (TILE_W, TILE_H), interpolation=cv2.INTER_AREA)
        cv2.rectangle(tile, (0, TILE_H - 34), (TILE_W, TILE_H), (0, 0, 0), -1)
        cv2.putText(tile, f"#{k}  frame {fr}  boxes {len(boxes)}", (8, TILE_H - 10), 0, 0.8, (0, 255, 255), 2)
        tiles.append(tile)
        rows.append({"i": k, "frame": int(fr), "boxes": int(len(boxes))})
        if len(tiles) == 4:
            cv2.imwrite(str(out_dir / f"sheet_{k // 4:03d}.jpg"), np.vstack([np.hstack(tiles[:2]), np.hstack(tiles[2:])]))
            tiles = []
    if tiles:
        while len(tiles) < 4:
            tiles.append(np.zeros_like(tiles[0]))
        cv2.imwrite(str(out_dir / f"sheet_{(len(rows) - 1) // 4:03d}.jpg"),
                    np.vstack([np.hstack(tiles[:2]), np.hstack(tiles[2:])]))
    doc = {"detector": "RF-DETR Medium 1.11.2, COCO person, threshold 0.3", "shots": shot_ids, "frames": rows}
    (out_dir / "frames.json").write_text(json.dumps(doc, indent=1) + "\n")
    return {"frames": len(rows), "sheets": (len(rows) + 3) // 4, "boxes": sum(r["boxes"] for r in rows)}


def score(slug_dir: Path) -> dict:
    labels = json.loads((slug_dir / "recall_labels.json").read_text())
    rows = labels["frames"]
    boxes = sum(r["boxes"] for r in rows)
    false = sum(r["false"] for r in rows)
    missed = sum(r["missed"] for r in rows)
    tp = boxes - false
    res = {"frames": len(rows), "boxes": boxes, "true_boxes": tp, "false_boxes": false, "missed": missed,
           "recall": round(tp / max(tp + missed, 1), 4), "precision": round(tp / max(boxes, 1), 4),
           "threshold_recall": 0.9, "labelled_by": labels.get("labelled_by"), "detector": labels.get("detector")}
    res["passed"] = res["recall"] >= 0.9 and len(rows) >= 200
    (slug_dir / "recall.json").write_text(json.dumps(res, indent=1) + "\n")
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m evals.pitchwatch.recall")
    ap.add_argument("slug_dir", type=Path)
    ap.add_argument("action", choices=("sheets", "score"))
    ap.add_argument("--shots", default="43,48,49,62,135")
    ap.add_argument("--per-shot", type=int, default=40)
    args = ap.parse_args(argv)
    if args.action == "sheets":
        print(json.dumps(sheets(args.slug_dir, [int(s) for s in args.shots.split(",")], args.per_shot)))
        return 0
    res = score(args.slug_dir)
    print(json.dumps(res))
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
