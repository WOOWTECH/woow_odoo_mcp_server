"""Remove the 3-step write tools when ODOO_MCP_ALLOW_DIRECT_WRITES=1.

When direct writes are enabled, Claude AI still sees preview_write,
validate_write, and execute_approved_write as available tools and
preferentially uses the 3-step flow — which frequently breaks due to
cross-session token loss.

This patch comments out the @mcp.tool() decorators on those 3 functions
so they are never registered with the MCP server, forcing Claude to
use execute_method for all write operations.

Only applies when ODOO_MCP_ALLOW_DIRECT_WRITES is set to 1/true/yes.
The script is idempotent.
"""

from __future__ import annotations

import glob
import os
import sys

MARKER = "PATCH_REMOVE_3STEP"

TARGETS = [
    ("preview_write", "Preview create, write, or unlink"),
    ("validate_write", "Validate a standard write payload"),
    ("execute_approved_write", "Execute a previously previewed"),
]


def find_tools_write() -> list[str]:
    paths: list[str] = []
    try:
        import importlib.util
        spec = importlib.util.find_spec("odoo_mcp.tools_write")
        if spec and spec.origin:
            paths.append(spec.origin)
    except (ImportError, ModuleNotFoundError, ValueError):
        pass
    for pattern in [
        os.path.join(sys.prefix, "lib", "python*", "site-packages", "odoo_mcp", "tools_write.py"),
    ]:
        for match in glob.glob(pattern):
            if match not in paths:
                paths.append(match)
    return paths


def patch(filepath: str) -> bool:
    with open(filepath) as f:
        lines = f.readlines()

    if MARKER in "".join(lines):
        print(f"[patch-remove-3step] Already applied to {filepath}")
        return False

    # Only apply if ALLOW_DIRECT_WRITES is enabled
    allow = os.environ.get("ODOO_MCP_ALLOW_DIRECT_WRITES", "").strip().lower()
    if allow not in ("1", "true", "yes"):
        print(f"[patch-remove-3step] Skipped (ODOO_MCP_ALLOW_DIRECT_WRITES={allow!r})")
        return False

    changed = False
    i = 0
    while i < len(lines):
        line = lines[i]
        # Look for @mcp.tool( decorator
        if line.strip() == "@mcp.tool(":
            # Check if the next few lines contain one of our target descriptions
            block = "".join(lines[i:i+10])
            for func_name, desc_prefix in TARGETS:
                if desc_prefix in block:
                    # Comment out the entire decorator block (@mcp.tool(...))
                    # Find the closing )
                    j = i
                    depth = 0
                    while j < len(lines):
                        depth += lines[j].count("(") - lines[j].count(")")
                        lines[j] = f"# {MARKER}: {lines[j]}"
                        if depth <= 0:
                            break
                        j += 1
                    print(f"[patch-remove-3step] Removed @mcp.tool for {func_name}")
                    changed = True
                    break
        i += 1

    if changed:
        with open(filepath, "w") as f:
            f.writelines(lines)
        # Clear cache
        cache_dir = os.path.join(os.path.dirname(filepath), "__pycache__")
        if os.path.isdir(cache_dir):
            for pyc in glob.glob(os.path.join(cache_dir, "tools_write*.pyc")):
                os.remove(pyc)
        print(f"[patch-remove-3step] Applied to {filepath}")
    return changed


def main() -> int:
    paths = find_tools_write()
    if not paths:
        print("[patch-remove-3step] ERROR: could not find tools_write.py", file=sys.stderr)
        return 1
    for filepath in paths:
        try:
            patch(filepath)
        except Exception as exc:
            print(f"[patch-remove-3step] ERROR: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
