"""RecapExecutor: the half-time and full-time recap card (TECH_PLAN 1.7 Recap row, T-050).

Role `recap_live` (gemini-4-argon; the golden precompute uses `recap`, the batch role), prompt `recap@2`, MCP tools
`top_moments` and `timeline` plus `player_stats` for the half's most involved players, resolved by the executor
before one structured call (45 s). Output {headline, body, claims, cards}; the Fact Checker checks it like any
draft and the Director holds it for the producer (approve / veto, `ctx.request_info`). Fallback: a template card.
"""

from __future__ import annotations

import json
import time
from collections import Counter

from agent_framework import WorkflowContext, handler

from newsroom import config
from newsroom.executors.base import NewsroomExecutor
from newsroom.executors.tactician import KINDS, to_claim
from newsroom.factcheck import league_data, verify_claims
from newsroom.llm import CacheMiss, LLMError
from newsroom.messages import Draft, Routed
from newsroom.templates import BODY_MAX, HEADLINE_MAX, clip, template_line

ROLE, PROMPT = "recap_live", "recap@2"
SCHEMA = {"type": "object", "required": ["headline", "body", "claims", "cards"], "properties": {
    "headline": {"type": "string"}, "body": {"type": "string"},
    "cards": {"type": "array", "items": {"type": "object", "required": ["title", "text"], "properties": {
        "title": {"type": "string"}, "text": {"type": "string"}}}},
    "claims": {"type": "array", "items": {"type": "object", "required": ["text", "kind", "unit", "evidence_ids"],
                                          "properties": {
        "text": {"type": "string"}, "kind": {"type": "string", "enum": KINDS}, "value_number": {"type": "number"},
        "value_text": {"type": "string"}, "unit": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}}}}}}}


async def gather(deps, match_id: str, period: int) -> dict:
    """The recap's inputs through the tool client (recorded in the golden precompute, cached in replay)."""
    tools = deps.rollout
    top = await tools.call("top_moments", {"match_id": match_id, "period": period, "k": 3})
    top = top if isinstance(top, list) and not (top and "error" in top[0]) else []
    for m in top:
        cfs = deps.bb.query("counterfactuals", match_id=match_id, moment_id=m["moment_id"])
        if cfs:
            cf = cfs[-1]
            m["counterfactual"] = {k: cf[k] for k in ("counterfactual_id", "actual", "alternative", "baseline",
                                                      "alternative_outcome", "delta_win_prob_home")}
    tl = await tools.call("timeline", {"match_id": match_id})
    series = [r for r in (tl.get("series", []) if isinstance(tl, dict) else []) if r["period"] == period]
    goals = [g for g in (tl.get("goals", []) if isinstance(tl, dict) else [])
             if (g["t_ms"] < 2_700_000) == (period == 1)]
    states = Counter(r["state"] for r in series if r.get("state"))
    involved = Counter(p for m in top for p in m.get("players", []))
    stats = []
    for pid, _ in involved.most_common(2):
        s = await tools.call("player_stats", {"match_id": match_id, "player_id": pid})
        if isinstance(s, dict) and "error" not in s:
            stats.append({k: s.get(k) for k in ("player_id", "name", "club", "position", "passes", "completion",
                                                "shots", "xt", "evidence_event_ids")})
    players, clubs = league_data()
    meta = next(iter(deps.bb.query("events", match_id=match_id, type="match_metadata", limit=1)), {}).get("attrs", {})
    teams = {side: {"club_id": meta.get(side), "name": clubs.get(meta.get(side), {}).get("short_name")}
             for side in ("home", "away")}

    def who(pid):
        p = players.get(pid, {})
        return {"player_id": pid, "name": p.get("name"), "surname": (p.get("name") or "").split()[-1] or None,
                "club": p.get("club")}

    for g in goals:
        g["scorer"] = who(g.get("player"))
        g["club"] = teams.get(g.get("team"), {}).get("name")
    for m in top:
        m["player_names"] = [who(p) for p in m.get("players", [])]
    return {"PERIOD": period, "TEAMS": teams, "GOALS": goals, "TOP_MOMENTS": top,
            "TIMELINE": {"states_every_30s": dict(states), "chaotic_spells": [r["clock"] for r in series
                                                                             if r.get("state") == "Chaotic"][:20]},
            "PLAYER_STATS": stats}


class RecapExecutor(NewsroomExecutor):
    @handler
    async def recap(self, msg: Routed, ctx: WorkflowContext[Draft]) -> None:
        started = time.perf_counter()
        m = msg.moment
        period = int(m.period or 1)
        status, model, body, claims, cards, info = "template", "template", None, [], [], {}
        if self.deps.llm is not None and self.deps.rollout is not None and not self.deps.state.get("degraded"):
            inputs = await gather(self.deps, m.match_id, period)
            messages = [{"role": "system", "content": config.prompt(PROMPT)[1]},
                        {"role": "user", "content": json.dumps(inputs, separators=(",", ":"), default=str)}]
            for _attempt in range(2):
                try:
                    res = await self.deps.llm.complete(ROLE, messages, None, match_id=m.match_id,
                                                       moment_id=m.moment_id, schema=SCHEMA, prompt_version=PROMPT,
                                                       producer="recap", attempt=1)
                except CacheMiss:
                    status = "cache_miss"
                    break
                except LLMError:
                    status = "error"
                    continue
                out = res.get("json") if isinstance(res.get("json"), dict) else {}
                claims = [c for c in (to_claim(x) for x in out.get("claims", []) if isinstance(x, dict)) if c]
                if out.get("headline") and out.get("body"):
                    body, cards, model, status = out, out.get("cards") or [], res.get("model"), "ok"
                    info = {k: res.get(k, 0) for k in ("cost_usd", "tokens_in", "tokens_out")}
                    break
                status = "invalid_output"
        if body is None:   # template card from whatever verified claims there are (none: a plain card)
            checked = [c for c in verify_claims(m.match_id, claims, self.deps.bb)["claims"] if c["verified"]]
            t = template_line("recap", checked)
            body, claims = {"headline": "Half-time recap" if period == 1 else "Full-time recap",
                            "body": t["body"]}, t["claims"]
        draft = Draft(**msg.hop(self.id).model_dump(), kind="recap", layer="recap_card",
                      headline=clip(body["headline"], HEADLINE_MAX), body=clip(body["body"], BODY_MAX),
                      why=body["body"][:400], claims=claims, explanation={"cards": cards}, model=model,
                      prompt_version=PROMPT, status=status if status != "ok" else "ok")
        self.trace(draft, started, status=status, model=model, cost_usd=info.get("cost_usd", 0.0),
                   tokens_in=info.get("tokens_in", 0), tokens_out=info.get("tokens_out", 0), cards=len(cards))
        await ctx.send_message(draft)
