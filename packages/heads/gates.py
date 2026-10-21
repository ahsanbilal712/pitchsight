"""Outcome-head gates (TECH_PLAN 1.6, T-025): read each <head>.metrics.json and fail with the head and the number
when a threshold is missed. Thresholds live here and in train.THRESHOLDS; they are never relaxed to pass.

    python -m heads.gates [packages/heads/artifacts]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .models import ARTIFACTS

GATES = {
    "xg": [("ece", "<=", 0.03)],
    "pass": [("ece", "<=", 0.03)],
    "winprob": [("ece", "<=", 0.03)],
    "goal8s": [("ece", "<=", 0.01), ("pr_auc", "report", None)],
    "chaos": [("auc", ">=", 0.70)],
}


class GateFailed(AssertionError):
    pass


def check(artifacts: Path = ARTIFACTS) -> dict[str, dict]:
    """{head: {metric: {value, op, threshold, passed}}}; raises GateFailed listing every miss."""
    out, misses = {}, []
    for head, rules in GATES.items():
        path = Path(artifacts) / f"{head}.metrics.json"
        if not path.exists():
            raise GateFailed(f"{head}: {path} is missing")
        test = json.loads(path.read_text(encoding="utf-8"))["test"]
        out[head] = {}
        for metric, op, thr in rules:
            v = float(test[metric])
            ok = True if op == "report" else (v <= thr if op == "<=" else v >= thr)
            out[head][metric] = {"value": v, "op": op, "threshold": thr, "passed": ok}
            if not ok:
                misses.append(f"{head} {metric} {v:.4f} misses {op} {thr}")
    if misses:
        raise GateFailed("; ".join(misses))
    return out


def main(argv: list[str] | None = None) -> int:
    path = Path(argv[0]) if argv else ARTIFACTS
    try:
        res = check(path)
    except GateFailed as err:
        print(f"FAIL: {err}")
        return 1
    for head, metrics in res.items():
        print(head, ", ".join(f"{m} {r['value']:.4f}" for m, r in metrics.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
