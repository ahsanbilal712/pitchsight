# mcp_server

whyline-mcp: the only data path for LLM agents (ADR-006).

Interface restated from `TECH_PLAN.md` section 1.4 "mcp_server" (TECH_PLAN wins on conflict).
Tests live in `tests/mcp_server/`.

Official MCP Python SDK (`mcp`, pin at T-001), FastMCP, Streamable HTTP on :8080. Tools (signatures in 1.7). Failure behaviour: every tool returns a structured error `{error, code}` and never raises into the agent. Tests: each tool against the golden match fixtures; `simulate_counterfactual` returns the cached `cf_000077` in replay mode.

## As built (T-030)

- mcp 2.3.0 renamed FastMCP to `mcp.server.mcpserver.MCPServer`; `python -m mcp_server` serves Streamable HTTP on
  `WHYLINE_MCP_PORT` (8080) at `/mcp`. `server.build_server(store)` registers the seven core tools with the 1.7
  signatures; returns are spelled `dict[str, Any]` / `list[dict[str, Any]]` because structured output needs it
  (list results arrive as `{"result": [...]}`).
- `tools_core.py`: the same tools as plain functions over a `MatchStore` (match `m_<seed>` in
  `data/matches/<seed>/`, events loaded into the blackboard on first use so evidence ids resolve).
  `get_pitch_control` writes `pc_<t_ms//100>` documents and a float16 grid in `data/runtime/pitch_control/`;
  overload labels (`overload_right_attacking_third`, `2v1`) feed Fact Checker rule 5.
  `simulate_counterfactual` wraps `rollout.sliding_doors` and stores `cf_` documents; a repeat call returns the
  stored result.
- `errors.guarded`: any failure comes back as `{error, code}` (`[{error, code}]` for list tools).
- Known limit: `player_stats` covers every event of the match file; in replay that includes the future of the
  replay clock until the api writes events as they are played (T-033/T-039).
