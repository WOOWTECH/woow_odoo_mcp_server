"""Kubernetes client wrapper for MCP Admin GUI applications."""

from __future__ import annotations

import asyncio
import base64
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator

from kubernetes import client, config
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)

_SA_NAMESPACE_PATH = Path("/var/run/secrets/kubernetes.io/serviceaccount/namespace")


class K8sClient:
    """High-level Kubernetes client for common MCP Admin operations.

    Automatically detects whether it is running inside a cluster (in-cluster
    config) or locally (kubeconfig).  The target namespace is resolved from,
    in order of precedence:

    1. The *namespace* constructor argument.
    2. The ``NAMESPACE`` environment variable.
    3. The service-account namespace file (in-cluster only).
    4. Falls back to ``"default"``.
    """

    def __init__(self, namespace: str | None = None) -> None:
        self._load_config()
        self.namespace = namespace or self._detect_namespace()
        self.core = client.CoreV1Api()
        self.apps = client.AppsV1Api()
        logger.info("K8sClient initialised for namespace=%s", self.namespace)

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_config() -> None:
        """Load in-cluster config, falling back to local kubeconfig."""
        try:
            config.load_incluster_config()
            logger.debug("Loaded in-cluster Kubernetes config")
        except config.ConfigException:
            try:
                config.load_kube_config()
                logger.debug("Loaded local kubeconfig")
            except config.ConfigException as exc:
                raise RuntimeError(
                    "Unable to load Kubernetes configuration. "
                    "Ensure you are running inside a cluster or have a valid kubeconfig."
                ) from exc

    @staticmethod
    def _detect_namespace() -> str:
        """Detect the current namespace from env or service-account token."""
        ns = os.environ.get("NAMESPACE")
        if ns:
            return ns
        if _SA_NAMESPACE_PATH.is_file():
            return _SA_NAMESPACE_PATH.read_text().strip()
        return "default"

    # ------------------------------------------------------------------
    # Secrets
    # ------------------------------------------------------------------

    def get_secret(self, name: str) -> dict[str, str]:
        """Return decoded data from a Kubernetes Secret.

        Returns an empty dict if the secret has no data field.

        Raises:
            ApiException: If the secret does not exist or access is denied.
        """
        try:
            secret = self.core.read_namespaced_secret(name, self.namespace)
        except ApiException as exc:
            logger.error("Failed to read secret %s/%s: %s", self.namespace, name, exc.reason)
            raise

        if not secret.data:
            return {}

        return {
            key: base64.b64decode(value).decode("utf-8")
            for key, value in secret.data.items()
        }

    def patch_secret(self, name: str, data: dict[str, str]) -> None:
        """Patch a Kubernetes Secret, base64-encoding the provided values.

        Raises:
            ApiException: If the secret does not exist or access is denied.
        """
        encoded = {
            key: base64.b64encode(value.encode("utf-8")).decode("ascii")
            for key, value in data.items()
        }
        body = client.V1Secret(data=encoded)
        try:
            self.core.patch_namespaced_secret(name, self.namespace, body)
            logger.info("Patched secret %s/%s (keys: %s)", self.namespace, name, list(data.keys()))
        except ApiException as exc:
            logger.error("Failed to patch secret %s/%s: %s", self.namespace, name, exc.reason)
            raise

    # ------------------------------------------------------------------
    # ConfigMaps
    # ------------------------------------------------------------------

    def get_configmap(
        self,
        name: str,
        include_metadata: bool = False,
    ) -> dict[str, str]:
        """Return data from a Kubernetes ConfigMap.

        If *include_metadata* is True, the returned dict also contains
        ``_annotations`` with the ConfigMap's annotation dict.

        Returns an empty dict if the configmap has no data field.

        Raises:
            ApiException: If the configmap does not exist or access is denied.
        """
        try:
            cm = self.core.read_namespaced_config_map(name, self.namespace)
        except ApiException as exc:
            logger.error("Failed to read configmap %s/%s: %s", self.namespace, name, exc.reason)
            raise

        result = dict(cm.data) if cm.data else {}
        if include_metadata:
            result["_annotations"] = dict(cm.metadata.annotations or {}) if cm.metadata and cm.metadata.annotations else {}
        return result

    def patch_configmap(
        self,
        name: str,
        data: dict[str, str] | None = None,
        annotations: dict[str, str] | None = None,
    ) -> None:
        """Patch a Kubernetes ConfigMap data and/or annotations.

        Raises:
            ApiException: If the configmap does not exist or access is denied.
        """
        body: dict[str, Any] = {}
        if data is not None:
            body["data"] = data
        if annotations is not None:
            body["metadata"] = {"annotations": annotations}

        if not body:
            return

        try:
            self.core.patch_namespaced_config_map(name, self.namespace, body)
            logger.info(
                "Patched configmap %s/%s (data_keys: %s, annotation_keys: %s)",
                self.namespace,
                name,
                list(data.keys()) if data else [],
                list(annotations.keys()) if annotations else [],
            )
        except ApiException as exc:
            logger.error("Failed to patch configmap %s/%s: %s", self.namespace, name, exc.reason)
            raise

    # ------------------------------------------------------------------
    # Deployments
    # ------------------------------------------------------------------

    def restart_deployment(self, name: str) -> None:
        """Trigger a rolling restart by patching the restartedAt annotation.

        Raises:
            ApiException: If the deployment does not exist or access is denied.
        """
        now = datetime.now(timezone.utc).isoformat()
        body = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "kubectl.kubernetes.io/restartedAt": now,
                        }
                    }
                }
            }
        }
        try:
            self.apps.patch_namespaced_deployment(name, self.namespace, body)
            logger.info("Restarted deployment %s/%s", self.namespace, name)
        except ApiException as exc:
            logger.error("Failed to restart deployment %s/%s: %s", self.namespace, name, exc.reason)
            raise

    def get_deployment_env(self, name: str) -> dict[str, str]:
        """Read environment variables from a Deployment's first container.

        Returns a dict of env var name → value.  Env vars sourced from
        ConfigMaps/Secrets (valueFrom) are skipped.

        Raises:
            ApiException: If the deployment does not exist or access is denied.
        """
        try:
            deploy = self.apps.read_namespaced_deployment(name, self.namespace)
        except ApiException as exc:
            logger.error("Failed to read deployment %s/%s: %s", self.namespace, name, exc.reason)
            raise

        containers = deploy.spec.template.spec.containers or []
        if not containers:
            return {}

        env_vars: dict[str, str] = {}
        for ev in containers[0].env or []:
            if ev.value is not None:
                env_vars[ev.name] = ev.value
        return env_vars

    def patch_deployment_env(self, name: str, env_updates: dict[str, str]) -> None:
        """Update environment variables on a Deployment's first container.

        Uses read-modify-write: reads the deployment, merges env updates,
        then patches.  This preserves existing env vars not in *env_updates*.

        Raises:
            ApiException: If the deployment does not exist or access is denied.
        """
        try:
            deploy = self.apps.read_namespaced_deployment(name, self.namespace)
        except ApiException as exc:
            logger.error("Failed to read deployment %s/%s: %s", self.namespace, name, exc.reason)
            raise

        container = deploy.spec.template.spec.containers[0]
        existing_env = {ev.name: ev for ev in (container.env or [])}

        for key, value in env_updates.items():
            existing_env[key] = client.V1EnvVar(name=key, value=value)

        container.env = list(existing_env.values())

        try:
            self.apps.patch_namespaced_deployment(name, self.namespace, deploy)
            logger.info(
                "Patched deployment env %s/%s (keys: %s)",
                self.namespace,
                name,
                list(env_updates.keys()),
            )
        except ApiException as exc:
            logger.error("Failed to patch deployment env %s/%s: %s", self.namespace, name, exc.reason)
            raise

    # ------------------------------------------------------------------
    # Pods
    # ------------------------------------------------------------------

    def get_pod_status(self, label_selector: str) -> list[dict[str, Any]]:
        """Return status information for pods matching the label selector.

        Each entry contains: name, phase, ready, restart_count, age,
        started_at, container_statuses.

        Raises:
            ApiException: If listing pods fails.
        """
        try:
            pods = self.core.list_namespaced_pod(self.namespace, label_selector=label_selector)
        except ApiException as exc:
            logger.error(
                "Failed to list pods in %s with selector %s: %s",
                self.namespace,
                label_selector,
                exc.reason,
            )
            raise

        result: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc)

        for pod in pods.items:
            restarts = 0
            ready_count = 0
            total_containers = 0
            container_statuses: list[dict[str, Any]] = []

            if pod.status and pod.status.container_statuses:
                for cs in pod.status.container_statuses:
                    total_containers += 1
                    restarts += cs.restart_count
                    if cs.ready:
                        ready_count += 1

                    # Build state dict
                    state: dict[str, Any] = {}
                    if cs.state:
                        if cs.state.running:
                            state = {"running": {"startedAt": str(cs.state.running.started_at) if cs.state.running.started_at else None}}
                        elif cs.state.waiting:
                            state = {"waiting": {"reason": cs.state.waiting.reason, "message": cs.state.waiting.message}}
                        elif cs.state.terminated:
                            state = {"terminated": {"reason": cs.state.terminated.reason, "exitCode": cs.state.terminated.exit_code}}

                    container_statuses.append({
                        "name": cs.name,
                        "ready": cs.ready,
                        "restart_count": cs.restart_count,
                        "state": state,
                    })
            elif pod.spec and pod.spec.containers:
                total_containers = len(pod.spec.containers)

            # Compute age
            age_seconds = 0
            started_at = None
            if pod.metadata and pod.metadata.creation_timestamp:
                ts = pod.metadata.creation_timestamp.replace(tzinfo=timezone.utc)
                delta = now - ts
                age_seconds = int(delta.total_seconds())
                started_at = ts.isoformat()

            phase = pod.status.phase if pod.status else "Unknown"
            all_ready = ready_count == total_containers and total_containers > 0

            result.append(
                {
                    "name": pod.metadata.name,
                    "phase": phase,
                    "ready": all_ready,
                    "ready_str": f"{ready_count}/{total_containers}",
                    "restart_count": restarts,
                    "age": _format_age(age_seconds),
                    "started_at": started_at,
                    "container_statuses": container_statuses,
                }
            )

        return result

    def get_pod_logs(
        self,
        label_selector: str,
        tail_lines: int = 100,
    ) -> dict[str, Any]:
        """Return recent log lines from the first pod matching the selector.

        Returns a dict with ``lines`` (list of str) and ``pod_name``.
        """
        try:
            pods = self.core.list_namespaced_pod(
                self.namespace, label_selector=label_selector
            )
        except ApiException as exc:
            logger.error(
                "Failed to list pods for logs in %s: %s",
                self.namespace,
                exc.reason,
            )
            raise

        if not pods.items:
            return {"lines": [], "pod_name": ""}

        pod_name = pods.items[0].metadata.name
        try:
            log_text = self.core.read_namespaced_pod_log(
                pod_name,
                self.namespace,
                tail_lines=tail_lines,
            )
        except ApiException as exc:
            logger.error("Failed to read logs for pod %s: %s", pod_name, exc.reason)
            raise

        lines = log_text.strip().split("\n") if log_text else []
        return {"lines": lines, "pod_name": pod_name}

    async def stream_pod_logs(
        self,
        label_selector: str,
        tail_lines: int = 100,
        follow: bool = True,
    ) -> AsyncGenerator[tuple[str, str], None]:
        """Stream log lines from pods matching the label selector.

        Yields ``(line, pod_name)`` tuples.  Only the most recent
        *tail_lines* per pod are included in the initial burst; if
        *follow* is True the stream follows new output.
        """
        try:
            pods = self.core.list_namespaced_pod(
                self.namespace, label_selector=label_selector
            )
        except ApiException as exc:
            logger.error(
                "Failed to list pods for log streaming in %s: %s",
                self.namespace,
                exc.reason,
            )
            yield (f"[error] Failed to list pods: {exc.reason}", "error")
            return

        if not pods.items:
            yield ("[info] No pods found matching the selector.", "info")
            return

        for pod in pods.items:
            pod_name = pod.metadata.name
            try:
                log_stream = self.core.read_namespaced_pod_log(
                    pod_name,
                    self.namespace,
                    tail_lines=tail_lines,
                    follow=follow,
                    _preload_content=False,
                )

                for raw_line in log_stream:
                    line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
                    yield (line, pod_name)
                    # Yield control so the event loop can handle other tasks
                    await asyncio.sleep(0)

            except ApiException as exc:
                yield (f"[error] {exc.reason}", pod_name)
            finally:
                if "log_stream" in locals():
                    log_stream.close()


def _format_age(seconds: int) -> str:
    """Format an age in seconds into a human-readable string (e.g. '3d', '5h', '12m')."""
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h"
    days = hours // 24
    return f"{days}d"
