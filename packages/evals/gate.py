"""evals-gate (TECH_PLAN 1.10 CI job, 1.11 thresholds; T-056): fails when a measured number misses its threshold.

    python -m evals.gate [packages/evals/results.json]

Reads the committed results.json that run_evals wrote. Exit 1 when any row is "fail" or a gated row has no status;
"pending" (not measurable yet, the owning ticket named), "reported" (no threshold) and "cut" (a documented cut line
was applied: the threshold is unchanged and the miss stays in the table) are listed but do not fail. Standard
library only, so the CI job needs no install.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "packages" / "evals" / "results.json"
STATUSES = ("pass", "fail", "pending", "reported", "cut")


def check(results: dict) -> list[str]:
    problems = []
    for row in results["rows"]:
        status = row.get("status")
        if status not in STATUSES:
            problems.append(f"{row['id']}: status {status!r} (must be one of {', '.join(STATUSES)})")
        elif status == "fail":
            problems.append(f"{row['id']}: {row['measured']} misses {row['threshold']}")
        elif status == "pending" and "T-" not in (row.get("measured") or ""):
            problems.append(f"{row['id']}: pending without the ticket that measures it")
    return problems


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    path = Path(argv[0]) if argv else RESULTS
    results = json.loads(path.read_text(encoding="utf-8"))
    problems = check(results)
    for row in results["rows"]:
        print(f"{row['status']:>8}  {row['id']}: {row['measured']}  (threshold {row['threshold']})")
    if problems:
        print("\nevals-gate FAILED:\n  " + "\n  ".join(problems))
        return 1
    print(f"\nevals-gate passed ({sum(r['status'] == 'pass' for r in results['rows'])} measured rows pass)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
