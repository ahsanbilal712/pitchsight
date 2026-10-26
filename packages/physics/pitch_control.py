"""Pitch control: which team would reach each 2 m cell first (Spearman-style).

Implemented from the published method (Spearman 2018, "Beyond expected goals"), simplified: each player's
time to intercept a cell is a reaction phase on the current velocity followed by a straight run at top speed;
control is the logistic arrival-time model of the paper extended to all 22 players as a softmin, so with one
player per team the home share is exactly 1 / (1 + exp(-(t_away - t_home) / s)) with s = sqrt(3) * sigma / pi.
Ball travel time and the integration over control build-up are left out (they cost time and the grid is only a
visual and a feature). Vectorised over 1,802 cells x 22 players.
"""

from __future__ import annotations

import math

import numpy as np

from .window import PITCH_L, PITCH_W

REACTION_S = 0.7          # players keep their velocity for this long before turning
VMAX = 5.0                # m/s, run speed after the reaction phase
SIGMA = 0.45              # s, arrival-time uncertainty (Spearman 2018)
SCALE = math.sqrt(3.0) * SIGMA / math.pi

_GRIDS: dict[float, tuple[np.ndarray, np.ndarray]] = {}


def grid(cell_m: float = 2.0) -> tuple[np.ndarray, np.ndarray]:
    """Cell centres (x [nx], y [ny]); 2 m cells give ny = 34 rows and nx = 53 columns over 105 x 68 m."""
    if cell_m not in _GRIDS:
        nx, ny = math.ceil(PITCH_L / cell_m - 1e-9), round(PITCH_W / cell_m)
        _GRIDS[cell_m] = ((np.arange(nx) + 0.5) * PITCH_L / nx, (np.arange(ny) + 0.5) * PITCH_W / ny)
    return _GRIDS[cell_m]


def arrival_times(S: np.ndarray, cell_m: float = 2.0) -> np.ndarray:
    """Time (s) for each of the 22 players to reach each cell: [22, ny, nx]."""
    gx, gy = grid(cell_m)
    p = np.asarray(S[:22, 0:2], dtype=np.float64) + REACTION_S * np.asarray(S[:22, 2:4], dtype=np.float64)
    dx = gx[None, None, :] - p[:, 0, None, None]
    dy = gy[None, :, None] - p[:, 1, None, None]
    return REACTION_S + np.sqrt(dx * dx + dy * dy) / VMAX


def pitch_control(S: np.ndarray, cell_m: float = 2.0) -> np.ndarray:
    """Home share of control per cell, [34, 53] for 2 m cells (rows = y bottom to top, columns = x left to right).

    S is one frame [23, 6] (rows 0-10 home, 11-21 away). Home share + away share = 1 in every cell.
    """
    t = arrival_times(S, cell_m)
    t_min = t.min(axis=0, keepdims=True)
    w = np.exp(-(t - t_min) / SCALE)
    home = w[:11].sum(axis=0)
    return home / (home + w[11:].sum(axis=0))


def control_at(S: np.ndarray, points: np.ndarray) -> np.ndarray:
    """Home share of control at arbitrary points [P, 2] (same model as `pitch_control`, no grid)."""
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    p = np.asarray(S[:22, 0:2], dtype=np.float64) + REACTION_S * np.asarray(S[:22, 2:4], dtype=np.float64)
    t = REACTION_S + np.hypot(pts[None, :, 0] - p[:, 0, None], pts[None, :, 1] - p[:, 1, None]) / VMAX   # [22, P]
    w = np.exp(-(t - t.min(axis=0, keepdims=True)) / SCALE)
    home = w[:11].sum(axis=0)
    return home / (home + w[11:].sum(axis=0))


def zones(pc: np.ndarray, home_attacks_right: bool = True) -> dict[str, float]:
    """Home share by third (defensive, middle, attacking from the home team's view) and the contested fraction."""
    nx = pc.shape[1]
    thirds = np.array_split(np.arange(nx), 3)
    if not home_attacks_right:
        thirds = thirds[::-1]
    names = ("home_defensive_third", "middle_third", "home_attacking_third")
    out = {n: float(pc[:, cols].mean()) for n, cols in zip(names, thirds, strict=True)}
    out["contested_frac"] = contested_fraction(pc)
    return out


def contested_fraction(pc: np.ndarray, band: float = 0.15) -> float:
    """Share of cells where neither team controls clearly (|share - 0.5| < band)."""
    return float(np.mean(np.abs(pc - 0.5) < band))
