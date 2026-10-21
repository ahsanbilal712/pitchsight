"""Tool clients for code executors: the MCP tools (TECH_PLAN 1.7) over Streamable HTTP, or the same functions
in-process. Both expose `await call(name, args) -> dict | list` and never raise: failures are {error, code}.

    McpTools("http://localhost:8080/mcp")   # MCPStreamableHTTPTool(name="whyline", url=...), core 1.22.0
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
        from mcp_server import tools_core
        from mcp_server.errors import guarded

        fn = guarded(getattr(tools_core, name))
        return await asyncio.to_thread(fn, self.store, **args)


class McpTools:
    def __init__(self, url: str = MCP_URL) -> None:
        from agent_framework import MCPStreamableHTTPTool

        self.tool = MCPStreamableHTTPTool(name="whyline", url=url)
        self._connected = False
        self._lock = asyncio.Lock()

    async def call(self, name: str, args: dict) -> Any:
        try:
            async with self._lock:
                if not self._connected:
                    await self.tool.connect()
                    self._connected = True
            out = await self.tool.call_tool(name, **args)
            text = out if isinstance(out, str) else "".join(getattr(c, "text", "") or "" for c in out)
            return unwrap(json.loads(text))
        except Exception as exc:  # transport or protocol failure: same shape as a tool error
            return {"error": f"{type(exc).__name__}: {exc}", "code": "mcp_unavailable"}

    async def close(self) -> None:
        if self._connected:
            await self.tool.close()
            self._connected = False
