"""File-based configuration store for MCP Admin.

Reads and writes ``/data/config.json`` (path configurable via
``MCP_ADMIN_CONFIG`` env var).  All Admin API routers use this
store instead of K8s Secrets/ConfigMaps, making the application
portable to Podman, Docker, or bare-metal environments.

The config file has this structure::

    {
      "admin_password": "...",
      "mcp_auth_token": "...",
      "connection": { ... },
      "tools": { "disabled": [], "disabled_operations": {} },
      "mcp_server": { "command": "...", "port": 8000, "env": { ... } },
      "proxy": { "timeout": 86400 },
      "token_history": []
    }
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = "/data/config.json"

# Default config seeded on first run
_DEFAULT_CONFIG: dict[str, Any] = {
    "admin_password": "admin",
    "mcp_auth_token": "",
    "connection": {},
    "tools": {
        "disabled": [],
        "disabled_operations": {},
    },
    "mcp_server": {
        "command": "",
        "args": [],
        "port": 8000,
        "env": {},
    },
    "proxy": {
        "timeout": 86400,
    },
    "token_history": [],
}


class ConfigStore:
    """Thread-safe, file-backed configuration store.

    All public methods are async so callers don't need to know
    whether the backing store is a file or a remote API.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path or os.environ.get("MCP_ADMIN_CONFIG", _DEFAULT_CONFIG_PATH))
        self._lock = asyncio.Lock()
        self._cache: dict[str, Any] | None = None
        self._ensure_file()

    # ------------------------------------------------------------------
    # File helpers
    # ------------------------------------------------------------------

    def _ensure_file(self) -> None:
        """Create config file with defaults if it doesn't exist."""
        if self._path.exists():
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(_DEFAULT_CONFIG, indent=2))
        logger.info("Created default config at %s", self._path)

    def _read_sync(self) -> dict[str, Any]:
        """Read and parse the config file (synchronous)."""
        try:
            data = json.loads(self._path.read_text())
            # Merge with defaults so new keys are always present
            merged = {**_DEFAULT_CONFIG, **data}
            for key in _DEFAULT_CONFIG:
                if isinstance(_DEFAULT_CONFIG[key], dict) and key in data and isinstance(data[key], dict):
                    merged[key] = {**_DEFAULT_CONFIG[key], **data[key]}
            return merged
        except (json.JSONDecodeError, FileNotFoundError) as exc:
            logger.warning("Config read failed (%s), using defaults", exc)
            return dict(_DEFAULT_CONFIG)

    def _write_sync(self, data: dict[str, Any]) -> None:
        """Write config to file (synchronous)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def load(self) -> dict[str, Any]:
        """Load the full config, using cache if available."""
        if self._cache is not None:
            return self._cache
        async with self._lock:
            self._cache = await asyncio.to_thread(self._read_sync)
            return self._cache

    async def save(self, data: dict[str, Any]) -> None:
        """Write the full config and update cache."""
        async with self._lock:
            await asyncio.to_thread(self._write_sync, data)
            self._cache = data

    async def get(self, key: str, default: Any = None) -> Any:
        """Get a top-level config value."""
        cfg = await self.load()
        return cfg.get(key, default)

    async def put(self, key: str, value: Any) -> None:
        """Set a top-level config value and persist."""
        cfg = await self.load()
        cfg[key] = value
        await self.save(cfg)

    async def patch(self, key: str, updates: dict[str, Any]) -> dict[str, Any]:
        """Merge *updates* into a top-level dict value and persist.

        Returns the merged value.
        """
        cfg = await self.load()
        current = cfg.get(key, {})
        if not isinstance(current, dict):
            current = {}
        current.update(updates)
        cfg[key] = current
        await self.save(cfg)
        return current

    async def reload(self) -> dict[str, Any]:
        """Force re-read from disk, clearing cache."""
        self._cache = None
        return await self.load()

    @property
    def path(self) -> Path:
        return self._path


# ------------------------------------------------------------------
# Singleton accessor
# ------------------------------------------------------------------

_instance: ConfigStore | None = None


def get_config_store() -> ConfigStore:
    """Return the global ConfigStore singleton."""
    global _instance  # noqa: PLW0603
    if _instance is None:
        _instance = ConfigStore()
    return _instance
