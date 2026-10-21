"""Stream message types and per-viewer filtering (TECH_PLAN 1.9, T-033).

Every WebSocket line is `{type, payload}`. Blackboard collections map to message types; `targets` on a cue decides
which viewers get it, server side. Studio gets every cue and the studio-only messages.
"""

from __future__ import annotations

import functools
from pathlib import Path

import yaml

BUDGETS = Path(__file__).resolve().parents[2] / "config" / "budgets.yaml"

# TECH_PLAN 1.9 message types, plus the additions screens already handle (lineup, counterfactual).
MESSAGE_TYPES = ("hello", "tracking_frame", "event", "fact", "moment", "cue", "cue_remove", "trace", "request_info",
                 "mode", "spend", "oracle", "lineup", "counterfactual")

# Blackboard collections the api forwards, and how.
#   timed: released when the stream clock reaches the document's time (t_ms, or t_in_ms for cues)
#   now:   forwarded as soon as they are written
TIMED_COLLECTIONS = {"cues": "cue", "facts": "fact", "moments": "moment", "oracle": "oracle"}
NOW_COLLECTIONS = {"traces": "trace", "modes": "mode", "requests": "request_info"}

# Message types only the producer console consumes (1.9 consumer column).
STUDIO_ONLY = {"moment", "trace", "request_info", "spend"}

DECISIONS = {"approve": "approved", "approved": "approved", "veto": "vetoed", "vetoed": "vetoed",
             "hold": "held", "held": "held"}


@functools.cache
def mode_kinds() -> dict[str, frozenset[str] | None]:
    """Allowed cue kinds per viewer mode (config/budgets.yaml director.modes); None = all kinds."""
    modes = yaml.safe_load(BUDGETS.read_text())["director"]["modes"]
    return {m: (None if "all" in cfg["kinds"] else frozenset(cfg["kinds"])) for m, cfg in modes.items()}


@functools.cache
def involved_only_modes() -> frozenset[str]:
    """Modes that show only cues involving the viewer's player (budgets.yaml only_player_involved)."""
    modes = yaml.safe_load(BUDGETS.read_text())["director"]["modes"]
    return frozenset(m for m, cfg in modes.items() if cfg.get("only_player_involved"))


def doc_time(doc: dict) -> int | None:
    t = doc.get("t_ms", doc.get("t_in_ms"))
    return int(t) if isinstance(t, int | float) else None


def is_studio(profile: dict) -> bool:
    return profile.get("mode") == "studio"


def wants(profile: dict, msg_type: str) -> bool:
    return is_studio(profile) or msg_type not in STUDIO_ONLY


def cue_matches(profile: dict, cue: dict) -> bool:
    """A cue goes to a viewer when its targets admit the viewer's mode, club and (player_cam) player.

    - studio receives every cue (1.9);
    - `targets.modes` must list the viewer's mode, and the cue's kind must be one the mode allows in
      config/budgets.yaml (the Director targets by the same list; the api enforces it as well);
    - `targets.clubs`: "any" (the default) matches everyone; otherwise a viewer with a club must be listed
      (a viewer without a club perspective sees every club's cues);
    - player-specific kinds (player_tag, decision_index) with `targets.players` go to player_cam viewers of one
      of those players only;
    - a mode with `only_player_involved` (player_cam) gets only cues whose `targets.players` include its player.
    """
    if is_studio(profile):
        return True
    targets = cue.get("targets") or {}
    mode = profile.get("mode")
    if mode not in (targets.get("modes") or []):
        return False
    allowed = mode_kinds().get(mode)
    if allowed is not None and cue.get("kind") not in allowed:
        return False
    clubs = targets.get("clubs") or ["any"]
    club = profile.get("club")
    if "any" not in clubs and club and club not in clubs:
        return False
    players = targets.get("players") or []
    if mode in involved_only_modes():
        return profile.get("player") in players
    if mode == "player_cam" and cue.get("kind") in ("player_tag", "decision_index") and players:
        return profile.get("player") in players
    return True


def mode_payload(doc: dict) -> dict:
    return {"mode": doc.get("mode", "replay"), "reason": doc.get("reason")}


def request_payload(doc: dict) -> dict:
    return {"request_id": doc.get("request_id") or doc.get("id"), "cue": doc.get("cue")}
