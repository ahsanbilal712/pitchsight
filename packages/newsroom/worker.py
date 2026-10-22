"""Newsroom worker: watch blackboard `moments`, one workflow run per moment (TECH_PLAN 1.1, 1.7).

    python -m newsroom.worker [--match m_4242] [--mode replay|live]

Checkpoints go to FileCheckpointStorage(WHYLINE_CHECKPOINT_DIR). Resume after a kill is T-051 (supervisor).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os

from agent_framework import FileCheckpointStorage

from newsroom import config
from newsroom.executors.base import Deps, trace_id_for
from newsroom.graph import build_workflow
from newsroom.messages import Moment, MomentIn

log = logging.getLogger("whyline.newsroom")


def run_id_for(moment: Moment) -> str:
    """Deterministic: the same moment gets the same run id in every run of the seed."""
    return f"run_{moment.match_id}_{moment.moment_id}"


def start_message(moment: dict | Moment, mode: str = "replay") -> MomentIn:
    m = moment if isinstance(moment, Moment) else Moment.model_validate(moment)
    run_id = run_id_for(m)
    return MomentIn(run_id=run_id, mode=mode, moment=m, trace_id=trace_id_for(run_id))


async def run_moment(workflow, msg: MomentIn) -> dict:
    """Run one moment to completion. Returns {outputs, requests, events} (requests = pending request_info)."""
    outputs, requests, kinds = [], [], []
    async for event in workflow.run(msg, stream=True):
        kinds.append(event.type)
        if event.type == "output":
            outputs.append(event.data)
        elif event.type == "request_info":
            requests.append(event)
        elif event.type == "failed":
            log.error("run %s failed: %s", msg.run_id, getattr(event, "details", None))
    return {"outputs": outputs, "requests": requests, "events": kinds}


def make_storage() -> FileCheckpointStorage:
    return FileCheckpointStorage(config.checkpoint_dir())


def make_deps(mode: str) -> Deps:
    """Replay mode injects cache.CacheClient as both LLM client and tool client (cache hits, misses raise or
    return cache_miss); live mode injects LiveClient and the MCP tools (TECH_PLAN 1.8)."""
    from blackboard import SqliteBlackboard
    from mcp_server.tools_core import MatchStore
    from newsroom.tools import LocalTools, McpTools

    bb = SqliteBlackboard()
    store = MatchStore(bb)
    url = os.environ.get("WHYLINE_MCP_URL")
    tools = McpTools(url) if url else LocalTools(store)   # agents' data path is MCP; in-process is the dev default
    # the Panel fits its 25 s budget live on Flash pundits (20.6 s measured, T-041); WHYLINE_PANEL=0 turns it off
    panel = os.environ.get("WHYLINE_PANEL", "1") != "0"
    if mode == "live":
        from newsroom.llm import LiveClient

        return Deps(bb=bb, llm=LiveClient(mode="live"), mode=mode, store=store, rollout=tools, panel_enabled=panel)
    from cache import CacheClient
    from cache.client import preload_evidence

    cache = CacheClient(inner_tools=tools)
    log.info("replay evidence preloaded: %d documents", preload_evidence(bb, cache.manifest, store))
    return Deps(bb=bb, llm=cache, mode=mode, store=store, rollout=cache, panel_enabled=panel)


async def serve(deps: Deps, storage=None, match_id: str | None = None, stop: asyncio.Event | None = None,
                on_result=None) -> None:
    """Resume runs a kill interrupted (T-051), then watch `moments` and run each new one. A moment is marked
    `running` before its run and `done` after; the run itself is tracked in blackboard `runs`."""
    from newsroom.resume import mark_run, resume_pending

    workflow = build_workflow(deps, storage=storage)
    if hasattr(deps.llm, "warm"):
        warmed = set()
        for role_name in ("narrator_fast", "tactician_live"):   # one per model: the cold first call is ~5-10 s
            model = config.role(role_name).model
            if model not in warmed:
                warmed.add(model)
                log.info("warm-up %s %.2f s", role_name, await deps.llm.warm(role_name))
    if storage is not None:
        await resume_pending(deps, storage, on_result=on_result)
    log.info("worker ready mode=%s", deps.mode)
    seen: set[str] = set()
    stop = stop or asyncio.Event()
    seq = 0
    pending: list[dict] = []
    while not stop.is_set():
        # poll the blackboard sequence (the same mechanism as bb.watch); a wait_for around an async generator's
        # __anext__ would close the generator on its first timeout and end the loop
        if not pending:
            batch = deps.bb.changes_since("moments", seq, match_id)
            if not batch:
                await asyncio.sleep(0.05)
                continue
            seq = batch[-1][0]
            pending = [doc for _, doc in batch]
        doc = pending.pop(0)
        key = f"{doc.get('match_id')}/{doc.get('moment_id')}"
        if key in seen or doc.get("status", "new") != "new":
            continue
        seen.add(key)
        msg = start_message(doc, deps.mode)
        log.info("run %s moment %s", msg.run_id, msg.moment.moment_id)
        deps.bb.put("moments", {**doc, "status": "running"})
        mark_run(deps.bb, msg, "running")
        result = await run_moment(workflow, msg)
        mark_run(deps.bb, msg, "done", cues=[c.get("cue_id") for c in result["outputs"] if isinstance(c, dict)])
        deps.bb.put("moments", {**doc, "status": "done"})
        if on_result:
            on_result(msg, result)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--match", default=None)
    parser.add_argument("--mode", default=config.mode())
    args = parser.parse_args()
    logging.basicConfig(level=os.environ.get("WHYLINE_LOG", "INFO"),
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    asyncio.run(serve(make_deps(args.mode), storage=make_storage(), match_id=args.match))


if __name__ == "__main__":
    main()
