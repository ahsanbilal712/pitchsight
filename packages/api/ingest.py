"""Live ingest (TECH_PLAN 1.1 live data flow, T-033): the engine posts events and 10 Hz tracking here
(`python -m kickoff play --seed N --target api`). The first post switches the stream to live mode; events also
land in blackboard `events` for the agents.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
FRAME_KEYS = {"t_ms", "period", "p", "ball_z", "holder", "possession"}


def _as_list(body: Any) -> list[dict]:
    items = body if isinstance(body, list) else [body]
    if not all(isinstance(x, dict) for x in items):
        raise HTTPException(422, "expected an object or a list of objects")
    return items


@router.post("/ingest/events")
async def ingest_events(request: Request) -> dict:
    events = _as_list(await request.json())
    for e in events:
        if not {"id", "match_id", "t_ms", "type"} <= set(e):
            raise HTTPException(422, f"event needs id, match_id, t_ms, type: {str(e)[:120]}")
    if events:
        request.app.state.bb.put_many("events", events)
        request.app.state.hub.ingest_events(events)
    return {"accepted": len(events)}


@router.post("/ingest/tracking")
async def ingest_tracking(request: Request, match_id: str) -> dict:
    frames = _as_list(await request.json())
    for f in frames:
        if set(f) != FRAME_KEYS or len(f["p"]) != 23:
            raise HTTPException(422, f"tracking_frame needs exactly {sorted(FRAME_KEYS)} with 23 rows")
    request.app.state.hub.ingest_frames(match_id, frames)
    return {"accepted": len(frames)}
