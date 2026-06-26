"""Connection configuration router.

Manages Odoo MCP connection settings stored in the config store.

Endpoints:
    GET  /api/config            - Current connection config
    PUT  /api/config/connection  - Update connection credentials
    POST /api/config/test        - Test XML-RPC connectivity
"""

from __future__ import annotations

import logging
import xmlrpc.client
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from mcp_admin_core.config import get_config_store
from mcp_admin_core.process import get_process_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ConnectionConfig(BaseModel):
    odoo_url: str = ""
    odoo_db: str = ""
    odoo_username: str = ""
    odoo_password_masked: str = "********"


class ConnectionUpdateRequest(BaseModel):
    odoo_url: str = Field(..., description="Odoo instance URL")
    odoo_db: str = Field(..., description="PostgreSQL database name")
    odoo_username: str = Field(..., description="Odoo login username")
    odoo_password: str = Field(..., description="Odoo login password")
    restart: bool = Field(default=True, description="Restart MCP server after update")


class ConnectionUpdateResponse(BaseModel):
    success: bool
    message: str
    restarted: bool = False


class ConnectionTestRequest(BaseModel):
    odoo_url: str
    odoo_db: str
    odoo_username: str
    odoo_password: str


class ConnectionTestResponse(BaseModel):
    success: bool
    message: str
    uid: int | None = None
    server_version: str | None = None
    details: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mask(s: str) -> str:
    if len(s) <= 2:
        return "****"
    return f"{s[0]}{'*' * (len(s) - 2)}{s[-1]}"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=ConnectionConfig)
async def get_config() -> ConnectionConfig:
    """Return current Odoo connection config (password masked)."""
    store = get_config_store()
    conn = await store.get("connection", {})
    pw = conn.get("odoo_password", "")
    return ConnectionConfig(
        odoo_url=conn.get("odoo_url", ""),
        odoo_db=conn.get("odoo_db", ""),
        odoo_username=conn.get("odoo_username", ""),
        odoo_password_masked=_mask(pw) if pw else "(not set)",
    )


@router.put("/connection", response_model=ConnectionUpdateResponse)
async def update_connection(req: ConnectionUpdateRequest) -> ConnectionUpdateResponse:
    """Update Odoo connection credentials and optionally restart MCP server."""
    store = get_config_store()
    await store.patch("connection", {
        "odoo_url": req.odoo_url,
        "odoo_db": req.odoo_db,
        "odoo_username": req.odoo_username,
        "odoo_password": req.odoo_password,
    })
    logger.info("Updated Odoo connection config")

    restarted = False
    if req.restart:
        pm = get_process_manager()
        if pm.is_running:
            await pm.restart()
            restarted = True

    return ConnectionUpdateResponse(
        success=True,
        message="Connection credentials updated",
        restarted=restarted,
    )


@router.post("/test", response_model=ConnectionTestResponse)
async def test_connection(req: ConnectionTestRequest) -> ConnectionTestResponse:
    """Test XML-RPC connectivity to an Odoo instance."""
    url = req.odoo_url.rstrip("/")

    try:
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True)
        version_info = common.version()
    except Exception as exc:
        return ConnectionTestResponse(success=False, message=f"Cannot reach Odoo: {exc}")

    server_version = version_info.get("server_version", "unknown") if isinstance(version_info, dict) else str(version_info)

    # Odoo 18 changed authenticate() signature: (db, credential_dict, user_agent_env)
    # Try new format first, fall back to old format for Odoo <=17 compatibility.
    try:
        try:
            # Odoo 18+ format
            result = common.authenticate(
                req.odoo_db,
                {"login": req.odoo_username, "password": req.odoo_password, "type": "password"},
                {},
            )
            uid = result.get("uid") if isinstance(result, dict) else result
        except (xmlrpc.client.Fault, TypeError):
            # Odoo <=17 format
            result = common.authenticate(req.odoo_db, req.odoo_username, req.odoo_password, {})
            uid = result.get("uid") if isinstance(result, dict) else result
    except xmlrpc.client.Fault as fault:
        return ConnectionTestResponse(success=False, message=f"XML-RPC fault: {fault.faultString}", server_version=server_version)
    except Exception as exc:
        return ConnectionTestResponse(success=False, message=f"Auth failed: {exc}", server_version=server_version)

    if not uid:
        return ConnectionTestResponse(success=False, message="Invalid credentials (uid=False)", server_version=server_version)

    return ConnectionTestResponse(
        success=True,
        message=f"Authenticated as UID {uid}",
        uid=uid,
        server_version=server_version,
        details={"database": req.odoo_db, "username": req.odoo_username},
    )
