"""Core MCP tools over one match store (TECH_PLAN 1.7 "MCP tool list", T-030). Plain functions, so the newsroom,
precompute and tests can call them without a server; `server.py` registers them as MCP tools.

Data: a match `m_<seed>` lives in `data/matches/<seed>/` (WHYLINE_MATCHES_DIR). Its events are loaded into the
blackboard on first use, so every evidence id a tool returns resolves for the Fact Checker. Pitch-control snapshots
are written as `pc_` documents (id `pc_` + t_ms // 100, the rollout's convention) plus a float16 `.npz` grid under
data/runtime/pitch_control/. Counterfactuals are written as `cf_` documents.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from blackboard.protocol import NotFound
from mcp_server.errors import ToolError

ROOT = Path(__file__).resolve().parents[2]
MATCHES = ROOT / "data" / "matches"
RUNTIME = ROOT / "data" / "runtime"
ON_BALL = {"pass", "carry", "shot", "clearance", "tackle", "interception", "save", "set_piece"}
CHANNELS = ("right", "centre", "left")          # attacking team's view: right flank is low v (auto-events frame)
THIRDS = ("defensive_third", "middle_third", "attacking_third")


@dataclass
class _Match:
    match_id: str
    dir: Path
    events: list[dict]
    window: object
    meta: dict
    ref: object | None = None
    chaos: list[tuple[int, float, str]] = field(default_factory=list)   # (t_ms, chaos, state) at 1 Hz
    sm: object | None = None
    sprints: list | None = None


class MatchStore:
    """Per-process cache of match data plus the blackboard the tools write to."""

    def __init__(self, bb, matches_dir: str | Path | None = None, runtime_dir: str | Path | None = None,
                 cache=None, replay: bool = False) -> None:
        self.bb = bb
        self.cache = cache          # cache.CacheClient: counterfactual hits (replay mode)
        self.replay = replay        # replay mode: a counterfactual miss is an error, never a fresh simulation
        self.matches_dir = Path(matches_dir or os.environ.get("WHYLINE_MATCHES_DIR") or MATCHES)
        self.runtime_dir = Path(runtime_dir or RUNTIME)
        self._matches: dict[str, _Match] = {}
        self._lock = threading.RLock()

    def match(self, match_id: str) -> _Match:
        with self._lock:
            if match_id in self._matches:
                return self._matches[match_id]
            if not match_id.startswith("m_") or not match_id[2:].isdigit():
                raise ToolError("bad_match_id", f"match ids look like m_4242, got {match_id!r}")
            d = self.matches_dir / match_id[2:]
            if not (d / "events.jsonl").exists():
                raise ToolError("unknown_match", f"no events for {match_id} in {self.matches_dir}")
            from physics.window import TrackingWindow

            events = [json.loads(line) for line in (d / "events.jsonl").read_text().splitlines() if line.strip()]
            if not self.bb.query("events", match_id=match_id, limit=1):
                self.bb.put_many("events", events)
            window = TrackingWindow.load(d) if (d / "tracking.npz").exists() else None
            meta = next((e["attrs"] for e in events if e["type"] == "match_metadata"), {})
            m = _Match(match_id, d, events, window, meta)
            self._matches[match_id] = m
            return m

    def tracking(self, m: _Match):
        if m.window is None:
            raise ToolError("no_tracking", f"{m.match_id} has no tracking.npz")
        return m.window


# ---------------------------------------------------------------------------------------------------- helpers

def _clock(t_ms: int) -> str:
    return f"{t_ms // 60000:02d}:{(t_ms // 1000) % 60:02d}"


def _check_t(m: _Match, t_ms: int) -> None:
    end = m.events[-1]["t_ms"] if m.events else 0
    if not 0 <= int(t_ms) <= end:
        raise ToolError("t_out_of_range", f"t_ms {t_ms} outside 0..{end} for {m.match_id}")


def _uv(x, y, team: int, period: int):
    from physics.auto_events import _uv as uv

    return uv(x, y, team, period)


def overloads(S: np.ndarray, team: int, period: int, k: int = 3) -> list[dict]:
    """Zones (third x channel, in `team`'s attacking frame) where `team` outnumbers the opponents, best first.
    Only the middle and attacking thirds count: a back line outnumbering a lone striker is not a story."""
    rows = np.arange(11) if team == 0 else np.arange(11, 22)
    other = np.arange(11, 22) if team == 0 else np.arange(11)
    out = []
    for idx in (rows, other):
        u, v = _uv(S[idx, 0], S[idx, 1], team, period)
        third = np.clip((np.asarray(u) // 35).astype(int), 0, 2)
        channel = np.clip((np.asarray(v) // (68 / 3)).astype(int), 0, 2)
        out.append(np.bincount(third * 3 + channel, minlength=9))
    att, dfn = out
    found = []
    for z in range(3, 9):
        if att[z] >= 2 and att[z] - dfn[z] >= 1:
            third, channel = THIRDS[z // 3], CHANNELS[z % 3]
            found.append({"label": f"overload_{channel}_{third}", "channel": channel, "third": third,
                          "attackers": int(att[z]), "defenders": int(dfn[z]),
                          "count": f"{int(att[z])}v{int(dfn[z])}"})
    found.sort(key=lambda o: (o["defenders"] - o["attackers"], -THIRDS.index(o["third"]), o["channel"]))
    return found[:k]


def _team_at(m: _Match, t_ms: int) -> int:
    w = m.window
    i = w.index_at(t_ms)
    pos = np.asarray(w.possession)[: i + 1]
    have = pos[pos >= 0]
    return int(have[-1]) if have.size else 0


# ---------------------------------------------------------------------------------------------------- tools

def query_events(store: MatchStore, match_id: str, t_from_ms: int, t_to_ms: int, kinds: list[str] | None = None,
                 player: str | None = None) -> list[dict]:
    store.match(match_id)  # loads the match's events into the blackboard on first use
    if t_to_ms < t_from_ms:
        raise ToolError("bad_range", f"t_to_ms {t_to_ms} < t_from_ms {t_from_ms}")
    filters: dict = {"match_id": match_id, "t_from_ms": int(t_from_ms), "t_to_ms": int(t_to_ms)}
    if kinds:
        filters["type"] = list(kinds)
    events = store.bb.query("events", **filters)
    if player:
        events = [e for e in events if player in (e.get("player"), (e.get("attrs") or {}).get("recipient"))]
    return events


def get_state(store: MatchStore, match_id: str, t_ms: int) -> dict:
    """Score, clock, possession, chaos state label, the 60 s indices and, when a player is in control, the
    engine's option probabilities at t_ms."""
    from physics.indices import chaos_index, indices, transition_share_at, turnover_rate
    from physics.pitch_control import pitch_control
    from physics.state_machine import StateMachine

    m = store.match(match_id)
    _check_t(m, t_ms)
    w = store.tracking(m)
    past = [e for e in m.events if e["t_ms"] <= t_ms]
    score = {"home": sum(1 for e in past if e["type"] == "goal" and e["team"] == "home"),
             "away": sum(1 for e in past if e["type"] == "goal" and e["team"] == "away")}
    with store._lock:  # extend the 1 Hz chaos/state series up to t_ms
        if m.sm is None:
            m.sm = StateMachine()
        start = m.chaos[-1][0] + 1000 if m.chaos else 1000
        for ts in range(start, int(t_ms) + 1, 1000):
            i = w.index_at(ts)
            c = chaos_index(pitch_control(w.S[i].astype(np.float64)), turnover_rate(m.events, ts),
                            transition_share_at(m.events, ts))
            m.sm.update(c, ts)
            m.chaos.append((ts, c, m.sm.state))
        series = [x for x in m.chaos if x[0] <= t_ms]
    i = w.index_at(t_ms)
    holder = int(w.holder[i])
    options = _options(store, m, int(t_ms)) if holder >= 0 else None
    win = w.slice(max(0, t_ms - 60_000), t_ms)
    idx = indices(win, [e for e in past if e["t_ms"] >= t_ms - 60_000]) if len(win) else {}
    return {"match_id": match_id, "t_ms": int(t_ms), "clock": _clock(int(t_ms)), "period": int(w.period[i]),
            "score": score, "possession": {0: "home", 1: "away"}.get(int(w.possession[i]), "none"),
            "holder": w.player_at(holder, int(t_ms)) if holder >= 0 else None,
            "state": series[-1][2] if series else "Settled", "chaos": round(series[-1][1], 2) if series else None,
            "indices": {k: round(float(v), 4) for k, v in idx.items()},
            "options": options}


def _options(store: MatchStore, m: _Match, t_ms: int) -> dict | None:
    """scripted_v1 probabilities of the player in control (team-mate ids, shoot, clear, carry): the policy_prob
    the Sliding Doors guard uses. From the match's engine, the one simulate_counterfactual also moves forward."""
    from rollout.core import MatchRef
    from rollout.sliding_doors import option_probs

    with store._lock:
        if m.ref is None:
            m.ref = MatchRef(seed=int(m.match_id[2:]), match_dir=m.dir)
        eng = m.ref.state_at(t_ms).source
        if int(eng.holder[0]) < 0 or eng.dead[0]:
            return None
        return {k: round(float(v), 4) for k, v in option_probs(eng).items()}


def get_pitch_control(store: MatchStore, match_id: str, t_ms: int) -> dict:
    """Snapshot id, home share, contested fraction, zones and the top-3 overloads; stored as a pc_ document."""
    from physics.pitch_control import contested_fraction, pitch_control, zones
    from physics.window import home_dir

    m = store.match(match_id)
    _check_t(m, t_ms)
    w = store.tracking(m)
    i = w.index_at(t_ms)
    S = w.S[i].astype(np.float64)
    period = int(w.period[i])
    pc = pitch_control(S)
    team = _team_at(m, t_ms)
    over = overloads(S, team, period)
    snapshot_id = f"pc_{int(t_ms) // 100:06d}"
    z = zones(pc, home_attacks_right=home_dir(period) > 0)
    z.update({o["label"]: o["count"] for o in over})
    grid_dir = store.runtime_dir / "pitch_control" / match_id
    grid_dir.mkdir(parents=True, exist_ok=True)
    grid_path = grid_dir / f"{snapshot_id}.npz"
    np.savez_compressed(grid_path, grid=pc.astype(np.float16))
    doc = {"snapshot_id": snapshot_id, "match_id": match_id, "t_ms": int(t_ms), "period": period,
           "team_in_possession": "home" if team == 0 else "away", "home_share": round(float(pc.mean()), 4),
           "contested_frac": round(contested_fraction(pc), 4), "zones": {k: (round(v, 4) if isinstance(v, float)
                                                                           else v) for k, v in z.items()},
           "overloads": over, "grid_path": str(grid_path.relative_to(ROOT)) if grid_path.is_relative_to(ROOT)
           else str(grid_path)}
    store.bb.put("pitch_control", doc)
    return doc


def simulate_counterfactual(store: MatchStore, match_id: str, t_ms: int, alternative: dict, n: int = 200,
                            horizon_s: float = 8) -> dict:
    """CounterfactualResult (counterfactual.schema.json) for forcing `alternative` at t_ms; stored as a cf_ doc.
    The same (t_ms, alternative, n, horizon_s) returns the stored result."""
    from kickoff import BranchError
    from rollout.core import MatchRef
    from rollout.sliding_doors import sliding_doors

    m = store.match(match_id)
    _check_t(m, t_ms)
    if not isinstance(alternative, dict) or alternative.get("kind") not in ("pass", "carry", "shoot", "clear",
                                                                          "hold"):
        raise ToolError("bad_alternative", "alternative needs kind pass|carry|shoot|clear|hold, actor, target")
    if not 1 <= int(n) <= 1000 or not 0 < float(horizon_s) <= 90:
        raise ToolError("bad_budget", "n must be 1..1000 and horizon_s 0..90")
    key = {k: alternative.get(k) for k in ("kind", "actor", "target")}
    if store.cache is not None:
        hit = store.cache.counterfactual(match_id, int(t_ms), key, int(n), float(horizon_s))
        if hit is not None:
            store.bb.put("counterfactuals", hit)
            return hit
    if store.replay:
        raise ToolError("cache_miss", f"replay mode: no cached counterfactual at {t_ms} for {key}")
    def stored() -> dict | None:
        for cf in store.bb.query("counterfactuals", match_id=match_id, t_ms=int(t_ms)):
            if {k: cf["alternative"].get(k) for k in key} == key and cf["n"] == n and cf["horizon_s"] == horizon_s:
                return cf
        return None

    if (hit := stored()) is not None:
        return hit
    with store._lock:
        if (hit := stored()) is not None:   # a concurrent call (the Proposer's prefetch) finished it meanwhile
            return hit
        if m.ref is None:
            m.ref = MatchRef(seed=int(match_id[2:]), match_dir=m.dir)
        started = time.perf_counter()
        try:
            cf = sliding_doors(m.ref, int(t_ms), key, n=int(n), horizon_s=float(horizon_s),
                               counterfactual_id=store.bb.next_id("counterfactuals", match_id))
        except BranchError as exc:
            raise ToolError("invalid_alternative", str(exc)) from exc
        cf["compute_ms"] = int((time.perf_counter() - started) * 1000)
        store.bb.put("counterfactuals", cf)
    try:
        store.bb.get("pitch_control", cf["pitch_control_snapshot_id"], match_id)
    except NotFound:
        get_pitch_control(store, match_id, int(t_ms))
    store.bb.put("counterfactuals", cf)
    return cf


def player_stats(store: MatchStore, match_id: str, player_id: str) -> dict:
    """Touches, passes, completion, xT added, shots, xG, sprints for one player over the match's events so far."""
    from kickoff.physics_prior import threat, to_team
    from newsroom.factcheck import league_data
    from physics.speeds import speeds

    m = store.match(match_id)
    players, _ = league_data()
    if player_id not in players:
        raise ToolError("unknown_player", f"no player {player_id!r}")
    mine = [e for e in m.events if e.get("player") == player_id]
    if not mine:
        raise ToolError("player_not_in_match", f"{player_id} has no events in {match_id}")
    passes = [e for e in mine if e["type"] == "pass"]
    done = [e for e in passes if e["outcome"] == "complete"]
    xt = 0.0
    for e in done + [e for e in mine if e["type"] == "carry"]:
        if not e.get("location") or not e.get("end_location"):
            continue
        d = (1 if e["period"] == 1 else -1) * (1 if e["team"] == "home" else -1)
        u0, v0 = to_team(np.float64(e["location"][0]), np.float64(e["location"][1]), d)
        u1, v1 = to_team(np.float64(e["end_location"][0]), np.float64(e["end_location"][1]), d)
        xt += float(threat(u1, v1) - threat(u0, v0))
    shots = [e for e in mine if e["type"] == "shot"]
    with store._lock:
        if m.sprints is None and m.window is not None:
            m.sprints = speeds(m.window).sprints
    runs = [s for s in (m.sprints or []) if s[0] == player_id]
    p = players[player_id]
    return {"match_id": match_id, "player_id": player_id, "name": p["name"], "club": p["club"],
            "position": p["position"], "touches": sum(1 for e in mine if e["type"] in ON_BALL),
            "passes": len(passes), "passes_completed": len(done),
            "completion": round(len(done) / len(passes), 4) if passes else None, "xt": round(xt, 4),
            "shots": len(shots), "xg": round(sum(e["attrs"].get("xg", 0.0) for e in shots), 4),
            "sprints": len(runs), "top_speed_kmh": max((s[1] for s in runs), default=None),
            "decision_index": None, "evidence_event_ids": [e["id"] for e in mine][-20:]}


def verify_claims(store: MatchStore, match_id: str, claims: list[dict]) -> dict:
    from newsroom.factcheck import verify_claims as check

    store.match(match_id)
    if not isinstance(claims, list):
        raise ToolError("bad_claims", "claims must be a list of claim objects")
    return check(match_id, claims, store.bb)


def get_budget(store: MatchStore, mode: str) -> dict:
    from newsroom.config import load_budgets

    cfg = load_budgets()
    modes = cfg["director"]["modes"]
    if mode not in modes:
        raise ToolError("unknown_mode", f"mode must be one of {sorted(modes)}")
    out = {"mode": mode, **modes[mode], "hard_rules": cfg["director"]["hard_rules"]}
    try:
        from api.spend import SpendGuard

        out["spend"] = SpendGuard().summary()
    except Exception as exc:  # the budget still answers without a ledger
        out["spend"] = {"error": str(exc)}
    return out
