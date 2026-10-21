"""Shared golden-match handle for the rollout tests (re-simulating to a branch point costs a few seconds)."""

from pathlib import Path

import pytest

from rollout import MatchRef

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "data" / "matches" / "4242"


@pytest.fixture(scope="session")
def golden() -> MatchRef:
    return MatchRef(4242, match_dir=GOLDEN)


@pytest.fixture(scope="session")
def decision_t(golden) -> int:
    """The decision tick of the first pass after 30:00 in the golden match (state the passer saw)."""
    ev = next(e for e in golden.events() if e["type"] == "pass" and e["t_ms"] > 1_800_000)
    return ev["t_ms"] - 100
