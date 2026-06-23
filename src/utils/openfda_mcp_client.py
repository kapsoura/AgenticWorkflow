"""
Live OpenFDA MCP client (US — live evidence retrieval).

Talks to the Node.js ``Augmented-Nature/OpenFDA-MCP-Server`` over stdio using
the *official* MCP Python SDK, so the connection performs the mandatory
``initialize`` / ``initialized`` handshake before any ``tools/call``.

Design goals
------------
* **Offline-first / graceful degradation** — mirrors ``AnthropicClient``. If
  Node, the built server, or the ``mcp`` SDK is missing, ``enabled`` is ``False``
  and every call returns an empty result instead of raising. The surrounding
  pipeline keeps working on its local archive + vector evidence.
* **Correct protocol** — uses ``mcp.ClientSession`` which sends ``initialize``
  and waits for the server's capabilities before calling tools.
* **Sync surface** — the rest of the (synchronous) pipeline calls plain methods;
  the async session is driven internally via ``asyncio.run`` per call.

Server entry resolution order:
  1. ``OPENFDA_MCP_SERVER_ENTRY`` environment variable (absolute path), else
  2. ``<repo_root>/Project/openfda-mcp-server/build/index.js``, else
  3. ``<repo_root>/openfda-mcp-server/build/index.js``.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]

_CANDIDATE_ENTRIES = [
    _REPO_ROOT / "Project" / "openfda-mcp-server" / "build" / "index.js",
    _REPO_ROOT / "openfda-mcp-server" / "build" / "index.js",
]

SUPPORTED_TOOLS = {
    "search_device_adverse_events",
    "search_device_recalls",
    "search_device_510k",
    "search_device_classifications",
}


def _resolve_entry() -> Optional[Path]:
    env_entry = os.environ.get("OPENFDA_MCP_SERVER_ENTRY", "").strip()
    if env_entry:
        p = Path(env_entry)
        return p if p.exists() else None
    for candidate in _CANDIDATE_ENTRIES:
        if candidate.exists():
            return candidate
    return None


class OpenFDAMCPClient:
    """Synchronous facade over the async OpenFDA MCP server session."""

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout
        self._entry: Optional[Path] = None
        self._node = shutil.which("node")
        self._sdk_ok = False

        try:
            # Imported lazily so a missing SDK only disables the feature.
            import mcp  # noqa: F401
            from mcp import ClientSession, StdioServerParameters  # noqa: F401
            from mcp.client.stdio import stdio_client  # noqa: F401

            self._sdk_ok = True
        except Exception:
            self._sdk_ok = False

        self._entry = _resolve_entry()

    @property
    def enabled(self) -> bool:
        """True only when Node, the built server and the SDK are all present."""
        return bool(self._node) and self._entry is not None and self._sdk_ok

    # ── public sync API ──────────────────────────────────────────────────────

    def call(self, tool: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke an OpenFDA tool. Returns parsed JSON ``dict`` or ``{}`` on any
        failure (never raises — the pipeline must keep running offline)."""
        if not self.enabled:
            return {}
        if tool not in SUPPORTED_TOOLS:
            return {}
        try:
            return asyncio.run(self._acall(tool, arguments))
        except Exception:
            return {}

    def search_adverse_events(
        self,
        device_name: Optional[str] = None,
        product_code: Optional[str] = None,
        limit: int = 5,
    ) -> List[dict]:
        args: Dict[str, Any] = {"limit": limit}
        if device_name:
            args["device_name"] = device_name
        if product_code:
            args["product_code"] = product_code
        raw = self.call("search_device_adverse_events", args)
        return raw.get("device_adverse_events") or raw.get("results") or []

    def search_recalls(
        self,
        device_name: Optional[str] = None,
        product_code: Optional[str] = None,
        limit: int = 5,
    ) -> List[dict]:
        args: Dict[str, Any] = {"limit": limit}
        if device_name:
            args["device_name"] = device_name
        if product_code:
            args["product_code"] = product_code
        raw = self.call("search_device_recalls", args)
        return raw.get("device_recalls") or raw.get("results") or []

    # ── async plumbing ───────────────────────────────────────────────────────

    async def _acall(self, tool: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(command=self._node, args=[str(self._entry)])

        async def _run() -> Dict[str, Any]:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()  # mandatory MCP handshake
                    result = await session.call_tool(tool, arguments)
                    return self._parse_result(result)

        return await asyncio.wait_for(_run(), timeout=self.timeout)

    @staticmethod
    def _parse_result(result: Any) -> Dict[str, Any]:
        """Extract the JSON payload from a CallToolResult's text content."""
        if getattr(result, "isError", False):
            return {}
        for block in getattr(result, "content", []) or []:
            text = getattr(block, "text", None)
            if not text:
                continue
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                continue
        return {}


__all__ = ["OpenFDAMCPClient", "SUPPORTED_TOOLS"]
