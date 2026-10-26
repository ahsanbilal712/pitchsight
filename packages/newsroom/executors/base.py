"""Shared executor plumbing: injected dependencies and trace rows (TECH_PLAN 1.3 `traces`)."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from agent_framework import Executor

from newsroom.messages import Envelope


def _null_publisher():
    from cloud.pubsub import NullCuePublisher

    return NullCuePublisher()


@dataclass
class Deps:
    """What executors need; the worker builds one per process. `llm` is CacheClient (replay) or LiveClient."""

    bb: Any                                   # blackboard.Blackboard
    llm: Any = None                           # newsroom.llm.LLMClient
    rollout: Any = None                       # tool client (newsroom.tools): MCP over HTTP, or in-process
    store: Any = None                         # mcp_server.tools_core.MatchStore: local match files
    guard: Any = None                         # api.spend.SpendGuard
    mode: str = "replay"
    panel_enabled: bool = False
    clock: Callable[[], float] = time.time
    state: dict = field(default_factory=dict)  # process-wide flags, e.g. {"degraded": True}
    publisher: Any = field(default_factory=lambda: _null_publisher())  # cloud cue fan-out (packages/cloud)


def trace_id_for(run_id: str) -> str:
    """Deterministic 16-hex trace id per run (same run, same id after a resume)."""
    return hashlib.sha256(run_id.encode()).hexdigest()[:16]


class NewsroomExecutor(Executor):
    """Executors keep no in-flight data between supersteps: every message carries its run envelope, so a
    checkpoint's pending messages are the whole run state and the checkpoint hooks save nothing (T-051)."""

    def __init__(self, id: str, deps: Deps) -> None:
        self.deps = deps
        super().__init__(id=id)

    async def on_checkpoint_save(self) -> dict:
        return {}

    async def on_checkpoint_restore(self, state: dict) -> None:
        return None

    def trace(self, msg: Envelope, started: float, *, status: str = "ok", model: str | None = None,
              tokens_in: int = 0, tokens_out: int = 0, cost_usd: float = 0.0, cache_hit: bool | None = None,
              **extra) -> None:
        """Write one trace row for this executor's step to the blackboard."""
        now = time.perf_counter()
        resumed = msg.resumed_from_checkpoint or self.deps.state.get("resumed", {}).get(msg.run_id)
        row = {"match_id": msg.moment.match_id, "run_id": msg.run_id, "moment_id": msg.moment.moment_id,
               "trace_id": msg.trace_id, "executor": self.id, "branch": msg.branch,
               "started_ms": int(self.deps.clock() * 1000), "latency_ms": int((now - started) * 1000),
               "model": model, "tokens_in": tokens_in, "tokens_out": tokens_out, "cost_usd": cost_usd,
               "cache_hit": cache_hit, "status": status, "checkpoint_id": resumed, **extra}
        self.deps.bb.put("traces", row)
