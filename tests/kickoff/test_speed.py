"""Performance, NaN guard and batch independence."""

import numpy as np
import pytest

from kickoff import Engine, EngineError


def test_full_match_under_60_seconds(full_match):
    rec = full_match["record"]
    assert len(rec.tracking["t_ms"]) == 54_001
    assert full_match["seconds"] < 60.0, f"90-minute match took {full_match['seconds']:.1f} s"
    print(f"\n90-minute match at B=1: {full_match['seconds']:.1f} s")


def test_nan_in_state_raises(league):
    engine = Engine(league, league.club_order[0], league.club_order[1], seed=3)
    engine.step()
    engine.S[0, 4, 0] = np.nan
    with pytest.raises(EngineError):
        engine.step()


def test_world_zero_is_independent_of_batch_size(league):
    home, away = league.club_order[0], league.club_order[1]
    single = Engine(league, home, away, seed=5, batch=1)
    batched = Engine(league, home, away, seed=5, batch=3)
    for _ in range(1200):
        single.step()
        batched.step()
    assert np.array_equal(single.S[0], batched.S[0])
    assert not np.array_equal(batched.S[0], batched.S[1])
    state = batched.state()
    assert state.S.shape == (3, 23, 6) and state.S.dtype == np.float32
    assert state.score.shape == (3, 2)
