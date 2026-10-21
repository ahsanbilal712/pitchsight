"""FactCheckExecutor: runs the eight deterministic rules on a draft (TECH_PLAN 1.7, T-019)."""

from __future__ import annotations

import time

from agent_framework import WorkflowContext, handler

from newsroom.executors.base import NewsroomExecutor
from newsroom.factcheck import verify_claims
from newsroom.messages import Draft


class FactCheckExecutor(NewsroomExecutor):
    @handler
    async def check(self, msg: Draft, ctx: WorkflowContext[Draft]) -> None:
        started = time.perf_counter()
        result = verify_claims(msg.moment.match_id, msg.claims, self.deps.bb,
                               text={"why": msg.why, "headline": msg.headline, "body": msg.body})
        out = msg.hop(self.id, verified=result["verified"], claims=result["claims"], diff=result["diff"],
                      checked=True)
        self.trace(out, started, status="verified" if result["verified"] else "rejected", attempt=msg.attempt,
                   rejects=len(result["diff"]))
        await ctx.send_message(out)
