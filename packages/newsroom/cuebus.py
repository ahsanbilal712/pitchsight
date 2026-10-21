"""CueBus: the last node of every run. Puts the cue into blackboard `cues` (the api watches that collection,
T-033) and yields it as the workflow output (TECH_PLAN 1.7, T-021)."""

from __future__ import annotations

import logging
import time
from typing import Never

from agent_framework import WorkflowContext, handler

from newsroom.executors.base import NewsroomExecutor
from newsroom.messages import CueOut
from newsroom.resume import demo_log

log = logging.getLogger("whyline.newsroom")


class CueBus(NewsroomExecutor):
    @handler
    async def publish(self, msg: CueOut, ctx: WorkflowContext[Never, dict]) -> None:
        started = time.perf_counter()
        cue = msg.cue
        self.deps.bb.put("cues", cue)
        self.trace(msg.hop(self.id), started, status="delivered", cue_id=cue["cue_id"])
        resumed = cue["provenance"].get("resumed_from_checkpoint")
        if resumed:
            demo_log(f"cue {cue['cue_id']} delivered resumed_from_checkpoint={resumed}")
        else:
            log.info("cue %s delivered", cue["cue_id"])
        await ctx.yield_output(cue)
