"""The rollout primitive (TECH_PLAN 1.5) and MatchRef, the handle callers use to reach a match state.

    rollout(state, overrides, B, horizon_s, seed, engine="scripted_v1") -> Futures

`state` must come from `MatchRef.state_at` or `Engine.snapshot_state` (its `source` is a one-world engine fork).
Determinism: world b draws from numpy.random.default_rng(seed + b); the same (state, overrides, B, horizon_s,
seed, engine, engine_hash) gives byte-identical Futures (`Futures.digest`).
"""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np

from heads.features import xt_xg_15
from kickoff import BranchError, Engine, League, Override, State
from kickoff.engine import TICK_MS
from physics.indices import chaos_index, transition_share_at, turnover_rate
from physics.pitch_control import pitch_control

from .futures import Futures, value_terminal, xt_gain

ROOT = Path(__file__).resolve().parents[2]
LEAGUE_DIR = ROOT / "data" / "league"
POLICY_MAX_HORIZON_S = 8.0          # ADR-002: learned rollouts are decision-only and capped at 8 s


def engine_hash() -> str:
    """SHA-1 over the kickoff and rollout sources: names the code that produced a cached future."""
    h = hashlib.sha1()
    for pkg in ("kickoff", "rollout"):
        for path in sorted((ROOT / "packages" / pkg).glob("*.py")):
            h.update(path.name.encode())
            h.update(path.read_bytes())
    return h.hexdigest()


@dataclass
class MatchRef:
    """A Kickoff match by seed. States are re-simulated from kick-off (never read from truth.json); events with ids
    come from `match_dir` (events.jsonl or events.jsonl.gz) when given, else from one full simulation."""
    seed: int
    home: str | None = None
    away: str | None = None
    match_dir: Path | None = None
    league_dir: Path = LEAGUE_DIR
    _league: League | None = field(default=None, repr=False)
    _engine: Engine | None = field(default=None, repr=False)
    _events: list[dict] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self._league = League.load(self.league_dir)
        if self.home is None or self.away is None:
            self.home, self.away = self._league.fixture(self.seed)

    @property
    def match_id(self) -> str:
        return f"m_{self.seed}"

    def engine_at(self, t_ms: int) -> Engine:
        """The running one-world engine moved to t_ms (forward in place; a past time restarts from kick-off)."""
        if self._engine is None or self._engine.t_ms > t_ms:
            self._engine = Engine(self._league, self.home, self.away, seed=self.seed)
            self._engine.record_events = False
        while self._engine.t_ms < t_ms:
            self._engine.step()
        return self._engine

    def state_at(self, t_ms: int) -> State:
        return self.engine_at(t_ms).snapshot_state()

    def events(self) -> list[dict]:
        if self._events is None:
            path = None if self.match_dir is None else Path(self.match_dir)
            if path is not None and (path / "events.jsonl").exists():
                lines = (path / "events.jsonl").read_text(encoding="utf-8").splitlines()
            elif path is not None and (path / "events.jsonl.gz").exists():
                with gzip.open(path / "events.jsonl.gz", "rt", encoding="utf-8") as fh:
                    lines = fh.read().splitlines()
            else:
                rec = Engine(self._league, self.home, self.away, seed=self.seed).play()
                lines = [json.dumps(e) for e in rec.events]
            self._events = [json.loads(line) for line in lines]
        return self._events


def context_at(events: list[dict], state: State) -> dict:
    """Match context for the win-probability head at the branch point (from events up to t_ms, never truth)."""
    t = state.t_ms
    past = [e for e in events if e["t_ms"] <= t]
    xt, xg = xt_xg_15(past, t)
    rate = turnover_rate(past, t)
    pc = pitch_control(np.asarray(state.S[0], dtype=np.float64))
    return {"xt_diff_15": xt, "xg_diff_15": xg, "chaos": chaos_index(pc, rate, transition_share_at(past, t))}


@dataclass
class Simulation:
    """The raw futures of one rollout before valuation: the engine after the horizon and what happened on the way."""
    eng: Engine
    goals: np.ndarray            # [B, 2]
    shots: np.ndarray            # [B, 2]
    paths: np.ndarray            # [B, horizon_s + 1, 2] ball at 1 Hz
    start_ball: np.ndarray       # [B, 2]


def simulate(state: State, overrides: Override | None, B: int, horizon_s: float, seed: int,
             engine: Literal["scripted_v1", "policy_v1"] = "scripted_v1", decide_now: bool = False) -> Simulation:
    """Branch `state` into B worlds and run them for horizon_s seconds (raises BranchError for an illegal override)."""
    if engine == "policy_v1":
        if horizon_s > POLICY_MAX_HORIZON_S:
            raise ValueError(f"policy_v1 rollouts are capped at {POLICY_MAX_HORIZON_S} s (ADR-002)")
        from .policy_engine import policy_branch  # T-036
        make = policy_branch
    elif engine == "scripted_v1":
        make = None
    else:
        raise ValueError(f"unknown engine {engine}")
    if state.source is None:
        raise ValueError("state has no source engine; use MatchRef.state_at or Engine.snapshot_state")
    src = state.source
    eng = src.branch(src.t_ms, B, overrides, seed=seed, decide_now=decide_now) if make is None \
        else make(src, B, overrides, seed=seed, decide_now=decide_now)
    steps = int(round(horizon_s * 1000 / TICK_MS))
    score0, shots0 = eng.score.copy(), eng.shots.copy()
    start_ball = eng.S[:, 22, 0:2].copy()
    paths = [start_ball.copy()]
    for i in range(1, steps + 1):
        eng.step()
        if i % 10 == 0:
            paths.append(eng.S[:, 22, 0:2].copy())
    return Simulation(eng, eng.score - score0, eng.shots - shots0, np.stack(paths, axis=1), start_ball)


def rollout(state: State, overrides: Override | None, B: int, horizon_s: float, seed: int,
            engine: Literal["scripted_v1", "policy_v1"] = "scripted_v1", decide_now: bool = False,
            events: list[dict] | None = None) -> Futures:
    """Run B futures of horizon_s seconds from `state`. `decide_now` makes the player in control take the decision
    model's own choice on the first tick (the unforced baseline at a decision point); `overrides.first_action` forces
    a choice instead. `events` (the match so far) feed the win-probability context; without them it is neutral."""
    meta = {"t_ms": int(state.t_ms), "B": int(B), "horizon_s": float(horizon_s), "seed": int(seed), "engine": engine}
    try:
        sim = simulate(state, overrides, B, horizon_s, seed, engine, decide_now)
    except BranchError as err:
        return Futures.invalid(str(err), meta)
    eng, goals, shots = sim.eng, sim.goals, sim.shots
    src = state.source
    context = context_at(events, state) if events is not None else {"xt_diff_15": 0.0, "xg_diff_15": 0.0, "chaos": 50.0}
    p_home, p_away, outcome = value_terminal(eng, goals, context)
    wp = outcome[:, 0]
    team0 = int(src.possession[0]) if src.possession[0] >= 0 else 0
    gain = xt_gain(sim.start_ball, eng.S[:, 22, 0:2], team0, src.period)
    half = 1.96 * float(np.std(wp)) / np.sqrt(B)
    mean_wp = float(np.mean(wp))
    return Futures(S_end=eng.S.astype(np.float32), goals=goals.astype(np.int16), shots=shots.astype(np.int16),
                   ball_paths=sim.paths.astype(np.float32), p_goal_home=float(np.mean(p_home)),
                   p_goal_away=float(np.mean(p_away)), win_prob_home=mean_wp, ci95=(mean_wp - half, mean_wp + half),
                   xt_gain_mean=float(np.mean(gain)), meta=meta,
                   per_world={"p_home": p_home, "p_away": p_away, "win_prob": wp, "away_win": outcome[:, 2],
                              "first_kind": eng.first_kind.copy(), "first_target": eng.first_target.copy()})
