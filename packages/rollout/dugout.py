"""Dugout: which style change helps a team most right now (TECH_PLAN 1.5 "Callers", T-047).

    dugout(match, t_ms, team, options, n=100, horizon_s=8, seed=4242) -> list[OptionResult]

One rollout per option with `Override(styles={team: delta})` from the same state and seed (common random numbers),
plus the unchanged baseline; options are ranked by the change in that team's own win probability. `GRID` is the
3 x 3 grid of press_height and directness deltas (+-0.15) without the no-change cell; `top_options` keeps three.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import numpy as np

from kickoff import Override

from .core import MatchRef, rollout
from .futures import Futures

STEP = 0.15
GRID = [{"press_height": dp, "directness": dd} for dp, dd in product((-STEP, 0.0, STEP), repeat=2) if (dp, dd) != (0, 0)]
WORDS = {"press_height": ("drop the press", "press higher"), "directness": ("keep the ball", "go more direct")}


@dataclass
class OptionResult:
    delta: dict[str, float]          # style delta, e.g. {"press_height": 0.15, "directness": -0.15}
    label: str
    win_prob: float                  # the team's own win probability with the option
    delta_win_prob: float            # versus no change, same seed
    ci95: tuple[float, float]
    n: int
    horizon_s: float
    seed: int
    engine: str


def label(delta: dict[str, float]) -> str:
    parts = [WORDS[k][v > 0] for k, v in delta.items() if v]
    return " and ".join(parts) if parts else "no change"


def team_win(f: Futures, team: str) -> tuple[float, tuple[float, float]]:
    w = f.per_world["win_prob"] if team == "home" else f.per_world["away_win"]
    mean, half = float(np.mean(w)), 1.96 * float(np.std(w)) / np.sqrt(len(w))
    return mean, (mean - half, mean + half)


def dugout(match: MatchRef, t_ms: int, team: str, options: list[dict[str, float]] | None = None, n: int = 100,
           horizon_s: float = 8, seed: int = 4242, engine: str = "scripted_v1") -> list[OptionResult]:
    """Options ranked by Δ win probability for `team` ("home" or "away")."""
    state = match.state_at(t_ms)
    events = match.events()
    base, _ = team_win(rollout(state, None, n, horizon_s, seed, engine=engine, events=events), team)
    out = []
    for delta in options or GRID:
        wp, ci = team_win(rollout(state, Override(styles={team: delta}), n, horizon_s, seed, engine=engine,
                                  events=events), team)
        out.append(OptionResult(delta=dict(delta), label=label(delta), win_prob=round(wp, 4),
                                delta_win_prob=round(wp - base, 4), ci95=(round(ci[0], 4), round(ci[1], 4)), n=n,
                                horizon_s=float(horizon_s), seed=seed, engine=engine))
    return sorted(out, key=lambda r: (-r.delta_win_prob, r.label))


def top_options(results: list[OptionResult], k: int = 3) -> list[OptionResult]:
    return results[:k]
