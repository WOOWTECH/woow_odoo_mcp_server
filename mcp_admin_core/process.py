"""MCP server subprocess manager.

Starts, stops, and monitors the MCP server process.  The command,
args, and environment are read from the config store's
``mcp_server`` section.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from typing import Any

from .config import get_config_store

logger = logging.getLogger(__name__)


class McpProcessManager:
    """Manage the MCP server as an asyncio subprocess."""

    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._running = False
        self._restart_count = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> bool:
        """Start the MCP server subprocess.  Returns True if started."""
        if self._running and self._process and self._process.returncode is None:
            logger.info("MCP server already running (pid=%s)", self._process.pid)
            return True

        store = get_config_store()
        mcp_cfg = await store.get("mcp_server", {})
        command = mcp_cfg.get("command", "")

        if not command:
            logger.warning("No MCP server command configured — skipping start")
            return False

        args = mcp_cfg.get("args", [])
        env_overrides = mcp_cfg.get("env", {})

        # Build connection env from config
        connection = await store.get("connection", {})

        # Merge: OS env + connection config + mcp_server.env overrides
        env = {**os.environ}
        for key, value in connection.items():
            env[key.upper()] = str(value)
        for key, value in env_overrides.items():
            env[key] = str(value)

        cmd = [command] + args
        logger.info("Starting MCP server: %s", " ".join(cmd))

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            self._running = True
            logger.info("MCP server started (pid=%s)", self._process.pid)

            # Start log drainer in background
            asyncio.create_task(self._drain_logs())
            return True

        except FileNotFoundError:
            logger.error("MCP server command not found: %s", command)
            self._running = False
            return False
        except Exception as exc:
            logger.error("Failed to start MCP server: %s", exc)
            self._running = False
            return False

    async def stop(self) -> None:
        """Gracefully stop the MCP server."""
        if not self._process or self._process.returncode is not None:
            self._running = False
            return

        pid = self._process.pid
        logger.info("Stopping MCP server (pid=%s)", pid)

        try:
            self._process.send_signal(signal.SIGTERM)
            try:
                await asyncio.wait_for(self._process.wait(), timeout=10)
            except asyncio.TimeoutError:
                logger.warning("MCP server did not stop in 10s, killing")
                self._process.kill()
                await self._process.wait()
        except ProcessLookupError:
            pass

        self._running = False
        logger.info("MCP server stopped")

    async def restart(self) -> bool:
        """Stop then start the MCP server.  Returns True if restarted."""
        await self.stop()
        self._restart_count += 1
        return await self.start()

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    async def status(self) -> dict[str, Any]:
        """Return current process status."""
        store = get_config_store()
        mcp_cfg = await store.get("mcp_server", {})

        if self._process and self._process.returncode is None:
            return {
                "running": True,
                "pid": self._process.pid,
                "restart_count": self._restart_count,
                "command": mcp_cfg.get("command", ""),
                "port": mcp_cfg.get("port", 8000),
            }
        return {
            "running": False,
            "pid": None,
            "restart_count": self._restart_count,
            "command": mcp_cfg.get("command", ""),
            "port": mcp_cfg.get("port", 8000),
            "exit_code": self._process.returncode if self._process else None,
        }

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _drain_logs(self) -> None:
        """Read stdout/stderr from the subprocess and log it."""
        if not self._process or not self._process.stdout:
            return
        try:
            async for line in self._process.stdout:
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    logger.info("[mcp-server] %s", text)
        except Exception:
            pass

        # Process exited
        if self._process:
            rc = self._process.returncode
            self._running = False
            logger.warning("MCP server exited with code %s", rc)


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_instance: McpProcessManager | None = None


def get_process_manager() -> McpProcessManager:
    """Return the global McpProcessManager singleton."""
    global _instance  # noqa: PLW0603
    if _instance is None:
        _instance = McpProcessManager()
    return _instance
