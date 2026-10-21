"""The CI workflow defines exactly the nine TECH_PLAN 1.10 jobs (T-005)."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
JOBS = ["lint", "unit", "schemas", "golden-determinism", "evals-gate", "licence-scan", "spend-ledger",
        "frozen-cache-guard", "chaos-resume"]


def test_ci_has_exactly_the_nine_jobs() -> None:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
    assert list(workflow["jobs"]) == JOBS


def test_guarded_jobs_print_their_ticket() -> None:
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    for ticket in ("T-007", "T-056", "T-066", "T-060", "T-051"):
        assert f'echo "skipped: {ticket}"' in text
