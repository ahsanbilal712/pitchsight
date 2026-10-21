"""Control endpoints (TECH_PLAN 1.4 api, 1.7 producer veto, T-033): replay clock, producer decisions, demo kill.

- `POST /replay/control {action: play|pause|seek|speed, value | t_ms}` drives the replay clock.
- `POST /producer/decision {request_id, decision}` writes `decisions/<request_id>` for the newsroom worker (T-050).
  A veto whose request_id is a shown cue's id also rewrites that cue as `producer_status: vetoed` and broadcasts
  `cue_remove` at once (the veto-a-shown-cue path of 1.7).
- `POST /demo/kill {target: newsroom}` (T-051) waits in the background until a running newsroom run has finished
  the Tactician and not the Narrator, then sends SIGKILL to the worker pid the supervisor wrote
  (WHYLINE_WORKER_PIDFILE) and logs `kill target=newsroom run_id=... at_executor=tactician`.
"""

from __future__ import annotations

import os
import re
import signal
import threading
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


def decide(bb, hub, request_id: str, status: str, match_id: str) -> dict:
    """Record a producer decision; a veto of a shown cue also marks the cue vetoed and removes it from screens."""
    bb.put("decisions", {"id": request_id, "request_id": request_id, "decision": status,
                         "match_id": match_id, "t_ms": hub.now(), "decided_at": time.time()})
    removed = False
    if CUE_ID.match(request_id):
        try:
            cue = bb.get("cues", request_id, match_id=match_id)
        except KeyError:
            cue = None
        if cue is not None:
            bb.put("cues", {**cue, "producer_status": status})
            if status == "vetoed":
                hub.send([envelope("cue_remove", {"cue_id": request_id})])
                removed = True
    return {"request_id": request_id, "decision": status, "cue_removed": removed}


@router.post("/producer/decision")
def producer_decision(request: Request, body: Decision) -> dict:
    status = DECISIONS.get(body.decision.lower())
    if status is None:
        raise HTTPException(422, f"decision must be one of approved, vetoed, held (got {body.decision!r})")
    hub, bb = request.app.state.hub, request.app.state.bb
    return decide(bb, hub, body.request_id, status, body.match_id or hub.match_id)


def kill_when_ready(bb, run_id: str | None = None, timeout_s: float = 120.0, poll_s: float = 0.02,
                    pid_path: str | None = None) -> dict:
    """Block until a running newsroom run (or `run_id`) has a Tactician trace row and no Narrator row, then SIGKILL
    the worker. Returns {killed, run_id, pid} or {killed: False, reason}."""
    from newsroom.resume import demo_log, mark_interrupted
    from newsroom.supervisor import pidfile

    end = time.time() + timeout_s
    while time.time() < end:
        runs = [r["id"] for r in bb.query("runs", status="running")] if run_id is None else [run_id]
        for rid in runs:
            done = {t["executor"] for t in bb.query("traces", run_id=rid)}
            if "tactician" in done and "narrator" not in done:
                path = pid_path or pidfile()
                pid = int(open(path).read().strip())
                os.kill(pid, signal.SIGKILL)
                demo_log(f"kill target=newsroom run_id={rid} at_executor=tactician")
                run = next((r for r in bb.query("runs", id=rid)), {"id": rid})
                mark_interrupted(bb, run, at_executor="narrator")   # the step the kill cut
                return {"killed": True, "run_id": rid, "pid": pid}
        time.sleep(poll_s)
    return {"killed": False, "reason": f"no run between Tactician and Narrator within {timeout_s:.0f} s"}


def thread_board(bb):
    """A blackboard connection for a background thread: one sqlite connection must not be used from two threads at
    once (the kill wait polls while the stream ticker queries), so file-backed boards get a connection of their own."""
    path = getattr(bb, "path", ":memory:")
    if path == ":memory:":
        return bb
    from blackboard import SqliteBlackboard

    return SqliteBlackboard(path)


@router.post("/demo/kill", status_code=202)
def demo_kill(request: Request, body: Kill) -> dict:
    if body.target not in ("newsroom", "mcp", "api"):
        raise HTTPException(422, f"unknown target {body.target!r}")
    if body.target != "newsroom":
        return {"accepted": False, "target": body.target, "note": "only the newsroom worker is supervised (T-051)"}
    bb = request.app.state.bb
    threading.Thread(target=kill_when_ready, args=(thread_board(bb),), daemon=True, name="demo-kill").start()
    return {"accepted": True, "target": body.target}
