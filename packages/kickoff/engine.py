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

import copy
import math
from dataclasses import dataclass, field

import numpy as np

from .errors import BranchError, EngineError
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
    STAMINA_COST,
    TACKLE_R,
    TICK_MS,
    G,
    cone_count,
    goal_angle,
    goal_distance,
    pass_launch,
    to_team,
    top_speed,
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
    Action,
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
    "phase_direct_play": {"directness": 0.3},
    "phase_patient_build": {"directness": -0.25},
    "phase_counter_attack": {"directness": 0.2, "press_height": -0.15},
}
# Hidden match state (truth phases with side "M"): one regime at a time for both teams. It shifts both teams'
# styles and scales duel intensity (tackle hazard, interception chance), so the game-state machine has a real,
# hidden signal to detect (T-055 scores it against these labels).
REGIMES = ("state_settled", "state_transitional", "state_chaotic")
REGIME_P = (0.45, 0.30, 0.25)
REGIME_MIN = (10, 18)                     # regime length in whole minutes (inclusive range)
REGIME_DELTA = {
    "state_settled": {"tempo": -0.4, "press_height": -0.4, "directness": -0.2},
    "state_transitional": {},
    "state_chaotic": {"tempo": 0.4, "press_height": 0.4, "directness": 0.3},
}
REGIME_INTENSITY = {"state_settled": 0.03, "state_transitional": 1.0, "state_chaotic": 8.0}
RESTART_DELAY_MS = {"kick_off": 40000, "throw_in": 3000, "goal_kick": 6000, "corner": 7000, "free_kick": 6000,
                    "penalty": 9000}
RESTART_DELAY_ARR = np.array([RESTART_DELAY_MS[k] for k in ("kick_off", "throw_in", "goal_kick", "corner",
                                                               "free_kick", "penalty")], dtype=np.int64)
RESTART_FLAG = {"kick_off": KICK_OFF, "throw_in": PASS_ONLY, "goal_kick": FREE, "corner": CROSS, "free_kick": FREE,
                "penalty": PENALTY}
SIDES = ("H", "A")
TEAM_ROWS = (np.arange(0, 11), np.arange(11, 22))
TEAM_ORDER = np.array([np.r_[0:22], np.r_[11:22, 0:11]])     # a team's rows first, then its opponents'
MOVE_HI = np.array([PITCH_L + 3.0, PITCH_W + 3.0])
PARKED = np.array([PITCH_L / 2, -1.0e4])          # where a sent-off player stands (Engine.send_off)
KEEPER_ROWS = np.array([0, 11])
KIND_CODE = {"pass": PASS, "carry": CARRY, "shoot": SHOOT, "clear": CLEAR, "hold": HOLD}
NOISE_BLOCK = 64                          # ticks of noise drawn per world at once
# Realism knobs, tuned on seeds 1-50 against TECH_PLAN 1.4 (T-014).
LINE_IN_POSS, LINE_OUT_POSS = 6.0, 10.0   # metres the defensive line moves up per unit of line_height
RUN_AMP_M = 3.0                           # forwards drift this far either side of the offside line on a 7 s cycle
FWD_REACH_M = 20.0                        # forwards push onto the offside line when it is this close to the ball
AIM_K = 1.0                               # pass aim error scales with regime intensity ** AIM_K
FIRST_TOUCH_K = 0.05                      # first-touch control falls by this per unit of regime intensity above 1
INTERCEPT_P = 0.65                        # chance an opponent within reach cuts out a pass in flight
FINISH = 0.62                             # open-play scoring probability = FINISH * xG (decisions see plain xG)
FORMATION_VMAX = 5.0                      # m/s cap while moving to a formation target in play
FORMATION_DEADZONE = 3.0                  # m, players within this of their target ease to a stop (0 = off)
FORMATION_GAIN = 0.8                      # 1/s, desired speed toward the target per metre of distance
TACKLE_INTENSITY_CAP = 2.5                # regime intensity scales the tackle hazard up to this factor
TACKLE_RATE, TACKLE_PRESS = 0.9, 0.3      # challenge hazard per second within TACKLE_R: rate * (0.6 + press * press_height)


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
    source: Engine | None = None   # a one-world fork of the engine at this state (set by Engine.snapshot_state)


@dataclass
class MatchRecord:
    match_id: str
    events: list[dict]
    tracking: dict[str, np.ndarray]
    truth: dict


RESTART_KINDS = ("kick_off", "throw_in", "goal_kick", "corner", "free_kick", "penalty")


@dataclass
class Override:
    """What a branch changes: the first on-ball action, team style deltas ({"home": {"press_height": 0.15}}) and/or
    players sent off from the branch point on ({"home": [8]}, team slots)."""
    first_action: Action | None = None
    styles: dict[str, dict[str, float]] | None = field(default=None)
    sent_off: dict[str, list[int]] | None = field(default=None)    # {"home": [slot, ...]}: outfield slots 1-10


class _WorldArrays:
    """Per-world discrete state that the vectorised tick reads for all worlds at once; _World exposes it as
    attributes, so the per-world code reads and writes it as before."""

    def __init__(self, B: int) -> None:
        self.pass_tgt = np.full(B, -1, dtype=np.int64)          # intended receiver of the pass in flight, -1 none
        self.pass_xy = np.zeros((B, 2))
        self.restart_code = np.full(B, -1, dtype=np.int64)      # index into RESTART_KINDS, -1 none yet
        self.restart_team = np.full(B, -1, dtype=np.int64)
        self.restart_pos = np.zeros((B, 2))
        self.restart_at = np.zeros(B, dtype=np.int64)
        self.restart_taker = np.full(B, -1, dtype=np.int64)
        self.ball_placed = np.zeros(B, dtype=bool)
        self.pressure_row = np.full(B, -1, dtype=np.int64)
        self.shot_blocker = np.full(B, -1, dtype=np.int64)


class _World:
    """Per-world discrete state: rng, event log, open events, restarts, bookings, substitutions, truth."""

    def __init__(self, b: int, seed: int, arrays: _WorldArrays) -> None:
        self.b = b
        self.a = arrays
        self.rng = np.random.default_rng(seed + b)
        self.log = EventLog(b)
        self.carry: Event | None = None
        self.carry_start: tuple[float, float] | None = None
        self.pressure: Event | None = None
        self.pass_ev: Event | None = None
        self.first_touch_restart = ""
        self.shot_ev: Event | None = None
        self.shot_outcome = ""
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

    def fork(self, b: int, seed: int, arrays: _WorldArrays) -> _World:
        """Copy of this world's discrete state as world b of a branched engine, with generator default_rng(seed + b)."""
        w = _World.__new__(_World)
        w.__dict__.update(self.__dict__)
        w.b, w.a, w.rng = b, arrays, np.random.default_rng(seed + b)
        w.log, copies = self.log.fork(b)
        for name in ("carry", "pressure", "pass_ev", "shot_ev"):
            ev = getattr(self, name)
            setattr(w, name, None if ev is None else copies.get(ev.seq, ev))
        w.booked, w.subs, w.subs_used = set(self.booked), list(self.subs), list(self.subs_used)
        w.row_ids, w.bench = list(self.row_ids), [list(x) for x in self.bench]
        w.tackle_cooldown, w.sub_log = dict(self.tackle_cooldown), list(self.sub_log)
        return w

    @property
    def pass_target(self) -> tuple[int, float, float] | None:
        tgt = int(self.a.pass_tgt[self.b])
        return None if tgt < 0 else (tgt, float(self.a.pass_xy[self.b, 0]), float(self.a.pass_xy[self.b, 1]))

    @pass_target.setter
    def pass_target(self, value: tuple[int, float, float] | None) -> None:
        if value is None:
            self.a.pass_tgt[self.b] = -1
        else:
            self.a.pass_tgt[self.b], self.a.pass_xy[self.b] = value[0], value[1:]

    @property
    def restart_kind(self) -> str:
        code = int(self.a.restart_code[self.b])
        return "" if code < 0 else RESTART_KINDS[code]

    @restart_kind.setter
    def restart_kind(self, kind: str) -> None:
        self.a.restart_code[self.b] = RESTART_KINDS.index(kind) if kind else -1

    @property
    def restart_pos(self) -> tuple[float, float]:
        return float(self.a.restart_pos[self.b, 0]), float(self.a.restart_pos[self.b, 1])

    @restart_pos.setter
    def restart_pos(self, pos: tuple[float, float]) -> None:
        self.a.restart_pos[self.b] = pos

    def _scalar(name: str, cast):  # noqa: N805 - property factory used in the class body
        def get(self):
            return cast(getattr(self.a, name)[self.b])

        def put(self, value) -> None:
            getattr(self.a, name)[self.b] = value
        return property(get, put)

    restart_team = _scalar("restart_team", int)
    restart_at = _scalar("restart_at", int)
    restart_taker = _scalar("restart_taker", int)
    ball_placed = _scalar("ball_placed", bool)
    pressure_row = _scalar("pressure_row", int)
    shot_blocker = _scalar("shot_blocker", int)
    del _scalar


class Engine:
    def __init__(self, league: League, home: str, away: str, seed: int, batch: int = 1,
                 decision_model=None, styles: dict | None = None) -> None:
        if batch < 1:
            raise ValueError("batch must be >= 1")
        self.league, self.home, self.away, self.seed, self.B = league, home, away, int(seed), int(batch)
        self.styles_arg = styles
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
        self.intensity = np.ones(B)
        self.shots = np.zeros((B, 2), dtype=np.int64)         # shots taken, for rollout futures
        self.vtop = np.tile([self._top_speed(p) for p in self.lineups[0][0] + self.lineups[1][0]], (B, 1))
        self.sent_off: np.ndarray | None = None          # [22] bool, players sent off (send_off); None: nobody
        self.force: dict | None = None                        # forced first action of a branch (rollouts)
        self.force_pending = np.zeros(B, dtype=bool)
        self.first_kind = np.full(B, -1, dtype=np.int64)       # a branch's first decision per world (kind, team slot)
        self.first_target = np.full(B, -1, dtype=np.int64)
        self.t_ms = 0
        self.period = 1
        self.finished = False
        self.record_events = True
        self._noise = np.zeros((B, NOISE_BLOCK, N_NOISE))
        self._noise_i = NOISE_BLOCK
        self.wa = _WorldArrays(B)
        self.worlds = [_World(b, self.seed, self.wa) for b in range(B)]
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
        t, label = 0, ""
        while t < MATCH_MS:
            dur = int(rng.integers(REGIME_MIN[0], REGIME_MIN[1] + 1)) * 60000
            p = np.array([0.0 if r == label else q for r, q in zip(REGIMES, REGIME_P, strict=True)])
            label = REGIMES[int(rng.choice(len(REGIMES), p=p / p.sum()))]
            w.phases.append({"side": "M", "label": label, "start_ms": t, "end_ms": min(MATCH_MS, t + dur)})
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

    def _top_speed(self, player_id: str) -> float:
        p = self.league.players[player_id]
        return top_speed(p.position, list(p.traits), p.age, player_id)

    def _kickoff_iso(self) -> str:
        day = 15 + self.seed % 120
        month, d = (8 + (day - 1) // 30, (day - 1) % 30 + 1)
        return f"2026-{month:02d}-{d:02d}T15:00:00Z"

    def _update_truth_effects(self) -> None:
        minute = min(self.t_ms // 60000, 90)
        for w in self.worlds:
            regime = self._phase_at(w, "M")
            for team in (0, 1):
                styles = self.base_styles[team] + w.jitter[team]
                deltas = list(PHASE_DELTA[p].items()) if (p := self._phase_at(w, SIDES[team])) else []
                deltas += list(REGIME_DELTA[regime].items()) if regime else []
                for k, delta in deltas:
                    styles = styles.copy()
                    styles[STYLE_KEYS.index(k)] += delta
                self.eff_styles[w.b, team] = np.clip(styles, 0, 1)
                self.mom[w.b, team] = w.momentum[team, minute]
            self.intensity[w.b] = REGIME_INTENSITY[regime] if regime else 1.0

    def _phase_at(self, w: _World, side: str) -> str | None:
        if self.t_ms >= MATCH_MS:
            return None
        return next(p["label"] for p in w.phases if p["side"] == side and p["start_ms"] <= self.t_ms < p["end_ms"])

    def truth(self, world: int = 0) -> dict:
        w = self.worlds[world]
        profiles = {SIDES[t]: {k: round(float(np.clip(self.base_styles[t][i] + w.jitter[t][i], 0, 1)), 4)
                               for i, k in enumerate(STYLE_KEYS)} for t in (0, 1)}
        return {"truth_version": "t2", "style_profiles": profiles, "phases": w.phases,
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
        order = TEAM_ORDER[team]
        return to_team(self.S[b, order, 0], self.S[b, order, 1], self.team_dir(team))

    def _pos(self, b: int, row: int) -> list[float]:
        return [float(self.S[b, row, 0]), float(self.S[b, row, 1])]

    def _ev(self, w: _World, type_: str, team: int | None, row: int | None, location, final: bool = True, **kw) -> Event:
        return w.log.new(final=final, t_ms=self.t_ms, period=self.period, type=type_,
                         team="none" if team is None else TEAM_NAMES[team],
                         player=None if row is None else w.row_ids[row], location=location, **kw)

    def _nearest_opponent(self, b: int, row: int) -> tuple[int, float]:
        team = self.team_of(row)
        opp = TEAM_ROWS[1 - team]
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
        if self.sent_off is not None and self.sent_off[w.restart_taker]:
            self._pick_restart_taker(w)

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
                self.vtop[b, row] = self._top_speed(on)
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
        if t % 60000 == 0:                       # phases, regimes and momentum change on whole minutes
            self._update_truth_effects()
        noise = self._next_noise()

        for b in np.flatnonzero(self._dead_due()):
            self._dead_tick(self.worlds[b])
        self._decide(noise)
        self._move_players()
        if self.sent_off is not None:
            self._park()
        self._move_ball()
        for b in np.flatnonzero(self._resolve_due()):
            self._resolve_ball(self.worlds[b], noise[b])
        for b in np.flatnonzero(self._duel_due(noise)):
            self._duels(self.worlds[b], noise[b])
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
                if self.sent_off is not None:
                    self._park()
            else:
                self.finished = True
        out: list[Event] = []
        if self.record_events:
            for w in self.worlds:
                if w.log.has_ready() or self.finished:
                    out.extend(w.log.release(flush=self.finished))
        return out

    # ------------------------------------------------------------------ vectorised gates
    # Each gate marks the worlds whose per-world method could change something this tick, with a small margin, so
    # the per-world code (unchanged) runs only where it matters and the result is identical to running it everywhere.
    def _next_noise(self) -> np.ndarray:
        """One noise row per world per tick, drawn from each world's generator in blocks of NOISE_BLOCK ticks
        (the same stream as one draw per tick)."""
        if self._noise_i >= NOISE_BLOCK:
            for w in self.worlds:
                self._noise[w.b] = w.rng.random((NOISE_BLOCK, N_NOISE))
            self._noise_i = 0
        row = self._noise[:, self._noise_i]
        self._noise_i += 1
        return row

    def _dead_due(self) -> np.ndarray:
        a = self.wa
        delay = RESTART_DELAY_ARR[np.maximum(a.restart_code, 0)]
        place_at = a.restart_at - np.maximum(0, delay - 1000)
        return self.dead & (((~a.ball_placed) & (self.t_ms >= place_at)) | (self.t_ms >= a.restart_at))

    def _resolve_due(self) -> np.ndarray:
        S, eps = self.S, 1e-6
        bx, by = S[:, 22, 0], S[:, 22, 1]
        live = ~self.dead
        held = self.holder >= 0
        out_held = (bx < -0.3 + eps) | (bx > PITCH_L + 0.3 - eps) | (by < -0.3 + eps) | (by > PITCH_W + 0.3 - eps)
        out_loose = (bx < eps) | (bx > PITCH_L - eps) | (by < eps) | (by > PITCH_W - eps)
        d = np.hypot(S[:, :22, 0] - bx[:, None], S[:, :22, 1] - by[:, None])          # [B, 22]
        reach = np.full(d.shape, CONTROL_R)
        for keeper in (0, 11):                                                    # keepers reach further in their box
            u = np.where(self.team_dir(self.team_of(keeper)) > 0, bx, PITCH_L - bx)
            reach[:, keeper] = np.where((u <= BOX_DEPTH + eps) & (np.abs(by - GOAL_Y) <= BOX_HALF + eps), KEEPER_R,
                                        CONTROL_R)
        ok = (d <= reach + eps) & (self.ball_z[:, None] <= HEADER_Z + 0.4 * (reach > CONTROL_R) + eps)
        kicker_out = (self.t_ms - self.kick_t < 400) & (self.kicker >= 0)
        ok[kicker_out, self.kicker[kicker_out]] = False
        loose_due = (self.flight == 2) | ok.any(axis=1) | out_loose
        return live & np.where(held, out_held, loose_due)

    def _duel_due(self, noise: np.ndarray) -> np.ndarray:
        eps = 1e-6
        due = (~self.dead) & (self.holder >= 0)
        idx = np.flatnonzero(due)
        if idx.size == 0:
            return due
        h = self.holder[idx]
        team = (h >= 11).astype(np.int64)
        opp = np.where(team[:, None] == 0, np.arange(11, 22)[None, :], np.arange(0, 11)[None, :])
        Sb = self.S[idx]
        hx, hy = Sb[np.arange(idx.size), h, 0], Sb[np.arange(idx.size), h, 1]
        ni = np.arange(idx.size)[:, None]
        ox, oy = Sb[ni, opp, 0], Sb[ni, opp, 1]
        dd = np.hypot(ox - hx[:, None], oy - hy[:, None])
        k = opp[np.arange(idx.size), np.argmin(dd, axis=1)]
        dist = dd.min(axis=1)
        prow = self.wa.pressure_row[idx]
        open_ = prow >= 0
        settled = self.t_ms - self.control_since[idx] >= 200
        rate = TACKLE_RATE * np.minimum(self.intensity[idx], TACKLE_INTENSITY_CAP) \
            * (0.6 + TACKLE_PRESS * self.eff_styles[idx, 1 - team, 0])
        tackle = (dist < TACKLE_R + eps) & (k % 11 != 0) & (noise[idx, N_TACKLE] < 1.0 - np.exp(-rate * DT) + eps)
        need = (open_ & ((dist > PRESSURE_R + 1.0 - eps) | (prow != k))) \
            | ((~open_) & (dist < PRESSURE_R + eps) & settled) | tackle
        out = np.zeros_like(due)
        out[idx[need]] = True
        return out

    def state(self) -> State:
        styles = {name: {k: float(self.eff_styles[0, t, i]) for i, k in enumerate(STYLE_KEYS)}
                  for t, name in enumerate(TEAM_NAMES)}
        return State(S=self.S.astype(np.float32), ball_z=self.ball_z.astype(np.float32),
                     holder=self.holder.astype(np.int16), possession=self.possession.astype(np.int8),
                     score=self.score.astype(np.int16), t_ms=self.t_ms, period=self.period,
                     attack_dir=self.home_dir, styles=styles)

    # ------------------------------------------------------------------ branching (TECH_PLAN 1.5)
    PER_WORLD = ("S", "ball_z", "ball_vz", "holder", "possession", "score", "control_since", "latency", "restart_flag",
                 "dead", "flight", "kicker", "kick_t", "last_touch", "carry_dir", "mode", "eff_styles", "mom",
                 "intensity", "shots", "force_pending", "first_kind", "first_target", "vtop")

    def _fork(self, batch: int, seed: int, world: int = 0) -> Engine:
        """`batch` copies of world `world` at the current tick; world b draws from default_rng(seed + b)."""
        new = copy.copy(self)
        new.B = int(batch)
        for name in self.PER_WORLD:
            setattr(new, name, np.repeat(getattr(self, name)[world:world + 1], batch, axis=0).copy())
        new.wa = _WorldArrays(batch)
        for name, arr in vars(self.wa).items():
            setattr(new.wa, name, np.repeat(arr[world:world + 1], batch, axis=0).copy())
        new.worlds = [self.worlds[world].fork(b, seed, new.wa) for b in range(batch)]
        new._noise = np.zeros((batch, NOISE_BLOCK, N_NOISE))
        new._noise_i = NOISE_BLOCK
        new.record_events = False
        new.force = None
        new.base_styles = self.base_styles.copy()
        return new

    def _at(self, t_ms: int) -> Engine:
        """This match (world 0) at t_ms: this engine if it is there, a deep copy run forward, or a re-simulation
        from kick-off for a past time. Never reads truth.json."""
        if t_ms % TICK_MS or not 0 <= t_ms <= MATCH_MS:
            raise ValueError(f"t_ms {t_ms} is not a tick of the match")
        if t_ms == self.t_ms:
            return self
        if t_ms > self.t_ms and self.B == 1:
            eng = copy.deepcopy(self)
        else:
            eng = Engine(self.league, self.home, self.away, self.seed, 1, self.model, self.styles_arg)
        eng.record_events = False
        while eng.t_ms < t_ms:
            eng.step()
        return eng

    def snapshot_state(self, world: int = 0) -> State:
        """State of one world with `source` set to a one-world fork, so rollouts can branch from it later."""
        src = self._fork(1, self.seed, world)
        st = src.state()
        st.source = src
        return st

    def send_off(self, rows: list[int]) -> None:
        """Players leave play for the rest of the match in every world (a red card). Each tick they stand at PARKED:
        on the halfway line (neutral for offside, where nobody is offside anyway) and far off the pitch, so no
        distance-based choice (presser, cover, lane, cone, tackle, interception) ever picks them; they are never a
        pass target or restart taker, and drop the ball if they hold it. The team keeps its other ten slots (no
        reshuffle). Keepers cannot be sent off here."""
        rows = sorted({int(r) for r in rows})
        if any(r % 11 == 0 or not 0 <= r < 22 for r in rows):
            raise BranchError("send_off takes outfield rows 1-10 and 12-21")
        mask = np.zeros(22, dtype=bool) if self.sent_off is None else self.sent_off.copy()
        mask[rows] = True
        self.sent_off = mask
        for w in self.worlds:
            if int(self.holder[w.b]) in rows:
                self._release(w, int(self.holder[w.b]))
            if w.restart_taker in rows:
                self._pick_restart_taker(w)
        self._park()

    def _park(self) -> None:
        rows = np.flatnonzero(self.sent_off)
        self.S[:, rows, 0:2] = PARKED
        self.S[:, rows, 2:4] = 0.0

    def _pick_restart_taker(self, w: _World) -> None:
        """The nearest available outfield player of the restart team (a sent-off taker is replaced)."""
        b, team = w.b, w.restart_team
        outfield = np.arange(11 * team + 1, 11 * team + 11)
        outfield = outfield[~self.sent_off[outfield]]
        d = np.hypot(self.S[b, outfield, 0] - w.restart_pos[0], self.S[b, outfield, 1] - w.restart_pos[1])
        w.restart_taker = int(outfield[int(np.argmin(d))])

    def branch(self, t_ms: int, batch: int, override: Override | None, seed: int | None = None,
               decide_now: bool = False) -> Engine:
        """Clone the match at t_ms into `batch` worlds. With `override.first_action`, the player in control makes that
        decision on the first tick in every world; with `decide_now`, he makes the decision model's choice on the first
        tick (an unforced baseline at a decision point). `override.styles` shifts a team's style profile."""
        src = self._at(t_ms)
        new = src._fork(batch, src.seed if seed is None else seed)
        if override is not None and override.styles:
            for key, delta in override.styles.items():
                team = 0 if key in ("home", 0, self.home) else 1
                for k, v in delta.items():
                    new.base_styles[team, STYLE_KEYS.index(k)] += float(v)
            new._update_truth_effects()
        if override is not None and override.sent_off:
            for key, slots in override.sent_off.items():
                team = 0 if key in ("home", 0, self.home) else 1
                new.send_off([11 * team + int(s) for s in slots])
        action = override.first_action if override is not None else None
        if action is not None or decide_now:
            row = int(new.holder[0])
            if row < 0 or new.dead[0]:
                raise BranchError("no player is in control of the ball at the branch point")
            if action is not None:
                self._validate(new, row, action)
            new.force = {"row": row, "action": action}
            new.force_pending[:] = True
        return new

    def _validate(self, eng: Engine, row: int, action: Action) -> None:
        team = self.team_of(row)
        if action.kind not in KIND_CODE:
            raise BranchError(f"unknown action kind {action.kind}")
        if action.kind == "pass":
            if action.target is None or not 0 <= int(action.target) <= 10 or 11 * team + int(action.target) == row:
                raise BranchError("pass needs a team-mate slot 0-10 other than the passer")
            U, _ = eng._team_frame(0, team)
            line = max(float(np.sort(U[11:])[-2]), float(U[row - 11 * team]), PITCH_L / 2)
            exempt = eng.worlds[0].first_touch_restart in ("throw_in", "goal_kick", "corner", "kick_off")
            if not exempt and int(action.target) != 0 and float(U[int(action.target)]) > line:
                raise BranchError("target offside")
        if action.kind == "carry" and action.direction is None:
            raise BranchError("carry needs a direction")

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

    def _decide(self, noise: np.ndarray, only: np.ndarray | None = None) -> None:
        need = (~self.dead) & (self.holder >= 0) & (self.t_ms - self.control_since >= self.latency)
        if only is not None:                       # a learned decision model handles the other worlds (T-036)
            need &= only
        forced = np.zeros(self.B, dtype=bool)
        if self.force is not None:                 # a branch's first decision happens on its first tick
            forced = self.force_pending & (~self.dead) & (self.holder == self.force["row"])
            if only is not None:
                forced &= only
            need |= forced
            self.force_pending[forced if only is not None else slice(None)] = False
        idx = np.flatnonzero(need)
        if idx.size == 0:
            return
        h = self.holder[idx]
        team = (h >= 11).astype(np.int64)
        order = TEAM_ORDER[team]
        d = np.where(team == 0, self.home_dir, -self.home_dir)                 # team_dir(team) per world
        X = self.S[idx[:, None], order, 0]
        Y = self.S[idx[:, None], order, 1]
        U = np.where(d[:, None] > 0, X, PITCH_L - X)
        V = np.where(d[:, None] > 0, Y, PITCH_W - Y)
        f = forced[idx]
        out = self.model.decide_batch(DecisionBatch(U=U, V=V, holder=h - 11 * team, styles=self.eff_styles[idx, team],
                                                    momentum=self.mom[idx, team], restart=self.restart_flag[idx],
                                                    noise=noise[idx], force_act=f if f.any() else None,
                                                    unavailable=None if self.sent_off is None
                                                    else self.sent_off[order[:, :11]]))
        kind = np.asarray(out.kind).copy()
        target = np.asarray(out.target).copy()
        lofted = np.asarray(out.lofted).copy()
        carry_dir = np.stack([out.dir_u * d, out.dir_v * d], axis=1)
        action = self.force.get("action") if self.force is not None else None
        if action is not None and f.any():          # the alternative replaces the model's first decision
            kind[f] = KIND_CODE[action.kind]
            target[f] = -1 if action.target is None else int(action.target)
            lofted[f] = bool(action.lofted)
            if action.direction is not None:
                carry_dir[f] = np.asarray(action.direction, dtype=float) / max(math.hypot(*action.direction), 1e-9)
        if f.any():
            self.first_kind[idx[f]], self.first_target[idx[f]] = kind[f], target[f]
        self.mode[idx] = kind
        self.carry_dir[idx] = carry_dir
        for i in np.flatnonzero((kind == PASS) | (kind == SHOOT) | (kind == CLEAR)):
            b, hb, tb = int(idx[i]), int(h[i]), int(team[i])
            w = self.worlds[b]
            if kind[i] == PASS:
                self._kick_pass(w, hb, 11 * tb + int(target[i]), bool(lofted[i]), noise[b])
            elif kind[i] == SHOOT:
                self._kick_shot(w, hb, noise[b])
            else:
                self._kick_clear(w, hb, noise[b])
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
        px = float(min(max(tx + self.S[b, target, 2] * lead, 0.5), PITCH_L - 0.5))
        py = float(min(max(ty + self.S[b, target, 3] * lead, 0.5), PITCH_W - 0.5))
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
            opp_rows = TEAM_ROWS[1 - team]
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
        jitter = (nz[N_AIM] - 0.5) * (0.06 if not lofted else 0.1) * self.intensity[b] ** AIM_K
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
        p_goal = 0.76 if penalty else FINISH * float(xg(dist, ang, cone))
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
            opp_rows = TEAM_ROWS[1 - team]
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
        self.shots[b, team] += 1
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
        """Formation targets for both teams at once ([B, 2, 11]: axis 1 is the team, each in its own frame)."""
        S, B = self.S, self.B
        bx, by = S[:, 22, 0], S[:, 22, 1]
        pos_dir = (self.home_dir > 0, self.home_dir < 0)                               # team attacks +x
        bu = np.stack([bx if d else PITCH_L - bx for d in pos_dir], axis=1)            # [B, 2]
        bv = np.stack([by if d else PITCH_W - by for d in pos_dir], axis=1)
        styles = self.eff_styles                                                       # [B, 2, 5]
        in_poss = self.possession[:, None] == np.array([0, 1])[None, :]
        line = np.where(in_poss, np.minimum(np.maximum(bu - 32 + LINE_IN_POSS * styles[..., 4], 12), 58),
                        np.minimum(np.maximum(bu - 28 + LINE_OUT_POSS * styles[..., 4] - 6 * (1 - styles[..., 0]), 6), 45))
        wscale = np.where(in_poss, 0.85 + 0.35 * styles[..., 2], 0.6 + 0.15 * styles[..., 2])
        u = line[..., None] + SLOT_U
        v = GOAL_Y + (SLOT_V - GOAL_Y) * wscale[..., None] + 0.3 * (bv[..., None] - GOAL_Y)
        ou = np.stack([S[:, 11:22, 0] if pos_dir[0] else PITCH_L - S[:, 11:22, 0],     # each team's opponents
                       S[:, 0:11, 0] if pos_dir[1] else PITCH_L - S[:, 0:11, 0]], axis=1)
        offside_line = np.maximum(np.partition(ou, 9, axis=2)[..., 9], bu)            # second-deepest opponent
        # forwards time their runs: each drifts up to RUN_AMP_M either side of the line on a 7 s cycle
        run = RUN_AMP_M * np.sin(2 * np.pi * self.t_ms / 7000.0 + np.array([0.0, 2.1, 4.2]))
        # and push up onto that line when it is within FWD_REACH_M of the ball
        cap = offside_line[..., None] - 0.3 + run
        push = np.where(cap < bu[..., None] + FWD_REACH_M, cap, u[..., 8:])
        u[..., 8:] = np.where(in_poss[..., None], np.minimum(np.maximum(u[..., 8:], push), cap), u[..., 8:])
        u[..., 0] = np.minimum(np.maximum(4.0 + 0.08 * bu, 3.0), 14.0)
        v[..., 0] = GOAL_Y + 0.25 * (bv - GOAL_Y)
        u, v = np.minimum(np.maximum(u, 1.0), PITCH_L - 1.0), np.minimum(np.maximum(v, 1.5), PITCH_W - 1.5)
        kick_off = self.dead & (self.wa.restart_code == 0)
        if kick_off.any():
            u = np.where(kick_off[:, None, None], np.minimum(u, 49.0), u)
        targets = np.empty((B, 22, 2))
        for k, d in enumerate(pos_dir):
            targets[:, 11 * k:11 * k + 11, 0] = u[:, k] if d else PITCH_L - u[:, k]
            targets[:, 11 * k:11 * k + 11, 1] = v[:, k] if d else PITCH_W - v[:, k]
        stam = 0.85 + 0.15 * S[:, :22, 4]
        vmax = (np.where(self.dead[:, None], 0.75 * JOG, FORMATION_VMAX) * stam if self.dead.any()
                else FORMATION_VMAX * stam)
        special = np.zeros((B, 22), dtype=bool)
        self._special_targets_all(targets, vmax, special, stam)
        pos = S[:, :22, 0:2]
        vel = S[:, :22, 2:4]
        desired = (targets - pos) * FORMATION_GAIN
        if FORMATION_DEADZONE > 0:            # settle near a formation spot instead of shuffling (not runs and presses)
            gap = np.hypot(desired[..., 0], desired[..., 1]) / FORMATION_GAIN
            ease = np.minimum(np.maximum((gap - FORMATION_DEADZONE) / FORMATION_DEADZONE, 0.0), 1.0)
            ease[:, KEEPER_ROWS] = 1.0         # keepers keep tracking the ball across their goal
            ease[special] = 1.0
            desired[..., 0] *= ease
            desired[..., 1] *= ease
        sp = np.hypot(desired[..., 0], desired[..., 1])
        scale = np.minimum(1.0, vmax / np.maximum(sp, 1e-9))
        desired[..., 0] *= scale             # per axis (same products, cheaper than a [..., None] broadcast)
        desired[..., 1] *= scale
        dv = desired - vel
        dvn = np.hypot(dv[..., 0], dv[..., 1])
        lim = np.minimum(1.0, ACCEL * DT / np.maximum(dvn, 1e-9))
        dv[..., 0] *= lim
        dv[..., 1] *= lim
        vel = vel + dv
        S[:, :22, 2:4] = vel
        for k in (0, 1):                      # per axis: broadcasting the two-element bound costs as much as the step
            S[:, :22, k] = np.minimum(np.maximum(S[:, :22, k] + vel[..., k] * DT, -3.0), MOVE_HI[k])

    def _special_targets_all(self, targets: np.ndarray, vmax: np.ndarray, special: np.ndarray,
                             stam: np.ndarray) -> None:
        """Vectorised `_special_targets` for every world (same values, same overwrite order)."""
        S, a = self.S, self.wa
        sprint = self.vtop * stam                                          # [B, 22], each player's own top speed
        bx, by = S[:, 22, 0], S[:, 22, 1]
        idx = np.flatnonzero(self.dead)
        if idx.size:
            r = a.restart_taker[idx]
            targets[idx, r] = a.restart_pos[idx]
            special[idx, r] = True
            vmax[idx, r] = sprint[idx, r]
        idx = np.flatnonzero(~self.dead & (self.holder >= 0))
        if idx.size:
            n = np.arange(idx.size)
            h = self.holder[idx]
            team = (h >= 11).astype(np.int64)
            opp = np.where(team[:, None] == 0, np.arange(11, 22)[None, :], np.arange(0, 11)[None, :])   # [n, 11]
            Sb = S[idx]
            hpos = Sb[n, h, 0:2]
            ox, oy = Sb[n[:, None], opp, 0], Sb[n[:, None], opp, 1]
            near = np.hypot(ox - hpos[:, 0:1], oy - hpos[:, 1:2]).min(axis=1)
            speed = np.where(self.mode[idx] == HOLD, 0.0, np.where(near < PRESSURE_R, 3.5, 5.0))
            targets[idx, h] = hpos + self.carry_dir[idx] * speed[:, None]
            special[idx, h] = True
            vmax[idx, h] = speed * (0.85 + 0.15 * Sb[n, h, 4])
            d = np.hypot(ox - bx[idx, None], oy - by[idx, None])
            order = opp[n[:, None], np.argsort(d, axis=1, kind="stable")]
            def_dir = np.where(team == 0, -self.home_dir, self.home_dir)          # team_dir(1 - team)
            du = np.where(def_dir > 0, bx[idx], PITCH_L - bx[idx])
            press_zone = 40.0 + 50.0 * self.eff_styles[idx, 1 - team, 0]
            keeper = 11 * (1 - team)
            presser = np.where(order[:, 0] != keeper, order[:, 0], order[:, 1])
            go = (du < press_zone) | (d.min(axis=1) < 8.0)
            targets[idx[go], presser[go]] = hpos[go]
            special[idx[go], presser[go]] = True
            vmax[idx[go], presser[go]] = sprint[idx[go], presser[go]]
            cover = np.where(order[:, 1] != presser, order[:, 1], order[:, 2])
            vec = np.stack([np.where(def_dir > 0, 0.0, PITCH_L), np.full(idx.size, GOAL_Y)], axis=1) - hpos
            targets[idx, cover] = hpos + 6.0 * vec / (np.hypot(vec[:, 0], vec[:, 1]) + 1e-9)[:, None]
            special[idx, cover] = True
            vmax[idx, cover] = 0.8 * sprint[idx, cover]
        idx = np.flatnonzero(~self.dead & (self.holder < 0))
        if idx.size == 0:
            return
        Sf = S[idx]
        vx, vy = Sf[:, 22, 2], Sf[:, 22, 3]
        ahead = np.stack([bx[idx] + vx * 0.6, by[idx] + vy * 0.6], axis=1)
        p = (self.flight[idx] == 1) & (a.pass_tgt[idx] >= 0)
        tgt = a.pass_tgt[idx[p]]
        targets[idx[p], tgt] = a.pass_xy[idx[p]]
        special[idx[p], tgt] = True
        vmax[idx[p], tgt] = sprint[idx[p], tgt]
        kicker = self.kicker[idx]
        kicker_team = (kicker >= 11).astype(np.int64)
        for team in (0, 1):
            shot = (self.flight[idx] == 2) & (team != kicker_team)
            j = idx[shot]
            targets[j, 11 * team] = np.stack([bx[j] + vx[shot] * 0.3, by[j] + vy[shot] * 0.3], axis=1)
            special[j, 11 * team] = True
            vmax[j, 11 * team] = sprint[j, 11 * team]
            blk = a.shot_blocker[j] >= 0
            jb, rb = j[blk], a.shot_blocker[j[blk]]
            targets[jb, rb] = np.stack([bx[jb], by[jb]], axis=1)
            special[jb, rb] = True
            vmax[jb, rb] = sprint[jb, rb]
            rows = np.arange(11 * team, 11 * team + 11)
            d = np.hypot(Sf[:, rows, 0] - ahead[:, 0:1], Sf[:, rows, 1] - ahead[:, 1:2])
            d[:, 0] += 15.0
            k = rows[np.argmin(d, axis=1)]
            go = ~shot & ~((k == kicker) & (self.t_ms - self.kick_t[idx] < 500))
            targets[idx[go], k[go]] = ahead[go]
            special[idx[go], k[go]] = True
            vmax[idx[go], k[go]] = sprint[idx[go], k[go]]

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
                intensity = self.intensity[b]
                if team == kicker_team:          # first touch: cleaner in a settled game, scrappier in a chaotic one
                    p = min(max(0.92 - FIRST_TOUCH_K * (intensity - 1.0), 0.72), 0.97)
                else:
                    p = min(0.92, INTERCEPT_P * math.sqrt(intensity)) if self.flight[b] == 1 else 0.85
                if nz[N_CONTROL] < p:
                    self._gain_ball(w, row, kicker_team)
                    return
        self._check_out(w, bx, by, z)

    def _in_own_box(self, keeper: int, x: float, y: float) -> bool:
        pos = self.team_dir(self.team_of(keeper)) > 0
        u, v = (x, y) if pos else (PITCH_L - x, PITCH_W - y)
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
        rate = TACKLE_RATE * min(self.intensity[b], TACKLE_INTENSITY_CAP) * (0.6 + TACKLE_PRESS * self.eff_styles[b, 1 - team, 0])
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
        np.arctan2(S[:, :22, 3], S[:, :22, 2], out=S[:, :22, 5], where=sp > 0.5)     # heading of moving players
        if not np.isfinite(S.sum() + self.ball_z.sum()):        # any NaN or inf makes the sum non-finite
            raise EngineError(f"non-finite state at t_ms={self.t_ms} (seed {self.seed})")


SLOT_POSITION = ("GK", "DF", "DF", "DF", "DF", "MF", "MF", "MF", "FW", "FW", "FW")
assert len(SLOT_POSITION) == len(SLOTS)
