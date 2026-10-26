"""Ruling -> referee_line cue (schemas/cue.schema.json), verified by construction.

Every number on screen is a claim that cites the event it came from, so the Fact Checker can re-verify it (the offside
margin is the event's margin_m). Geometry the events do not carry (the fouler's closing speed, the contact point, the
offside line's x) is drawn or said in words, never shown as a number. The geometry was computed by code from the
frames, which is why the cue is `verified` without a model in the loop.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .foul import FoulRuling
from .offside import OffsideRuling

ROOT = Path(__file__).resolve().parents[2]
SHOW_MS = 8000
FAST_CLOSING_MS = 3.0                  # closing speed (m/s) worded as "came in at speed"


@lru_cache(maxsize=1)
def _names() -> dict[str, str]:
    players = json.loads((ROOT / "data" / "league" / "players.json").read_text(encoding="utf-8"))
    return {p["id"]: p["name"].split()[-1] for p in players}


def _clock(t_ms: int) -> str:
    s = t_ms // 1000
    return f"{s // 60:02d}:{s % 60:02d}"


def ruling_to_cue(r: OffsideRuling | FoulRuling, t_ms: int, match_id: str = "m_4242", cue_id: str | None = None,
                  evidence_event_id: str | None = None, period: int | None = None) -> dict:
    """A referee_line cue for the ruling, shown from t_ms for 8 s. `evidence_event_id` is the offside or foul event
    id (defaults to the pass or foul event)."""
    names = _names()
    cid = cue_id or f"c_{9 * 10**5 + (t_ms // 100) % 10**5:06d}"
    if isinstance(r, OffsideRuling):
        ev = evidence_event_id or r.pass_event_id
        who = names.get(r.offside_player, r.offside_player)
        m = abs(r.margin_m)
        if r.offside:
            headline = f"Offside: {who}, {m:.1f} m"
            body = f"{who} was {m:.1f} m beyond the last defender when the ball was played."
        else:
            headline = f"Onside: {who}"
            body = f"{who} was {m:.1f} m behind the last defender when the ball was played." if r.reason == "onside" \
                else f"{who} was level with the last defender: onside."
        claims = [{"text": f"{m:.1f} m", "kind": "number", "value": round(m, 1), "unit": "metres", "evidence_ids": [ev],
                   "verified": True, "reject_reason": None},
                  {"text": who, "kind": "player", "value": r.offside_player, "unit": None, "evidence_ids": [ev],
                   "verified": True, "reject_reason": None}]
        lines, players = [r.line], [r.offside_player, r.last_defender]
        why = "Offside line drawn at the second-last defender, in the frame the pass was played."
    else:
        ev = evidence_event_id or r.foul_event_id
        who = names.get(r.fouler, r.fouler)
        where = "inside the penalty area" if r.in_box else "outside the penalty area"
        verdict = "Penalty" if r.in_box else "Free kick"
        headline = f"{verdict}: {who}" + (f", {r.card} card" if r.card else "")
        closing = "came in at speed" if r.closing_speed_ms >= FAST_CLOSING_MS else "made the contact"
        body = f"Contact {where}; {who} {closing}."
        claims = [{"text": who, "kind": "player", "value": r.fouler, "unit": None, "evidence_ids": [ev],
                   "verified": True, "reject_reason": None}]
        lines, players = r.box_lines, [r.fouler, r.fouled_player]
        why = f"Contact point marked {where}, in the frame of the foul."
    return {
        "schema_version": "1.0.0", "cue_id": cid, "match_id": match_id, "moment_id": None,
        "t_in_ms": int(t_ms), "t_out_ms": int(t_ms) + SHOW_MS, "clock": _clock(t_ms),
        "period": int(period or (1 if t_ms <= 45 * 60 * 1000 else 2)), "layer": "referee_line", "priority": 0.7,
        "leverage": None, "kind": "fourth_official",
        "targets": {"modes": ["analyst", "casual", "player_cam", "studio"], "clubs": ["any"],
                    "players": [p for p in players if isinstance(p, str)]},
        "text": {"headline": headline[:60], "body": body[:280]},
        "graphics": {"pitch_control_snapshot": None, "ghost_trail": [], "players_highlight": [p for p in players if p],
                     "lines": lines, "bar": None},
        "explain": {"why": why[:400], "claims": claims, "counterfactual_id": None, "explanation_id": None},
        "verified": True, "producer_status": "auto",
        "provenance": {"mode": "replay", "agent_path": ["scout", "fourth_official", "director"],
                       "trace_id": f"fo_{t_ms:09d}", "resumed_from_checkpoint": None, "model": None,
                       "prompt_version": None, "cache_key": None},
    }
