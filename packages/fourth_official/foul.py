"""Foul geometry (Law 12): contact point, closing speed, in or out of the penalty area (T-049)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from physics.window import TrackingWindow

from .rules import in_penalty_area, penalty_area_lines


@dataclass
class FoulRuling:
    foul_event_id: str
    t_ms: int
    fouler: str
    fouled_player: str
    contact_point: list[float]
    closing_speed_ms: float            # the fouler's speed toward the fouled player at contact
    in_box: bool                       # inside the penalty area the fouling team defends
    card: str | None                   # yellow | red | None
    team: str                          # fouling team
    period: int
    box_lines: list[list[list[float]]]

    @property
    def kind(self) -> str:
        return "foul"


def check_foul(events: list[dict], frames: TrackingWindow) -> FoulRuling | None:
    """Ruling for the last foul event in `events` that falls inside `frames` (None if there is none)."""
    fouls = [e for e in events if e.get("type") == "foul" and len(frames)
             and frames.t_ms[0] <= e["t_ms"] <= frames.t_ms[-1]]
    if not fouls:
        return None
    e = fouls[-1]
    frame = frames.frame_at(e["t_ms"] - 100) if e["t_ms"] - 100 >= frames.t_ms[0] else frames.frame_at(e["t_ms"])
    a, b = frame.row_of(e["player"]), frame.row_of(e["attrs"].get("fouled_player", ""))
    S = np.asarray(frame.S, dtype=np.float64)
    contact = [float(v) for v in e["attrs"].get("contact_point") or e["location"]]
    closing = 0.0
    if a >= 0 and b >= 0:
        rel = S[b, 0:2] - S[a, 0:2]
        dist = float(np.hypot(*rel))
        closing = max(0.0, float(np.dot(S[a, 2:4] - S[b, 2:4], rel / max(dist, 1e-9))))
    team = 0 if e["team"] == "home" else 1
    card = next((c["attrs"].get("colour") for c in events if c.get("type") == "card" and e["id"] in c.get("related_event_ids", [])),
                None)
    return FoulRuling(foul_event_id=e["id"], t_ms=int(e["t_ms"]), fouler=e["player"],
                      fouled_player=e["attrs"].get("fouled_player"), contact_point=[round(v, 2) for v in contact],
                      closing_speed_ms=round(closing, 2), in_box=in_penalty_area(contact[0], contact[1], team, e["period"]),
                      card=card, team=e["team"], period=int(e["period"]), box_lines=penalty_area_lines(team, e["period"]))
