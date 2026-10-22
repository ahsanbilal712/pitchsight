"""Player stats for the Player-Cam card (TECH_PLAN 1.9 fan app, T-044).

    GET /match/{match_id}/players/{player_id}/stats

The body is MCP `player_stats` (packages/mcp_server/tools_core.py: touches, passes, completion, xT, shots, xG,
sprints, top speed, decision_index), called on the same code, plus:
- `distance_m`: metres covered while on the pitch, from tracking.npz (rows follow substitutions);
- `decision_index` while the MCP value is null: the latest blackboard fact `{name: decision_index, player}`, else
  the golden cache's rollout index (cache/analytics/decision_index.json `players[pid].index`, T-048), with
  `decision_index_source` saying which (players with fewer than 5 decisions have none).
Numbers cover the whole recorded match, as MCP's do.
"""

from __future__ import annotations

import functools
import json
import threading

import numpy as np
from fastapi import APIRouter, HTTPException, Request

from api.replay import MatchData

router = APIRouter()
_lock = threading.Lock()


def _store(app):
    with _lock:
        if getattr(app.state, "mcp_store", None) is None:
            from mcp_server.tools_core import MatchStore

            app.state.mcp_store = MatchStore(app.state.bb)
        return app.state.mcp_store


def on_pitch(data: MatchData, player_id: str) -> list[tuple[int, int, int]]:
    """(row, first frame, last frame + 1) spans where player_id occupies a tracking row."""
    spans = []
    n = len(data.t_ms)
    if player_id in data.player_ids:
        row, start = data.player_ids.index(player_id), 0
        off = next((t for t, r, _ in data.subs if r == row), None)
        spans.append((row, start, n if off is None else data.index_at(off)))
    for t, row, pid in data.subs:
        if pid == player_id:
            later = next((t2 for t2, r2, _ in data.subs if r2 == row and t2 > t), None)
            spans.append((row, data.index_at(t), n if later is None else data.index_at(later)))
    return spans


def distance_m(data: MatchData, player_id: str) -> float:
    total = 0.0
    for row, a, b in on_pitch(data, player_id):
        xy = data.S[a:b, row, :2].astype(np.float64)
        if len(xy) > 1:
            total += float(np.hypot(*np.diff(xy, axis=0).T).sum())
    return round(total, 1)


@router.get("/match/{match_id}/players/{player_id}/stats")
def player_stats(request: Request, match_id: str, player_id: str) -> dict:
    from mcp_server.errors import ToolError
    from mcp_server.tools_core import player_stats as mcp_player_stats

    mid = match_id if match_id.startswith("m_") else f"m_{match_id}"
    try:
        stats = dict(mcp_player_stats(_store(request.app), mid, player_id))
    except ToolError as exc:
        raise HTTPException(404, str(exc)) from exc
    data: MatchData = request.app.state.data
    stats["distance_m"] = distance_m(data, player_id) if mid == data.match_id else None
    stats["decision_index_source"] = "mcp" if stats.get("decision_index") is not None else None
    if stats.get("decision_index") is None:
        facts = request.app.state.bb.query("facts", match_id=mid, name="decision_index", player=player_id)
        if facts:
            stats["decision_index"] = facts[-1]["value"]
            stats["decision_index_source"] = "fact"
        else:
            index = cached_decision_index(mid).get(player_id)
            if index is not None:
                stats["decision_index"], stats["decision_index_source"] = index, "cache"
    return stats


@functools.lru_cache(maxsize=8)
def cached_decision_index(match_id: str) -> dict[str, float]:
    """{player: Decision Index 0-100} from the golden cache (T-048), or {}."""
    from api.replay import match_dir

    path = match_dir(match_id) / "cache" / "analytics" / "decision_index.json"
    if not path.exists():
        return {}
    players = json.loads(path.read_text()).get("players", {})
    return {pid: v["index"] for pid, v in players.items() if isinstance(v, dict) and "index" in v}
