"""Pitch control: shape, shares sum to 1, mirror symmetry, nearest player wins (T-013)."""

import numpy as np
import pytest

from physics import pitch_control, zones
from physics.pitch_control import grid


def _frame(seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    S = np.zeros((23, 6))
    S[:, 0] = rng.uniform(0, 105, 23)
    S[:, 1] = rng.uniform(0, 68, 23)
    S[:, 2:4] = rng.normal(0, 2.5, (23, 2))
    return S


def _swap_teams(S: np.ndarray) -> np.ndarray:
    return np.concatenate([S[11:22], S[0:11], S[22:]])


def test_grid_shape_and_range():
    gx, gy = grid(2.0)
    assert (len(gy), len(gx)) == (34, 53)
    pc = pitch_control(_frame())
    assert pc.shape == (34, 53)
    assert np.all((pc >= 0) & (pc <= 1))


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_home_and_away_shares_sum_to_one(seed):
    S = _frame(seed)
    home = pitch_control(S)
    away = pitch_control(_swap_teams(S))             # the away team's share computed as if it were home
    np.testing.assert_allclose(home + away, 1.0, atol=1e-12)


@pytest.mark.parametrize("seed", [3, 4])
def test_mirroring_the_pitch_inverts_the_shares(seed):
    S = _frame(seed)
    M = S.copy()
    M[:, 0], M[:, 1] = 105.0 - S[:, 0], 68.0 - S[:, 1]
    M[:, 2:4] = -S[:, 2:4]
    mirrored = pitch_control(_swap_teams(M))
    np.testing.assert_allclose(mirrored[::-1, ::-1], 1.0 - pitch_control(S), atol=1e-12)


def test_nearest_player_controls_his_cell():
    S = np.zeros((23, 6))
    S[:11, 0], S[:11, 1] = 20.0, 34.0                 # all home players at (20, 34)
    S[11:22, 0], S[11:22, 1] = 85.0, 34.0             # all away players at (85, 34)
    pc = pitch_control(S)
    gx, gy = grid()
    row, near_home, near_away = int(np.argmin(abs(gy - 34))), int(np.argmin(abs(gx - 20))), int(np.argmin(abs(gx - 85)))
    assert pc[row, near_home] > 0.99 and pc[row, near_away] < 0.01
    assert abs(pc[row, 26] - 0.5) < 0.05             # the halfway column is contested
    z = zones(pc)
    assert z["home_defensive_third"] > 0.9 and z["home_attacking_third"] < 0.1
