# mcp_server

whyline-mcp: the only data path for LLM agents (ADR-006).

Interface restated from `TECH_PLAN.md` section 1.4 "mcp_server" (TECH_PLAN wins on conflict).
Tests live in `tests/mcp_server/`.

Official MCP Python SDK (`mcp`, pin at T-001), FastMCP, Streamable HTTP on :8080. Tools (signatures in 1.7). Failure behaviour: every tool returns a structured error `{error, code}` and never raises into the agent. Tests: each tool against the golden match fixtures; `simulate_counterfactual` returns the cached `cf_000077` in replay mode.
