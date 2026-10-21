"""Scout rules: moment detection and the branch predicates of TECH_PLAN 1.7 (T-029).

Classification (TECH_PLAN 1.7, exact):
    is_fast      goal, big_chance (xG >= 0.30), milestone, player_tag (peak sprint >= PLAYER_TAG_KMH)
    is_explained leverage >= 0.04, or a state change
    is_panel     leverage >= 0.06 and panel.enabled
    is_referee   offside, foul or card
    is_recap     period_end
A moment can take several branches; the Scout emits one message per branch (multiple Case matches do not fan out).

Leverage = the absolute swing of GoalIn8sHead between the frame before an event (t - 100 ms) and the frame after
it (t + 100 ms): max(|dP(home scores in 8 s)|, |dP(away scores in 8 s)|). The heads load at start-up and a
missing artefact raises (never a silent fallback).

Sources: engine events (goals, referee events, period ends), auto-events (physics.auto_events, T-026), on-ball
events whose leverage reaches the explained floor, chaos-state changes (physics.state_machine at 1 Hz) and sprints.
Detections of the same team within MERGE_MS collapse into one moment (one possession, one story).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

BIG_CHANCE_XG = 0.30
EXPLAINED_LEVERAGE = 0.04
PANEL_LEVERAGE = 0.06
PLAYER_TAG_KMH = 34.0
LEVERAGE_AFTER_MS = 100     # adjacent frames: "the frame before and after the event" (TECH_PLAN 1.7)
MERGE_MS = 5000
SAME_INSTANT_MS = 1000      # a goal or whistle this soon after the same team's detection is that play's outcome
REFEREE_KINDS = {"offside", "foul", "card"}
ON_BALL = {"pass", "carry", "shot", "clearance"}   # decisions a counterfactual can replace (rollout action kinds)
AUTO_KINDS = {"pressing_trap", "line_break", "switch_of_play", "overload", "counter_attack", "big_chance"}
# which detection names the moment when several merge (lower index wins)
KIND_ORDER = ["goal", "big_chance", "counter_attack", "pressing_trap", "line_break", "overload", "switch_of_play",
              "decision", "state_change", "player_tag", "milestone"]


def _get(m, key, default=None):
    return m.get(key, default) if isinstance(m, dict) else getattr(m, key, default)


# ---------------------------------------------------------------------------------------------- predicates

def is_fast(m) -> bool:
    kind = _get(m, "kind")
    if kind in ("goal", "milestone"):
        return True
    if kind == "big_chance":
        return float(_get(m, "xg", 0) or 0) >= BIG_CHANCE_XG
    if kind == "player_tag":
        return float(_get(m, "kmh", 0) or 0) >= PLAYER_TAG_KMH
    return False


def is_explained(m) -> bool:
    return float(_get(m, "leverage", 0) or 0) >= EXPLAINED_LEVERAGE or _get(m, "kind") == "state_change"


def is_panel(m, panel_enabled: bool) -> bool:
    return bool(panel_enabled) and float(_get(m, "leverage", 0) or 0) >= PANEL_LEVERAGE


def is_referee(m) -> bool:
    return _get(m, "kind") in REFEREE_KINDS


def is_recap(m) -> bool:
    return _get(m, "kind") == "period_end"


def branches(m, panel_enabled: bool = False) -> list[str]:
    """Every branch the moment takes, in graph order."""
    out = []
    if is_fast(m):
        out.append("fast")
    if is_explained(m):
        out.append("explained")
    if is_panel(m, panel_enabled):
        out.append("panel")
    if is_referee(m):
        out.append("referee")
    if is_recap(m):
        out.append("recap")
    return out


# ---------------------------------------------------------------------------------------------- leverage

class Leverage:
    """GoalIn8sHead swing around events over a TrackingWindow."""

    def __init__(self, window, head=None) -> None:
        from heads.models import GoalIn8sHead

        self.w = window
        self.head = head or GoalIn8sHead()   # raises HeadArtifactMissing if the artefact is absent
        pos = np.asarray(window.possession).astype(np.int64)
        idx = np.where(pos >= 0, np.arange(len(pos)), -1)
        np.maximum.accumulate(idx, out=idx)
        self.team = np.where(idx >= 0, pos[np.maximum(idx, 0)], 0)   # possession carried over loose balls

    def probs(self, frames: np.ndarray) -> np.ndarray:
        """[n, 2] P(home, away scores within 8 s) at frame indices."""
        from heads.features import state_features

        w = self.w
        f = state_features(w.S[frames], w.ball_z[frames], w.holder[frames], self.team[frames], w.period[frames],
                           w.t_ms[frames], np.asarray(w.possession)[frames] >= 0)
        return self.head.predict(f.assign(poss_team=self.team[frames]))

    def at(self, t_ms: Iterable[int]) -> np.ndarray:
        """Leverage for each event time: max |dP| between t - 100 ms and t + LEVERAGE_AFTER_MS."""
        t = np.asarray(list(t_ms), dtype=np.int64)
        if t.size == 0:
            return np.zeros(0)
        before = np.array([self.w.index_at(int(x) - 100) for x in t])
        after = np.array([self.w.index_at(int(x) + LEVERAGE_AFTER_MS) for x in t])
        p = self.probs(np.concatenate([before, after]))
        return np.abs(p[t.size:] - p[:t.size]).max(axis=1)


# ---------------------------------------------------------------------------------------------- detection

@dataclass
class Detection:
    kind: str
    t_ms: int
    period: int
    team: str | None
    evidence: list[str]
    players: list[str] = field(default_factory=list)
    leverage: float | None = None
    extra: dict = field(default_factory=dict)
    hypotheses: list[str] = field(default_factory=list)


def clock(t_ms: int) -> str:
    return f"{t_ms // 60000:02d}:{(t_ms // 1000) % 60:02d}"


def _period_at(events: list[dict], t_ms: int) -> int:
    p = 1
    for e in events:
        if e["t_ms"] > t_ms:
            break
        p = e.get("period", p)
    return p


def detect(events: list[dict], window, head=None, xg_head=None, auto=None) -> list[Detection]:
    """Every raw detection of a match (or a live window), unmerged, in time order."""
    from physics.auto_events import auto_events
    from physics.indices import chaos_index, transition_share_at, turnover_rate
    from physics.pitch_control import pitch_control
    from physics.speeds import speeds
    from physics.state_machine import StateMachine

    lev = Leverage(window, head)
    by_id = {e["id"]: e for e in events}
    found: list[Detection] = []
    # on-ball events whose swing reaches the explained floor
    on_ball = [e for e in events if e["type"] in ON_BALL]
    values = lev.at(e["t_ms"] for e in on_ball)
    lev_by_id = {e["id"]: float(v) for e, v in zip(on_ball, values, strict=True)}
    for e, v in zip(on_ball, values, strict=True):
        if v >= EXPLAINED_LEVERAGE:
            found.append(Detection("decision", e["t_ms"], e["period"], e["team"], [e["id"]],
                                   [e["player"]] if e.get("player") else [], float(v),
                                   hypotheses=[f"decision:{e['type']}"]))
    # goals, referee events, period ends
    rest = [e for e in events if e["type"] in {"goal", "period_end"} | REFEREE_KINDS]
    rest_lev = lev.at(e["t_ms"] for e in rest)
    for e, v in zip(rest, rest_lev, strict=True):
        kind = e["type"]
        players = [p for p in (e.get("player"), (e.get("attrs") or {}).get("fouled_player")) if isinstance(p, str)]
        evidence = [e["id"], *[r for r in e.get("related_event_ids", []) if r in by_id]]
        found.append(Detection(kind, e["t_ms"], e["period"], e["team"] if e["team"] in ("home", "away") else None,
                               evidence, players, None if kind == "period_end" else float(v)))
    # auto-events (T-026)
    for a in (auto if auto is not None else auto_events(window, events, xg_head)):
        anchor = max((by_id[r] for r in a.related_event_ids if r in by_id), key=lambda x: x["t_ms"], default=None)
        v = lev_by_id.get(anchor["id"]) if anchor else None
        if v is None:
            v = float(lev.at([a.t_ms])[0])
        extra = {"xg": a.value} if a.auto_kind == "big_chance" else {}
        found.append(Detection(a.auto_kind, a.t_ms, _period_at(events, a.t_ms), a.team, list(a.related_event_ids),
                               [p for p in a.players if isinstance(p, str)], v, extra, [a.auto_kind]))
    # chaos-state changes at 1 Hz
    sm = StateMachine()
    t = np.asarray(window.t_ms)
    for i in np.flatnonzero(t % 1000 == 0):
        ti = int(t[i])
        chaos = chaos_index(pitch_control(window.S[i].astype(np.float64)), turnover_rate(events, ti),
                            transition_share_at(events, ti))
        new = sm.update(chaos, ti)
        if new is not None:
            recent = [e["id"] for e in events if ti - 60_000 < e["t_ms"] <= ti and e["type"] == "possession_change"]
            found.append(Detection("state_change", ti, int(window.period[i]), None, recent[-3:] or
                                   [max((e for e in events if e["t_ms"] <= ti), key=lambda e: e["t_ms"])["id"]],
                                   extra={"state": new}, hypotheses=[f"state:{new}"]))
    # player tags: each player's fastest sprint of the match, if above the tag threshold
    best: dict[str, tuple[float, int]] = {}
    for pid, kmh, ts in speeds(window).sprints:
        if kmh >= PLAYER_TAG_KMH and kmh > best.get(pid, (0, 0))[0]:
            best[pid] = (kmh, ts)
    for pid, (kmh, ts) in best.items():
        near = min(events, key=lambda e: abs(e["t_ms"] - ts))
        found.append(Detection("player_tag", ts, _period_at(events, ts), near["team"] if near["team"] in
                               ("home", "away") else None, [near["id"]], [pid], extra={"kmh": kmh}))
    found.sort(key=lambda d: (d.t_ms, KIND_ORDER.index(d.kind) if d.kind in KIND_ORDER else 99, d.kind))
    return found


KEEP_ALONE = {"goal", "period_end", "player_tag", "milestone"} | REFEREE_KINDS


class Merger:
    """Collapse consecutive same-team detections within MERGE_MS into one moment. Goals, referee events, period ends
    and player tags stay separate (each drives its own cue); a detection of the other team ends the story, a
    team-less one (a chaos-state change) does not. A goal or referee event within SAME_INSTANT_MS of the same
    team's detection absorbs it: one event, one moment, all its branches.
    `add` returns (moment, is_new): live mode updates the moment already written when is_new is False."""

    def __init__(self) -> None:
        self.out: list[Detection] = []
        self.last: Detection | None = None

    def add(self, d: Detection) -> tuple[Detection, bool]:
        o = self.last
        if d.team is None:  # team-less (a chaos-state change): its own moment, and it does not end a possession
            m = Detection(d.kind, d.t_ms, d.period, d.team, list(d.evidence), list(d.players), d.leverage,
                          dict(d.extra), list(d.hypotheses))
            self.out.append(m)
            return m, True
        if (d.kind in KEEP_ALONE and o is not None and o.team == d.team and o.kind not in KEEP_ALONE
                and 0 <= d.t_ms - o.t_ms <= SAME_INSTANT_MS):
            # the goal or whistle of the play just detected: one event, one moment, all its branches
            o.kind, o.t_ms = d.kind, d.t_ms
            o.evidence += [e for e in d.evidence if e not in o.evidence]
            o.players += [p for p in d.players if p not in o.players]
            o.extra.update(d.extra)
            if d.leverage is not None and (o.leverage is None or d.leverage > o.leverage):
                o.leverage = d.leverage
            self.last = None
            return o, False
        if d.kind in KEEP_ALONE or o is None or o.team != d.team or d.t_ms - o.t_ms > MERGE_MS:
            m = Detection(d.kind, d.t_ms, d.period, d.team, list(d.evidence), list(d.players), d.leverage,
                          dict(d.extra), list(d.hypotheses))
            self.out.append(m)
            if d.kind not in REFEREE_KINDS | {"period_end"}:
                self.last = None if d.kind in KEEP_ALONE else m
            return m, True
        if KIND_ORDER.index(d.kind) < KIND_ORDER.index(o.kind):
            o.kind = d.kind
        o.evidence += [e for e in d.evidence if e not in o.evidence]
        o.players += [p for p in d.players if p not in o.players]
        o.hypotheses += [h for h in d.hypotheses if h not in o.hypotheses]
        o.extra.update(d.extra)
        if d.leverage is not None and (o.leverage is None or d.leverage > o.leverage):
            o.leverage, o.t_ms = d.leverage, max(o.t_ms, d.t_ms)
        return o, False


def merge(found: list[Detection]) -> list[Detection]:
    merger = Merger()
    for d in found:
        merger.add(d)
    return merger.out


def to_moment(d: Detection, match_id: str) -> dict:
    """Blackboard `moments` document (TECH_PLAN 1.3) without its id; put() allocates mo_ ids."""
    doc = {"match_id": match_id, "t_ms": int(d.t_ms), "clock": clock(int(d.t_ms)), "period": int(d.period),
           "kind": d.kind, "leverage": None if d.leverage is None else round(float(d.leverage), 4),
           "players": d.players, "team": d.team, "evidence_event_ids": d.evidence, "hypotheses": d.hypotheses,
           "status": "new", **d.extra}
    doc["fast"] = is_fast(doc)
    return doc


def detect_match(match_dir: str | Path, bb=None, panel_enabled: bool = False) -> list[dict]:
    """Moments of a whole recorded match, in time order; written to `bb` (mo_ ids) when given."""
    from physics.window import TrackingWindow

    match_dir = Path(match_dir)
    events = [json.loads(line) for line in (match_dir / "events.jsonl").read_text().splitlines() if line.strip()]
    window = TrackingWindow.load(match_dir)
    from heads.models import XGHead

    moments = [to_moment(d, events[0]["match_id"]) for d in merge(detect(events, window, xg_head=XGHead()))]
    if bb is not None:
        for m in moments:
            m["moment_id"] = bb.put("moments", m)
    return moments


class ScoutStream:
    """Live detection, one event at a time (TECH_PLAN 1.7: Scout is code, 50 ms per event).

    `observe(event)` needs the tracking window to reach t + 100 ms (the caller waits one frame). It runs the
    leverage of the event, the engine-event rules, auto-events over the last AUTO_WINDOW_MS, the chaos state machine
    for each whole second passed, and returns the (moment, is_new) pairs the Merger produced.
    """

    AUTO_WINDOW_MS = 15_000

    def __init__(self, match_id: str, window, head=None, xg_head=None) -> None:
        from physics.state_machine import StateMachine

        self.match_id = match_id
        self.window = window
        self.lev = Leverage(window, head)
        self.xg_head = xg_head
        self.events: list[dict] = []
        self.merger = Merger()
        self.sm = StateMachine()
        self.next_second = 1000
        self.seen_auto: set[str] = set()

    def observe(self, e: dict) -> list[tuple[Detection, bool]]:
        from physics.auto_events import auto_events
        from physics.indices import chaos_index, transition_share_at, turnover_rate
        from physics.pitch_control import pitch_control

        self.events.append(e)
        t = int(e["t_ms"])
        found: list[Detection] = []
        if e["type"] in ON_BALL | {"goal"} | REFEREE_KINDS:
            v = float(self.lev.at([t])[0])
            if e["type"] in ON_BALL and v >= EXPLAINED_LEVERAGE:
                found.append(Detection("decision", t, e["period"], e["team"], [e["id"]],
                                       [e["player"]] if e.get("player") else [], v,
                                       hypotheses=[f"decision:{e['type']}"]))
            elif e["type"] not in ON_BALL:
                players = [p for p in (e.get("player"), (e.get("attrs") or {}).get("fouled_player"))
                           if isinstance(p, str)]
                found.append(Detection(e["type"], t, e["period"], e["team"] if e["team"] in ("home", "away")
                                       else None, [e["id"], *e.get("related_event_ids", [])], players, v))
        elif e["type"] == "period_end":
            found.append(Detection("period_end", t, e["period"], None, [e["id"]]))
        recent = [x for x in self.events if x["t_ms"] >= t - self.AUTO_WINDOW_MS]
        w = self.window.slice(t - self.AUTO_WINDOW_MS, t)
        if len(w):
            for a in auto_events(w, recent, self.xg_head):
                if a.auto_id in self.seen_auto:
                    continue
                self.seen_auto.add(a.auto_id)
                extra = {"xg": a.value} if a.auto_kind == "big_chance" else {}
                found.append(Detection(a.auto_kind, a.t_ms, e["period"], a.team, list(a.related_event_ids),
                                       [p for p in a.players if isinstance(p, str)], float(self.lev.at([a.t_ms])[0]),
                                       extra, [a.auto_kind]))
        while self.next_second <= t:
            ts = self.next_second
            i = self.window.index_at(ts)
            chaos = chaos_index(pitch_control(self.window.S[i].astype(np.float64)), turnover_rate(self.events, ts),
                                transition_share_at(self.events, ts))
            if (new := self.sm.update(chaos, ts)) is not None:
                found.append(Detection("state_change", ts, int(self.window.period[i]), None, [e["id"]],
                                       extra={"state": new}, hypotheses=[f"state:{new}"]))
            self.next_second += 1000
        found.sort(key=lambda d: (d.t_ms, KIND_ORDER.index(d.kind) if d.kind in KIND_ORDER else 99))
        return [self.merger.add(d) for d in found]
