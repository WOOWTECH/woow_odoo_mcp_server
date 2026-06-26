"""MCP reverse proxy — replaces the nginx auth proxy.

Routes ``/private_{token}/{path}`` requests to the MCP server on
localhost, validating the token against the config store.  Supports
streaming responses required by the MCP protocol (SSE, chunked).
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from .config import get_config_store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["mcp-proxy"])

# Shared client with long timeout for MCP streaming calls
_client: httpx.AsyncClient | None = None


def _get_client(timeout: float = 86400) -> httpx.AsyncClient:
    global _client  # noqa: PLW0603
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10.0))
    return _client


@router.api_route(
    "/private_{token}/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    include_in_schema=False,
)
async def mcp_proxy(token: str, path: str, request: Request) -> StreamingResponse:
    """Validate the URL-path token and reverse-proxy to the MCP server."""
    store = get_config_store()
    expected_token = await store.get("mcp_auth_token", "")

    if not expected_token or token != expected_token:
        raise HTTPException(status_code=403, detail="Invalid or missing MCP auth token")

    # Build upstream URL
    mcp_cfg = await store.get("mcp_server", {})
    mcp_port = mcp_cfg.get("port", 8000)
    upstream_url = f"http://127.0.0.1:{mcp_port}/{path}"

    # Forward query string
    if request.url.query:
        upstream_url += f"?{request.url.query}"

    # Build headers — forward most, drop hop-by-hop
    forward_headers = {}
    skip = {"host", "connection", "transfer-encoding", "keep-alive"}
    for key, value in request.headers.items():
        if key.lower() not in skip:
            forward_headers[key] = value
    forward_headers["host"] = "localhost"

    # Add bearer token if configured (n8n proxy pattern)
    proxy_cfg = await store.get("proxy", {})
    bearer = proxy_cfg.get("bearer_token")
    if bearer:
        forward_headers["authorization"] = f"Bearer {bearer}"

    # Read body
    body = await request.body()

    client = _get_client(proxy_cfg.get("timeout", 86400))

    try:
        upstream_req = client.build_request(
            method=request.method,
            url=upstream_url,
            headers=forward_headers,
            content=body if body else None,
        )
        upstream_resp = await client.send(upstream_req, stream=True)
    except httpx.ConnectError:
        raise HTTPException(502, detail="MCP server not reachable")
    except httpx.TimeoutException:
        raise HTTPException(504, detail="MCP server timed out")

    # Stream response back — disable buffering for SSE
    resp_headers = dict(upstream_resp.headers)
    for h in ("transfer-encoding", "content-encoding", "content-length"):
        resp_headers.pop(h, None)
    resp_headers["x-accel-buffering"] = "no"

    async def stream_body():
        try:
            async for chunk in upstream_resp.aiter_bytes():
                yield chunk
        finally:
            await upstream_resp.aclose()

    return StreamingResponse(
        stream_body(),
        status_code=upstream_resp.status_code,
        headers=resp_headers,
        media_type=upstream_resp.headers.get("content-type"),
    )


# Bare /private_TOKEN (no trailing path) also needs to work
@router.api_route(
    "/private_{token}",
    methods=["GET", "POST"],
    include_in_schema=False,
)
async def mcp_proxy_root(token: str, request: Request) -> StreamingResponse:
    """Proxy root path (no trailing slash)."""
    return await mcp_proxy(token, "", request)
