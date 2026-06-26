"""Health dashboard router.

Returns data in the format the Dashboard frontend expects.

Endpoints:
    GET /api/health - Dashboard health data
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter

from mcp_admin_core.config import get_config_store
from mcp_admin_core.process import get_process_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/health", tags=["health"])


async def _check_odoo(odoo_url: str) -> dict[str, Any]:
    """Check Odoo health via /web/health."""
    if not odoo_url:
        return {"healthy": False, "url": "", "error": "Not configured"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{odoo_url.rstrip('/')}/web/health")
            return {
                "healthy": resp.status_code == 200,
                "url": odoo_url,
                "status_code": resp.status_code,
            }
    except httpx.ConnectError:
        return {"healthy": False, "url": odoo_url, "error": "Connection refused"}
    except httpx.TimeoutException:
        return {"healthy": False, "url": odoo_url, "error": "Timed out"}
    except Exception as exc:
        return {"healthy": False, "url": odoo_url, "error": str(exc)}


async def _get_odoo_info(odoo_url: str, db: str, username: str, password: str) -> dict[str, Any]:
    """Get Odoo version and module count via XML-RPC."""
    info: dict[str, Any] = {"version": None, "db_name": db, "item_count": None}
    if not odoo_url or not username:
        return info
    try:
        import xmlrpc.client
        common = xmlrpc.client.ServerProxy(f"{odoo_url.rstrip('/')}/xmlrpc/2/common", allow_none=True)
        ver = common.version()
        info["version"] = ver.get("server_version", "unknown") if isinstance(ver, dict) else str(ver)

        # Odoo 18+ changed authenticate() signature: (db, credential_dict, user_agent_env)
        # Try new format first, fall back to old format for Odoo <=17 compatibility.
        try:
            result = common.authenticate(
                db,
                {"login": username, "password": password, "type": "password"},
                {},
            )
        except (xmlrpc.client.Fault, TypeError):
            result = common.authenticate(db, username, password, {})
        uid = result.get("uid") if isinstance(result, dict) else result
        if uid:
            models = xmlrpc.client.ServerProxy(f"{odoo_url.rstrip('/')}/xmlrpc/2/object", allow_none=True)
            count = models.execute_kw(db, uid, password, "ir.module.module", "search_count", [[["state", "=", "installed"]]])
            info["item_count"] = count
    except Exception as exc:
        logger.debug("Failed to get Odoo info: %s", exc)
    return info


@router.get("")
async def get_health() -> dict[str, Any]:
    """Return health data in the format the Dashboard frontend expects."""
    store = get_config_store()
    pm = get_process_manager()

    conn = await store.get("connection", {})
    odoo_url = conn.get("odoo_url", "")
    pm_status = await pm.status()

    # MCP server status
    mcp_running = pm_status.get("running", False)
    mcp_server = {
        "healthy": mcp_running,
        "pod_name": f"pid={pm_status.get('pid')}" if mcp_running else "stopped",
        "restart_count": pm_status.get("restart_count", 0),
    }

    # Odoo health
    target_app = await _check_odoo(odoo_url)

    # MCP proxy (built-in, always healthy if admin is running)
    proxy = {
        "healthy": True,
        "pod_name": "built-in reverse proxy",
    }

    # Extra info from Odoo
    odoo_info = await _get_odoo_info(
        odoo_url,
        conn.get("odoo_db", ""),
        conn.get("odoo_username", ""),
        conn.get("odoo_password", ""),
    )

    # Overall
    all_healthy = mcp_running and target_app.get("healthy", False)

    return {
        "app_type": "odoo",
        "overall_status": "ok" if all_healthy else "degraded" if mcp_running or target_app.get("healthy") else "error",
        "mcp_server": mcp_server,
        "target_app": target_app,
        "proxy": proxy,
        "version": odoo_info.get("version"),
        "db_name": odoo_info.get("db_name"),
        "item_count": odoo_info.get("item_count"),
        "namespace": "podman",
    }
