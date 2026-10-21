"""Match indices over a tracking window and the chaos index (TECH_PLAN 1.4 physics).

`indices` returns control, pressure, tempo and turnover rate plus the inputs of `chaos_index` (contested share,
turnovers in the window, transition share) and the mean closing speed of the nearest defender, so one call
yields every number the facts stream and the chaos head (T-015) need.
"""

from __future__ import annotations

import numpy as np

from .pitch_control import contested_fraction, pitch_control
from .window import TrackingWindow

PRESSURE_R = 3.0          # m, an opponent this close to the holder is pressing
TRANSITION_S = 10.0       # s after a turnover counts as transition
# chaos_index weights (sum 1) and the saturation points of its inputs; calibrated on seeds 1-50 (T-013)
CHAOS_W = {"contested": 0.25, "turnovers": 0.45, "transition": 0.30}
CONTESTED_SAT, TURNOVERS_SAT = 0.06, 6.0


def team_possession(possession: np.ndarray) -> np.ndarray:
    """Possession with -1 (dead ball, loose) carried forward from the last team in control; -1 before any."""
    pos = np.asarray(possession).astype(np.int64)
    idx = np.where(pos >= 0, np.arange(len(pos)), -1)
    np.maximum.accumulate(idx, out=idx)
    return np.where(idx >= 0, pos[np.maximum(idx, 0)], -1)


def turnover_mask(possession: np.ndarray) -> np.ndarray:
    """True at frames where possession passes from one team to the other (loose balls in between are skipped)."""
    team = team_possession(possession)
    out = np.zeros(len(team), dtype=bool)
    out[1:] = (team[1:] != team[:-1]) & (team[1:] >= 0) & (team[:-1] >= 0)
    return out


def transition_share(window: TrackingWindow, after_s: float = TRANSITION_S) -> float:
    """Share of the window's frames that fall within `after_s` of a turnover."""
    if len(window) == 0:
        return 0.0
    t = window.t_ms
    turn_t = t[turnover_mask(window.possession)]
    if turn_t.size == 0:
        return 0.0
    k = np.searchsorted(turn_t, t, side="right") - 1
    since = np.where(k >= 0, t - turn_t[np.maximum(k, 0)], np.inf)
    return float(np.mean(since <= after_s * 1000))


def _holder_pressure(window: TrackingWindow) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per frame with a holder: holder team, nearest-opponent distance, nearest opponent's closing speed."""
    held = np.flatnonzero(window.holder >= 0)
    if held.size == 0:
        return np.zeros(0, dtype=np.int64), np.zeros(0), np.zeros(0)
    h = window.holder[held].astype(np.int64)
    team = (h >= 11).astype(np.int64)
    S = window.S[held].astype(np.float64)
    pos_h = S[np.arange(held.size), h, 0:2]
    vel_h = S[np.arange(held.size), h, 2:4]
    opp_rows = np.where(team[:, None] == 0, np.arange(11, 22)[None, :], np.arange(0, 11)[None, :])
    opp = np.take_along_axis(S[:, :22, :], opp_rows[:, :, None], axis=1)
    rel = pos_h[:, None, :] - opp[:, :, 0:2]
    d = np.hypot(rel[..., 0], rel[..., 1])
    k = np.argmin(d, axis=1)
    rows = np.arange(held.size)
    dmin = d[rows, k]
    unit = rel[rows, k] / np.maximum(dmin, 1e-6)[:, None]
    closing = np.sum((opp[rows, k, 2:4] - vel_h) * unit, axis=1)
    return team, dmin, closing


def indices(window: TrackingWindow, events: list[dict]) -> dict[str, float]:
    """Indices over the window (typically the last 60 s); pitch control from the window's last frame."""
    if len(window) == 0:
        raise ValueError("empty tracking window")
    pc = pitch_control(window.S[-1])
    minutes = max(window.duration_s / 60.0, 1.0 / 60.0)
    team, dmin, closing = _holder_pressure(window)
    pressed = dmin < PRESSURE_R
    away_has, home_has = team == 1, team == 0
    t0, t1 = int(window.t_ms[0]), int(window.t_ms[-1])
    passes = sum(1 for e in events if e.get("type") == "pass" and t0 <= e["t_ms"] <= t1)
    turnovers = int(turnover_mask(window.possession).sum())
    trans = transition_share(window)
    contested = contested_fraction(pc)
    out = {
        "control_home": float(pc.mean()),
        "control_away": float(1.0 - pc.mean()),
        "pressure_home": float(pressed[away_has].mean()) if away_has.any() else 0.0,
        "pressure_away": float(pressed[home_has].mean()) if home_has.any() else 0.0,
        "tempo": passes / minutes,
        "turnover_rate": turnovers / minutes,
        "turnovers": float(turnovers),
        "transition_share": trans,
        "contested_frac": contested,
        "closing_speed": float(np.clip(closing[pressed], 0, None).mean()) if pressed.any() else 0.0,
    }
    out["chaos"] = chaos_index(pc, turnovers * 60.0 / max(window.duration_s, 1.0), trans)
    return out


def chaos_index(pc: np.ndarray, turnovers_60s: float, transition_share: float) -> float:
    """0-100 fallback formula until the learned chaos head exists: contested pitch, turnovers per 60 s and the
    share of time spent in transition, each saturating, weighted by CHAOS_W."""
    contested = min(contested_fraction(pc) / CONTESTED_SAT, 1.0)
    turnovers = min(float(turnovers_60s) / TURNOVERS_SAT, 1.0)
    trans = min(max(float(transition_share), 0.0), 1.0)
    value = (CHAOS_W["contested"] * contested + CHAOS_W["turnovers"] * turnovers + CHAOS_W["transition"] * trans)
    return float(round(100.0 * value, 3))
