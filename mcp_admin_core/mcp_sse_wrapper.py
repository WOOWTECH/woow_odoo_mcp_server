"""Wrapper to run any MCP stdio server as an SSE HTTP server.

Usage:
    python -m mcp_admin_core.mcp_sse_wrapper mcp_server_odoo.server:server --port 8000

This imports the MCP ``Server`` object from the specified module and
exposes it via SSE transport on an HTTP port, allowing the admin GUI's
reverse proxy to forward MCP client requests to it.
"""

from __future__ import annotations

import argparse
import importlib
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Run MCP server with SSE transport")
    parser.add_argument("server_spec", help="module.path:server_object (e.g. mcp_server_odoo.server:server)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    # Import the server object
    module_path, obj_name = args.server_spec.rsplit(":", 1)
    module = importlib.import_module(module_path)
    server = getattr(module, obj_name)

    # Build SSE app
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Mount, Route

    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ],
    )

    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
