"""Match indices over a tracking window and the chaos index (TECH_PLAN 1.4 physics).

Turnovers are open-play possession changes (`possession_change` events), so restarts do not count as chaos.
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
RATE_TAU_S = 60.0         # s, time constant of the exponentially weighted turnover rate
# chaos_index: the turnover rate maps linearly from RATE_LO (chaos 20) to RATE_HI (chaos 85) per minute; transition
# share and contested pitch nudge it by at most CHAOS_NUDGE points each. Calibrated against the hidden match regimes
# (truth phases with side "M") so the state machine's 65 / 50 thresholds separate them (T-013, T-055).
RATE_LO, RATE_HI = 1.0, 7.0
CHAOS_NUDGE = 0.0           # measured: nudges cost macro F1 (0.748 vs 0.765, seeds 1-30), so off for now
TRANSITION_MID, CONTESTED_MID = 0.40, 0.035


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


def open_play_turnovers(events: list[dict], t0: int, t1: int) -> np.ndarray:
    """Times of open-play turnovers (possession_change events: tackles won, interceptions, loose balls) in
    [t0, t1]. Restarts that hand the ball over (throw-ins, goal kicks) are not turnovers."""
    return np.array(sorted(e["t_ms"] for e in events if e.get("type") == "possession_change" and t0 <= e["t_ms"] <= t1),
                    dtype=np.int64)


def transition_share(window: TrackingWindow, after_s: float = TRANSITION_S, events: list[dict] | None = None) -> float:
    """Share of the window's frames that fall within `after_s` of a turnover (open-play turnovers from `events`
    when given, else every change of the team in possession in the tracking)."""
    if len(window) == 0:
        return 0.0
    t = window.t_ms
    if events is None:
        turn_t = t[turnover_mask(window.possession)]
    else:
        turn_t = open_play_turnovers(events, int(t[0]) - int(after_s * 1000), int(t[-1]))
    if turn_t.size == 0:
        return 0.0
    k = np.searchsorted(turn_t, t, side="right") - 1
    since = np.where(k >= 0, t - turn_t[np.maximum(k, 0)], np.inf)
    return float(np.mean(since <= after_s * 1000))


def transition_share_at(events: list[dict], t_ms: int, window_s: int = 60, after_s: float = TRANSITION_S) -> float:
    """Share of the 1 s points in the last `window_s` seconds that fall within `after_s` of an open-play turnover
    (events only, no tracking: the form the heads and the rollout context use)."""
    turns = open_play_turnovers(events, t_ms - (window_s + 10) * 1000, t_ms)
    if turns.size == 0:
        return 0.0
    grid_t = np.arange(t_ms - (window_s - 1) * 1000, t_ms + 1, 1000)
    k = np.searchsorted(turns, grid_t, side="right") - 1
    return float(np.mean(np.where(k >= 0, grid_t - turns[np.maximum(k, 0)], 10**9) <= after_s * 1000))


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
    turnovers = int(open_play_turnovers(events, t0, t1).size)
    trans = transition_share(window, events=events)
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
    out["turnovers_60s"] = turnover_rate(events, t1)
    out["chaos"] = chaos_index(pc, out["turnovers_60s"], trans)
    return out


def turnover_rate(events: list[dict], t_ms: int, tau_s: float = RATE_TAU_S) -> float:
    """Open-play turnovers per minute at t_ms, exponentially weighted with time constant tau_s (unbiased for a
    constant rate; less noisy than a box count over the same lag)."""
    t = open_play_turnovers(events, int(t_ms - 8 * tau_s * 1000), int(t_ms))
    if t.size == 0:
        return 0.0
    return float(np.exp(-(t_ms - t) / (tau_s * 1000.0)).sum() / tau_s * 60.0)


def chaos_index(pc: np.ndarray, turnovers_60s: float, transition_share: float) -> float:
    """0-100 fallback formula until the learned chaos head exists. `turnovers_60s` is a rate per 60 s (indices
    passes the exponentially weighted rate); transition share and contested pitch add or remove a few points."""
    base = 20.0 + 65.0 * (float(turnovers_60s) - RATE_LO) / (RATE_HI - RATE_LO)
    nudge = CHAOS_NUDGE * np.clip((float(transition_share) - TRANSITION_MID) / TRANSITION_MID, -1, 1)
    nudge += CHAOS_NUDGE * np.clip((contested_fraction(pc) - CONTESTED_MID) / CONTESTED_MID, -1, 1)
    return float(round(np.clip(base + nudge, 0.0, 100.0), 3))
