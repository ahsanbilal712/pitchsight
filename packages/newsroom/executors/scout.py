"""ScoutExecutor: classifies a moment and emits one message per branch it takes (TECH_PLAN 1.7, T-029).

Detection itself (engine events, auto-events, GoalIn8sHead leverage, chaos states) is in `newsroom.scout_rules`;
moments arrive here from blackboard `moments`. Multiple Case matches do not fan out in Agent Framework, so the Scout
sends one Routed message per matching branch; a moment that matches none goes to the drop branch.
"""

from __future__ import annotations

import time

from agent_framework import WorkflowContext, handler

from newsroom.executors.base import NewsroomExecutor
from newsroom.messages import MomentIn, Routed
from newsroom.scout_rules import branches


class ScoutExecutor(NewsroomExecutor):
    @handler
    async def scout(self, msg: MomentIn, ctx: WorkflowContext[Routed]) -> None:
        started = time.perf_counter()
        routes = branches(msg.moment, self.deps.panel_enabled) or ["drop"]
        base = msg.hop(self.id).model_dump(exclude={"branch"})
        for branch in routes:
            out = Routed(**base, branch=branch)
            self.trace(out, started, status="routed")
            await ctx.send_message(out)
