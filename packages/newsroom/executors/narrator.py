"""NarratorExecutor: one lower-third from verified claims only (TECH_PLAN 1.7, T-020).

Role `narrator_fast` (gemini-3.8-flash since ADR-004 Revision 1), prompt `narrator@2`, timeout 4 s with one retry.
Fallback chain: model -> retry once (a provider error, or the role's `provider_fallback` role if one is configured)
-> deterministic template on timeout, second failure, cache miss or spend cap. Rewrites receive the Fact Checker's
`diff` and the previous draft.
"""

from __future__ import annotations

import json
import time

from agent_framework import WorkflowContext, handler

from newsroom import config
from newsroom.executors.base import Deps, NewsroomExecutor
from newsroom.factcheck import verify_claims
from newsroom.llm import CacheMiss, LLMTimeout, load_fewshot
from newsroom.messages import Draft, Envelope, Explained
from newsroom.templates import BODY_MAX, HEADLINE_MAX, clip, template_line

ROLE = "narrator_fast"
PROMPT = "narrator@2"
FEWSHOT_MAX = 4          # examples in a live prompt: each one costs input tokens on every call
SCHEMA = {"type": "object", "required": ["headline", "body", "claims"],
          "properties": {"headline": {"type": "string"}, "body": {"type": "string"},
                         "claims": {"type": "array", "items": {"type": "string"}}}}
CUE_KINDS = {"sliding_doors", "state_change", "big_chance", "goal", "tempo_shift", "player_tag", "milestone",
             "pressing_trap", "fourth_official", "oracle", "dugout", "decision_index", "recap", "fast_line"}


def build_messages(kind: str, claims: list[dict], diff: list[dict] | None = None,
                   previous: dict | None = None) -> list[dict]:
    _, system = config.prompt(PROMPT)
    # few-shots belong to the prompt version after the hand review (T-057): narrator@2 made the golden cache
    # without them, so loading them under the same version would change a cached prompt silently
    shots = [] if PROMPT == "narrator@2" else load_fewshot(config.PROMPTS / "fewshot" / "narrator.jsonl")[:FEWSHOT_MAX]
    msgs = [{"role": "system", "content": system}]
    for shot in shots:
        msgs.append({"role": "user", "content": json.dumps(shot["input"])})
        msgs.append({"role": "assistant", "content": json.dumps(shot["output"])})
    payload = {"moment_kind": kind,
               "CLAIMS": [{"text": c["text"], "kind": c["kind"], "unit": c.get("unit")} for c in claims]}
    if diff:
        payload["REWRITE"] = {"previous": previous or {}, "rejected": diff}
    msgs.append({"role": "user", "content": json.dumps(payload)})
    return msgs


async def write_line(deps: Deps, msg: Envelope, kind: str, claims: list[dict], diff: list[dict] | None = None,
                     previous: dict | None = None, attempt: int = 1, producer: str = "narrator") -> dict:
    """{headline, body, claims, model, status, prompt_version, cache_key}; never raises."""
    verified = [c for c in claims if c.get("verified")]
    fallback = {**template_line(kind, verified), "model": "template", "prompt_version": PROMPT, "cache_key": None}
    if deps.llm is None or deps.state.get("degraded"):
        return {**fallback, "status": "template"}
    role = config.role(ROLE)
    roles = [ROLE, role.extra.get("provider_fallback", ROLE)]  # one retry
    ctx = {"match_id": msg.moment.match_id, "moment_id": msg.moment.moment_id, "schema": SCHEMA,
           "prompt_version": PROMPT, "attempt": attempt, "timeout_s": role.timeout_s, "producer": producer}
    messages = build_messages(kind, verified, diff, previous)
    status, reason = "template", None
    for name in roles:
        try:
            res = await deps.llm.complete(name, messages, None, **ctx)
        except CacheMiss as exc:
            return {**fallback, "status": "cache_miss", "reason": f"{name}: {exc}"}
        except LLMTimeout as exc:
            return {**fallback, "status": "timeout", "reason": f"{name}: {exc}"}
        except Exception as exc:  # LLMError, SpendCapReached, anything unexpected: template (degraded on SpendCap)
            if type(exc).__name__ == "SpendCapReached":
                deps.state["degraded"] = True
                return {**fallback, "status": "degraded", "reason": str(exc)}
            status, reason = "error", f"{name}: {type(exc).__name__}: {exc}"[:300]
            continue
        out = res.get("json") if isinstance(res.get("json"), dict) else None
        if not out or not isinstance(out.get("headline"), str) or not isinstance(out.get("body"), str):
            status, reason = "error", f"{name}: invalid_json (no headline/body)"
            continue
        by_text = {c["text"]: c for c in verified}
        used = [by_text[t] for t in out.get("claims", []) if isinstance(t, str) and t in by_text]
        used += [c for c in verified if c not in used and (c["text"] in out["headline"] or c["text"] in out["body"])]
        return {"headline": clip(out["headline"], HEADLINE_MAX), "body": clip(out["body"], BODY_MAX),
                "claims": used, "model": res.get("model"), "status": "ok", "prompt_version": PROMPT,
                "cache_key": res.get("cache_key"), "cost_usd": res.get("cost_usd", 0.0),
                "tokens_in": res.get("tokens_in", 0), "tokens_out": res.get("tokens_out", 0),
                "cache_hit": res.get("cache_hit")}
    return {**fallback, "status": status, "reason": reason}


def draft_kind(moment_kind: str, comparison: dict | None) -> str:
    """A comparison of the real choice with an alternative (a counterfactual, or a real clip's goal-in-10s or xG
    decision) is a Sliding Doors cue."""
    if comparison:
        return "sliding_doors"
    return moment_kind if moment_kind in CUE_KINDS else "fast_line"


class NarratorExecutor(NewsroomExecutor):
    async def _emit(self, ctx, out: Draft, line: dict, started: float) -> None:
        self.trace(out, started, status=line["status"], model=line.get("model"),
                   tokens_in=line.get("tokens_in", 0), tokens_out=line.get("tokens_out", 0),
                   cost_usd=line.get("cost_usd", 0.0), cache_hit=line.get("cache_hit"), attempt=out.attempt,
                   reason=line.get("reason"))
        await ctx.send_message(out)

    @handler
    async def narrate(self, msg: Explained, ctx: WorkflowContext[Draft]) -> None:
        started = time.perf_counter()
        exp = msg.explanation
        checked = [c for c in verify_claims(msg.moment.match_id, exp.get("claims", []), self.deps.bb)["claims"]
                   if c["verified"]]  # the Narrator only ever sees verified claims
        kind = draft_kind(msg.moment.kind, msg.counterfactual or getattr(msg.moment, "goal_in_10s", None)
                          or getattr(msg.moment, "xg_decision", None))
        line = await write_line(self.deps, msg, kind, checked, attempt=1)
        base = msg.hop(self.id).model_dump(exclude={"explanation", "counterfactual"})
        out = Draft(**base, kind=kind, headline=line["headline"], body=line["body"], why=exp.get("why", ""),
                    claims=checked, explanation=exp, counterfactual=msg.counterfactual, attempt=1,
                    model=line.get("model"), prompt_version=line["prompt_version"], cache_key=line.get("cache_key"),
                    status=line["status"], reason=line.get("reason"))
        await self._emit(ctx, out, line, started)

    @handler
    async def rewrite(self, msg: Draft, ctx: WorkflowContext[Draft]) -> None:
        started = time.perf_counter()
        attempt = msg.attempt + 1
        previous = {"headline": msg.headline, "body": msg.body}
        line = await write_line(self.deps, msg, msg.kind, msg.claims, msg.diff, previous, attempt=attempt)
        why = msg.why
        if any(d.get("where") == "why" for d in msg.diff):
            why = ""  # the Tactician's why carried the rejected content; the drawer falls back to the body
        out = msg.hop(self.id, headline=line["headline"], body=line["body"], why=why, attempt=attempt,
                      checked=False, verified=False, model=line.get("model"), status=line["status"],
                      reason=line.get("reason"), cache_key=line.get("cache_key"))
        await self._emit(ctx, out, line, started)
