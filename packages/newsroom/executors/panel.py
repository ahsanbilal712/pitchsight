"""PanelExecutor: three pundits and a chair debate one high-leverage moment.

A sub-workflow built with `agent_framework.orchestrations.GroupChatBuilder` runs inside the executor: the three
pundits (press, possession, sceptic; role `panel_pundit`, gemini-3.8-flash live; `panel_pundit_golden`,
gemini-4-argon, in the golden precompute) are custom participant executors that
speak in a fixed order, one per round, with `max_rounds=3`. The chair (`panel_chair`, gemini-3.8-flash) closes
the debate with {consensus, dissent, headline}. Both go through the newsroom LLMClient, so replay serves them from
the cache and live calls go through SpendGuard.

Before the chat the executor resolves the evidence the pundits argue over: the decision point, the engine's
option probabilities, the best plausible alternative's counterfactual and its pitch-control snapshot (the same
path as the explained branch). Pundits may still call `simulate_counterfactual` and `get_pitch_control`
(max_tool_rounds 1). Every pundit claim must cite a cf_ or pc_ id and pass the Fact Checker; others are dropped.

Budget: 25 s for the whole panel. On timeout the panel cue is dropped (no retry).

Chair as manager: Agent Framework's agent-based orchestrator asks its manager for a structured next-speaker
decision every round (three more model calls inside the 25 s budget), so the speaking order is a selection
function and the chair manages the outcome: it alone writes what goes on screen.
"""

from __future__ import annotations

import asyncio
import json
import time

from agent_framework import Executor, Message, WorkflowContext, handler
from agent_framework.orchestrations import GroupChatBuilder, GroupChatRequestMessage, GroupChatState
from agent_framework_orchestrations._base_group_chat_orchestrator import (
    GroupChatParticipantMessage,
    GroupChatResponseMessage,
)

from newsroom import config
from newsroom.decision import attach_options, decision_point, proposer_rule
from newsroom.executors.base import Deps, NewsroomExecutor
from newsroom.executors.rollout import choose, simulate, timeout_s
from newsroom.executors.tactician import make_tools, to_claim
from newsroom.factcheck import verify_claims
from newsroom.llm import LLMError
from newsroom.messages import Draft, Envelope, Routed
from newsroom.templates import BODY_MAX, HEADLINE_MAX, clip

PUNDITS = ("press", "possession", "sceptic")
BUDGET_S = 25.0
MAX_ROUNDS = 3
PUNDIT_SCHEMA = {"type": "object", "required": ["take", "claims", "stance"], "properties": {
    "take": {"type": "string"}, "stance": {"type": "string", "enum": ["agree", "disagree", "nuance"]},
    "claims": {"type": "array", "items": {"type": "object", "required": ["text", "kind", "unit", "evidence_ids"],
                                          "properties": {
        "text": {"type": "string"}, "kind": {"type": "string", "enum": ["number", "tactical"]},
        "value_number": {"type": "number"}, "value_text": {"type": "string"}, "unit": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}}}}}}}
CHAIR_SCHEMA = {"type": "object", "required": ["consensus", "dissent", "headline"], "properties": {
    "consensus": {"type": "string"}, "dissent": {"type": "string"}, "headline": {"type": "string"}}}


def pundit_prompt(name: str) -> str:
    version, text = config.prompt(f"pundit_{name}@1")
    return text + (config.PROMPTS / "pundit_rules.md").read_text()


def panel_claims(match_id: str, raw: list, bb) -> list[dict]:
    """Pundit claims that cite a cf_ or pc_ id and pass the Fact Checker."""
    claims = [c for c in (to_claim(x) for x in raw if isinstance(x, dict)) if c]
    claims = [c for c in claims if any(i.startswith(("cf_", "pc_")) for i in c["evidence_ids"])]
    if not claims:
        return []
    return [c for c in verify_claims(match_id, claims, bb)["claims"] if c["verified"]]


class PunditExecutor(Executor):
    """A group-chat participant: hears the broadcast takes, speaks when the orchestrator asks."""

    def __init__(self, name: str, deps: Deps, env: Envelope, evidence: dict, spent: dict, takes: dict) -> None:
        self.name, self.deps, self.env, self.evidence, self.spent, self.takes = name, deps, env, evidence, spent, takes
        self.heard: list[Message] = []
        super().__init__(id=name)

    @handler
    async def hear(self, msg: GroupChatParticipantMessage, ctx: WorkflowContext) -> None:
        self.heard.extend(msg.messages)

    @handler
    async def speak(self, msg: GroupChatRequestMessage, ctx: WorkflowContext[GroupChatResponseMessage]) -> None:
        m = self.env.moment
        earlier = [{"pundit": x.author_name, "take": x.text} for x in self.heard if x.author_name in PUNDITS]
        user = {"EVIDENCE": self.evidence, "EARLIER_TAKES": earlier}
        trace: list = []
        tools = make_tools(self.deps, trace) if self.deps.rollout is not None else None
        tools = [t for t in tools or [] if t.name in config.role("panel_pundit").tools] or None
        take = {"take": "", "claims": [], "stance": "nuance"}
        try:
            res = await self.deps.llm.complete(
                "panel_pundit", [{"role": "system", "content": pundit_prompt(self.name)},
                                 {"role": "user", "content": json.dumps(user, separators=(",", ":"), default=str)}],
                tools, match_id=m.match_id, moment_id=m.moment_id, schema=PUNDIT_SCHEMA,
                prompt_version=f"pundit_{self.name}@1", producer="panel", attempt=1)
            body = res.get("json") if isinstance(res.get("json"), dict) else {}
            take = {"take": str(body.get("take", "")), "stance": body.get("stance", "nuance"),
                    "claims": panel_claims(m.match_id, body.get("claims", []), self.deps.bb)}
            for k in ("cost_usd", "tokens_in", "tokens_out"):
                self.spent[k] = self.spent.get(k, 0) + (res.get(k) or 0)
            self.spent.setdefault("pundit_s", []).append(res.get("latency_ms", 0) / 1000)
        except LLMError as exc:
            take["take"], take["error"] = "", str(exc)
        self.takes[self.name] = take
        out = Message("assistant", [json.dumps(take)], author_name=self.name)
        await ctx.send_message(GroupChatResponseMessage(message=out))


def speaking_order(state: GroupChatState) -> str:
    return PUNDITS[state.current_round % len(PUNDITS)]


async def resolve_evidence(deps: Deps, msg: Envelope) -> dict:
    """Decision point, best plausible counterfactual and its pitch-control snapshot (as the explained branch)."""
    m = msg.moment
    evidence: dict = {"moment": {k: getattr(m, k, None) for k in ("moment_id", "clock", "kind", "team", "players",
                                                                  "leverage", "evidence_event_ids")}}
    d = decision_point(deps.store, m) if deps.store is not None else None
    if d is None or deps.rollout is None:
        return evidence
    state = await deps.rollout.call("get_state", {"match_id": m.match_id, "t_ms": d["t_ms"]})
    d = attach_options(d, state.get("options") if isinstance(state, dict) else None)
    results = [(await simulate(deps.rollout, m.match_id, d["t_ms"], a, timeout_s()))[0] for a in proposer_rule(d)]
    cf = choose(results)
    evidence["decision"] = {k: d[k] for k in ("t_ms", "actor", "actor_name", "team", "actual")}
    if cf:
        evidence["counterfactual"] = {k: v for k, v in cf.items() if k != "futures_sample"}
        pc = await deps.rollout.call("get_pitch_control", {"match_id": m.match_id, "t_ms": cf["t_ms"]})
        if isinstance(pc, dict) and "snapshot_id" in pc:
            evidence["pitch_control"] = {k: v for k, v in pc.items() if k != "grid_path"}
    return evidence


LAST_TIMINGS: dict = {}   # stage timings of the latest panel run (also kept when it times out)


async def run_panel(deps: Deps, msg: Envelope) -> dict:
    """{takes, chair, claims, evidence, spent}; raises TimeoutError past BUDGET_S (the caller drops the cue)."""
    spent: dict = {}
    LAST_TIMINGS.clear()
    LAST_TIMINGS["spent"] = spent

    async def go() -> dict:
        t0 = time.perf_counter()
        evidence = await resolve_evidence(deps, msg)
        spent["timings"] = {"evidence_s": round(time.perf_counter() - t0, 2)}
        takes: dict = {}   # the orchestrator's output is a closing notice, not the conversation: pundits record here
        pundits = [PunditExecutor(n, deps, msg, evidence, spent, takes) for n in PUNDITS]
        chat = GroupChatBuilder(name="panel", participants=pundits, selection_func=speaking_order,
                                max_rounds=MAX_ROUNDS).build()
        start = Message("user", [json.dumps({"panel_on": evidence["moment"]}, default=str)])
        async for _event in chat.run([start], stream=True):
            pass
        spent["timings"]["pundits_s"] = round(time.perf_counter() - t0 - spent["timings"]["evidence_s"], 2)
        takes = {k: v for k, v in takes.items() if v.get("take")}
        claims = list({c["text"]: c for t in takes.values() for c in t.get("claims", [])}.values())
        m = msg.moment
        res = await deps.llm.complete(
            "panel_chair", [{"role": "system", "content": config.prompt("chair@1")[1]},
                            {"role": "user", "content": json.dumps({"TAKES": takes}, default=str)}],
            None, match_id=m.match_id, moment_id=m.moment_id, schema=CHAIR_SCHEMA, prompt_version="chair@1",
            producer="panel", attempt=1)
        for k in ("cost_usd", "tokens_in", "tokens_out"):
            spent[k] = spent.get(k, 0) + (res.get(k) or 0)
        chair = res.get("json") if isinstance(res.get("json"), dict) else {}
        spent["timings"]["total_s"] = round(time.perf_counter() - t0, 2)
        return {"takes": takes, "chair": chair, "claims": claims, "evidence": evidence, "spent": spent}

    budget = deps.state.get("panel_budget_s", BUDGET_S)   # None in the golden precompute: rounds are batches
    return await (go() if budget is None else asyncio.wait_for(go(), timeout=budget))


class PanelExecutor(NewsroomExecutor):
    @handler
    async def panel(self, msg: Routed, ctx: WorkflowContext[Draft]) -> None:
        started = time.perf_counter()
        if self.deps.llm is None or self.deps.state.get("degraded"):
            self.trace(msg.hop(self.id), started, status="dropped", reason="no model in this mode")
            return
        try:
            out = await run_panel(self.deps, msg)
        except TimeoutError:
            self.trace(msg.hop(self.id), started, status="timeout", reason=f"panel over {BUDGET_S:.0f} s: dropped")
            return
        except Exception as exc:  # any failure drops the panel cue, never the moment's other branches
            self.trace(msg.hop(self.id), started, status="error", reason=f"{type(exc).__name__}: {exc}")
            return
        chair = out["chair"]
        if not chair.get("headline") or not out["takes"]:
            self.trace(msg.hop(self.id), started, status="dropped", reason="no takes or no chair headline")
            return
        dissent = chair.get("dissent", "")
        body = chair.get("consensus", "") + ("" if dissent.lower() in ("", "none") else f" {dissent}")
        cf = out["evidence"].get("counterfactual")
        draft = Draft(**msg.hop(self.id).model_dump(), kind="sliding_doors", layer="options_card",
                      headline=clip(chair["headline"], HEADLINE_MAX), body=clip(body, BODY_MAX), why=body[:400],
                      claims=out["claims"], counterfactual=cf, model=config.role("panel_pundit").model,
                      prompt_version="chair@1", graphics={"players_highlight": []})
        self.trace(draft, started, status="ok", model=draft.model, cost_usd=out["spent"].get("cost_usd", 0.0),
                   tokens_in=out["spent"].get("tokens_in", 0), tokens_out=out["spent"].get("tokens_out", 0),
                   takes={k: v.get("stance") for k, v in out["takes"].items()})
        await ctx.send_message(draft)
