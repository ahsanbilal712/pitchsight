"""Recap tools:

    top_moments(match_id: str, period: int | None = None, k: int = 5) -> list[dict]
    timeline(match_id: str) -> dict          # chaos, control, xT series at 30 s

Moments come from blackboard `moments` (live: what the Scout has written so far), else from the match's cached
`moments.jsonl` (replay). The timeline covers the match events so far in the blackboard's match files.
"""

from __future__ import annotations

import json

import numpy as np

from mcp_server.errors import ToolError
from mcp_server.tools_core import MatchStore

STEP_MS = 30_000
MOMENT_KEYS = ("moment_id", "t_ms", "clock", "period", "kind", "leverage", "team", "players", "evidence_event_ids",
               "hypotheses")


def _moments(store: MatchStore, match_id: str) -> list[dict]:
    docs = store.bb.query("moments", match_id=match_id)
    if docs:
        return docs
    m = store.match(match_id)
    path = m.dir / "cache" / "moments.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def top_moments(store: MatchStore, match_id: str, period: int | None = None, k: int = 5) -> list[dict]:
    """The k moments with the largest leverage (goal-in-8-s swing), optionally one period, in match order."""
    if period not in (None, 1, 2):
        raise ToolError("bad_period", "period is 1, 2 or null")
    if not 1 <= int(k) <= 20:
        raise ToolError("bad_k", "k is 1..20")
    pool = [m for m in _moments(store, match_id) if (period is None or m.get("period") == period)
            and m.get("leverage") is not None]
    best = sorted(pool, key=lambda m: (-float(m["leverage"]), m["t_ms"]))[:int(k)]
    return [{key: m.get(key) for key in MOMENT_KEYS} for m in sorted(best, key=lambda m: m["t_ms"])]


def timeline(store: MatchStore, match_id: str) -> dict:
    """Every 30 s: chaos index, home pitch-control share, home-minus-away expected threat and xG over the last
    15 minutes. Values come from the match's tracking and events."""
    from heads.features import xt_xg_15
    from mcp_server.tools_core import get_state
    from physics.pitch_control import pitch_control

    m = store.match(match_id)
    w = store.tracking(m)
    end = int(m.events[-1]["t_ms"]) if m.events else 0
    get_state(store, match_id, end)              # fills the 1 Hz chaos/state series up to the end
    chaos = {t: (c, s) for t, c, s in m.chaos}
    rows = []
    for t in range(STEP_MS, end + 1, STEP_MS):
        i = w.index_at(t)
        xt, xg = xt_xg_15([e for e in m.events if e["t_ms"] <= t], t)
        c, state = chaos.get(t, (None, None))
        rows.append({"t_ms": t, "clock": f"{t // 60000:02d}:{(t // 1000) % 60:02d}", "period": int(w.period[i]),
                     "chaos": None if c is None else round(float(c), 1), "state": state,
                     "control_home": round(float(np.mean(pitch_control(w.S[i].astype(np.float64)))), 4),
                     "xt_diff_15": round(float(xt), 4), "xg_diff_15": round(float(xg), 4)})
    goals = [{"t_ms": e["t_ms"], "clock": e["clock"], "team": e["team"], "player": e.get("player"), "id": e["id"]}
             for e in m.events if e["type"] == "goal"]
    return {"match_id": match_id, "step_ms": STEP_MS, "series": rows, "goals": goals}
