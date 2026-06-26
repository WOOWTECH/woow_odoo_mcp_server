"""Settings router — full config.json management via Web GUI.

Provides CRUD for all config sections: connection, mcp_server,
proxy, tools, admin_password, mcp_auth_token.

Endpoints:
    GET  /api/settings           - Full config (password masked)
    PUT  /api/settings           - Replace full config
    GET  /api/settings/{section} - Get one section
    PUT  /api/settings/{section} - Replace one section
    POST /api/settings/mcp/restart - Restart MCP server process
    GET  /api/settings/mcp/status  - MCP server process status
"""

from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..config import get_config_store
from ..process import get_process_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class McpServerConfig(BaseModel):
    """MCP server process configuration."""

    command: str = Field("", description="Executable command (e.g. 'odoo-mcp-server')")
    args: list[str] = Field(default_factory=list, description="Command-line arguments")
    port: int = Field(8000, ge=1, le=65535, description="MCP server listen port")
    env: dict[str, str] = Field(default_factory=dict, description="Environment variables")


class ProxyConfig(BaseModel):
    """MCP proxy configuration."""

    timeout: int = Field(86400, description="Proxy timeout in seconds")
    bearer_token: str | None = Field(None, description="Optional Bearer token for upstream")


class ConnectionConfig(BaseModel):
    """Upstream service connection settings (Odoo or n8n)."""

    # Generic — routers use whatever keys are present
    model_config = {"extra": "allow"}


class ToolsConfig(BaseModel):
    """Tool enable/disable settings."""

    disabled: list[str] = Field(default_factory=list)
    disabled_operations: dict[str, list[str]] = Field(default_factory=dict)


class FullConfig(BaseModel):
    """Complete config for GET /api/settings (password masked)."""

    admin_password_masked: str = ""
    mcp_auth_token: str = ""
    connection: dict[str, Any] = {}
    mcp_server: dict[str, Any] = {}
    proxy: dict[str, Any] = {}
    tools: dict[str, Any] = {}


class McpProcessStatus(BaseModel):
    """MCP server process status."""

    running: bool
    pid: int | None = None
    restart_count: int = 0
    command: str = ""
    port: int = 8000
    exit_code: int | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mask(value: str) -> str:
    if len(value) <= 4:
        return "****"
    return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=FullConfig)
async def get_settings() -> FullConfig:
    """Return full config with sensitive values masked."""
    store = get_config_store()
    cfg = await store.load()

    password = cfg.get("admin_password", "")
    conn = dict(cfg.get("connection", {}))

    # Mask password fields in connection
    for key in list(conn.keys()):
        if "password" in key.lower() or "key" in key.lower() or "secret" in key.lower():
            conn[key] = _mask(str(conn[key])) if conn[key] else ""

    return FullConfig(
        admin_password_masked=_mask(password) if password else "(not set)",
        mcp_auth_token=cfg.get("mcp_auth_token", ""),
        connection=conn,
        mcp_server=cfg.get("mcp_server", {}),
        proxy=cfg.get("proxy", {}),
        tools=cfg.get("tools", {}),
    )


@router.get("/{section}")
async def get_section(section: str) -> dict[str, Any]:
    """Get a single config section."""
    store = get_config_store()
    value = await store.get(section)
    if value is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown section: {section}")
    if isinstance(value, dict):
        return value
    return {"value": value}


@router.put("/{section}")
async def put_section(section: str, body: dict[str, Any]) -> dict[str, str]:
    """Replace a config section. Restarts MCP server if connection or mcp_server changed."""
    store = get_config_store()

    # Special handling for admin_password
    if section == "admin_password":
        new_pass = body.get("value", "")
        if not new_pass or len(new_pass) < 4:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Password must be at least 4 characters")
        await store.put("admin_password", new_pass)
        return {"status": "ok", "message": "Admin password updated"}

    await store.put(section, body)
    logger.info("Updated config section: %s", section)

    # Auto-restart MCP server if relevant config changed
    if section in ("connection", "mcp_server"):
        pm = get_process_manager()
        if pm.is_running:
            await pm.restart()
            return {"status": "ok", "message": f"Section '{section}' updated, MCP server restarted"}

    return {"status": "ok", "message": f"Section '{section}' updated"}


@router.post("/mcp_auth_token/rotate")
async def rotate_mcp_token() -> dict[str, str]:
    """Generate a new random MCP auth token."""
    store = get_config_store()
    cfg = await store.load()

    # Save old token to history
    old_token = cfg.get("mcp_auth_token", "")
    history = cfg.get("token_history", [])
    if old_token:
        from datetime import datetime, timezone
        history.insert(0, {
            "token_masked": _mask(old_token),
            "rotated_at": datetime.now(timezone.utc).isoformat(),
        })
        history = history[:10]  # keep last 10
        cfg["token_history"] = history

    new_token = secrets.token_hex(32)
    cfg["mcp_auth_token"] = new_token
    await store.save(cfg)

    return {"status": "ok", "token": new_token, "message": "Token rotated. Save it — shown only once."}


@router.get("/mcp/status", response_model=McpProcessStatus)
async def mcp_status() -> McpProcessStatus:
    """Return MCP server process status."""
    pm = get_process_manager()
    info = await pm.status()
    return McpProcessStatus(**info)


@router.post("/mcp/restart")
async def mcp_restart() -> dict[str, str]:
    """Restart the MCP server process."""
    pm = get_process_manager()
    ok = await pm.restart()
    if ok:
        return {"status": "ok", "message": "MCP server restarted"}
    return {"status": "error", "message": "Failed to restart MCP server — check command config"}
