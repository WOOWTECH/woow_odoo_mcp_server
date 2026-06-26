"""Token management router.

Manages MCP proxy authentication tokens. Tokens are stored in the
file-backed config store and applied by restarting the MCP server
subprocess via the process manager.

Endpoints:
    GET  /api/tokens        - Current token (masked) and rotation history
    POST /api/tokens/rotate - Generate a new token, update config, restart server
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from mcp_admin_core.config import get_config_store
from mcp_admin_core.process import get_process_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tokens", tags=["tokens"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_HISTORY = 10
DEFAULT_TOKEN_LENGTH = 32  # bytes -> 64 hex chars


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TokenHistoryEntry(BaseModel):
    """A single token rotation event."""

    token_prefix: str = Field(..., description="First 8 chars of the token")
    created_at: str = Field(..., description="ISO 8601 timestamp of creation")
    rotated_by: str = Field(default="admin", description="Who triggered the rotation")


class TokenInfoResponse(BaseModel):
    """Current token info and rotation history."""

    current_token_masked: str = Field(..., description="Current token with middle chars masked")
    token_prefix: str = Field(..., description="First 8 chars of current token")
    created_at: str | None = Field(None, description="When the current token was created")
    history: list[TokenHistoryEntry] = Field(default_factory=list)


class TokenRotateRequest(BaseModel):
    """Request body for token rotation."""

    token_length: int = Field(default=DEFAULT_TOKEN_LENGTH, ge=16, le=128, description="Token length in bytes (hex output is 2x)")
    restart_proxy: bool = Field(default=True, description="Restart MCP server after rotation")


class TokenRotateResponse(BaseModel):
    """Response after token rotation."""

    success: bool
    new_token: str = Field(..., description="The newly generated token (shown once)")
    token_prefix: str
    proxy_restarted: bool = False
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mask_token(token: str) -> str:
    """Mask a token, showing only first 8 and last 4 characters."""
    if len(token) <= 12:
        return token[:4] + "****"
    return f"{token[:8]}{'*' * (len(token) - 12)}{token[-4:]}"


def _token_prefix(token: str) -> str:
    """Extract the first 8 characters of a token for identification."""
    return token[:8] if len(token) >= 8 else token


async def _load_history() -> list[TokenHistoryEntry]:
    """Load token rotation history from the config store."""
    try:
        store = get_config_store()
        raw = await store.get("token_history", [])
        if isinstance(raw, list):
            return [TokenHistoryEntry(**e) for e in raw]
        return []
    except Exception:
        return []


async def _save_history(history: list[TokenHistoryEntry]) -> None:
    """Persist token rotation history to the config store."""
    store = get_config_store()
    serialized = [e.model_dump() for e in history[-MAX_HISTORY:]]
    await store.put("token_history", serialized)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=TokenInfoResponse)
async def get_tokens() -> TokenInfoResponse:
    """Return the current proxy token (masked) and rotation history."""
    try:
        store = get_config_store()
        current_token = await store.get("mcp_auth_token", "")
        history = await _load_history()

        if not current_token:
            return TokenInfoResponse(
                current_token_masked="(not configured)",
                token_prefix="",
                history=history,
            )

        # Determine creation time from the most recent history entry
        created_at = history[-1].created_at if history else None

        return TokenInfoResponse(
            current_token_masked=_mask_token(current_token),
            token_prefix=_token_prefix(current_token),
            created_at=created_at,
            history=history,
        )
    except Exception as exc:
        logger.error("Failed to read token info: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read token info: {exc}",
        ) from exc


@router.post("/rotate", response_model=TokenRotateResponse)
async def rotate_token(req: TokenRotateRequest | None = None) -> TokenRotateResponse:
    """Generate a new proxy token, update config, and optionally restart MCP server.

    The new token is returned in plain text exactly once. Subsequent
    GET requests will only show the masked version.
    """
    if req is None:
        req = TokenRotateRequest()

    try:
        store = get_config_store()

        # Generate cryptographically secure token
        new_token = secrets.token_hex(req.token_length)
        now = datetime.now(timezone.utc).isoformat()

        # Update the token in config store
        await store.put("mcp_auth_token", new_token)
        logger.info("Rotated proxy token (prefix: %s)", _token_prefix(new_token))

        # Update history
        history = await _load_history()
        history.append(TokenHistoryEntry(
            token_prefix=_token_prefix(new_token),
            created_at=now,
            rotated_by="admin",
        ))
        await _save_history(history)

        # Optionally restart the MCP server
        proxy_restarted = False
        if req.restart_proxy:
            pm = get_process_manager()
            if pm.is_running:
                await pm.restart()
                proxy_restarted = True
                logger.info("Restarted MCP server after token rotation")

        return TokenRotateResponse(
            success=True,
            new_token=new_token,
            token_prefix=_token_prefix(new_token),
            proxy_restarted=proxy_restarted,
            message="Token rotated successfully. Save the new token -- it will not be shown again.",
        )
    except Exception as exc:
        logger.error("Failed to rotate token: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rotate token: {exc}",
        ) from exc
