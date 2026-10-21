"""Auto-events: tactical patterns detected from tracking and events (TECH_PLAN 1.4 physics, T-026).

    auto_events(window, events) -> list[AutoEvent]
    python -m physics.auto_events --match data/matches/4242     # writes auto_events_report.json

Kinds: pressing_trap, line_break, switch_of_play, overload, counter_attack, big_chance. They are not schema events
(event.schema.json has no such types) and never go into events.jsonl; each becomes a blackboard `facts` document
{kind: "state", name: <auto_kind>, evidence_event_ids} via `AutoEvent.to_fact`.

Coordinates are taken into the acting team's frame (own goal at u = 0, attacked goal at u = 105, v mirrored so the
right flank is low v). Every detector reads only the window and the events inside it, so calling auto_events on the
last ~15 s every frame stays inside the physics budget; detections carry a stable `auto_id` for de-duplication.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .window import PITCH_L, PITCH_W, TrackingWindow, home_dir

KINDS = ("pressing_trap", "line_break", "switch_of_play", "overload", "counter_attack", "big_chance")
BIG_CHANCE_XG = 0.30            # TECH_PLAN 1.7 Scout classification
SWITCH_M, SWITCH_S = 35.0, 3.0  # lateral ball travel and time limit
TRAP_U, TRAP_PRESS_S, TRAP_PRESSERS = 63.0, 5.0, 2   # won in the attacking 40% after >= 2 players pressed
COUNTER_FROM_U, COUNTER_TO_U, COUNTER_S = 45.0, 80.0, 10.0
OVERLOAD_U, OVERLOAD_EDGE, OVERLOAD_MARGIN, OVERLOAD_GAP_S = 60.0, 25.0, 2, 30.0


@dataclass
class AutoEvent:
    auto_kind: str
    t_ms: int
    team: str                                   # home | away
    related_event_ids: list[str] = field(default_factory=list)
    players: list[str] = field(default_factory=list)
    value: float | str | None = None            # xG for big_chance, metres for switch_of_play, side for overload

    @property
    def auto_id(self) -> str:
        return f"{self.auto_kind}:{self.team}:{self.t_ms}"

    def to_fact(self, match_id: str, fact_id: str, window_s: float | None = None) -> dict:
        """Blackboard `facts` document (TECH_PLAN 1.3)."""
        return {"fact_id": fact_id, "match_id": match_id, "t_ms": int(self.t_ms), "kind": "state", "name": self.auto_kind,
                "value": self.value, "unit": "xg" if self.auto_kind == "big_chance" else
                ("m" if self.auto_kind == "switch_of_play" else None), "window_s": window_s, "team": self.team,
                "players": self.players, "evidence_event_ids": list(self.related_event_ids)}


def _team(e: dict) -> int:
    return 0 if e["team"] == "home" else 1


def _uv(x, y, team: int, period: int):
    """Absolute (x, y) into `team`'s attacking frame."""
    d = home_dir(period) if team == 0 else -home_dir(period)
    return (x, y) if d > 0 else (PITCH_L - np.asarray(x), PITCH_W - np.asarray(y))


def _frame_at(window: TrackingWindow, t_ms: int) -> int | None:
    if len(window) == 0 or t_ms < window.t_ms[0] or t_ms > window.t_ms[-1]:
        return None
    return window.index_at(t_ms)


def _in_window(events: list[dict], window: TrackingWindow) -> list[dict]:
    if len(window) == 0:
        return []
    t0, t1 = int(window.t_ms[0]), int(window.t_ms[-1])
    return [e for e in events if t0 <= e["t_ms"] <= t1]


# ---------------------------------------------------------------------------------------------------- detectors
def big_chances(window: TrackingWindow, events: list[dict], xg_head=None) -> list[AutoEvent]:
    """Shots the XGHead rates at xG >= 0.30 (the event's own engine xG when no head is given)."""
    out = []
    for e in _in_window(events, window):
        if e["type"] != "shot":
            continue
        xg = float(e["attrs"].get("xg", 0.0))
        i = _frame_at(window, e["t_ms"] - 100)
        if xg_head is not None and i is not None:
            import pandas as pd

            from heads.features import shot_features
            xg = float(xg_head.predict(pd.DataFrame([shot_features(e, window.S[i])]))[0])
        if xg >= BIG_CHANCE_XG:
            out.append(AutoEvent("big_chance", e["t_ms"], e["team"], [e["id"]], [e["player"]], round(xg, 3)))
    return out


def line_breaks(window: TrackingWindow, events: list[dict]) -> list[AutoEvent]:
    """Completed pass from in front of the opponents' last outfield defender to a receiver who controls the ball
    beyond that line (the line measured when the pass is played)."""
    out = []
    for e in _in_window(events, window):
        if e["type"] != "pass" or e["outcome"] != "complete" or not e["end_location"]:
            continue
        i = _frame_at(window, e["t_ms"] - 100)
        if i is None:
            continue
        team, period = _team(e), e["period"]
        S = window.S[i]
        opp = np.arange(11, 22) if team == 0 else np.arange(0, 11)
        ou, _ = _uv(S[opp[1:], 0], S[opp[1:], 1], team, period)               # outfield opponents
        line = float(np.max(ou))
        u0, _ = _uv(e["location"][0], e["location"][1], team, period)
        u1, _ = _uv(e["end_location"][0], e["end_location"][1], team, period)
        if u0 < line - 2.0 and u1 > line + 1.0:
            out.append(AutoEvent("line_break", e["t_ms"], e["team"], [e["id"]],
                                 [e["player"], e["attrs"].get("recipient")], round(float(u1 - line), 1)))
    return out


def switches_of_play(window: TrackingWindow, events: list[dict]) -> list[AutoEvent]:
    """A completed pass whose ball travels more than 35 m across the pitch and is controlled within 3 s (35 m, not
    the brief's example 30 m: at 30 m the golden match has 51 switches, above the 40 cap)."""
    out = []
    evs = _in_window(events, window)
    for k, e in enumerate(evs):
        if e["type"] != "pass" or e["outcome"] != "complete" or not e["end_location"]:
            continue
        dy = abs(e["end_location"][1] - e["location"][1])
        if dy <= SWITCH_M:
            continue
        rec = next((f for f in evs[k + 1:] if f["type"] in ("carry", "pass", "shot", "clearance", "possession_change")
                    and f["player"] == e["attrs"].get("recipient")), None)
        arrive = rec["t_ms"] if rec is not None else None
        if arrive is None:
            i0 = _frame_at(window, e["t_ms"])
            if i0 is None:
                continue
            j = np.flatnonzero(window.holder[i0:] >= 0)
            arrive = int(window.t_ms[i0 + j[0]]) if j.size else None
        if arrive is not None and arrive - e["t_ms"] <= SWITCH_S * 1000:
            out.append(AutoEvent("switch_of_play", e["t_ms"], e["team"], [e["id"]],
                                 [e["player"], e["attrs"].get("recipient")], round(float(dy), 1)))
    return out


def _turnovers(evs: list[dict]) -> list[dict]:
    return [e for e in evs if e["type"] == "possession_change" and e["team"] in ("home", "away")]


def pressing_traps(window: TrackingWindow, events: list[dict]) -> list[AutoEvent]:
    """The ball won in the attacking 40% of the pitch within 5 s of at least two players of the winning team
    pressing the ball carrier (a coordinated press, not one tackle)."""
    evs = _in_window(events, window)
    out = []
    for e in _turnovers(evs):
        team = _team(e)
        u, _ = _uv(e["location"][0], e["location"][1], team, e["period"])
        if u < TRAP_U:
            continue
        press = [p for p in evs if p["type"] == "pressure" and p["team"] == e["team"]
                 and e["t_ms"] - TRAP_PRESS_S * 1000 <= p["t_ms"] <= e["t_ms"]]
        if len({p["player"] for p in press}) >= TRAP_PRESSERS:
            out.append(AutoEvent("pressing_trap", e["t_ms"], e["team"], [p["id"] for p in press] + [e["id"]],
                                 sorted({p["player"] for p in press} | {e["player"]})))
    return out


def counter_attacks(window: TrackingWindow, events: list[dict]) -> list[AutoEvent]:
    """Possession won in the team's own half, then the ball carried or passed into the final 25 m within 10 s
    without losing it."""
    evs = _in_window(events, window)
    out = []
    for e in _turnovers(evs):
        team = _team(e)
        u0, _ = _uv(e["location"][0], e["location"][1], team, e["period"])
        if u0 > COUNTER_FROM_U:
            continue
        i0 = _frame_at(window, e["t_ms"])
        i1 = _frame_at(window, e["t_ms"] + int(COUNTER_S * 1000))
        if i0 is None or i1 is None:
            continue
        seg = slice(i0, i1 + 1)
        poss = window.possession[seg]
        bu, _ = _uv(window.S[seg, 22, 0], window.S[seg, 22, 1], team, e["period"])
        lost = np.flatnonzero((poss >= 0) & (poss != team))
        end = lost[0] if lost.size else len(poss)
        reach = np.flatnonzero(np.asarray(bu)[:end] >= COUNTER_TO_U)
        if reach.size:
            t_reach = int(window.t_ms[i0 + reach[0]])
            ids = [f["id"] for f in evs if e["t_ms"] <= f["t_ms"] <= t_reach and f["team"] == e["team"]
                   and f["type"] in ("possession_change", "pass", "carry", "shot")]
            out.append(AutoEvent("counter_attack", e["t_ms"], e["team"], ids or [e["id"]], [e["player"]],
                                 round((t_reach - e["t_ms"]) / 1000.0, 1)))
    return out


def overloads(window: TrackingWindow, events: list[dict], step_ms: int = 1000) -> list[AutoEvent]:
    """Team in possession has at least two more players than the defenders in a wide channel of the attacking
    half (u > 60, within 25 m of a touchline) with the ball in that channel; one detection per team per 30 s."""
    out: list[AutoEvent] = []
    last = {0: -10**9, 1: -10**9}
    idx = np.flatnonzero(window.t_ms % step_ms == 0)
    for i in idx:
        team = int(window.possession[i])
        if team < 0 or window.holder[i] < 0:
            continue
        t = int(window.t_ms[i])
        if t - last[team] < OVERLOAD_GAP_S * 1000:
            continue
        period = int(window.period[i])
        S = window.S[i]
        U, V = _uv(S[:23, 0], S[:23, 1], team, period)
        U, V = np.asarray(U), np.asarray(V)
        bu, bv = U[22], V[22]
        if bu < OVERLOAD_U:
            continue
        side = "right" if bv < OVERLOAD_EDGE else ("left" if bv > PITCH_W - OVERLOAD_EDGE else None)
        if side is None:
            continue
        zone = (U[:22] > OVERLOAD_U - 5.0) & ((V[:22] < OVERLOAD_EDGE) if side == "right" else (V[:22] > PITCH_W - OVERLOAD_EDGE))
        att = np.arange(11 * team, 11 * team + 11)
        dfn = np.arange(11 * (1 - team), 11 * (1 - team) + 11)
        n_att, n_def = int(zone[att].sum()), int(zone[dfn].sum())
        if n_att >= n_def + OVERLOAD_MARGIN:
            last[team] = t
            near = [f["id"] for f in events if t - 5000 <= f["t_ms"] <= t and f["team"] == ("home", "away")[team]
                    and f["type"] in ("pass", "carry")]
            out.append(AutoEvent("overload", t, ("home", "away")[team], near[-3:],
                                 [window.player_at(int(r), t) for r in att[zone[att]]], f"overload_{side}"))
    return out


def auto_events(window: TrackingWindow, events: list[dict], xg_head=None) -> list[AutoEvent]:
    """All six detectors over the window, in time order."""
    found = (big_chances(window, events, xg_head) + line_breaks(window, events) + switches_of_play(window, events)
             + pressing_traps(window, events) + counter_attacks(window, events) + overloads(window, events))
    return sorted(found, key=lambda a: (a.t_ms, KINDS.index(a.auto_kind), a.team))


def report(match_dir: Path, use_head: bool = True) -> dict:
    """Counts per kind over a whole match (and the detections) for auto_events_report.json."""
    match_dir = Path(match_dir)
    window = TrackingWindow.load(match_dir)
    events = [json.loads(line) for line in (match_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    head = None
    if use_head:
        from heads.models import XGHead
        head = XGHead()
    found = auto_events(window, events, head)
    counts = Counter(a.auto_kind for a in found)
    return {"match_id": events[0]["match_id"], "xg_source": "XGHead" if head else "event attrs",
            "counts": {k: int(counts.get(k, 0)) for k in KINDS},
            "detections": [{"auto_kind": a.auto_kind, "t_ms": a.t_ms, "team": a.team, "value": a.value,
                            "related_event_ids": a.related_event_ids} for a in found]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m physics.auto_events")
    ap.add_argument("--match", type=Path, default=Path("data/matches/4242"))
    args = ap.parse_args(argv)
    rep = report(args.match)
    (args.match / "auto_events_report.json").write_text(json.dumps(rep, indent=1, sort_keys=True) + "\n",
                                                        encoding="utf-8")
    print(json.dumps(rep["counts"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
