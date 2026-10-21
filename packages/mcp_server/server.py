"""whyline-mcp: the only data path for agents (ADR-006, TECH_PLAN 1.7 "MCP tool list", T-030).

mcp 2.x renamed FastMCP to `MCPServer`; it serves Streamable HTTP at /mcp (port WHYLINE_MCP_PORT, default 8080).
Every tool is wrapped by `errors.guarded`, so a failure comes back as {error, code} and never raises into the agent.
Signatures are copied from TECH_PLAN 1.7 (returns spelled dict[str, Any], which structured output needs). `top_moments` and `timeline` (T-050) come later; `similar_moments` is T-054.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from mcp_server import tools_core as core
from mcp_server.errors import guarded

INSTRUCTIONS = ("WHYLINE match data for one fictional football match. Cite the ids these tools return "
                "(e_, cf_, f_, pc_) as evidence for every claim.")
TOOLS = ("query_events", "get_state", "get_pitch_control", "simulate_counterfactual", "player_stats",
         "verify_claims", "get_budget", "similar_moments")


def build_server(store: core.MatchStore) -> MCPServer:
    mcp = MCPServer("whyline", instructions=INSTRUCTIONS)

    @mcp.tool(structured_output=True)
    @guarded
    def query_events(match_id: str, t_from_ms: int, t_to_ms: int, kinds: list[str] | None = None,
                     player: str | None = None) -> list[dict[str, Any]]:
        """Match events between two times (ms from kick-off), optionally only some types or one player."""
        return core.query_events(store, match_id, t_from_ms, t_to_ms, kinds, player)

    @mcp.tool(structured_output=True)
    @guarded
    def get_state(match_id: str, t_ms: int) -> dict[str, Any]:
        """Score, clock, possession, game state (Settled/Transitional/Chaotic), chaos index, 60 s indices and the
        simulator's option probabilities for the player in control."""
        return core.get_state(store, match_id, t_ms)

    @mcp.tool(structured_output=True)
    @guarded
    def get_pitch_control(match_id: str, t_ms: int) -> dict[str, Any]:
        """Pitch-control snapshot: snapshot_id (pc_), home share, contested fraction, zones, top-3 overloads."""
        return core.get_pitch_control(store, match_id, t_ms)

    @mcp.tool(structured_output=True)
    @guarded
    def simulate_counterfactual(match_id: str, t_ms: int, alternative: dict, n: int = 200,
                                horizon_s: float = 8) -> dict[str, Any]:
        """Replay the moment n times with the player in control forced to `alternative`
        ({kind: pass|carry|shoot|clear|hold, actor, target}); returns a CounterfactualResult (cf_)."""
        return core.simulate_counterfactual(store, match_id, t_ms, alternative, n, horizon_s)

    @mcp.tool(structured_output=True)
    @guarded
    def player_stats(match_id: str, player_id: str) -> dict[str, Any]:
        """Touches, passes, completion, xT added, shots, xG and sprints for one player."""
        return core.player_stats(store, match_id, player_id)

    @mcp.tool(structured_output=True)
    @guarded
    def verify_claims(match_id: str, claims: list[dict]) -> dict[str, Any]:
        """Run the Fact Checker on claims: {verified, claims[], diff[]}."""
        return core.verify_claims(store, match_id, claims)

    @mcp.tool(structured_output=True)
    @guarded
    def get_budget(mode: str) -> dict[str, Any]:
        """Director screen-time budget for a viewer mode, the hard rules and the spend summary."""
        return core.get_budget(store, mode)

    @mcp.tool(structured_output=True)
    @guarded
    def similar_moments(match_id: str, t_ms: int, k: int = 3) -> list[dict[str, Any]]:
        """The k moments of the golden season most like this one (other matches), each with its phase name."""
        from mcp_server import tools_similar
        return tools_similar.similar_moments(store, match_id, t_ms, k)

    return mcp
