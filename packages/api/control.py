"""Control endpoints (TECH_PLAN 1.4 api, 1.7 producer veto, T-033): replay clock, producer decisions, demo kill.

- `POST /replay/control {action: play|pause|seek|speed, value | t_ms}` drives the replay clock.
- `POST /producer/decision {request_id, decision}` writes `decisions/<request_id>` for the newsroom worker (T-050).
  A veto whose request_id is a shown cue's id also rewrites that cue as `producer_status: vetoed` and broadcasts
  `cue_remove` at once (the veto-a-shown-cue path of 1.7).
- `POST /demo/kill {target}` is a stub answering 202 until the supervisor exists (T-051).
"""

from __future__ import annotations

import re
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from api.messages import DECISIONS
from api.models import ControlRequest, envelope
from api.replay import ReplayClock, parse_clock

router = APIRouter()
CUE_ID = re.compile(r"^c_[0-9]{6}$")


class Decision(BaseModel):
    request_id: str
    decision: str
    match_id: str | None = None


class Kill(BaseModel):
    target: str


@router.post("/replay/control")
def replay_control(request: Request, req: ControlRequest) -> dict:
    clock: ReplayClock = request.app.state.clock
    try:
        if req.action == "play":
            clock.play()
        elif req.action == "pause":
            clock.pause()
        elif req.action == "seek":
            target = req.value if req.value is not None else req.t_ms
            if target is None:
                raise ValueError("seek needs value (ms or mm:ss) or t_ms")
            clock.seek(parse_clock(target))
        elif req.action == "speed":
            if req.value is None:
                raise ValueError("speed needs value")
            clock.set_speed(float(req.value))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return clock.state().model_dump()


@router.post("/producer/decision")
def producer_decision(request: Request, body: Decision) -> dict:
    status = DECISIONS.get(body.decision.lower())
    if status is None:
        raise HTTPException(422, f"decision must be one of approved, vetoed, held (got {body.decision!r})")
    hub, bb = request.app.state.hub, request.app.state.bb
    match_id = body.match_id or hub.match_id
    bb.put("decisions", {"id": body.request_id, "request_id": body.request_id, "decision": status,
                         "match_id": match_id, "t_ms": hub.now(), "decided_at": time.time()})
    removed = False
    if CUE_ID.match(body.request_id):
        try:
            cue = bb.get("cues", body.request_id, match_id=match_id)
        except KeyError:
            cue = None
        if cue is not None:
            bb.put("cues", {**cue, "producer_status": status})
            if status == "vetoed":
                hub.send([envelope("cue_remove", {"cue_id": body.request_id})])
                removed = True
    return {"request_id": body.request_id, "decision": status, "cue_removed": removed}


@router.post("/demo/kill", status_code=202)
def demo_kill(body: Kill) -> dict:
    if body.target not in ("newsroom", "mcp", "api"):
        raise HTTPException(422, f"unknown target {body.target!r}")
    return {"accepted": True, "target": body.target, "note": "stub until T-051 (supervisor)"}
