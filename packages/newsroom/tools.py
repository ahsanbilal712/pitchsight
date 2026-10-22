"""Tool clients for code executors: the MCP tools (TECH_PLAN 1.7) over Streamable HTTP, or the same functions
in-process. Both expose `await call(name, args) -> dict | list` and never raise: failures are {error, code}.

    McpTools("http://localhost:8080/mcp")   # mcp.Client over Streamable HTTP (see the class for why not
                                            # agent_framework.MCPStreamableHTTPTool)
    LocalTools(store)                       # mcp_server.tools_core over a MatchStore, on a worker thread
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

MCP_URL = "http://localhost:8080/mcp"


def unwrap(value: Any) -> Any:
    """Structured list results arrive as {"result": [...]}."""
    if isinstance(value, dict) and set(value) == {"result"}:
        return value["result"]
    return value


def is_error(value: Any) -> bool:
    if isinstance(value, list) and len(value) == 1:
        value = value[0]
    return isinstance(value, dict) and "error" in value and "code" in value


class LocalTools:
    def __init__(self, store) -> None:
        self.store = store

    async def call(self, name: str, args: dict) -> Any:
        from mcp_server import tools_core, tools_recap
        from mcp_server.errors import guarded

        fn = guarded(getattr(tools_core, name, None) or getattr(tools_recap, name))
        return await asyncio.to_thread(fn, self.store, **args)


class McpTools:
    """MCP over Streamable HTTP with the MCP SDK's own client. Agent Framework 1.22.0's MCPStreamableHTTPTool
    cannot talk to the pinned mcp 2.3.0 (it reads `InitializeResult.protocolVersion`, renamed `protocol_version`
    in mcp 2), so the newsroom uses `mcp.Client`; one session per McpTools, opened on first use."""

    def __init__(self, url: str = MCP_URL) -> None:
        self.url = url
        self._client = None
        self._lock = asyncio.Lock()

    async def call(self, name: str, args: dict) -> Any:
        try:
            async with self._lock:
                if self._client is None:
                    from mcp import Client

                    client = Client(self.url)
                    await client.__aenter__()
                    self._client = client
            res = await self._client.call_tool(name, args)
            if res.structured_content is not None:
                return unwrap(res.structured_content)
            return unwrap(json.loads("".join(getattr(c, "text", "") or "" for c in res.content)))
        except Exception as exc:  # transport or protocol failure: same shape as a tool error
            return {"error": f"{type(exc).__name__}: {exc}", "code": "mcp_unavailable"}

    async def close(self) -> None:
        if self._client is not None:
            await self._client.__aexit__(None, None, None)
            self._client = None
