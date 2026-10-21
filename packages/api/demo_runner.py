"""Demo-script runner (TECH_PLAN 1.8 "Demo script", T-061): applies packages/demo/demo_script.yaml on the replay
clock so every take is the same.

    kill   -> the T-051 path: wait for a run between Tactician and Narrator, SIGKILL the worker
    veto   -> producer decision `vetoed` on the pending request whose cue has `cue_kind` (the half-time recap);
              if the request is not there yet, the veto waits for it (up to VETO_WAIT_MS of match time)
    speed  -> replay speed

An action fires once when the clock passes its time. Seeking backwards re-arms the actions after the new clock;
seeking forwards over an action skips it (a seek is a cut, not a performance). Armed by WHYLINE_DEMO_SCRIPT or
POST /demo/script {action: arm|disarm}; GET /demo/script shows the plan and what fired.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from demo.clocks import fmt, resolve

log = logging.getLogger("whyline.demo")
router = APIRouter()
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCRIPT = ROOT / "packages" / "demo" / "demo_script.yaml"
TICK_S = 0.05
SEEK_JUMP_MS = 2000  # a clock jump larger than this is a seek
VETO_WAIT_MS = 60_000


@dataclass
class Action:
    at_ms: int
    action: str
    spec: dict
    fired: bool = False
    result: dict = field(default_factory=dict)


def load_script(path: str | Path = DEFAULT_SCRIPT) -> list[Action]:
    rows = yaml.safe_load(Path(path).read_text()) or []
    out = []
    for row in rows:
        if row.get("action") not in ("kill", "veto", "speed"):
            raise ValueError(f"unknown demo action {row!r}")
        out.append(Action(resolve(str(row["at_clock"])), row["action"], row))
    return out


class DemoRunner:
    def __init__(self, app_state, actions: list[Action], kill=None) -> None:
        self.state = app_state
        self.actions = actions
        self.kill = kill  # injectable for tests; default: control.kill_when_ready on a thread
        self.last_t: int | None = None
        self.pending_veto: list[Action] = []

    # ------------------------------------------------------------------ actions
    def _demo_log(self, line: str) -> None:
        try:
            from newsroom.resume import demo_log

            demo_log(line)
        except Exception:  # the log is evidence, not control flow
            log.info(line)

    def fire(self, a: Action, t_ms: int) -> None:
        a.fired = True
        if a.action == "speed":
            self.state.clock.set_speed(float(a.spec["value"]))
            a.result = {"speed": float(a.spec["value"])}
        elif a.action == "kill":
            if self.kill is not None:
                a.result = self.kill(a.spec.get("target", "newsroom")) or {}
            else:
                from api.control import kill_when_ready, thread_board

                threading.Thread(target=kill_when_ready, args=(thread_board(self.state.bb),), daemon=True,
                                 name="demo-script-kill").start()
                a.result = {"started": True}
        elif a.action == "veto":
            self.pending_veto.append(a)
            self._try_vetoes(t_ms)
        self._demo_log(f"demo action={a.action} at={fmt(a.at_ms)} clock={fmt(t_ms)} {a.result}")

    def _try_vetoes(self, t_ms: int) -> None:
        from api.control import decide

        bb, hub = self.state.bb, self.state.hub
        for a in list(self.pending_veto):
            decided = {d.get("request_id") for d in bb.query("decisions", match_id=hub.match_id)}
            for r in bb.query("requests", match_id=hub.match_id):
                rid = r.get("request_id") or r.get("id")
                if (r.get("cue") or {}).get("kind") == a.spec.get("cue_kind", "recap") and rid not in decided:
                    a.result = decide(bb, hub, rid, "vetoed", hub.match_id)
                    self.pending_veto.remove(a)
                    break
            else:
                if t_ms - a.at_ms > VETO_WAIT_MS:
                    a.result = {"vetoed": False, "reason": "no pending request"}
                    self.pending_veto.remove(a)

    # ------------------------------------------------------------------ clock
    def tick(self) -> None:
        if self.state.hub.live:
            return
        t = self.state.hub.now()
        last = self.last_t
        self.last_t = t
        if last is None or abs(t - last) > SEEK_JUMP_MS:
            for a in self.actions:  # a seek re-arms what lies ahead and skips what it jumped over
                a.fired = a.at_ms <= t
            self.pending_veto = [a for a in self.pending_veto if a.at_ms <= t]
            return
        for a in sorted(self.actions, key=lambda x: x.at_ms):
            if not a.fired and last < a.at_ms <= t:
                self.fire(a, t)
        if self.pending_veto:
            self._try_vetoes(t)

    async def run(self) -> None:
        while True:
            try:
                self.tick()
            except Exception:
                log.exception("demo script tick failed")
            await asyncio.sleep(TICK_S)

    def status(self) -> dict:
        return {"armed": True, "actions": [{"at": fmt(a.at_ms), "action": a.action, "fired": a.fired,
                                            "result": a.result} for a in self.actions]}


def start(app, path: str | Path | None = None) -> DemoRunner:
    stop(app)
    runner = DemoRunner(app.state, load_script(path or os.environ.get("WHYLINE_DEMO_SCRIPT") or DEFAULT_SCRIPT))
    app.state.demo_runner = runner
    app.state.demo_task = asyncio.get_event_loop().create_task(runner.run())
    return runner


def stop(app) -> None:
    task = getattr(app.state, "demo_task", None)
    if task is not None:
        task.cancel()
    app.state.demo_runner = None
    app.state.demo_task = None


class ScriptControl(BaseModel):
    action: str
    path: str | None = None


@router.get("/demo/script")
def script_status(request: Request) -> dict:
    runner = getattr(request.app.state, "demo_runner", None)
    return runner.status() if runner else {"armed": False, "actions": []}


@router.post("/demo/script")
async def script_control(request: Request, body: ScriptControl) -> dict:
    if body.action == "arm":
        try:
            return start(request.app, body.path).status()
        except (OSError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc
    if body.action == "disarm":
        stop(request.app)
        return {"armed": False, "actions": []}
    raise HTTPException(422, "action must be arm or disarm")
