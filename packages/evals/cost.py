"""Cost per match from the spend ledger.

    python -m evals.cost [--ledger data/spend/ledger.jsonl] [--matches 9001,9002,9003]

Sums `cost_usd` per match and mode from every ledger row SpendGuard wrote. Gate: each live match <= $2.50
(`budgets.yaml` spend.per_match_cap); the golden match's precompute is reported against the same cap; the project
total against spend.project_total_cap ($50). Rows without a match (offline jobs: cluster naming, the CI judge) count
only in the total.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "data" / "spend" / "ledger.jsonl"


def caps() -> tuple[float, float]:
    spend = yaml.safe_load((ROOT / "config" / "budgets.yaml").read_text(encoding="utf-8")).get("spend", {}) or {}
    return float(spend.get("per_match_cap", 2.50)), float(spend.get("project_total_cap", 50.0))


def ledger_costs(path: Path = LEDGER) -> dict:
    per: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    total, rows = 0.0, 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        c = float(r.get("cost_usd") or 0.0)
        total += c
        rows += 1
        per[r.get("match_id") or "none"][r.get("mode") or "unknown"] += c
    per_match, project = caps()
    matches = {m: {"by_mode": {k: round(v, 4) for k, v in modes.items()}, "total_usd": round(sum(modes.values()), 4)}
               for m, modes in sorted(per.items())}
    for m, row in matches.items():
        row["passed"] = None if m == "none" else row["total_usd"] <= per_match
    return {"matches": matches, "project_total_usd": round(total, 4), "rows": rows, "per_match_cap_usd": per_match,
            "project_cap_usd": project, "project_passed": total <= project}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m evals.cost")
    ap.add_argument("--ledger", type=Path, default=LEDGER)
    ap.add_argument("--matches", default="")
    args = ap.parse_args(argv)
    res = ledger_costs(args.ledger)
    wanted = [m if m.startswith("m_") else f"m_{m}" for m in args.matches.split(",") if m]
    if wanted:
        res["matches"] = {m: res["matches"].get(m, {"total_usd": 0.0, "by_mode": {}, "passed": None}) for m in wanted}
    print(json.dumps(res, indent=1))
    bad = [m for m, r in res["matches"].items() if r["passed"] is False]
    return 1 if bad or not res["project_passed"] else 0


if __name__ == "__main__":
    sys.exit(main())
