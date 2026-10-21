"""Match events (schemas/event.schema.json) and the per-world event log.

Events are created when something starts (a pass is kicked, a carry begins) and finalised when its
outcome is known. The log releases finalised events in (t_ms, creation order) and only once no
still-open event started earlier, so ids e_0001.. are monotonic in both id and time.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field

SCHEMA_VERSION = "1.0.0"
EVENT_TYPES = (
    "pass", "carry", "shot", "tackle", "interception", "pressure", "possession_change", "clearance", "save",
    "foul", "card", "offside", "goal", "substitution", "set_piece", "period_start", "period_end", "match_metadata",
)
TEAM_NAMES = ("home", "away")


def clock(t_ms: int) -> str:
    s = t_ms // 1000
    return f"{s // 60:02d}:{s % 60:02d}"


def _round(value, nd: int = 3):
    if isinstance(value, float):
        return round(value, nd) + 0.0
    if isinstance(value, (list, tuple)):
        return [_round(v, nd) for v in value]
    if isinstance(value, dict):
        return {k: _round(v, nd) for k, v in value.items()}
    return value


@dataclass(eq=False)
class Event:
    t_ms: int
    period: int
    type: str
    team: str                       # home | away | none
    player: str | None
    location: list[float] | None
    outcome: str = "n/a"
    end_location: list[float] | None = None
    under_pressure: bool = False
    related: list[Event] = field(default_factory=list)
    attrs: dict = field(default_factory=dict)
    world: int = 0
    seq: int = 0
    idx: int | None = None

    @property
    def id(self) -> str:
        if self.idx is None:
            raise ValueError("event has not been released yet")
        return f"e_{self.idx:04d}"

    def to_dict(self, match_id: str) -> dict:
        attrs = {k: (v.id if isinstance(v, Event) else v) for k, v in self.attrs.items()}
        return {
            "schema_version": SCHEMA_VERSION,
            "id": self.id,
            "match_id": match_id,
            "idx": self.idx,
            "t_ms": int(self.t_ms),
            "period": int(self.period),
            "clock": clock(self.t_ms),
            "type": self.type,
            "team": self.team,
            "player": self.player,
            "location": None if self.location is None else _round([float(v) for v in self.location], 2),
            "end_location": None if self.end_location is None else _round([float(v) for v in self.end_location], 2),
            "outcome": self.outcome,
            "under_pressure": bool(self.under_pressure),
            "related_event_ids": [r.id for r in self.related if r.idx is not None],
            "attrs": _round(attrs),
        }


class EventLog:
    """Open and finalised events of one world; releases them in time order with monotonic ids."""

    def __init__(self, world: int) -> None:
        self.world = world
        self._seq = 0
        self._next_idx = 1
        self._open: dict[int, Event] = {}
        self._ready: list[tuple[int, int, Event]] = []
        self.released: list[Event] = []

    def new(self, *, final: bool = True, **kw) -> Event:
        self._seq += 1
        ev = Event(world=self.world, seq=self._seq, **kw)
        if final:
            heapq.heappush(self._ready, (ev.t_ms, ev.seq, ev))
        else:
            self._open[ev.seq] = ev
        return ev

    def finalise(self, ev: Event) -> None:
        if self._open.pop(ev.seq, None) is not None:
            heapq.heappush(self._ready, (ev.t_ms, ev.seq, ev))

    def drop(self, ev: Event) -> None:
        self._open.pop(ev.seq, None)

    def is_open(self, ev: Event) -> bool:
        return ev.seq in self._open

    def has_ready(self) -> bool:
        return bool(self._ready)

    def release(self, flush: bool = False) -> list[Event]:
        if flush:
            for ev in list(self._open.values()):
                self.finalise(ev)
        horizon = min(((e.t_ms, e.seq) for e in self._open.values()), default=None)
        out = []
        while self._ready and (horizon is None or self._ready[0][:2] < horizon):
            _, _, ev = heapq.heappop(self._ready)
            ev.idx = self._next_idx
            self._next_idx += 1
            out.append(ev)
        self.released.extend(out)
        return out
