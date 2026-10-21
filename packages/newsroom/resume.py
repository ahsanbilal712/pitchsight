"""Resume after a kill (TECH_PLAN 1.7 "Checkpoints, resume and the kill-switch demo", T-051).

The worker records each run in blackboard `runs` (`running` → `done`). On start it calls `resume_pending`: for every
run still `running`, the latest checkpoint whose pending messages belong to that run is restored with
`workflow.run(checkpoint_id=..., checkpoint_storage=storage, stream=True)`. Executors keep no in-flight state between
supersteps (every message carries its run envelope), so the checkpoint's messages are the whole run state; the
Director stamps `provenance.resumed_from_checkpoint` from `deps.state["resumed"]`.

`demo_log(line)` writes the four kill-switch lines to the `whyline.demo` logger and, when WHYLINE_DEMO_LOG is set,
appends them to that file, so the api, the supervisor and the worker share one ordered log.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

log = logging.getLogger("whyline.demo")


def demo_log(line: str) -> None:
    log.info(line)
    path = os.environ.get("WHYLINE_DEMO_LOG")
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')}.{int(time.time() * 1000) % 1000:03d} {line}\n")
            fh.flush()


def _run_ids(checkpoint) -> set[str]:
    out = set()
    for msgs in (checkpoint.messages or {}).values():
        for m in msgs:
            data = m.get("data") if isinstance(m, dict) else getattr(m, "data", None)
            run_id = data.get("run_id") if isinstance(data, dict) else getattr(data, "run_id", None)
            if run_id:
                out.add(run_id)
    return out


async def latest_checkpoint(storage, run_id: str, workflow_name: str = "newsroom"):
    """The newest checkpoint with a pending message of `run_id`, or None."""
    mine = [cp for cp in await storage.list_checkpoints(workflow_name=workflow_name) if run_id in _run_ids(cp)]
    return max(mine, key=lambda cp: (cp.timestamp, cp.iteration_count)) if mine else None


def mark_run(bb, msg, status: str, **extra) -> None:
    bb.put("runs", {"id": msg.run_id, "match_id": msg.moment.match_id, "moment_id": msg.moment.moment_id,
                    "status": status, "updated_at": time.time(), **extra})


async def resume_pending(deps, storage, run_moment_fn=None, on_result=None) -> list[str]:
    """Resume every run left `running`; returns the run ids resumed."""
    from newsroom.graph import WORKFLOW_NAME, build_workflow
    from newsroom.messages import Moment, MomentIn

    resumed = []
    for run in deps.bb.query("runs", status="running"):
        cp = await latest_checkpoint(storage, run["id"], WORKFLOW_NAME)
        if cp is None:
            deps.bb.put("runs", {**run, "status": "lost", "updated_at": time.time()})
            continue
        deps.state.setdefault("resumed", {})[run["id"]] = cp.checkpoint_id
        demo_log(f"resume run_id={run['id']} checkpoint_id={cp.checkpoint_id}")
        workflow = build_workflow(deps, storage=storage)
        outputs = []
        async for event in workflow.run(checkpoint_id=cp.checkpoint_id, checkpoint_storage=storage, stream=True):
            if event.type == "output":
                outputs.append(event.data)
        deps.bb.put("runs", {**run, "status": "done", "resumed_from_checkpoint": cp.checkpoint_id,
                             "updated_at": time.time()})
        resumed.append(run["id"])
        if on_result:
            moment = Moment.model_validate(deps.bb.get("moments", run["moment_id"], run["match_id"]))
            on_result(MomentIn(run_id=run["id"], moment=moment), {"outputs": outputs, "requests": [], "events": []})
    return resumed
