"""The CI workflow defines exactly the nine CI jobs."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
JOBS = ["lint", "unit", "schemas", "golden-determinism", "evals-gate", "licence-scan", "spend-ledger",
        "frozen-cache-guard", "chaos-resume"]


def test_ci_has_exactly_the_nine_jobs() -> None:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
    assert list(workflow["jobs"]) == JOBS


def test_every_job_runs_unconditionally() -> None:
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "hashFiles(" not in text and "skipped" not in text
