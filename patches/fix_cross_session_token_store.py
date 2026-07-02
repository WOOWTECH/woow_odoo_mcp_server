"""Patch odoo-mcp-server's server_core.py to use a process-global token store.

Problem
-------
The MCP SDK (>=1.27) calls ``app_lifespan()`` once per HTTP session, creating
a **fresh** ``AppContext`` each time.  Because ``write_approvals`` is a
per-instance dict, tokens stored by ``validate_write`` in Session A are
invisible to ``execute_approved_write`` in Session B.

Claude.ai frequently opens separate sessions for each batch of tool calls,
so ``validate_write`` and ``execute_approved_write`` almost always land in
different sessions — making the three-step write flow unusable.

Fix
---
Replace the per-instance ``write_approvals`` dict with a module-level
singleton so every ``AppContext`` instance shares the same token store
within one process.

Usage
-----
Run once after ``pip install odoo-mcp-server``::

    python patches/fix_cross_session_token_store.py

The script is idempotent — re-running it on an already-patched file is safe.
"""

from __future__ import annotations

import glob
import os
import sys


def find_server_core() -> str | None:
    """Locate server_core.py inside the installed odoo_mcp package."""
    patterns = [
        # Standard pip install location
        os.path.join(sys.prefix, "lib", "python*", "site-packages", "odoo_mcp", "server_core.py"),
        # Editable / development install
        os.path.join(os.path.dirname(__file__), "..", "src", "odoo_mcp", "server_core.py"),
    ]
    for pattern in patterns:
        matches = glob.glob(pattern)
        if matches:
            return matches[0]
    return None


def patch(filepath: str) -> bool:
    """Apply the cross-session token store patch.  Returns True if patched."""
    with open(filepath) as f:
        content = f.read()

    if "_GLOBAL_WRITE_APPROVALS" in content:
        print(f"[patch] Already applied to {filepath}")
        return False

    # 1. Add module-level dict after WRITE_APPROVAL_TTL_SECONDS
    old_ttl = "WRITE_APPROVAL_TTL_SECONDS = 10 * 60"
    new_ttl = (
        "WRITE_APPROVAL_TTL_SECONDS = 10 * 60\n"
        "\n"
        "# PATCH(woowtech): process-global token store shared across MCP sessions.\n"
        "# Without this, validate_write and execute_approved_write fail when\n"
        "# they land in different HTTP sessions (each gets its own AppContext).\n"
        "_GLOBAL_WRITE_APPROVALS: Dict[str, Dict[str, Any]] = {}\n"
    )
    if old_ttl not in content:
        print(f"[patch] ERROR: cannot find TTL constant in {filepath}", file=sys.stderr)
        return False
    content = content.replace(old_ttl, new_ttl, 1)

    # 2. Point AppContext.write_approvals to the global dict
    old_field = "    write_approvals: Dict[str, Dict[str, Any]] = field(default_factory=dict)"
    new_field = "    write_approvals: Dict[str, Dict[str, Any]] = field(default_factory=lambda: _GLOBAL_WRITE_APPROVALS)"
    if old_field not in content:
        print(f"[patch] ERROR: cannot find write_approvals field in {filepath}", file=sys.stderr)
        return False
    content = content.replace(old_field, new_field, 1)

    with open(filepath, "w") as f:
        f.write(content)

    # 3. Remove .pyc cache so Python reads the patched source
    cache_dir = os.path.join(os.path.dirname(filepath), "__pycache__")
    if os.path.isdir(cache_dir):
        for pyc in glob.glob(os.path.join(cache_dir, "server_core*.pyc")):
            os.remove(pyc)
            print(f"[patch] Removed cache: {pyc}")

    # 4. Verify
    with open(filepath) as f:
        patched = f.read()
    assert "_GLOBAL_WRITE_APPROVALS" in patched, "Global dict not found after patch"
    assert "lambda: _GLOBAL_WRITE_APPROVALS" in patched, "Factory not updated after patch"

    print(f"[patch] Successfully applied to {filepath}")
    return True


def main() -> int:
    filepath = find_server_core()
    if filepath is None:
        print("[patch] ERROR: could not locate odoo_mcp/server_core.py", file=sys.stderr)
        return 1
    try:
        patch(filepath)
        return 0
    except Exception as exc:
        print(f"[patch] ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
