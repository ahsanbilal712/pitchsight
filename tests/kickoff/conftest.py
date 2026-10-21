"""One full Kickoff match shared by the kickoff tests (about 15 s on CPU)."""

import time
from pathlib import Path

import pytest

from kickoff import Engine, League

ROOT = Path(__file__).resolve().parents[2]
LEAGUE_DIR = ROOT / "data" / "league"
SEED = 7


@pytest.fixture(scope="session")
def league() -> League:
    return League.load(LEAGUE_DIR)


@pytest.fixture(scope="session")
def full_match(league):
    engine = Engine(league, league.club_order[0], league.club_order[1], seed=SEED)
    started = time.perf_counter()
    record = engine.play()
    return {"record": record, "seconds": time.perf_counter() - started, "engine": engine}
