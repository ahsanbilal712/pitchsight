"""python -m mcp_server  ->  Streamable HTTP on :WHYLINE_MCP_PORT (8080) at /mcp."""

from __future__ import annotations

import logging
import os

from blackboard import SqliteBlackboard
from mcp_server.server import build_server
from mcp_server.tools_core import MatchStore


def main() -> None:
    logging.basicConfig(level=os.environ.get("WHYLINE_LOG", "INFO"))
    server = build_server(MatchStore(SqliteBlackboard()))
    server.run("streamable-http", host=os.environ.get("WHYLINE_MCP_HOST", "127.0.0.1"),
               port=int(os.environ.get("WHYLINE_MCP_PORT", "8080")), streamable_http_path="/mcp")


if __name__ == "__main__":
    main()
