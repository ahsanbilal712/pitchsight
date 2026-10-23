"""Engine.send_off (track B's red-card cost, video v3): the player leaves play in every world, the default path is
untouched (golden determinism covers that), and ten men fare worse."""

from pathlib import Path

import numpy as np

from kickoff import Override
from rollout import MatchRef

GOLDEN = Path(__file__).resolve().parents[2] / "data" / "matches" / "4242"


def _run(eng, ticks):
    held, takers = [], []
    for _ in range(ticks):
        eng.step()
        held.append(eng.holder.copy())
        takers.append(eng.wa.restart_taker.copy())
    return np.array(held), np.array(takers)


def test_sent_off_player_never_plays():
    src = MatchRef(4242, match_dir=GOLDEN).state_at(1_800_000).source
    eng = src.branch(src.t_ms, 32, Override(sent_off={"home": [8]}), seed=7)
    held, takers = _run(eng, 1200)                     # two minutes
    row = 8
    assert not (held == row).any()
    assert not (takers == row).any()
    assert np.all(eng.S[:, row, 1] < -1000)            # parked off the pitch
    assert eng.sent_off[row] and eng.sent_off.sum() == 1


def test_ten_men_concede_more():
    src = MatchRef(4242, match_dir=GOLDEN).state_at(1_800_000).source
    goals = {}
    for name, ov in (("eleven", None), ("ten", Override(sent_off={"home": [5, 8]}))):
        eng = src.branch(src.t_ms, 64, ov, seed=11)
        for _ in range(6000):                          # ten minutes
            eng.step()
        goals[name] = (eng.score[:, 1] - eng.score[:, 0]).mean()
    assert goals["ten"] > goals["eleven"]
