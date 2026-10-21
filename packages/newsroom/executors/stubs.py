"""Stub executors for graph branches built in later tickets (T-018). Each keeps the real executor's id,
input and output types, so swapping in the real one leaves the graph (and its checkpoint signature) unchanged.
Tests also use them directly, e.g. `StubFactCheck(verdict=lambda d: False)` for the rewrite loop.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Never

from agent_framework import WorkflowContext, handler

from newsroom.executors.base import Deps, NewsroomExecutor
from newsroom.messages import CueOut, Draft, Explained, MomentIn, Proposals, RolloutDone, Routed


def stub_branches(msg: MomentIn) -> list[str]:
    """Routing used until the real Scout (T-029): an explicit `branches` list on the moment, else fast/explained."""
    explicit = getattr(msg.moment, "branches", None)
    if explicit:
        return list(explicit)
    return ["fast"] if msg.moment.fast else ["explained"]


class StubScout(NewsroomExecutor):
    @handler
    async def scout(self, msg: MomentIn, ctx: WorkflowContext[Routed]) -> None:
        started = time.perf_counter()
        for branch in stub_branches(msg):
            out = Routed(**msg.hop(self.id).model_dump(exclude={"branch"}), branch=branch)
            self.trace(out, started)
            await ctx.send_message(out)


class StubProposer(NewsroomExecutor):
    @handler
    async def propose(self, msg: Routed, ctx: WorkflowContext[Proposals]) -> None:
        await ctx.send_message(Proposals(**msg.hop(self.id).model_dump(), alternatives=[]))


class StubRollout(NewsroomExecutor):
    @handler
    async def roll(self, msg: Proposals, ctx: WorkflowContext[RolloutDone]) -> None:
        await ctx.send_message(RolloutDone(**msg.hop(self.id).model_dump(), counterfactual=None))


class StubTactician(NewsroomExecutor):
    @handler
    async def explain(self, msg: RolloutDone, ctx: WorkflowContext[Explained]) -> None:
        m = msg.moment
        explanation = {"why": f"{m.kind.replace('_', ' ').capitalize()} at {m.clock}.", "claims": []}
        base = msg.hop(self.id).model_dump(exclude={"alternatives", "counterfactual"})
        await ctx.send_message(Explained(**base, explanation=explanation, counterfactual=msg.counterfactual))


class StubNarrator(NewsroomExecutor):
    @handler
    async def narrate(self, msg: Explained, ctx: WorkflowContext[Draft]) -> None:
        exp = msg.explanation
        await ctx.send_message(Draft(**msg.hop(self.id).model_dump(exclude={"explanation", "counterfactual"}),
                                     kind="sliding_doors", headline=msg.moment.kind.replace("_", " ").title(),
                                     body=exp.get("why", ""), why=exp.get("why", ""), claims=exp.get("claims", []),
                                     explanation=exp, counterfactual=msg.counterfactual))

    @handler
    async def rewrite(self, msg: Draft, ctx: WorkflowContext[Draft]) -> None:
        await ctx.send_message(msg.hop(self.id, attempt=msg.attempt + 1, checked=False))


class StubFastLine(NewsroomExecutor):
    @handler
    async def line(self, msg: Routed, ctx: WorkflowContext[Draft]) -> None:
        m = msg.moment
        await ctx.send_message(Draft(**msg.hop(self.id).model_dump(), kind="fast_line",
                                     headline=m.kind.replace("_", " ").title(), body="", status="template"))


class StubFactCheck(NewsroomExecutor):
    def __init__(self, id: str, deps: Deps, verdict: Callable[[Draft], bool] = lambda d: True) -> None:
        self.verdict = verdict
        super().__init__(id, deps)

    @handler
    async def check(self, msg: Draft, ctx: WorkflowContext[Draft]) -> None:
        ok = bool(self.verdict(msg))
        diff = [] if ok else [{"claim": None, "reject_reason": "stub_reject"}]
        await ctx.send_message(msg.hop(self.id, verified=ok, checked=True, diff=diff))


class StubPanel(NewsroomExecutor):
    @handler
    async def panel(self, msg: Routed, ctx: WorkflowContext[Draft]) -> None:
        await ctx.send_message(Draft(**msg.hop(self.id).model_dump(), kind="sliding_doors", headline="Panel"))


class StubFourthOfficial(NewsroomExecutor):
    @handler
    async def rule(self, msg: Routed, ctx: WorkflowContext[Draft]) -> None:
        await ctx.send_message(Draft(**msg.hop(self.id).model_dump(), kind="fourth_official", layer="referee_line",
                                     headline="Fourth Official", verified=True, checked=True))


class StubRecap(NewsroomExecutor):
    @handler
    async def recap(self, msg: Routed, ctx: WorkflowContext[Draft]) -> None:
        await ctx.send_message(Draft(**msg.hop(self.id).model_dump(), kind="recap", layer="recap_card",
                                     headline="Half-time recap"))


class StubDirector(NewsroomExecutor):
    @handler
    async def direct(self, msg: Draft, ctx: WorkflowContext[CueOut]) -> None:
        m = msg.moment
        cue = {"match_id": m.match_id, "moment_id": m.moment_id, "t_in_ms": m.t_ms, "t_out_ms": m.t_ms + 8000,
               "kind": msg.kind, "layer": msg.layer, "text": {"headline": msg.headline, "body": msg.body},
               "verified": msg.verified, "attempt": msg.attempt}
        out = msg.hop(self.id)
        await ctx.send_message(CueOut(**out.model_dump(include=set(CueOut.model_fields) - {"cue"}), cue=cue))


class StubCueBus(NewsroomExecutor):
    @handler
    async def publish(self, msg: CueOut, ctx: WorkflowContext[Never, dict]) -> None:
        cue = {**msg.cue, "agent_path": [*msg.agent_path, self.id]}
        cue_id = self.deps.bb.put("cues", cue)
        await ctx.yield_output({**cue, "cue_id": cue_id})
