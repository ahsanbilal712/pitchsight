# ADR-006: The MCP server is the only data path for LLM agents

## Status

Accepted, 2026-10-21

## Context

- The Fact Checker requires every claim's `evidence_ids` to resolve in the blackboard and every number to match its evidence within a tolerance (TECH_PLAN 1.7, rules 1 and 2). The agents and the checker therefore need one auditable way to read the same facts.
- Replay mode must give agents the same tool surface as live mode. In replay, `simulate_counterfactual` returns the cached `cf_000077` (TECH_PLAN 1.4, mcp_server).
- Agent Framework core 1.22.0 includes MCP client tools, and the plan names `MCPStreamableHTTPTool` (verified in `config/pins.txt`). The audit notes that `agent-framework-mcp` does not exist and `HostedMCPTool` is not exported; the hosted path is `client.get_mcp_tool()` (audit A.1 rows 35 and 39).
- The Tactician's tool rounds dominate the explained-cue budget: 4 to 10 s for the Tactician with two or three rounds (audit C.1), against a 15 s p95 target.
- The audit's multi-agent test asks what is genuinely agentic. A Tactician that chooses which tools to call, and how many times, is on its list (C.2).

## Decision

`whyline-mcp` (`python -m mcp_server`) is built on the official MCP Python SDK (`mcp`) with FastMCP and serves Streamable HTTP on :8080. It exposes ten tools: `query_events`, `get_state`, `get_pitch_control`, `simulate_counterfactual`, `player_stats`, `similar_moments`, `verify_claims`, `top_moments`, `timeline` and `get_budget`.

LLM-backed agents attach with `MCPStreamableHTTPTool(name="whyline", url="http://localhost:8080/mcp")` and read events, pitch control, counterfactuals and stats only through these tools. Code executors (Scout, Rollout, Fact Checker, Director) write their outputs through the `Blackboard` client held by the newsroom worker, which is the only writer. `RolloutExecutor` still calls `simulate_counterfactual` and `FactCheckExecutor` calls `verify_claims` over MCP. Tool lists per role are set in `config/models.yaml` (Tactician five tools, pundits two, Recap two, Director `get_budget`). Every tool returns a structured `{error, code}` and never raises into the agent.

## Alternatives rejected

- Direct SQL or a blackboard client inside LLM agents: no audit boundary, and each agent could read anything.
- Hosted MCP tool (`HostedMCPTool`, `client.get_mcp_tool()`): `HostedMCPTool` is not exported in 1.22.0, and a local server needs no hosted dependency.

## Consequences

- Positive: the tool surface is the audit boundary for everything a model can see. Each call lands in a trace, and evidence IDs in claims resolve through the same server that agents used.
- Positive: replay and live share one surface. Reuse by GitHub Copilot Agent Mode is a plan, not a verified feature.
- Negative: every tool round adds a network hop inside the live Tactician's budget. `tactician_live` is limited to `max_tool_rounds: 2` and `tactician_degraded` is the template fallback. The golden Tactician gets its tool results inlined by precompute instead (ADR-003).
- Negative: one more process to run and deploy (a Container App in Azure). If it is down, tool-using agents fail and the Director falls back to templates. Cold start after scale-to-zero has not been measured.
- Negative: tool outputs must stay small. `config/budgets.yaml` caps the Tactician context at 12,000 tokens and the blackboard snapshot at 2,500 tokens.
- Negative: the worker's `Blackboard` client is a single writer, so the worker is a single point of write. Reads by agents and writes by code executors take different paths, and a test must keep LLM agents from ever receiving the client.
- Negative: `mcp` is unpinned until T-001.

## Related

- TECH_PLAN 1.1, 1.4 (mcp_server), 1.7 (MCP tool list, Fact Checker rules), 1.3 (blackboard documents).
- ADR-003, ADR-005, ADR-007.
- Schemas: `schemas/explanation.schema.json` (`claims`, `tool_trace_id`), `schemas/counterfactual.schema.json`.
- Audit: A.1 rows 35, 39 and 55, C.1, C.2.
