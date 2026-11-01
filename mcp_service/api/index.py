"""Vercel ASGI entrypoint for the LIQUIDITY NEXUS MCP endpoint."""
import os
os.environ.setdefault("FASTMCP_STREAMABLE_HTTP_PATH", "/api/index")
from server import mcp

app = mcp.streamable_http_app()
