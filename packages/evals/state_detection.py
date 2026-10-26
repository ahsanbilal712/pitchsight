"""State detection vs hidden truth.

    python -m evals.state_detection --seeds 1..50

Every second of each evaluation match, the physics state machine (Settled / Transitional / Chaotic, fed with the
chaos index over the last 60 s) is compared with the engine's hidden match regime: truth.json phases with side "M"
(state_settled / state_transitional / state_chaotic). Truth is read only here, for scoring. Reports macro precision,
recall and F1 (gate: F1 >= 0.75), per-class numbers and a confusion matrix; writes packages/evals/out/
state_detection.json and state_confusion.png.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "data" / "matches" / "corpus"
OUT = ROOT / "packages" / "evals" / "out"
STATES = ("Settled", "Transitional", "Chaotic")
TRUTH = {"state_settled": "Settled", "state_transitional": "Transitional", "state_chaotic": "Chaotic"}
THRESHOLD = 0.75


def parse_seeds(text: str) -> list[int]:
    out: list[int] = []
    for part in text.split(","):
        a, _, b = part.partition("..")
        out.extend(range(int(a), int(b or a) + 1))
    return out


def label_match(seed: int) -> tuple[list[str], list[str]]:
    """(truth, predicted) per second of one full-tracking evaluation match."""
    from physics import StateMachine, TrackingWindow, indices

    d = CORPUS / str(seed)
    window = TrackingWindow.load(d)
    events = [json.loads(line) for line in (d / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    regimes = [p for p in json.loads((d / "truth.json").read_text(encoding="utf-8"))["phases"] if p["side"] == "M"]
    sm = StateMachine()
    truth, pred = [], []
    for t in range(1000, 5_400_000, 1000):
        sm.update(indices(window.slice(max(0, t - 60_000), t), events)["chaos"], t)
        truth.append(TRUTH[next(p["label"] for p in regimes if p["start_ms"] <= t < p["end_ms"])])
        pred.append(sm.state)
    return truth, pred


def score(truth: list[str], pred: list[str]) -> dict:
    y, p = np.array(truth), np.array(pred)
    per, cm = {}, np.zeros((3, 3), dtype=int)
    for i, a in enumerate(STATES):
        for j, b in enumerate(STATES):
            cm[i, j] = int(np.sum((y == a) & (p == b)))
    for k in STATES:
        tp = int(np.sum((y == k) & (p == k)))
        prec = tp / max(int(np.sum(p == k)), 1)
        rec = tp / max(int(np.sum(y == k)), 1)
        per[k] = {"precision": round(prec, 4), "recall": round(rec, 4),
                  "f1": round(2 * prec * rec / max(prec + rec, 1e-12), 4), "support_s": int(np.sum(y == k))}
    macro = {m: round(float(np.mean([per[k][m] for k in STATES])), 4) for m in ("precision", "recall", "f1")}
    return {"macro": macro, "per_class": per, "confusion": cm.tolist(), "labels": list(STATES),
            "accuracy": round(float(np.mean(y == p)), 4)}


def plot(cm: list[list[int]], macro_f1: float, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    m = np.array(cm, dtype=float)
    norm = m / np.maximum(m.sum(axis=1, keepdims=True), 1)
    fig, ax = plt.subplots(figsize=(5.2, 4.4), dpi=110)
    ax.imshow(norm, cmap="Blues", vmin=0, vmax=1)
    for i in range(3):
        for j in range(3):
            ax.text(j, i, f"{norm[i, j]:.2f}\n({int(m[i, j]):,} s)", ha="center", va="center", fontsize=8,
                    color="white" if norm[i, j] > 0.5 else "black")
    ax.set_xticks(range(3), STATES)
    ax.set_yticks(range(3), STATES)
    ax.set_xlabel("state machine (chaos index)")
    ax.set_ylabel("hidden match regime (truth)")
    ax.set_title(f"State detection, seeds 1-50: macro F1 {macro_f1:.3f}", fontsize=10)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m evals.state_detection")
    ap.add_argument("--seeds", default="1..50")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    args = ap.parse_args(argv)
    seeds = parse_seeds(args.seeds)
    if any(not 1 <= s <= 50 for s in seeds):
        raise SystemExit("state detection uses the evaluation seeds 1-50 (full tracking)")
    with Pool(args.workers) as pool:
        parts = pool.map(label_match, seeds)
    truth = [t for tr, _ in parts for t in tr]
    pred = [p for _, pr in parts for p in pr]
    res = {**score(truth, pred), "seeds": [min(seeds), max(seeds)], "matches": len(seeds), "seconds": len(truth),
           "threshold_f1": THRESHOLD, "truth": "truth.json phases side M (hidden match regime)",
           "detector": "physics.StateMachine over physics.indices chaos (60 s window, turnover EWMA)"}
    res["passed"] = res["macro"]["f1"] >= THRESHOLD
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "state_detection.json").write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    plot(res["confusion"], res["macro"]["f1"], args.out / "state_confusion.png")
    print(json.dumps({"macro": res["macro"], "accuracy": res["accuracy"], "passed": res["passed"]}))
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
