"""JWT authentication middleware and login router for MCP Admin GUI."""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from ..config import get_config_store

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JWT configuration
# ---------------------------------------------------------------------------

JWT_SECRET: str = os.environ.get("JWT_SECRET", "")
if not JWT_SECRET:
    JWT_SECRET = secrets.token_urlsafe(32)
    logger.warning(
        "JWT_SECRET not set in environment; generated a random secret. "
        "Tokens will not survive restarts."
    )

JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.environ.get("JWT_EXPIRY_HOURS", "24"))


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


def create_token(admin_password: str, provided_password: str) -> str | None:
    """Create a JWT if *provided_password* matches *admin_password*."""
    if not secrets.compare_digest(admin_password, provided_password):
        return None

    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": "admin",
        "iat": now,
        "exp": now + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _verify_token(token: str) -> dict[str, Any] | None:
    """Decode and verify a JWT."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ---------------------------------------------------------------------------
# Auth middleware
# ---------------------------------------------------------------------------


class AuthMiddleware(BaseHTTPMiddleware):
    """Enforce JWT auth on ``/api/*`` routes (except login and MCP proxy)."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        path = request.url.path

        # Public: non-API routes, auth endpoints, MCP proxy, healthz
        if not path.startswith("/api/") or path.startswith("/api/auth/"):
            return await call_next(request)

        # Also skip MCP proxy paths (token validated by proxy itself)
        if path.startswith("/private_"):
            return await call_next(request)

        # Extract JWT from header, cookie, or query parameter
        # (EventSource/SSE cannot set headers, so token may come as ?token=...)
        token: str | None = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        if not token:
            token = request.cookies.get("mcp-admin-token")
        if not token:
            token = request.query_params.get("token")

        if not token:
            return JSONResponse({"detail": "Authentication required"}, status_code=401)

        payload = _verify_token(token)
        if payload is None:
            return JSONResponse({"detail": "Invalid or expired token"}, status_code=401)

        request.state.user = payload
        return await call_next(request)


# ---------------------------------------------------------------------------
# Login router
# ---------------------------------------------------------------------------


class _LoginRequest(BaseModel):
    password: str


login_router = APIRouter(prefix="/api/auth", tags=["auth"])


@login_router.post("/login")
async def login(body: _LoginRequest) -> JSONResponse:
    """Authenticate with admin password from config store."""
    store = get_config_store()
    admin_password = await store.get("admin_password", "")

    if not admin_password:
        raise HTTPException(status_code=500, detail="Admin password not configured")

    token = create_token(admin_password, body.password)
    if token is None:
        raise HTTPException(status_code=401, detail="Invalid password")

    response = JSONResponse({"token": token})
    response.set_cookie(
        key="mcp-admin-token",
        value=token,
        httponly=True,
        samesite="strict",
        max_age=JWT_EXPIRY_HOURS * 3600,
    )
    return response
