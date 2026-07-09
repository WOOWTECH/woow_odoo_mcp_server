"""Patch odoo-mcp-server to allow direct create/write/unlink via execute_method.

Problem
-------
The upstream ``execute_method`` tool unconditionally blocks ``create``,
``write``, and ``unlink`` calls, forcing a three-step approval flow
(``preview_write`` -> ``validate_write`` -> ``execute_approved_write``).

Claude.ai frequently drops write-approval tokens across sessions, making
this three-step flow unreliable in practice.

Fix
---
When the environment variable ``ODOO_MCP_ALLOW_DIRECT_WRITES`` is set to
``1`` (or ``true`` / ``yes``), the ``DESTRUCTIVE_METHODS`` guard in
``execute_method`` is bypassed, allowing direct ORM calls.

This patch is **opt-in** and safe to apply unconditionally — the guard is
only lifted when the env var is explicitly set.

Usage
-----
Run once after ``pip install odoo-mcp-server``::

    python patches/fix_direct_writes.py

The script is idempotent — re-running it on an already-patched file is safe.
"""

from __future__ import annotations

import glob
import os
import sys

MARKER = "ODOO_MCP_ALLOW_DIRECT_WRITES"

OLD_BLOCK = (
    '        if method in DESTRUCTIVE_METHODS:\n'
    '            return {\n'
    '                "success": False,\n'
    '                "error": (\n'
    '                    "Direct execute_method blocks create/write/unlink. Use "\n'
    '                    "preview_write -> validate_write -> execute_approved_write."\n'
    '                ),\n'
    '            }'
)

NEW_BLOCK = (
    '        if method in DESTRUCTIVE_METHODS:\n'
    '            # PATCH(woowtech): allow direct writes when opt-in env var is set.\n'
    '            if not os.environ.get("ODOO_MCP_ALLOW_DIRECT_WRITES", "").strip().lower() in ("1", "true", "yes"):\n'
    '                return {\n'
    '                    "success": False,\n'
    '                    "error": (\n'
    '                        "Direct execute_method blocks create/write/unlink. Use "\n'
    '                        "preview_write -> validate_write -> execute_approved_write, "\n'
    '                        "or set ODOO_MCP_ALLOW_DIRECT_WRITES=1."\n'
    '                    ),\n'
    '                }'
)


def find_tools_write() -> list[str]:
    """Locate tools_write.py inside the installed odoo_mcp package."""
    paths: list[str] = []
    # Try importlib first (most reliable)
    try:
        import importlib.util
        spec = importlib.util.find_spec("odoo_mcp.tools_write")
        if spec and spec.origin:
            paths.append(spec.origin)
    except (ImportError, ModuleNotFoundError, ValueError):
        pass
    # Fallback to glob patterns
    patterns = [
        os.path.join(sys.prefix, "lib", "python*", "site-packages", "odoo_mcp", "tools_write.py"),
        os.path.join(os.path.dirname(__file__), "..", "src", "odoo_mcp", "tools_write.py"),
    ]
    for pattern in patterns:
        for match in glob.glob(pattern):
            if match not in paths:
                paths.append(match)
    return paths


def patch(filepath: str) -> bool:
    """Apply the direct-writes patch.  Returns True if patched."""
    with open(filepath) as f:
        content = f.read()

    if MARKER in content:
        print(f"[patch-direct-writes] Already applied to {filepath}")
        return False

    if OLD_BLOCK not in content:
        print(f"[patch-direct-writes] ERROR: target block not found in {filepath}", file=sys.stderr)
        return False

    content = content.replace(OLD_BLOCK, NEW_BLOCK, 1)

    # Ensure 'import os' exists at the top
    if "import os" not in content[:500]:
        content = "import os\n" + content

    with open(filepath, "w") as f:
        f.write(content)

    # Clear .pyc cache
    cache_dir = os.path.join(os.path.dirname(filepath), "__pycache__")
    if os.path.isdir(cache_dir):
        for pyc in glob.glob(os.path.join(cache_dir, "tools_write*.pyc")):
            os.remove(pyc)
            print(f"[patch-direct-writes] Removed cache: {pyc}")

    # Verify
    with open(filepath) as f:
        assert MARKER in f.read(), "Marker not found after patch"

    print(f"[patch-direct-writes] Applied to {filepath}")
    return True


def main() -> int:
    paths = find_tools_write()
    if not paths:
        print("[patch-direct-writes] ERROR: could not locate odoo_mcp/tools_write.py", file=sys.stderr)
        return 1
    ok = True
    for filepath in paths:
        try:
            patch(filepath)
        except Exception as exc:
            print(f"[patch-direct-writes] ERROR: {exc}", file=sys.stderr)
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
