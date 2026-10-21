"""TacticianExecutor: the explanation behind an explained moment (TECH_PLAN 1.7, T-032).

Role `tactician_live` (gemini-4-argon since ADR-004 Revision 1, effort medium, max 2 tool rounds, 12 s), prompt
`tactician@3`. Tools are the MCP tools `query_events`, `get_pitch_control`, `simulate_counterfactual` and
`player_stats`, reached through the newsroom tool client (MCP over HTTP, or the same functions in-process);
the chat client's own loop runs the rounds in this process and stops after `max_tool_rounds`. Structured output
via a response schema; the result is turned into an explanation.schema.json document. One retry, then
`tactician_degraded`: a template from the counterfactual's numbers.

The system prompt starts with a stable league block (the two clubs, styles and squads) so Gemini's implicit prefix
caching can serve it (budgets.yaml tokens.league_context_block_tokens).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from agent_framework import WorkflowContext, handler, tool
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from blackboard.ids import format_id, parse_id
from newsroom import config
from newsroom.executors.base import Deps, NewsroomExecutor
from newsroom.factcheck import league_data
from newsroom.llm import CacheMiss, LLMError, LLMTimeout
from newsroom.messages import Envelope, Explained, RolloutDone
from newsroom.templates import tactician_template

ROLE, PROMPT = "tactician_live", "tactician@3"
ROOT = Path(__file__).resolve().parents[3]
UNITS = {"xg", "xt", "win_prob", "win_prob_delta", "p_goal", "metres", "kmh", "seconds", "count", "percent", "minute"}
KINDS = ["number", "player", "team", "minute", "tactical"]
# Gemini's schema converter takes one type per field: value is split into value_number / value_text
RESPONSE_SCHEMA = {"type": "object", "required": ["why", "claims", "confidence"], "properties": {
    "why": {"type": "string"}, "confidence": {"type": "number"},
    "claims": {"type": "array", "items": {"type": "object", "required": ["text", "kind", "unit", "evidence_ids"],
                                          "properties": {
        "text": {"type": "string"}, "kind": {"type": "string", "enum": KINDS},
        "value_number": {"type": "number"}, "value_text": {"type": "string"}, "unit": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}}}}}}}
EVENT_KEEP = ("id", "t_ms", "clock", "type", "team", "player", "outcome", "location", "end_location")


def _validator() -> Draft202012Validator:
    registry, schemas = Registry(), {}
    for p in (ROOT / "schemas").glob("*.schema.json"):
        s = json.loads(p.read_text())
        schemas[p.name] = s
        registry = registry.with_resource(s["$id"], Resource.from_contents(s))
    return Draft202012Validator(schemas["explanation.schema.json"], registry=registry)


VALIDATOR = _validator()


def league_block(meta: dict) -> str:
    """The stable prefix: both clubs, their style dials and squads (names, positions, ids)."""
    players, clubs = league_data()
    styles = json.loads((ROOT / "data" / "league" / "styles.json").read_text())
    styles = {s.get("club", s.get("id")): s for s in styles} if isinstance(styles, list) else styles
    lines = ["LEAGUE CONTEXT (fictional league)"]
    for side in ("home", "away"):
        cid = meta.get(side)
        if cid not in clubs:
            continue
        c = clubs[cid]
        lines.append(f"{side.upper()}: {c['name']} ({c['short_name']}, club id {cid}). Style: "
                     + json.dumps({k: v for k, v in (styles.get(cid) or {}).items() if k not in ("club", "id")}))
        squad = meta.get("lineups", {}).get(side, {})
        for group in ("starting", "bench"):
            names = [f"{players[p]['name']} ({players[p]['position']}, {p})" for p in squad.get(group, [])
                     if p in players]
            lines.append(f"  {group}: " + "; ".join(names))
    return "\n".join(lines)


def compact_event(e: dict) -> dict:
    out = {k: e.get(k) for k in EVENT_KEEP}
    attrs = e.get("attrs") or {}
    out["attrs"] = {k: v for k, v in attrs.items() if k in ("xg", "recipient", "distance_m", "shot_speed_kmh",
                                                            "length_m", "progressive_m", "pass_completion_p")}
    return out


def make_tools(deps: Deps, trace: list) -> list:
    """The four Tactician tools as Agent Framework function tools over the newsroom tool client."""
    client = deps.rollout

    async def run(name: str, args: dict):
        trace.append({"tool": name, "args": args})
        out = await client.call(name, args)
        return json.dumps(out, separators=(",", ":"), default=str)

    @tool(approval_mode="never_require")
    async def query_events(match_id: str, t_from_ms: int, t_to_ms: int, kinds: list[str] | None = None,
                           player: str | None = None) -> str:
        """Match events between two times (ms from kick-off); optional event types and player id."""
        trace.append({"tool": "query_events", "args": {"t_from_ms": t_from_ms, "t_to_ms": t_to_ms}})
        out = await client.call("query_events", {"match_id": match_id, "t_from_ms": t_from_ms,
                                                  "t_to_ms": t_to_ms, "kinds": kinds, "player": player})
        events = out if isinstance(out, list) else []
        return json.dumps([compact_event(e) if "id" in e else e for e in events[-40:]], separators=(",", ":"))

    @tool(approval_mode="never_require")
    async def get_pitch_control(match_id: str, t_ms: int) -> str:
        """Pitch-control snapshot at t_ms: snapshot_id (pc_), home share, contested fraction, zones, overloads."""
        return await run("get_pitch_control", {"match_id": match_id, "t_ms": t_ms})

    @tool(approval_mode="never_require")
    async def simulate_counterfactual(match_id: str, t_ms: int, alternative: dict, n: int = 200,
                                      horizon_s: float = 8) -> str:
        """Replay the moment n times with the player on the ball forced to `alternative`
        ({kind: pass|carry|shoot|clear|hold, actor, target}); returns a counterfactual (cf_)."""
        out = await client.call("simulate_counterfactual", {"match_id": match_id, "t_ms": t_ms,
                                                            "alternative": alternative, "n": n,
                                                            "horizon_s": horizon_s})
        trace.append({"tool": "simulate_counterfactual", "args": {"t_ms": t_ms, "alternative": alternative}})
        if isinstance(out, dict):
            out = {k: v for k, v in out.items() if k != "futures_sample"}
        return json.dumps(out, separators=(",", ":"), default=str)

    @tool(approval_mode="never_require")
    async def player_stats(match_id: str, player_id: str) -> str:
        """Touches, passes, completion, xT added, shots, xG and sprints for one player."""
        return await run("player_stats", {"match_id": match_id, "player_id": player_id})

    available = {"query_events": query_events, "get_pitch_control": get_pitch_control,
                 "simulate_counterfactual": simulate_counterfactual, "player_stats": player_stats}
    return [available[n] for n in config.role(ROLE).tools if n in available]


def build_messages(meta: dict, moment, decision: dict | None, cf: dict | None, pc: dict | None,
                   alternatives: list[dict]) -> list[dict]:
    _, system = config.prompt(PROMPT)
    players, _ = league_data()
    m = moment.model_dump() if hasattr(moment, "model_dump") else dict(moment)
    view = {k: m.get(k) for k in ("match_id", "moment_id", "t_ms", "clock", "period", "kind", "leverage", "team",
                                  "players", "evidence_event_ids", "hypotheses")}
    view["player_names"] = {p: players[p]["name"] for p in m.get("players", []) if p in players}
    payload = {"MOMENT": view, "DECISION": None if decision is None else
               {k: decision[k] for k in ("t_ms", "actor", "actor_name", "team", "actual", "anchor_event_id")},
               "COUNTERFACTUAL": None if cf is None else {k: v for k, v in cf.items() if k != "futures_sample"},
               "PITCH_CONTROL": pc, "ALTERNATIVES_TRIED": alternatives}
    return [{"role": "system", "content": league_block(meta) + "\n\n" + system},
            {"role": "user", "content": json.dumps(payload, separators=(",", ":"), default=str)}]


def to_claim(c: dict) -> dict | None:
    kind = c.get("kind")
    if kind not in KINDS or not isinstance(c.get("text"), str) or not c.get("evidence_ids"):
        return None
    if kind in ("number", "minute"):
        value = c.get("value_number")
    else:
        value = c.get("value_text") or c.get("value_number")
    unit = c.get("unit") or None
    if unit not in UNITS:
        unit = None
    return {"text": c["text"][:80], "kind": kind, "value": value, "unit": unit,
            "evidence_ids": [str(i) for i in c["evidence_ids"]], "verified": False, "reject_reason": None}


def explanation_id_for(moment_id: str) -> str:
    """ex_ + moment number, so the explanation of mo_00077 is ex_000077 in every run."""
    return format_id("explanations", parse_id(moment_id)[1])


def finish(msg: Envelope, body: dict, model: str, cf: dict | None, alternatives: list[dict]) -> dict:
    m = msg.moment
    return {"schema_version": "1.0.0", "explanation_id": explanation_id_for(m.moment_id), "match_id": m.match_id,
            "moment_id": m.moment_id, "why": str(body.get("why", ""))[:400], "claims": body["claims"][:8],
            "counterfactual_id": cf["counterfactual_id"] if cf else None,
            "alternatives_considered": [f"{a.get('kind')} {a.get('target') or ''}".strip() for a in alternatives],
            "confidence": max(0.0, min(1.0, float(body.get("confidence", 0.5) or 0.5))), "model": model,
            "prompt_version": PROMPT, "tool_trace_id": msg.trace_id or None, "attempt": 1}


def valid(explanation: dict) -> list[str]:
    return [e.message for e in VALIDATOR.iter_errors(explanation)]


async def explain(deps: Deps, msg: Envelope, decision: dict | None, cf: dict | None,
                  alternatives: list[dict]) -> tuple[dict, dict]:
    """(explanation, info); never raises. Model with tools -> one retry -> tactician_degraded template."""
    m = msg.moment
    players, _ = league_data()
    names = {p: players[p]["name"].split()[-1] for p in players}
    template = finish(msg, tactician_template(m, cf, names), "template", cf, alternatives)
    if deps.llm is None or deps.state.get("degraded"):
        return template, {"status": "template", "model": "template"}
    meta = next(iter(deps.bb.query("events", match_id=m.match_id, type="match_metadata", limit=1)), {}).get("attrs",
                                                                                                          {})
    pc = None
    if cf and cf.get("pitch_control_snapshot_id"):
        try:
            pc = deps.bb.get("pitch_control", cf["pitch_control_snapshot_id"], m.match_id)
            pc = {k: v for k, v in pc.items() if k != "grid_path"}
        except KeyError:
            pc = None
    role = config.role(ROLE)
    trace: list = []
    tools = make_tools(deps, trace) if deps.rollout is not None else None
    messages = build_messages(meta, m, decision, cf, pc, alternatives)
    ctx = {"match_id": m.match_id, "moment_id": m.moment_id, "schema": RESPONSE_SCHEMA, "prompt_version": PROMPT,
           "producer": "tactician",
           "timeout_s": role.timeout_s, "max_tool_rounds": deps.state.get("max_tool_rounds", role.max_tool_rounds)}
    status, spent = "template", {"cost_usd": 0.0, "tokens_in": 0, "tokens_out": 0}
    for _attempt in range(2):
        try:
            res = await deps.llm.complete(ROLE, messages, tools, **ctx)
        except CacheMiss:
            return template, {"status": "cache_miss", "model": "template"}
        except LLMTimeout:
            status = "timeout"
            continue
        except LLMError:
            status = "error"
            continue
        except Exception as exc:
            if type(exc).__name__ == "SpendCapReached":
                deps.state["degraded"] = True
                return template, {"status": "degraded", "model": "template"}
            status = "error"
            continue
        for k in spent:
            spent[k] += res.get(k, 0) or 0
        body = res.get("json") if isinstance(res.get("json"), dict) else {}
        claims = [c for c in (to_claim(x) for x in body.get("claims", []) if isinstance(x, dict)) if c]
        if claims and body.get("why"):
            exp = finish(msg, {**body, "claims": claims}, res.get("model"), cf, alternatives)
            if not valid(exp):
                return exp, {"status": "ok", "model": res.get("model"), "tools": trace,
                             "cache_hit": res.get("cache_hit"), **spent}
        status = "invalid_output"
    return template, {"status": status, "model": "template", "tools": trace, **spent}


class TacticianExecutor(NewsroomExecutor):
    @handler
    async def explain(self, msg: RolloutDone, ctx: WorkflowContext[Explained]) -> None:
        started = time.perf_counter()
        exp, info = await explain(self.deps, msg, msg.decision, msg.counterfactual, msg.alternatives)
        self.deps.bb.put("explanations", exp)
        base = msg.hop(self.id).model_dump(exclude={"alternatives", "decision", "counterfactual"})
        out = Explained(**base, explanation=exp, counterfactual=msg.counterfactual)
        self.trace(out, started, status=info["status"], model=info.get("model"), cost_usd=info.get("cost_usd", 0.0),
                   tokens_in=info.get("tokens_in", 0), tokens_out=info.get("tokens_out", 0),
                   cache_hit=info.get("cache_hit"), tool_calls=[t["tool"] for t in info.get("tools", [])],
                   explanation_id=exp["explanation_id"])
        await ctx.send_message(out)
