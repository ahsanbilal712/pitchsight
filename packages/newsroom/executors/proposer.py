"""ProposerExecutor: up to three alternatives for the moment's on-ball decision (TECH_PLAN 1.7, T-031).

Role `proposer` (gemini-3.8-flash since ADR-004 Revision 1), prompt `proposer@1`, inline JSON, timeout 6 s with one
retry, then `proposer_rule` (passes to the three team-mates with the highest xT gain). The decision point comes
from local match data (newsroom.decision) plus the engine's option probabilities from MCP get_state; a moment
with no on-ball decision gets no alternatives.
"""

from __future__ import annotations

import asyncio
import json
import time

from agent_framework import WorkflowContext, handler

from newsroom import config
from newsroom.decision import attach_options, decision_point, proposer_rule, valid_alternatives
from newsroom.executors.base import Deps, NewsroomExecutor
from newsroom.llm import CacheMiss, LLMError
from newsroom.messages import Envelope, Proposals, Routed

ROLE, PROMPT = "proposer", "proposer@1"
# Gemini's schema converter takes one type per field, so target is a string ("" when there is none)
SCHEMA = {"type": "object", "required": ["alternatives"], "properties": {"alternatives": {
    "type": "array", "items": {"type": "object", "required": ["kind", "actor", "target", "reason"], "properties": {
        "kind": {"type": "string"}, "actor": {"type": "string"}, "target": {"type": "string"},
        "reason": {"type": "string"}}}}}}


def build_messages(decision: dict, moment_kind: str) -> list[dict]:
    _, system = config.prompt(PROMPT)
    view = {k: decision.get(k) for k in ("actor", "actor_name", "team", "actual", "ball", "options", "teammates")}
    return [{"role": "system", "content": system},
            {"role": "user", "content": json.dumps({"moment_kind": moment_kind, "DECISION": view})}]


async def propose(deps: Deps, msg: Envelope, decision: dict) -> tuple[list[dict], dict]:
    """(alternatives, call info); never raises. Model -> one retry -> rule."""
    rule = proposer_rule(decision)
    if deps.llm is None or deps.state.get("degraded"):
        return rule, {"status": "rule", "model": "proposer_rule"}
    role = config.role(ROLE)
    ctx = {"match_id": msg.moment.match_id, "moment_id": msg.moment.moment_id, "schema": SCHEMA,
           "prompt_version": PROMPT, "timeout_s": role.timeout_s, "producer": "proposer"}
    messages = build_messages(decision, msg.moment.kind)
    status = "rule"
    for _attempt in range(2):
        try:
            res = await deps.llm.complete(ROLE, messages, None, **ctx)
        except CacheMiss:
            return rule, {"status": "cache_miss", "model": "proposer_rule"}
        except LLMError:
            status = "error"
            continue
        except Exception as exc:
            if type(exc).__name__ == "SpendCapReached":
                deps.state["degraded"] = True
                return rule, {"status": "degraded", "model": "proposer_rule"}
            status = "error"
            continue
        out = res.get("json") if isinstance(res.get("json"), dict) else {}
        alts = valid_alternatives(decision, out.get("alternatives"))
        if alts:
            return alts, {"status": "ok", "model": res.get("model"), "cost_usd": res.get("cost_usd", 0.0),
                          "tokens_in": res.get("tokens_in", 0), "tokens_out": res.get("tokens_out", 0),
                          "cache_hit": res.get("cache_hit")}
        status = "invalid_output"
    return rule, {"status": status, "model": "proposer_rule"}


class ProposerExecutor(NewsroomExecutor):
    def prefetch(self, msg: Envelope, decision: dict) -> None:
        """Live mode: start the rule alternatives' rollouts while the model proposes. The MCP tool stores each
        result, so the RolloutExecutor gets them back at once when the model proposes the same alternatives
        (it usually does); different ones are simulated then as before."""
        if self.deps.rollout is None or self.deps.mode == "replay":
            return
        from newsroom.executors.rollout import simulate, timeout_s

        tasks = self.deps.state.setdefault("prefetch", set())
        for alt in proposer_rule(decision):
            task = asyncio.create_task(simulate(self.deps.rollout, msg.moment.match_id, decision["t_ms"], alt,
                                                timeout_s()))
            tasks.add(task)
            task.add_done_callback(tasks.discard)

    @handler
    async def propose(self, msg: Routed, ctx: WorkflowContext[Proposals]) -> None:
        started = time.perf_counter()
        decision = decision_point(self.deps.store, msg.moment) if self.deps.store is not None else None
        if decision is not None and self.deps.rollout is not None:
            state = await self.deps.rollout.call("get_state", {"match_id": msg.moment.match_id,
                                                               "t_ms": decision["t_ms"]})
            decision = attach_options(decision, state.get("options") if isinstance(state, dict) else None)
        if decision is None:
            alts, info = [], {"status": "no_decision", "model": None}
        else:
            self.prefetch(msg, decision)
            alts, info = await propose(self.deps, msg, decision)
        out = Proposals(**msg.hop(self.id).model_dump(), alternatives=alts, decision=decision)
        self.trace(out, started, status=info["status"], model=info.get("model"), cost_usd=info.get("cost_usd", 0.0),
                   tokens_in=info.get("tokens_in", 0), tokens_out=info.get("tokens_out", 0),
                   cache_hit=info.get("cache_hit"), alternatives=len(alts))
        await ctx.send_message(out)
