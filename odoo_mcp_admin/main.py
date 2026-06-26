"""Odoo MCP Admin - FastAPI application entry point.

Run with:
    uvicorn odoo_mcp_admin.main:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

from mcp_admin_core.app import create_app

from .routers import config, health, logs, tokens, tools

app = create_app(
    title="Odoo MCP Admin",
    extra_routers=[
        config.router,
        tools.router,
        tokens.router,
        health.router,
        logs.router,
    ],
)
