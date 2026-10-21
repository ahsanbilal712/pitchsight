"""Kickoff: a batched, deterministic football match engine with hidden tactical truth (ADR-001).

B worlds advance in lock-step at 10 Hz. Continuous physics (player movement, ball flight) is vectorised
over worlds; discrete match logic (control, duels, restarts, events) runs per world only where something
happens. World b draws all randomness from numpy.random.default_rng(seed + b): first its hidden truth
(style jitter, phases, momentum), then one fixed-width noise row per tick, so a world's match is a pure
function of (league, clubs, seed + b, decision model).

Coordinates follow schemas/event.schema.json: 105 x 68 m, origin bottom-left, home attacks +x in period 1.
State rows: 0-10 home, 11-21 away, 22 ball; columns x, y, vx, vy, stamina, facing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .errors import EngineError
from .events import TEAM_NAMES, Event, EventLog
from .league import SLOTS, STYLE_KEYS, League
from .physics_prior import (
    ACCEL,
    AIR_DRAG,
    BALL_REST_Z,
    BOX_DEPTH,
    BOX_HALF,
    CONTROL_R,
    DT,
    GOAL_H,
    GOAL_HALF,
    GOAL_Y,
    GROUND_DECAY,
    HEADER_Z,
    JOG,
    KEEPER_R,
    PENALTY_SPOT,
    PITCH_L,
    PITCH_W,
    PRESSURE_R,
    SPRINT,
    STAMINA_COST,
    TACKLE_R,
    TICK_MS,
    G,
    cone_count,
    goal_angle,
    goal_distance,
    pass_launch,
    to_team,
    xg,
)
from .rules import (
    CARRY,
    CLEAR,
    CROSS,
    FREE,
    HOLD,
    KICK_OFF,
    PASS,
    PASS_ONLY,
    PENALTY,
    SHOOT,
    DecisionBatch,
    ScriptedRule,
)

PERIOD_MS = 45 * 60 * 1000
MATCH_MS = 2 * PERIOD_MS
N_NOISE = 40
# engine noise slots (0-15 belong to the decision rule)
N_CONTROL, N_TACKLE, N_TACKLE_OUT, N_SHOT, N_AIM, N_SPEED, N_CATCH, N_CARD, N_DEFLECT, N_FOOT, N_CLEAR = range(16, 27)

# team-frame formation for 4-3-3 (u offset from the defensive line, v); GK handled separately
SLOT_U = np.array([0.0, 3.0, 0.0, 0.0, 3.0, 14.0, 10.0, 14.0, 30.0, 32.0, 30.0])
SLOT_V = np.array([34.0, 8.0, 25.0, 43.0, 60.0, 22.0, 34.0, 46.0, 10.0, 34.0, 58.0])
PHASES = ("phase_high_press", "phase_low_block", "phase_direct_play", "phase_patient_build", "phase_counter_attack")
PHASE_DELTA = {
    "phase_high_press": {"press_height": 0.25, "line_height": 0.15},
    "phase_low_block": {"press_height": -0.25, "line_height": -0.2},
    "phase_direct_play": {"directness": 0.3, "tempo": 0.1},
    "phase_patient_build": {"directness": -0.25, "tempo": -0.15},
    "phase_counter_attack": {"directness": 0.2, "press_height": -0.15, "tempo": 0.2},
}
RESTART_DELAY_MS = {"kick_off": 40000, "throw_in": 3000, "goal_kick": 6000, "corner": 7000, "free_kick": 6000,
                    "penalty": 9000}
RESTART_FLAG = {"kick_off": KICK_OFF, "throw_in": PASS_ONLY, "goal_kick": FREE, "corner": CROSS, "free_kick": FREE,
                "penalty": PENALTY}
SIDES = ("H", "A")


@dataclass
class State:
    S: np.ndarray            # [B, 23, 6] float32
    ball_z: np.ndarray       # [B] float32
    holder: np.ndarray       # [B] int16, row index or -1
    possession: np.ndarray   # [B] int8, 0 home, 1 away, -1 none
    score: np.ndarray        # [B, 2] int16
    t_ms: int
    period: int
    attack_dir: int          # +1 when home attacks +x
    styles: dict             # effective styles of world 0 {"home": {...}, "away": {...}}


@dataclass
class MatchRecord:
    match_id: str
    events: list[dict]
    tracking: dict[str, np.ndarray]
    truth: dict


class _World:
    """Per-world discrete state: rng, event log, open events, restarts, bookings, substitutions, truth."""

    def __init__(self, b: int, seed: int) -> None:
        self.b = b
        self.rng = np.random.default_rng(seed + b)
        self.log = EventLog(b)
        self.carry: Event | None = None
        self.carry_start: tuple[float, float] | None = None
        self.pressure: Event | None = None
        self.pressure_row = -1
        self.pass_ev: Event | None = None
        self.pass_target: tuple[int, float, float] | None = None
        self.first_touch_restart = ""
        self.shot_ev: Event | None = None
        self.shot_outcome = ""
        self.shot_blocker = -1
        self.restart_kind = ""
        self.restart_team = -1
        self.restart_pos = (0.0, 0.0)
        self.restart_at = 0
        self.restart_taker = -1
        self.ball_placed = False
        self.booked: set[str] = set()
        self.subs: list[tuple[int, int]] = []          # (due_ms, team)
        self.subs_used = [0, 0]
        self.row_ids: list[str] = []
        self.bench: list[list[str]] = [[], []]
        self.tackle_cooldown: dict[int, int] = {}
        self.sub_log: list[tuple[int, int, str]] = []  # (t_ms, row, player_on)
        self.phases: list[dict] = []
        self.momentum: np.ndarray = np.zeros((2, 91))
        self.jitter: np.ndarray = np.zeros((2, 5))


class Engine:
    def __init__(self, league: League, home: str, away: str, seed: int, batch: int = 1,
                 decision_model=None, styles: dict | None = None) -> None:
        if batch < 1:
            raise ValueError("batch must be >= 1")
        self.league, self.home, self.away, self.seed, self.B = league, home, away, int(seed), int(batch)
        self.model = decision_model if decision_model is not None else ScriptedRule()
        self.match_id = f"m_{self.seed}"
        base = {0: dict(league.styles[home]), 1: dict(league.styles[away])}
        for key, team in (("home", 0), ("away", 1)):
            base[team].update((styles or {}).get(key, {}))
        self.base_styles = np.array([[base[t][k] for k in STYLE_KEYS] for t in (0, 1)])
        self.lineups = [league.lineup(home), league.lineup(away)]

        B = self.B
        self.S = np.zeros((B, 23, 6))
        self.S[:, :22, 4] = 1.0
        self.ball_z = np.full(B, BALL_REST_Z)
        self.ball_vz = np.zeros(B)
        self.holder = np.full(B, -1, dtype=np.int64)
        self.possession = np.full(B, -1, dtype=np.int64)
        self.score = np.zeros((B, 2), dtype=np.int64)
        self.control_since = np.zeros(B, dtype=np.int64)
        self.latency = np.full(B, 300, dtype=np.int64)
        self.restart_flag = np.zeros(B, dtype=np.int64)
        self.dead = np.ones(B, dtype=bool)
        self.flight = np.zeros(B, dtype=np.int64)        # 0 none, 1 pass, 2 shot, 3 loose
        self.kicker = np.full(B, -1, dtype=np.int64)
        self.kick_t = np.zeros(B, dtype=np.int64)
        self.last_touch = np.full(B, -1, dtype=np.int64)
        self.carry_dir = np.zeros((B, 2))
        self.mode = np.full(B, CARRY, dtype=np.int64)
        self.eff_styles = np.zeros((B, 2, 5))
        self.mom = np.zeros((B, 2))
        self.t_ms = 0
        self.period = 1
        self.finished = False
        self.worlds = [_World(b, self.seed) for b in range(B)]
        for w in self.worlds:
            self._init_world(w)
        self._update_truth_effects()
        self._kickoff_positions(np.arange(B), kicking_team=0)
        for w in self.worlds:
            self._start_period(w)

    # ------------------------------------------------------------------ set-up and truth
    def _init_world(self, w: _World) -> None:
        rng = w.rng
        w.jitter = rng.normal(0.0, 0.04, size=(2, 5))
        for team in (0, 1):
            styles = np.clip(self.base_styles[team] + w.jitter[team], 0, 1)
            press, directness = styles[0], styles[3]
            weights = np.array([press, 1 - press, directness, 1 - directness, 0.5 * (1 - press) + 0.3]) + 0.05
            t = 0
            while t < MATCH_MS:
                dur = int(rng.integers(5, 12)) * 60000
                label = PHASES[int(rng.choice(len(PHASES), p=weights / weights.sum()))]
                w.phases.append({"side": SIDES[team], "label": label, "start_ms": t, "end_ms": min(MATCH_MS, t + dur)})
                t += dur
        m = np.zeros((2, 91))
        for k in range(1, 91):
            m[:, k] = np.clip(0.8 * m[:, k - 1] + rng.normal(0.0, 0.25, size=2), -1, 1)
        w.momentum = m
        w.subs = sorted((int(due) * 60000, team) for team in (0, 1) for due in rng.integers(55, 86, size=3))
        w.row_ids = list(self.lineups[0][0]) + list(self.lineups[1][0])
        w.bench = [list(self.lineups[0][1]), list(self.lineups[1][1])]
        meta = {"home": self.home, "away": self.away, "venue": self.league.clubs[self.home].stadium,
                "kickoff_iso": self._kickoff_iso(), "seed": self.seed,
                "lineups": {"home": {"starting": self.lineups[0][0], "bench": self.lineups[0][1]},
                            "away": {"starting": self.lineups[1][0], "bench": self.lineups[1][1]}}}
        w.log.new(t_ms=0, period=1, type="match_metadata", team="none", player=None, location=None, attrs=meta)

    def _kickoff_iso(self) -> str:
        day = 15 + self.seed % 120
        month, d = (8 + (day - 1) // 30, (day - 1) % 30 + 1)
        return f"2026-{month:02d}-{d:02d}T15:00:00Z"

    def _update_truth_effects(self) -> None:
        minute = min(self.t_ms // 60000, 90)
        for w in self.worlds:
            for team in (0, 1):
                styles = self.base_styles[team] + w.jitter[team]
                phase = next(p for p in w.phases if p["side"] == SIDES[team] and p["start_ms"] <= self.t_ms < p["end_ms"]) \
                    if self.t_ms < MATCH_MS else None
                if phase:
                    for k, delta in PHASE_DELTA[phase["label"]].items():
                        styles = styles.copy()
                        styles[STYLE_KEYS.index(k)] += delta
                self.eff_styles[w.b, team] = np.clip(styles, 0, 1)
                self.mom[w.b, team] = w.momentum[team, minute]

    def truth(self, world: int = 0) -> dict:
        w = self.worlds[world]
        profiles = {SIDES[t]: {k: round(float(np.clip(self.base_styles[t][i] + w.jitter[t][i], 0, 1)), 4)
                               for i, k in enumerate(STYLE_KEYS)} for t in (0, 1)}
        return {"truth_version": "t1", "style_profiles": profiles, "phases": w.phases,
                "momentum": {"step_ms": 60000, "H": [round(float(v), 4) for v in w.momentum[0]],
                             "A": [round(float(v), 4) for v in w.momentum[1]]}}

    # ------------------------------------------------------------------ helpers
    @property
    def home_dir(self) -> int:
        return 1 if self.period == 1 else -1

    def team_dir(self, team: int) -> int:
        return self.home_dir if team == 0 else -self.home_dir

    @staticmethod
    def team_of(row: int) -> int:
        return 0 if row < 11 else 1

    def _team_frame(self, b: int, team: int) -> tuple[np.ndarray, np.ndarray]:
        """Positions of all 22 players in `team`'s frame, team first then opponents."""
        order = np.r_[np.arange(11 * team, 11 * team + 11), np.arange(11 * (1 - team), 11 * (1 - team) + 11)]
        return to_team(self.S[b, order, 0], self.S[b, order, 1], self.team_dir(team))

    def _pos(self, b: int, row: int) -> list[float]:
        return [float(self.S[b, row, 0]), float(self.S[b, row, 1])]

    def _ev(self, w: _World, type_: str, team: int | None, row: int | None, location, final: bool = True, **kw) -> Event:
        return w.log.new(final=final, t_ms=self.t_ms, period=self.period, type=type_,
                         team="none" if team is None else TEAM_NAMES[team],
                         player=None if row is None else w.row_ids[row], location=location, **kw)

    def _nearest_opponent(self, b: int, row: int) -> tuple[int, float]:
        team = self.team_of(row)
        opp = np.arange(11 * (1 - team), 11 * (1 - team) + 11)
        d = np.hypot(self.S[b, opp, 0] - self.S[b, row, 0], self.S[b, opp, 1] - self.S[b, row, 1])
        k = int(np.argmin(d))
        return int(opp[k]), float(d[k])

    # ------------------------------------------------------------------ periods and restarts
    def _kickoff_positions(self, worlds: np.ndarray, kicking_team: int) -> None:
        for team in (0, 1):
            rows = np.arange(11 * team, 11 * team + 11)
            u = np.minimum(np.where(np.arange(11) == 0, 4.0, SLOT_U + 22.0) * 0.9, 49.0)
            v = SLOT_V.copy()
            if team != kicking_team:
                u = np.where(np.abs(v - GOAL_Y) < 12, np.minimum(u, 42.0), u)
            x, y = to_team(u, v, self.team_dir(team))
            self.S[np.ix_(worlds, rows, [0])] = x[None, :, None]
            self.S[np.ix_(worlds, rows, [1])] = y[None, :, None]
            self.S[np.ix_(worlds, rows, [2, 3])] = 0.0
        self.S[worlds, 22, 0:4] = [PITCH_L / 2, PITCH_W / 2, 0.0, 0.0]
        self.ball_z[worlds] = BALL_REST_Z
        self.ball_vz[worlds] = 0.0

    def _start_period(self, w: _World) -> None:
        self._ev(w, "period_start", None, None, None)
        kicking = 0 if self.period == 1 else 1
        self._stoppage(w, "kick_off", kicking, (PITCH_L / 2, PITCH_W / 2), delay_ms=0)

    def _stoppage(self, w: _World, kind: str, team: int, pos, delay_ms: int | None = None) -> None:
        b = w.b
        self._close_open(w)
        self.dead[b] = True
        self.holder[b] = -1
        self.flight[b] = 0
        self.possession[b] = team
        w.pass_target = None
        w.restart_kind, w.restart_team = kind, team
        w.restart_pos = (float(np.clip(pos[0], 0.3, PITCH_L - 0.3)), float(np.clip(pos[1], 0.3, PITCH_W - 0.3)))
        w.restart_at = self.t_ms + (RESTART_DELAY_MS[kind] if delay_ms is None else delay_ms)
        w.ball_placed = False
        rows = np.arange(11 * team, 11 * team + 11)
        if kind == "goal_kick":
            w.restart_taker = 11 * team
        elif kind in ("penalty", "kick_off"):
            w.restart_taker = 11 * team + 9
        else:
            outfield = rows[1:]
            d = np.hypot(self.S[b, outfield, 0] - w.restart_pos[0], self.S[b, outfield, 1] - w.restart_pos[1])
            w.restart_taker = int(outfield[int(np.argmin(d))])

    def _close_open(self, w: _World) -> None:
        b = w.b
        if w.pass_ev is not None:
            w.pass_ev.outcome = "incomplete"
            w.pass_ev.end_location = self._pos(b, 22)
            w.log.finalise(w.pass_ev)
            w.pass_ev = None
        self._end_carry(w)
        self._end_pressure(w)
        w.shot_ev = None

    def _restart(self, w: _World) -> None:
        b, team, taker = w.b, w.restart_team, w.restart_taker
        self._do_subs(w)
        x, y = w.restart_pos
        self.S[b, taker, 0:4] = [x, y, 0.0, 0.0]
        self.S[b, 22, 0:4] = [x, y, 0.0, 0.0]
        self.ball_z[b], self.ball_vz[b] = BALL_REST_Z, 0.0
        self._ev(w, "set_piece", team, taker, [x, y], attrs={"kind": w.restart_kind})
        self.dead[b] = False
        self.restart_flag[b] = RESTART_FLAG[w.restart_kind]
        w.first_touch_restart = w.restart_kind
        self._take_control(w, taker, latency_ms=500, change_event=False)

    def _do_subs(self, w: _World) -> None:
        b = w.b
        for i, (due, team) in enumerate(list(w.subs)):
            if due > self.t_ms or w.subs_used[team] >= 3:
                continue
            rows = np.arange(11 * team + 1, 11 * team + 11)
            for row in rows[np.argsort(self.S[b, rows, 4], kind="stable")]:
                pos = SLOT_POSITION[int(row) - 11 * team]
                on = next((p for p in w.bench[team] if self.league.players[p].position == pos), None)
                if on is None:
                    continue
                off = w.row_ids[row]
                self._ev(w, "substitution", team, int(row), None, attrs={"player_off": off, "player_on": on})
                w.bench[team].remove(on)
                w.row_ids[row] = on
                self.S[b, row, 4] = 1.0
                w.subs_used[team] += 1
                w.sub_log.append((self.t_ms, int(row), on))
                break
            w.subs[i] = (MATCH_MS + 1, team)

    # ------------------------------------------------------------------ control, carries, pressure
    def _take_control(self, w: _World, row: int, latency_ms: int = 300, change_event: bool = True,
                      related: list[Event] | None = None) -> None:
        b = w.b
        team = self.team_of(row)
        if change_event and self.possession[b] != team:
            self._ev(w, "possession_change", team, row, self._pos(b, row), related=related or [])
        self._end_carry(w)
        self._end_pressure(w)
        w.pass_target = None
        self.carry_dir[b] = 0.0
        self.holder[b] = row
        self.possession[b] = team
        self.last_touch[b] = row
        self.flight[b] = 0
        self.control_since[b] = self.t_ms
        self.latency[b] = latency_ms
        self.mode[b] = CARRY
        self.ball_z[b], self.ball_vz[b] = BALL_REST_Z, 0.0
        w.carry = self._ev(w, "carry", team, row, self._pos(b, row), final=False, outcome="complete")
        w.carry_start = (float(self.S[b, row, 0]), float(self.S[b, row, 1]))

    def _end_carry(self, w: _World) -> None:
        if w.carry is None:
            return
        b, ev = w.b, w.carry
        row = int(self.holder[b]) if self.holder[b] >= 0 else None
        end = self._pos(b, row) if row is not None else self._pos(b, 22)
        dist = math.dist(end, w.carry_start)
        if dist < 3.0:
            w.log.drop(ev)
        else:
            team = 0 if ev.team == "home" else 1
            ev.end_location = end
            prog = (end[0] - w.carry_start[0]) * self.team_dir(team)
            ev.attrs = {"distance_m": dist, "progressive_m": prog}
            w.log.finalise(ev)
        w.carry = None

    def _end_pressure(self, w: _World) -> None:
        if w.pressure is None:
            return
        w.pressure.attrs["duration_ms"] = int(self.t_ms - w.pressure.t_ms)
        w.log.finalise(w.pressure)
        w.pressure, w.pressure_row = None, -1

    # ------------------------------------------------------------------ main loop
    def step(self) -> list[Event]:
        if self.finished:
            return []
        self.t_ms += TICK_MS
        t = self.t_ms
        if t % 1000 == 0:
            self._update_truth_effects()
        noise = np.stack([w.rng.random(N_NOISE) for w in self.worlds])

        for w in self.worlds:
            if self.dead[w.b]:
                self._dead_tick(w)
        self._decide(noise)
        self._move_players()
        self._move_ball()
        for w in self.worlds:
            if not self.dead[w.b]:
                self._resolve_ball(w, noise[w.b])
            if not self.dead[w.b] and self.holder[w.b] >= 0:
                self._duels(w, noise[w.b])
        self._bookkeeping()

        if t >= PERIOD_MS * self.period:
            for w in self.worlds:
                self._close_open(w)
                self._ev(w, "period_end", None, None, None)
            if self.period == 1:
                self.period = 2
                self._kickoff_positions(np.arange(self.B), kicking_team=1)
                for w in self.worlds:
                    self._start_period(w)
            else:
                self.finished = True
        out: list[Event] = []
        for w in self.worlds:
            out.extend(w.log.release(flush=self.finished))
        return out

    def state(self) -> State:
        styles = {name: {k: float(self.eff_styles[0, t, i]) for i, k in enumerate(STYLE_KEYS)}
                  for t, name in enumerate(TEAM_NAMES)}
        return State(S=self.S.astype(np.float32), ball_z=self.ball_z.astype(np.float32),
                     holder=self.holder.astype(np.int16), possession=self.possession.astype(np.int8),
                     score=self.score.astype(np.int16), t_ms=self.t_ms, period=self.period,
                     attack_dir=self.home_dir, styles=styles)

    def play(self, until_ms: int | None = None) -> MatchRecord:
        """Run world 0 to `until_ms` (default: full time) and return its events, 10 Hz tracking and truth."""
        end = MATCH_MS if until_ms is None else min(int(until_ms), MATCH_MS)
        n = (end - self.t_ms) // TICK_MS + 1
        t_ms = np.zeros(n, dtype=np.int64)
        period = np.zeros(n, dtype=np.int8)
        S = np.zeros((n, 23, 6), dtype=np.float32)
        ball_z = np.zeros(n, dtype=np.float32)
        holder = np.zeros(n, dtype=np.int16)
        possession = np.zeros(n, dtype=np.int8)

        def record(i: int) -> None:
            t_ms[i], period[i] = self.t_ms, self.period
            S[i], ball_z[i] = self.S[0], self.ball_z[0]
            holder[i], possession[i] = self.holder[0], self.possession[0]

        record(0)
        for i in range(1, n):
            self.step()
            record(i)
        if not self.finished:
            for w in self.worlds:
                w.log.release(flush=True)
        w0 = self.worlds[0]
        events = [e.to_dict(self.match_id) for e in w0.log.released]
        subs = w0.sub_log
        tracking = {
            "t_ms": t_ms, "period": period, "S": S, "ball_z": ball_z, "holder": holder, "possession": possession,
            "player_ids": np.array(self.lineups[0][0] + self.lineups[1][0], dtype="<U5"),
            "sub_t_ms": np.array([s[0] for s in subs], dtype=np.int64),
            "sub_row": np.array([s[1] for s in subs], dtype=np.int8),
            "sub_player_id": np.array([s[2] for s in subs], dtype="<U5"),
        }
        return MatchRecord(match_id=self.match_id, events=events, tracking=tracking, truth=self.truth(0))

    # ------------------------------------------------------------------ per-tick pieces
    def _dead_tick(self, w: _World) -> None:
        b = w.b
        if not w.ball_placed and self.t_ms >= w.restart_at - max(0, RESTART_DELAY_MS[w.restart_kind] - 1000):
            self.S[b, 22, 0:4] = [w.restart_pos[0], w.restart_pos[1], 0.0, 0.0]
            self.ball_z[b], self.ball_vz[b] = BALL_REST_Z, 0.0
            w.ball_placed = True
        if self.t_ms >= w.restart_at:
            gap = math.dist(self._pos(b, w.restart_taker), w.restart_pos)
            if gap <= 2.0 or self.t_ms >= w.restart_at + 5000:
                self._restart(w)

    def _decide(self, noise: np.ndarray) -> None:
        need = (~self.dead) & (self.holder >= 0) & (self.t_ms - self.control_since >= self.latency)
        idx = np.flatnonzero(need)
        if idx.size == 0:
            return
        U = np.zeros((idx.size, 22))
        V = np.zeros((idx.size, 22))
        slot = np.zeros(idx.size, dtype=np.int64)
        styles = np.zeros((idx.size, 5))
        mom = np.zeros(idx.size)
        for i, b in enumerate(idx):
            h = int(self.holder[b])
            team = self.team_of(h)
            U[i], V[i] = self._team_frame(b, team)
            slot[i], styles[i], mom[i] = h - 11 * team, self.eff_styles[b, team], self.mom[b, team]
        out = self.model.decide_batch(DecisionBatch(U=U, V=V, holder=slot, styles=styles, momentum=mom,
                                                    restart=self.restart_flag[idx], noise=noise[idx]))
        for i, b in enumerate(idx):
            w = self.worlds[b]
            h = int(self.holder[b])
            team = self.team_of(h)
            d = self.team_dir(team)
            kind = int(out.kind[i])
            self.mode[b] = kind
            self.carry_dir[b] = [out.dir_u[i] * d, out.dir_v[i] * d]
            if kind == PASS:
                self._kick_pass(w, h, 11 * team + int(out.target[i]), bool(out.lofted[i]), noise[b])
            elif kind == SHOOT:
                self._kick_shot(w, h, noise[b])
            elif kind == CLEAR:
                self._kick_clear(w, h, noise[b])
            if kind in (PASS, SHOOT, CLEAR):
                self.restart_flag[b] = FREE

    def _release(self, w: _World, row: int) -> bool:
        """Let go of the ball; returns True when this is the first touch of a restart exempt from offside."""
        b = w.b
        self._end_carry(w)
        self._end_pressure(w)
        self.holder[b] = -1
        self.kicker[b], self.kick_t[b], self.last_touch[b] = row, self.t_ms, row
        self.S[b, 22, 0] = min(max(self.S[b, row, 0], 0.2), PITCH_L - 0.2)
        self.S[b, 22, 1] = min(max(self.S[b, row, 1], 0.2), PITCH_W - 0.2)
        exempt = w.first_touch_restart in ("throw_in", "goal_kick", "corner", "kick_off")
        w.first_touch_restart = ""
        return exempt

    def _kick_pass(self, w: _World, row: int, target: int, lofted: bool, nz: np.ndarray) -> None:
        b = w.b
        team = self.team_of(row)
        d = self.team_dir(team)
        x0, y0 = self.S[b, row, 0], self.S[b, row, 1]
        tx, ty = self.S[b, target, 0], self.S[b, target, 1]
        dist0 = math.hypot(tx - x0, ty - y0)
        lead = dist0 / 16.0
        px = float(np.clip(tx + self.S[b, target, 2] * lead, 0.5, PITCH_L - 0.5))
        py = float(np.clip(ty + self.S[b, target, 3] * lead, 0.5, PITCH_W - 0.5))
        dist = max(math.hypot(px - x0, py - y0), 1.0)
        _, opp_d = self._nearest_opponent(b, row)
        U, V = self._team_frame(b, team)
        line = max(float(np.sort(U[11:])[-2]), float(U[row - 11 * team]), PITCH_L / 2)
        tu = float(U[target - 11 * team])
        pc = float(1.0 / (1.0 + math.exp(-(1.6 - 0.035 * dist - 0.6 * lofted))))
        ev = self._ev(w, "pass", team, row, [float(x0), float(y0)], final=False, outcome="complete",
                      under_pressure=opp_d < PRESSURE_R, end_location=[px, py],
                      attrs={"recipient": w.row_ids[target], "length_m": dist,
                             "angle_deg": math.degrees(math.atan2((py - y0) * d, (px - x0) * d)),
                             "height": "lofted" if lofted else "ground", "progressive_m": (px - x0) * d,
                             "pass_difficulty": round(1 - pc, 3), "pass_completion_p": round(pc, 3)})
        if w.carry is not None:
            ev.related.append(w.carry)
        exempt = self._release(w, row)
        if not exempt and target != 11 * team and tu > line:
            opp_rows = np.arange(11 * (1 - team), 11 * (1 - team) + 11)
            Uo, _ = to_team(self.S[b, opp_rows, 0], self.S[b, opp_rows, 1], d)
            last_def = int(opp_rows[np.argsort(Uo, kind="stable")[-2]])
            ev.outcome = "incomplete"
            ev.end_location = self._pos(b, target)
            w.log.finalise(ev)
            self._ev(w, "offside", team, target, self._pos(b, target), related=[ev],
                     attrs={"offside_player": w.row_ids[target], "margin_m": tu - line,
                            "last_defender": w.row_ids[last_def], "pass_event_id": ev})
            self._stoppage(w, "free_kick", 1 - team, self._pos(b, target))
            return
        w.pass_ev = ev
        v0, vz = pass_launch(dist, lofted)
        jitter = (nz[N_AIM] - 0.5) * (0.06 if not lofted else 0.1)
        ang = math.atan2(py - y0, px - x0) + jitter
        self.S[b, 22, 2:4] = [v0 * math.cos(ang), v0 * math.sin(ang)]
        self.ball_vz[b] = vz
        self.flight[b] = 1
        w.pass_target = (target, px, py)

    def _kick_shot(self, w: _World, row: int, nz: np.ndarray) -> None:
        b = w.b
        team = self.team_of(row)
        d = self.team_dir(team)
        U, V = self._team_frame(b, team)
        u0, v0 = float(U[row - 11 * team]), float(V[row - 11 * team])
        penalty = self.restart_flag[b] == PENALTY
        dist, ang = float(goal_distance(u0, v0)), float(goal_angle(u0, v0))
        cone = 0 if penalty else cone_count(u0, v0, U[11:], V[11:])
        p_goal = 0.76 if penalty else float(xg(dist, ang, cone))
        r = nz[N_SHOT]
        if r < p_goal:
            outcome = "goal"
        else:
            q = (r - p_goal) / (1 - p_goal)
            outcome = "blocked" if cone > 0 and q < 0.2 + 0.1 * cone else ("saved" if q < 0.62 else "off_target")
        keeper = 11 * (1 - team)
        gku, gkv = to_team(self.S[b, keeper, 0], self.S[b, keeper, 1], d)
        aim = nz[N_AIM]
        blocker = -1
        if outcome == "goal":
            tu, tv = PITCH_L + 0.6, GOAL_Y + (aim - 0.5) * 2 * (GOAL_HALF - 0.4)
        elif outcome == "saved":
            tu, tv = PITCH_L + 0.6, float(np.clip(gkv + (aim - 0.5) * 1.4, GOAL_Y - GOAL_HALF + 0.3, GOAL_Y + GOAL_HALF - 0.3))
        elif outcome == "blocked":
            opp_rows = np.arange(11 * (1 - team), 11 * (1 - team) + 11)
            Uo, Vo = to_team(self.S[b, opp_rows, 0], self.S[b, opp_rows, 1], d)
            ahead = np.where(Uo > u0, np.hypot(Uo - u0, Vo - v0), np.inf)
            ahead[0] = np.inf
            k = int(np.argmin(ahead))
            blocker = int(opp_rows[k])
            tu, tv = float(Uo[k]), float(Vo[k])
        else:
            side = 1 if aim >= 0.5 else -1
            tu, tv = PITCH_L + 0.6, GOAL_Y + side * (GOAL_HALF + 0.5 + 3.0 * abs(aim - 0.5))
        speed = 22.0 + 9.0 * nz[N_SPEED] + (4.0 if penalty else 0.0)
        tx, ty = to_team(np.float64(tu), np.float64(tv), d)
        x0, y0 = float(self.S[b, row, 0]), float(self.S[b, row, 1])
        heading = math.atan2(float(ty) - y0, float(tx) - x0)
        body = "right_foot" if nz[N_FOOT] < 0.62 else ("left_foot" if nz[N_FOOT] < 0.9 else "head")
        _, opp_d = self._nearest_opponent(b, row)
        w.shot_ev = self._ev(w, "shot", team, row, [x0, y0], outcome=outcome, under_pressure=opp_d < PRESSURE_R,
                             end_location=[float(tx), float(ty)],
                             attrs={"xg": round(p_goal, 3), "body_part": body, "shot_speed_kmh": speed * 3.6,
                                    "on_target": outcome in ("goal", "saved"), "distance_m": dist,
                                    "angle_deg": math.degrees(ang), "defenders_in_cone": cone,
                                    **({"penalty": True} if penalty else {})})
        if w.carry is not None:
            w.shot_ev.related.append(w.carry)
        self._release(w, row)
        w.shot_outcome, w.shot_blocker = outcome, blocker
        self.S[b, 22, 2:4] = [speed * math.cos(heading), speed * math.sin(heading)]
        self.ball_vz[b] = 1.2 if outcome != "off_target" or aim < 0.8 else 3.5
        self.flight[b] = 2

    def _kick_clear(self, w: _World, row: int, nz: np.ndarray) -> None:
        b = w.b
        team = self.team_of(row)
        d = self.team_dir(team)
        x0, y0 = float(self.S[b, row, 0]), float(self.S[b, row, 1])
        u0, v0 = to_team(np.float64(x0), np.float64(y0), d)
        tu = float(u0) + 40.0 + 15.0 * nz[N_CLEAR]
        tv = float(np.clip(v0 + (nz[N_AIM] - 0.5) * 40.0, 2.0, PITCH_W - 2.0))
        tx, ty = to_team(np.float64(tu), np.float64(tv), d)
        dist = math.hypot(float(tx) - x0, float(ty) - y0)
        v0h, vz = pass_launch(dist, True)
        ang = math.atan2(float(ty) - y0, float(tx) - x0)
        _, opp_d = self._nearest_opponent(b, row)
        self._ev(w, "clearance", team, row, [x0, y0], under_pressure=opp_d < PRESSURE_R,
                 end_location=[float(tx), float(ty)])
        self._release(w, row)
        self.S[b, 22, 2:4] = [v0h * math.cos(ang), v0h * math.sin(ang)]
        self.ball_vz[b] = vz
        self.flight[b] = 3

    def _move_players(self) -> None:
        S, B = self.S, self.B
        targets = np.zeros((B, 22, 2))
        vmax = np.zeros((B, 22))
        bx, by = S[:, 22, 0], S[:, 22, 1]
        for team in (0, 1):
            d = self.team_dir(team)
            rows = slice(11 * team, 11 * team + 11)
            bu, bv = to_team(bx, by, d)
            styles = self.eff_styles[:, team]
            in_poss = self.possession == team
            line = np.where(in_poss, np.clip(bu - 32 + 14 * styles[:, 4], 12, 58),
                            np.clip(bu - 28 + 10 * styles[:, 4] - 6 * (1 - styles[:, 0]), 6, 45))
            wscale = np.where(in_poss, 0.85 + 0.35 * styles[:, 2], 0.6 + 0.15 * styles[:, 2])
            u = line[:, None] + SLOT_U[None, :]
            v = GOAL_Y + (SLOT_V[None, :] - GOAL_Y) * wscale[:, None] + 0.3 * (bv[:, None] - GOAL_Y)
            opp = slice(11 * (1 - team), 11 * (1 - team) + 11)
            ou, _ = to_team(S[:, opp, 0], S[:, opp, 1], d)
            offside_line = np.maximum(np.sort(ou, axis=1)[:, -2], bu)
            # forwards time their runs: each drifts up to 2 m either side of the line on a 7 s cycle
            run = 2.0 * np.sin(2 * np.pi * self.t_ms / 7000.0 + np.array([0.0, 2.1, 4.2]))
            u[:, 8:] = np.where(in_poss[:, None], np.minimum(u[:, 8:], offside_line[:, None] - 0.3 + run[None, :]),
                                u[:, 8:])
            u[:, 0] = np.clip(4.0 + 0.08 * bu, 3.0, 14.0)
            v[:, 0] = GOAL_Y + 0.25 * (bv - GOAL_Y)
            u, v = np.clip(u, 1.0, PITCH_L - 1.0), np.clip(v, 1.5, PITCH_W - 1.5)
            kick_off = self.dead & np.array([w.restart_kind == "kick_off" for w in self.worlds])
            u = np.where(kick_off[:, None], np.minimum(u, 49.0), u)
            x, y = to_team(u, v, d)
            targets[:, rows, 0], targets[:, rows, 1] = x, y
            stam = 0.85 + 0.15 * S[:, rows, 4]
            vmax[:, rows] = np.where(self.dead[:, None], 0.75 * JOG, 5.0) * stam
        for w in self.worlds:
            self._special_targets(w, targets, vmax)
        pos = S[:, :22, 0:2]
        vel = S[:, :22, 2:4]
        desired = (targets - pos) * 0.8
        sp = np.hypot(desired[..., 0], desired[..., 1])
        scale = np.minimum(1.0, vmax / np.maximum(sp, 1e-9))
        desired *= scale[..., None]
        dv = desired - vel
        dvn = np.hypot(dv[..., 0], dv[..., 1])
        dv *= np.minimum(1.0, ACCEL * DT / np.maximum(dvn, 1e-9))[..., None]
        vel = vel + dv
        S[:, :22, 2:4] = vel
        S[:, :22, 0:2] = np.clip(pos + vel * DT, [-3.0, -3.0], [PITCH_L + 3.0, PITCH_W + 3.0])

    def _special_targets(self, w: _World, targets: np.ndarray, vmax: np.ndarray) -> None:
        b, S = w.b, self.S
        stam = 0.85 + 0.15 * S[b, :22, 4]
        sprint = SPRINT * stam
        if self.dead[b]:
            r = w.restart_taker
            targets[b, r] = w.restart_pos
            vmax[b, r] = sprint[r]
            return
        h = int(self.holder[b])
        bx, by = S[b, 22, 0], S[b, 22, 1]
        if h >= 0:
            team = self.team_of(h)
            mode = self.mode[b]
            speed = 0.0 if mode == HOLD else (3.5 if self._nearest_opponent(b, h)[1] < PRESSURE_R else 5.0)
            targets[b, h] = S[b, h, 0:2] + self.carry_dir[b] * speed
            vmax[b, h] = speed * stam[h]
            opp = np.arange(11 * (1 - team), 11 * (1 - team) + 11)
            d = np.hypot(S[b, opp, 0] - bx, S[b, opp, 1] - by)
            order = opp[np.argsort(d, kind="stable")]
            du, _ = to_team(bx, by, self.team_dir(1 - team))     # ball depth in the defending team's frame
            press_zone = 40.0 + 50.0 * self.eff_styles[b, 1 - team, 0]
            presser = int(order[0]) if order[0] != 11 * (1 - team) else int(order[1])
            if du < press_zone or d.min() < 8.0:
                targets[b, presser] = S[b, h, 0:2]
                vmax[b, presser] = sprint[presser]
            cover = int(order[1]) if int(order[1]) != presser else int(order[2])
            gx = 0.0 if self.team_dir(1 - team) > 0 else PITCH_L
            vec = np.array([gx, GOAL_Y]) - S[b, h, 0:2]
            targets[b, cover] = S[b, h, 0:2] + 6.0 * vec / (np.hypot(*vec) + 1e-9)
            vmax[b, cover] = 0.8 * sprint[cover]
            return
        # ball in flight: the intended receiver runs to the pass target, the nearest players chase the ball
        vx, vy = S[b, 22, 2], S[b, 22, 3]
        ahead = np.array([bx + vx * 0.6, by + vy * 0.6])
        if self.flight[b] == 1 and w.pass_target is not None:
            tgt, px, py = w.pass_target
            targets[b, tgt] = (px, py)
            vmax[b, tgt] = sprint[tgt]
        for team in (0, 1):
            rows = np.arange(11 * team, 11 * team + 11)
            if self.flight[b] == 2 and team != self.team_of(int(self.kicker[b])):
                keeper = 11 * team
                targets[b, keeper] = (bx + vx * 0.3, by + vy * 0.3)
                vmax[b, keeper] = sprint[keeper]
                if w.shot_blocker >= 0:
                    targets[b, w.shot_blocker] = (bx, by)
                    vmax[b, w.shot_blocker] = sprint[w.shot_blocker]
                continue
            d = np.hypot(S[b, rows, 0] - ahead[0], S[b, rows, 1] - ahead[1])
            d[0] += 15.0                                          # keepers stay home unless the ball is close
            k = int(rows[int(np.argmin(d))])
            if k == self.kicker[b] and self.t_ms - self.kick_t[b] < 500:
                continue
            targets[b, k] = ahead
            vmax[b, k] = sprint[k]

    def _move_ball(self) -> None:
        S = self.S
        held = (self.holder >= 0) & ~self.dead
        if held.any():
            idx = np.flatnonzero(held)
            rows = self.holder[idx]
            fac = S[idx, rows, 5]
            S[idx, 22, 0] = S[idx, rows, 0] + 0.45 * np.cos(fac)
            S[idx, 22, 1] = S[idx, rows, 1] + 0.45 * np.sin(fac)
            S[idx, 22, 2:4] = S[idx, rows, 2:4]
        fly = (self.holder < 0) & ~self.dead
        if fly.any():
            idx = np.flatnonzero(fly)
            air = (self.ball_z[idx] > 0.25) | (self.flight[idx] == 2)
            decay = np.where(air, 1.0 - AIR_DRAG * DT, math.exp(-GROUND_DECAY * DT))
            S[idx, 22, 2:4] *= decay[:, None]
            S[idx, 22, 0:2] += S[idx, 22, 2:4] * DT
            self.ball_vz[idx] -= G * DT
            self.ball_z[idx] += self.ball_vz[idx] * DT
            low = self.ball_z[idx] < BALL_REST_Z
            if low.any():
                j = idx[low]
                bounce = self.ball_vz[j] < -1.5
                self.ball_z[j] = BALL_REST_Z
                self.ball_vz[j] = np.where(bounce, -0.45 * self.ball_vz[j], 0.0)
                S[j[bounce], 22, 2:4] *= 0.8
        dead = self.dead
        if dead.any():
            S[dead, 22, 2:4] = 0.0

    def _resolve_ball(self, w: _World, nz: np.ndarray) -> None:
        b, S = w.b, self.S
        if self.holder[b] >= 0:
            x, y = float(S[b, 22, 0]), float(S[b, 22, 1])
            if x < -0.3 or x > PITCH_L + 0.3 or y < -0.3 or y > PITCH_W + 0.3:
                self._check_out(w, x, y, float(self.ball_z[b]))
            return
        bx, by, z = float(S[b, 22, 0]), float(S[b, 22, 1]), float(self.ball_z[b])
        if self.flight[b] == 2:
            if self._resolve_shot(w, bx, by, z, nz):
                return
        else:
            d = np.hypot(S[b, :22, 0] - bx, S[b, :22, 1] - by)
            reach = np.full(22, CONTROL_R)
            for keeper in (0, 11):
                if self._in_own_box(keeper, bx, by):
                    reach[keeper] = KEEPER_R
            ok = (d <= reach) & (z <= HEADER_Z + 0.4 * (reach > CONTROL_R))
            if self.t_ms - self.kick_t[b] < 400 and self.kicker[b] >= 0:
                ok[self.kicker[b]] = False
            cand = np.flatnonzero(ok)
            if cand.size:
                row = int(cand[np.argmin(d[cand])])
                team = self.team_of(row)
                kicker_team = self.team_of(int(self.kicker[b])) if self.kicker[b] >= 0 else -1
                p = 0.92 if team == kicker_team else (0.65 if self.flight[b] == 1 else 0.85)
                if nz[N_CONTROL] < p:
                    self._gain_ball(w, row, kicker_team)
                    return
        self._check_out(w, bx, by, z)

    def _in_own_box(self, keeper: int, x: float, y: float) -> bool:
        team = self.team_of(keeper)
        u, v = to_team(np.float64(x), np.float64(y), self.team_dir(team))
        return bool(u <= BOX_DEPTH and abs(v - GOAL_Y) <= BOX_HALF)

    def _gain_ball(self, w: _World, row: int, kicker_team: int) -> None:
        b = w.b
        team = self.team_of(row)
        related: list[Event] = []
        if w.pass_ev is not None:
            ev, w.pass_ev = w.pass_ev, None
            ev.end_location = self._pos(b, row)
            if team == kicker_team:
                ev.outcome = "complete"
                ev.attrs["recipient"] = w.row_ids[row]
                w.log.finalise(ev)
            else:
                ev.outcome = "incomplete"
                w.log.finalise(ev)
                related = [self._ev(w, "interception", team, row, self._pos(b, row), outcome="won", related=[ev])]
        self._take_control(w, row, related=related)

    def _resolve_shot(self, w: _World, bx: float, by: float, z: float, nz: np.ndarray) -> bool:
        b = w.b
        shooter = int(self.kicker[b])
        team = self.team_of(shooter)
        d = self.team_dir(team)
        u, v = to_team(np.float64(bx), np.float64(by), d)
        keeper = 11 * (1 - team)
        if w.shot_outcome == "blocked" and w.shot_blocker >= 0:
            if math.dist(self._pos(b, w.shot_blocker), (bx, by)) <= CONTROL_R + 0.3:
                ang = math.atan2(-self.S[b, 22, 3], -self.S[b, 22, 2]) + (nz[N_DEFLECT] - 0.5) * 2.0
                self.S[b, 22, 2:4] = [8.0 * math.cos(ang), 8.0 * math.sin(ang)]
                self.ball_vz[b] = 2.0
                self.flight[b] = 3
                self.last_touch[b] = w.shot_blocker
                w.shot_ev = None
                return True
        if w.shot_outcome == "saved" and (math.dist(self._pos(b, keeper), (bx, by)) <= KEEPER_R or u >= PITCH_L):
            self.S[b, keeper, 0:2] = [bx, by] if u < PITCH_L else self.S[b, keeper, 0:2]
            save = self._ev(w, "save", 1 - team, keeper, self._pos(b, keeper), outcome="won", related=[w.shot_ev])
            w.shot_ev = None
            if nz[N_CATCH] < 0.65:
                self._take_control(w, keeper, latency_ms=1500, related=[save])
            else:
                corner_y = 0.0 if by < GOAL_Y else PITCH_W
                corner_x = PITCH_L if d > 0 else 0.0
                self.last_touch[b] = keeper
                self._stoppage(w, "corner", team, (corner_x, corner_y))
            return True
        if u >= PITCH_L:
            if w.shot_outcome == "goal" and abs(v - GOAL_Y) <= GOAL_HALF and z <= GOAL_H:
                self.score[b, team] += 1
                self._ev(w, "goal", team, shooter, [bx, by], outcome="goal", related=[w.shot_ev])
                w.shot_ev = None
                self._stoppage(w, "kick_off", 1 - team, (PITCH_L / 2, PITCH_W / 2))
                return True
            w.shot_ev = None
            self._stoppage(w, "goal_kick", 1 - team, self._goal_kick_spot(1 - team))
            return True
        return False

    def _goal_kick_spot(self, team: int) -> tuple[float, float]:
        x, y = to_team(np.float64(5.5), np.float64(GOAL_Y), self.team_dir(team))
        return float(x), float(y)

    def _check_out(self, w: _World, bx: float, by: float, z: float) -> None:
        b = w.b
        last = int(self.last_touch[b]) if self.last_touch[b] >= 0 else 0
        last_team = self.team_of(last)
        if by < 0.0 or by > PITCH_W:
            self._stoppage(w, "throw_in", 1 - last_team, (min(max(bx, 0.0), PITCH_L), 0.0 if by < 0 else PITCH_W))
        elif bx < 0.0 or bx > PITCH_L:
            defending = 0 if (bx < 0) == (self.home_dir > 0) else 1      # team whose own goal is at this end
            if last_team == defending:
                self._stoppage(w, "corner", 1 - defending, (0.0 if bx < 0 else PITCH_L, 0.0 if by < GOAL_Y else PITCH_W))
            else:
                self._stoppage(w, "goal_kick", defending, self._goal_kick_spot(defending))

    def _duels(self, w: _World, nz: np.ndarray) -> None:
        b, S = w.b, self.S
        h = int(self.holder[b])
        team = self.team_of(h)
        k, dist = self._nearest_opponent(b, h)
        if w.pressure is not None and (dist > PRESSURE_R + 1.0 or w.pressure_row != k):
            self._end_pressure(w)
        if w.pressure is None and dist < PRESSURE_R and self.t_ms - self.control_since[b] >= 200:
            rel = S[b, h, 0:2] - S[b, k, 0:2]
            closing = float(np.dot(S[b, k, 2:4] - S[b, h, 2:4], rel / (np.hypot(*rel) + 1e-9)))
            w.pressure = self._ev(w, "pressure", 1 - team, k, self._pos(b, k), final=False,
                                  attrs={"duration_ms": 0, "closing_speed_ms": max(closing, 0.0)})
            w.pressure_row = k
        if dist >= TACKLE_R or w.tackle_cooldown.get(k, -1) > self.t_ms or k % 11 == 0:
            return
        rate = 0.9 * (0.6 + 0.8 * self.eff_styles[b, 1 - team, 0])
        if nz[N_TACKLE] >= 1.0 - math.exp(-rate * DT):
            return
        r = nz[N_TACKLE_OUT]
        contact = [float((S[b, h, 0] + S[b, k, 0]) / 2), float((S[b, h, 1] + S[b, k, 1]) / 2)]
        if r < 0.13:
            foul = self._ev(w, "foul", 1 - team, k, contact, outcome="committed",
                            attrs={"contact_point": contact, "fouled_player": w.row_ids[h]})
            if w.row_ids[k] not in w.booked and nz[N_CARD] < 0.12:
                w.booked.add(w.row_ids[k])
                self._ev(w, "card", 1 - team, k, contact, related=[foul], attrs={"colour": "yellow"})
            u, v = to_team(np.float64(S[b, h, 0]), np.float64(S[b, h, 1]), self.team_dir(team))
            if u >= PITCH_L - BOX_DEPTH and abs(v - GOAL_Y) <= BOX_HALF:
                px, py = to_team(np.float64(PENALTY_SPOT), np.float64(GOAL_Y), self.team_dir(team))
                self._stoppage(w, "penalty", team, (float(px), float(py)))
            else:
                self._stoppage(w, "free_kick", team, self._pos(b, h))
        elif r < 0.13 + 0.42:
            tackle = self._ev(w, "tackle", 1 - team, k, self._pos(b, k), outcome="won", attrs={"won": True})
            self._take_control(w, k, latency_ms=400, related=[tackle])
        else:
            self._ev(w, "tackle", 1 - team, k, self._pos(b, k), outcome="lost", attrs={"won": False})
            w.tackle_cooldown[k] = self.t_ms + 1500

    def _bookkeeping(self) -> None:
        S = self.S
        sp = np.hypot(S[:, :22, 2], S[:, :22, 3])
        S[:, :22, 4] = np.maximum(0.0, S[:, :22, 4] - STAMINA_COST * sp * sp)
        moving = sp > 0.5
        S[:, :22, 5] = np.where(moving, np.arctan2(S[:, :22, 3], S[:, :22, 2]), S[:, :22, 5])
        if not np.isfinite(S).all() or not np.isfinite(self.ball_z).all():
            raise EngineError(f"non-finite state at t_ms={self.t_ms} (seed {self.seed})")


SLOT_POSITION = ("GK", "DF", "DF", "DF", "DF", "MF", "MF", "MF", "FW", "FW", "FW")
assert len(SLOT_POSITION) == len(SLOTS)
