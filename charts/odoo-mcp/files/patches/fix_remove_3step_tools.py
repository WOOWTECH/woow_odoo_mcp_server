"""Conditionally hide the 3-step write tools at runtime.

When ODOO_MCP_ALLOW_DIRECT_WRITES=1, removes preview_write, validate_write,
and execute_approved_write from the MCP tool list so Claude AI is forced
to use execute_method for all write operations.

This does NOT modify source code — it uses mcp.remove_tool() at runtime,
so the tools can be restored by toggling the env var and restarting.

The script patches server_core.py to hook into app_lifespan(), calling
remove_tool() after the MCP server is fully initialized.

Idempotent — safe to re-run.
"""

from __future__ import annotations

import glob
import os
import sys

MARKER = "PATCH_HIDE_3STEP"
TOOLS_TO_HIDE = ["preview_write", "validate_write", "execute_approved_write"]

# Code to inject after app_lifespan yields AppContext
HOOK_CODE = '''
    # PATCH_HIDE_3STEP: conditionally hide 3-step write tools at runtime
    if os.environ.get("ODOO_MCP_ALLOW_DIRECT_WRITES", "").strip().lower() in ("1", "true", "yes"):
        for _tool_name in ["preview_write", "validate_write", "execute_approved_write"]:
            try:
                server.remove_tool(_tool_name)
            except Exception:
                pass
'''


def find_server_core() -> str | None:
    try:
        import importlib.util
        spec = importlib.util.find_spec("odoo_mcp.server_core")
        if spec and spec.origin:
            return spec.origin
    except (ImportError, ModuleNotFoundError, ValueError):
        pass
    for pattern in [
        os.path.join(sys.prefix, "lib", "python*", "site-packages", "odoo_mcp", "server_core.py"),
    ]:
        for match in glob.glob(pattern):
            return match
    return None


def patch(filepath: str) -> bool:
    with open(filepath) as f:
        content = f.read()

    if MARKER in content:
        print(f"[patch-hide-3step] Already applied to {filepath}")
        return False

    # Find the yield line in app_lifespan
    # Pattern: "    yield AppContext()"
    target = "    yield AppContext()"
    if target not in content:
        print(f"[patch-hide-3step] ERROR: cannot find '{target}' in {filepath}", file=sys.stderr)
        return False

    # Ensure 'import os' exists
    if "import os" not in content[:1000]:
        content = "import os\n" + content

    # Insert hook BEFORE yield (so tools are removed before server starts serving)
    content = content.replace(
        target,
        HOOK_CODE + "\n" + target,
        1,
    )

    with open(filepath, "w") as f:
        f.write(content)

    # Clear cache
    cache_dir = os.path.join(os.path.dirname(filepath), "__pycache__")
    if os.path.isdir(cache_dir):
        for pyc in glob.glob(os.path.join(cache_dir, "server_core*.pyc")):
            os.remove(pyc)

    print(f"[patch-hide-3step] Applied to {filepath}")
    return True


def main() -> int:
    filepath = find_server_core()
    if not filepath:
        print("[patch-hide-3step] ERROR: cannot find server_core.py", file=sys.stderr)
        return 1
    try:
        patch(filepath)
    except Exception as exc:
        print(f"[patch-hide-3step] ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
