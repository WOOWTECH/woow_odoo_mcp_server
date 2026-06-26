"""Kubernetes client utilities for MCP Admin GUI.

Exports both the :class:`K8sClient` class and convenient async module-level
wrapper functions.  The wrappers lazily instantiate a :class:`K8sClient` per
namespace so callers can simply ``await get_secret("my-secret")`` without
managing client instances.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator

from .client import K8sClient

__all__ = [
    "K8sClient",
    # Async wrapper functions
    "get_secret",
    "patch_secret",
    "get_configmap",
    "patch_configmap",
    "restart_deployment",
    "get_deployment_env",
    "patch_deployment_env",
    "get_pod_status",
    "get_pod_logs",
    "stream_pod_logs",
]

# ---------------------------------------------------------------------------
# Lazy client cache — one K8sClient per namespace
# ---------------------------------------------------------------------------

_clients: dict[str, K8sClient] = {}


def _get_client(namespace: str | None = None) -> K8sClient:
    """Return a cached K8sClient for the given namespace."""
    key = namespace or "__default__"
    if key not in _clients:
        _clients[key] = K8sClient(namespace=namespace)
    return _clients[key]


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------


async def get_secret(
    name: str,
    *,
    namespace: str | None = None,
) -> dict[str, str]:
    """Read and decode a Kubernetes Secret."""
    c = _get_client(namespace)
    return await asyncio.to_thread(c.get_secret, name)


async def patch_secret(
    name: str,
    data: dict[str, str],
    *,
    namespace: str | None = None,
) -> None:
    """Patch a Kubernetes Secret (values are auto base64-encoded)."""
    c = _get_client(namespace)
    await asyncio.to_thread(c.patch_secret, name, data)


# ---------------------------------------------------------------------------
# ConfigMaps
# ---------------------------------------------------------------------------


async def get_configmap(
    name: str,
    *,
    namespace: str | None = None,
    include_metadata: bool = False,
) -> dict[str, str]:
    """Read a Kubernetes ConfigMap."""
    c = _get_client(namespace)
    return await asyncio.to_thread(c.get_configmap, name, include_metadata)


async def patch_configmap(
    name: str,
    data: dict[str, str] | None = None,
    *,
    annotations: dict[str, str] | None = None,
    namespace: str | None = None,
) -> None:
    """Patch a Kubernetes ConfigMap data and/or annotations."""
    c = _get_client(namespace)
    await asyncio.to_thread(c.patch_configmap, name, data, annotations)


# ---------------------------------------------------------------------------
# Deployments
# ---------------------------------------------------------------------------


async def restart_deployment(
    name: str,
    *,
    namespace: str | None = None,
) -> None:
    """Trigger a rolling restart of a Deployment."""
    c = _get_client(namespace)
    await asyncio.to_thread(c.restart_deployment, name)


async def get_deployment_env(
    name: str,
    *,
    namespace: str | None = None,
) -> dict[str, str]:
    """Read env vars from a Deployment's first container."""
    c = _get_client(namespace)
    return await asyncio.to_thread(c.get_deployment_env, name)


async def patch_deployment_env(
    name: str,
    env_updates: dict[str, str],
    *,
    namespace: str | None = None,
) -> None:
    """Update env vars on a Deployment's first container."""
    c = _get_client(namespace)
    await asyncio.to_thread(c.patch_deployment_env, name, env_updates)


# ---------------------------------------------------------------------------
# Pods
# ---------------------------------------------------------------------------


async def get_pod_status(
    label_selector: str,
    *,
    namespace: str | None = None,
) -> list[dict[str, Any]]:
    """Return status information for pods matching a label selector."""
    c = _get_client(namespace)
    return await asyncio.to_thread(c.get_pod_status, label_selector)


async def get_pod_logs(
    label_selector: str,
    *,
    namespace: str | None = None,
    tail_lines: int = 100,
) -> dict[str, Any]:
    """Return recent log lines from the first matching pod."""
    c = _get_client(namespace)
    return await asyncio.to_thread(c.get_pod_logs, label_selector, tail_lines)


async def stream_pod_logs(
    label_selector: str,
    *,
    namespace: str | None = None,
    tail_lines: int = 100,
    follow: bool = True,
) -> AsyncGenerator[tuple[str, str], None]:
    """Stream log lines as ``(line, pod_name)`` tuples."""
    c = _get_client(namespace)
    async for item in c.stream_pod_logs(
        label_selector,
        tail_lines=tail_lines,
        follow=follow,
    ):
        yield item
