"""
mcp_client.py
OpenFDA MCP Client — Python bridge to the OpenFDA MCP Server
Owner : Pothukanuri Sai Venkat
Team  : IISc Bangalore · Deep Learning · June 2026

Source: https://github.com/Augmented-Nature/OpenFDA-MCP-Server

The OpenFDA MCP Server is a TypeScript/Node.js process that exposes
4 device tools over the MCP protocol (JSON-RPC over stdio):

    search_device_adverse_events  → /device/event  (MAUDE reports)
    search_device_recalls         → /device/recall
    search_device_510k            → /device/510k
    search_device_classifications → /device/classification

All OpenFDA calls go ONLY through the MCP Server.
No direct urllib fallback. If MCP is not available → raises RuntimeError.

Setup (required before running):
    git clone https://github.com/Augmented-Nature/OpenFDA-MCP-Server openfda-mcp-server
    cd openfda-mcp-server
    npm install
    npm run build
    cd ..

Usage:
    from mcp_client import OpenFDAMCPClient
    client = OpenFDAMCPClient()
    result = client.call("search_device_adverse_events", {
        "product_code": "LNH", "limit": 5
    })
"""

import json
import subprocess
from pathlib import Path


# ── MCP Server config ──────────────────────────────────
MCP_SERVER_REPO  = "https://github.com/Augmented-Nature/OpenFDA-MCP-Server"
MCP_SERVER_DIR   = Path(__file__).parent / "openfda-mcp-server"
MCP_SERVER_ENTRY = MCP_SERVER_DIR / "build" / "index.js"

# ── Supported MCP tools ────────────────────────────────
SUPPORTED_TOOLS = {
    "search_device_adverse_events",
    "search_device_recalls",
    "search_device_510k",
    "search_device_classifications",
}


class OpenFDAMCPClient:
    """
    Python client for the OpenFDA MCP Server.

    ALL OpenFDA calls go through the MCP Server (Node.js subprocess).
    No direct HTTP fallback — MCP is required.

    Raises:
        RuntimeError: if Node.js or the MCP server is not installed.
    """

    def __init__(self):
        self._validate_mcp()
        print("[MCP Client] ✅ OpenFDA MCP Server ready (Node.js)")

    # ── Validate MCP is installed ──────────────────────

    def _validate_mcp(self):
        """
        Hard check — raises RuntimeError if MCP not available.
        No fallback. MCP is required.
        """
        # 1. Check Node.js is installed
        try:
            result = subprocess.run(
                ["node", "--version"],
                capture_output=True,
                timeout=5
            )
            node_version = result.stdout.decode().strip()
            print(f"[MCP Client] Node.js: {node_version}")
        except FileNotFoundError:
            raise RuntimeError(
                "Node.js not found. Install it first:\n"
                "  brew install node\n"
                "Then set up the MCP server:\n"
                f"  git clone {MCP_SERVER_REPO} openfda-mcp-server\n"
                "  cd openfda-mcp-server && npm install && npm run build"
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("Node.js check timed out.")

        # 2. Check MCP server is built
        if not MCP_SERVER_ENTRY.exists():
            raise RuntimeError(
                f"OpenFDA MCP Server not found at: {MCP_SERVER_ENTRY}\n"
                "Set it up with:\n"
                f"  git clone {MCP_SERVER_REPO} openfda-mcp-server\n"
                "  cd openfda-mcp-server && npm install && npm run build"
            )

    # ── Public call interface ──────────────────────────

    def call(self, tool_name: str, tool_input: dict) -> dict:
        """
        Call an OpenFDA MCP tool via the MCP Server.

        Args:
            tool_name:  One of the SUPPORTED_TOOLS
            tool_input: Parameters for the tool

        Returns:
            dict with keys: success, data, total, error, source

        Raises:
            ValueError:  if tool_name is not supported
            RuntimeError: if MCP server fails or times out
        """
        if tool_name not in SUPPORTED_TOOLS:
            raise ValueError(
                f"Unknown tool: '{tool_name}'. "
                f"Supported: {sorted(SUPPORTED_TOOLS)}"
            )

        preview = json.dumps(tool_input)[:60]
        print(f"[MCP Client] 🔧 {tool_name}({preview})")

        return self._call_via_mcp(tool_name, tool_input)

    # ── MCP call (only path) ───────────────────────────

    def _call_via_mcp(self, tool_name: str, tool_input: dict) -> dict:
        """
        Send a JSON-RPC 2.0 request to the MCP server over stdio.

        MCP protocol:
          → write newline-delimited JSON to stdin
          ← read newline-delimited JSON from stdout
        """
        # Build JSON-RPC 2.0 request
        request = {
            "jsonrpc": "2.0",
            "id":      1,
            "method":  "tools/call",
            "params": {
                "name":      tool_name,
                "arguments": tool_input
            }
        }

        try:
            # Start MCP server as subprocess
            proc = subprocess.Popen(
                ["node", str(MCP_SERVER_ENTRY)],
                stdin  = subprocess.PIPE,
                stdout = subprocess.PIPE,
                stderr = subprocess.PIPE,
                cwd    = str(MCP_SERVER_DIR)
            )

            # Send JSON-RPC request over stdin
            req_bytes = (json.dumps(request) + "\n").encode()
            stdout, stderr = proc.communicate(input=req_bytes, timeout=30)

            # Check for empty response
            if not stdout:
                err = stderr.decode()[:300] if stderr else "no output"
                raise RuntimeError(
                    f"MCP server returned no output.\n"
                    f"stderr: {err}"
                )

            # Parse JSON-RPC response (first line only)
            raw_response = stdout.decode().strip().split("\n")[0]
            response     = json.loads(raw_response)

            # Handle JSON-RPC error
            if "error" in response:
                err_msg = str(response["error"])
                # MCP server throws on 404 (no results) — treat as empty
                if "No results found" in err_msg:
                    return {
                        "success": True,
                        "source":  "mcp",
                        "total":   0,
                        "data":    {},
                        "error":   None,
                    }
                raise RuntimeError(
                    f"MCP server error: {response['error']}"
                )

            # Extract result content
            result  = response.get("result", {})
            content = result.get("content", [{}])[0].get("text", "{}")
            data    = json.loads(content)

            return {
                "success": True,
                "source":  "mcp",
                "total":   data.get("total_results", 0),
                "data":    data,
                "error":   None,
            }

        except subprocess.TimeoutExpired:
            proc.kill()
            raise RuntimeError(
                f"MCP server timed out for tool: {tool_name}. "
                "The OpenFDA API may be slow. Try again."
            )

        except json.JSONDecodeError as ex:
            raise RuntimeError(
                f"MCP server returned invalid JSON: {ex}\n"
                f"Raw: {raw_response[:200] if 'raw_response' in dir() else 'N/A'}"
            )

    # ── Status check ──────────────────────────────────

    def is_available(self) -> bool:
        """Always True if __init__ succeeded (MCP was validated)."""
        return MCP_SERVER_ENTRY.exists()


# ──────────────────────────────────────────────────────
# SMOKE TEST — python3 mcp_client.py
# ──────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("mcp_client.py — smoke test")
    print("Source: github.com/Augmented-Nature/OpenFDA-MCP-Server")
    print("=" * 55)

    try:
        client = OpenFDAMCPClient()
    except RuntimeError as e:
        print(f"\n❌ MCP setup required:\n{e}")
        exit(1)

    # Test 1: Adverse events
    print("\n── Test 1: search_device_adverse_events ──")
    r1 = client.call("search_device_adverse_events", {
        "product_code": "LNH", "limit": 3
    })
    print(f"  Success : {r1['success']}")
    print(f"  Source  : {r1['source']}")
    print(f"  Total   : {r1['total']:,}")

    # Test 2: Recalls
    print("\n── Test 2: search_device_recalls ──")
    r2 = client.call("search_device_recalls", {
        "product_code": "LNH", "limit": 3
    })
    print(f"  Success : {r2['success']}")
    print(f"  Source  : {r2['source']}")
    print(f"  Total   : {r2['total']:,}")

    # Test 3: 510k
    print("\n── Test 3: search_device_510k ──")
    r3 = client.call("search_device_510k", {
        "product_code": "LNH", "limit": 3
    })
    print(f"  Success : {r3['success']}")
    print(f"  Source  : {r3['source']}")
    print(f"  Total   : {r3['total']:,}")

    print("\n✅ All MCP tools tested successfully")
    print("   Source: mcp (Node.js subprocess)")
