"""DropExecutor: the switch-case default; records that the moment produced no cue."""

from __future__ import annotations

import time

from agent_framework import WorkflowContext, handler

from newsroom.executors.base import NewsroomExecutor
from newsroom.messages import Routed


class DropExecutor(NewsroomExecutor):
    @handler
    async def drop(self, msg: Routed, ctx: WorkflowContext) -> None:
        self.trace(msg.hop(self.id), time.perf_counter(), status="dropped")
