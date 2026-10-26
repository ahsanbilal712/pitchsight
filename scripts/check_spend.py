"""Fail if the spend ledger breaks the project or per-match caps.

Usage: python scripts/check_spend.py [LEDGER]

Reads caps from config/budgets.yaml (spend block) and the ledger from LEDGER, else
$WHYLINE_SPEND_LEDGER, else spend.ledger_path. A missing or empty ledger is fine.
Fails when the ledger total exceeds project_total_cap or any live match_id exceeds per_match_cap.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FIELDS = {"ts", "role", "model", "tokens_in", "tokens_out", "cost_usd", "match_id", "mode"}


def main() -> int:
    spend = yaml.safe_load((ROOT / "config" / "budgets.yaml").read_text())["spend"]
    arg = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("WHYLINE_SPEND_LEDGER", spend["ledger_path"])
    ledger = Path(arg) if Path(arg).is_absolute() else ROOT / arg
    errors: list[str] = []
    total, per_live_match, per_day = 0.0, defaultdict(float), defaultdict(float)
    lines = ledger.read_text().splitlines() if ledger.exists() else []
    for n, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {n}: invalid JSON: {exc}")
            continue
        if set(row) != FIELDS:
            errors.append(f"line {n}: fields {sorted(row)} != {sorted(FIELDS)}")
            continue
        cost = float(row["cost_usd"])
        total += cost
        per_day[str(row["ts"])[:10]] += cost
        if row["mode"] == "live" and row["match_id"]:
            per_live_match[row["match_id"]] += cost
    if total > spend["project_total_cap"]:
        errors.append(f"ledger total ${total:.4f} exceeds project cap ${spend['project_total_cap']:.2f}")
    for match_id, cost in sorted(per_live_match.items()):
        if cost > spend["per_match_cap"]:
            errors.append(f"live match {match_id} spent ${cost:.4f}, cap ${spend['per_match_cap']:.2f}")
    worst_day = max(per_day.items(), key=lambda kv: kv[1], default=("-", 0.0))
    if errors:
        print("check_spend: FAIL")
        for e in errors:
            print("  " + e)
        return 1
    print(f"check_spend: OK ({len(lines)} ledger lines, total ${total:.4f} of ${spend['project_total_cap']:.2f}; "
          f"busiest day {worst_day[0]} ${worst_day[1]:.4f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
