"""GRF coordinates: metre mapping holds, team 0 attacks +x all game, speeds plausible, tokens flipped."""

from pathlib import Path

import numpy as np
import pytest

from policy.data import PITCH_L, PITCH_W, SHOOT, grf_file, grf_games

CSV = Path(__file__).resolve().parents[2] / "data" / "grf" / "tiny_set" / "gfootball_results_games_0-2.csv"


@pytest.fixture(scope="module")
def games():
    if not CSV.exists():
        pytest.skip("needs data/grf/tiny_set")
    return grf_games(CSV)


def test_positions_inside_the_pitch(games):
    for g in games.values():
        p = g["pos"][:, :22]
        inside = (p[..., 0] > -2) & (p[..., 0] < PITCH_L + 2) & (p[..., 1] > -2) & (p[..., 1] < PITCH_W + 2)
        assert inside.mean() > 0.999


def test_team_zero_defends_the_left_all_game(games):
    for g in games.values():
        T = len(g["holder"])
        for half in (slice(0, T // 2), slice(T // 2, T)):
            assert g["pos"][half, 0, 0].mean() < 20 and g["pos"][half, 11, 0].mean() > PITCH_L - 20


def test_speeds_plausible(games):
    for g in games.values():
        sp = np.hypot(g["vel"][:, :22, 0], g["vel"][:, :22, 1])
        assert np.percentile(sp, 99) < 10.0                         # m/s, a sprint is about 8


def test_tokens_attack_plus_x():
    data = grf_file(CSV)
    tok = data["tokens"].astype(np.float32)
    holder = tok[:, :, 5].argmax(axis=1)
    shots = data["kind"] == SHOOT
    assert shots.any() and np.mean(tok[shots, holder[shots], 0] * PITCH_L) > 70
