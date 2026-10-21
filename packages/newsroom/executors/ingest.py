"""IngestExecutor: start of every run; takes the moment from the worker and hands it to the Scout."""

from __future__ import annotations

import time

from agent_framework import WorkflowContext, handler

from newsroom.executors.base import NewsroomExecutor
from newsroom.messages import MomentIn


class IngestExecutor(NewsroomExecutor):
    @handler
    async def ingest(self, msg: MomentIn, ctx: WorkflowContext[MomentIn]) -> None:
        started = time.perf_counter()
        out = msg.hop(self.id)
        self.trace(out, started)
        await ctx.send_message(out)
