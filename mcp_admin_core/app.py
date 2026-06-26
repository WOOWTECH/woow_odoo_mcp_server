"""FastAPI application factory for MCP Admin GUI services."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Sequence

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .auth.middleware import AuthMiddleware, login_router
from .process import get_process_manager
from .proxy import router as proxy_router
from .routers.settings import router as settings_router

logger = logging.getLogger(__name__)


def create_app(
    title: str,
    extra_routers: Sequence[APIRouter] | None = None,
    *,
    static_dir: str | Path | None = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    """Create and configure a FastAPI application.

    Parameters
    ----------
    title:
        The application title shown in the OpenAPI docs.
    extra_routers:
        Additional ``APIRouter`` instances to include in the app.
    static_dir:
        Path to a directory of static files to serve.
        Defaults to ``./static`` if it exists.
    cors_origins:
        List of allowed CORS origins.  Defaults to ``["*"]``.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        # Startup: start MCP server if configured
        pm = get_process_manager()
        await pm.start()
        yield
        # Shutdown: stop MCP server
        await pm.stop()

    app = FastAPI(title=title, lifespan=lifespan)

    # -- Auth middleware -------------------------------------------------------
    app.add_middleware(AuthMiddleware)

    # -- CORS ------------------------------------------------------------------
    origins = cors_origins if cors_origins is not None else ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -- Core routers ----------------------------------------------------------
    app.include_router(login_router)
    app.include_router(settings_router)
    app.include_router(proxy_router)

    if extra_routers:
        for router in extra_routers:
            app.include_router(router)

    # -- Health endpoint (before SPA fallback) ---------------------------------
    @app.get("/healthz", tags=["system"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # -- Static files + SPA fallback (must be last) ----------------------------
    if static_dir is None:
        static_dir = Path.cwd() / "static"
    else:
        static_dir = Path(static_dir)

    if static_dir.is_dir():
        assets_dir = static_dir / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        index_html = static_dir / "index.html"
        if index_html.is_file():
            _index_content = index_html.read_text()

            @app.get("/{path:path}", include_in_schema=False)
            async def spa_fallback(path: str) -> HTMLResponse:
                return HTMLResponse(_index_content)

        logger.info("Serving SPA from %s", static_dir)
    else:
        logger.debug("No static directory found at %s; skipping", static_dir)

    logger.info("Created application '%s'", title)
    return app
