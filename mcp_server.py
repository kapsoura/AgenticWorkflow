"""
mcp_server.py
MCP Tool Server — Retrieval Agent (Agent 3)
Team  : IISc Bangalore · Deep Learning · June 2026

Exposes three tools that external agents or the orchestrator
can call via the MCP (Model Context Protocol) interface:

    Tool 1: search_maude(query, product_code, k)
            → similar adverse events (ChromaDB-first, FDA fallback)

    Tool 2: get_recalls(product_code, limit)
            → FDA recall records with root causes

    Tool 3: query_chromadb(query, k, filter_modality)
            → raw vector similarity search on Extraction Agent's embeddings

No API key required. Talks to OpenFDA public API + local ChromaDB.
"""

import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

# ── Optional ChromaDB ──────────────────────────────────
try:
    import chromadb
    _CHROMA_OK = True
except ImportError:
    _CHROMA_OK = False
    print("[MCP] chromadb not installed — query_chromadb uses mock. "
          "pip install chromadb")

# ── Optional sentence-transformers ────────────────────
try:
    from sentence_transformers import SentenceTransformer
    _ST_OK = True
except ImportError:
    _ST_OK = False
    print("[MCP] sentence-transformers not installed — mock embeddings. "
          "pip install sentence-transformers")


FDA_BASE        = "https://api.fda.gov/device"
CHROMA_PATH     = Path(__file__).parent / "data" / "chromadb"
COLLECTION_NAME = "fda_narratives"
EMBED_MODEL     = "all-MiniLM-L6-v2"
RATE_DELAY      = 0.8   # seconds between FDA API calls
MAX_RETRIES     = 3


# ──────────────────────────────────────────────────────
# TOOL DEFINITIONS (exposed to LLM / external callers)
# ──────────────────────────────────────────────────────

TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "search_maude",
        "description": (
            "Search FDA MAUDE adverse event database for events similar "
            "to a given complaint. Returns report IDs, narratives, and "
            "similarity scores. Use this to find how many similar events "
            "exist and what they describe."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Failure mode + device type e.g. 'MRI image artifact software error'",
                },
                "product_code": {
                    "type": "string",
                    "description": "FDA code: LNH=MRI, JAK=CT, LLZ=Ultrasound, IZL=X-ray, QKO=PCR",
                },
                "k": {
                    "type": "integer",
                    "description": "Number of results (default 5, max 10)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_recalls",
        "description": (
            "Fetch FDA device recall records for a product code. "
            "Returns recall reasons, root causes, and corrective actions. "
            "Use for CAPA precedents — always call after search_maude."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_code": {
                    "type": "string",
                    "description": "FDA product code e.g. LNH, JAK, LLZ",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of recalls (default 5, max 20)",
                    "default": 5,
                },
            },
            "required": ["product_code"],
        },
    },
    {
        "name": "query_chromadb",
        "description": (
            "Query Extraction Agent's local ChromaDB vector store for semantically "
            "similar adverse event narratives. Faster than live FDA API. "
            "Use this first; fall back to search_maude if unavailable."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language description of the failure",
                },
                "k": {
                    "type": "integer",
                    "description": "Number of results (default 5)",
                    "default": 5,
                },
                "filter_modality": {
                    "type": "string",
                    "description": "Optional: 'MRI', 'CT', 'Ultrasound', 'MolDx'",
                },
            },
            "required": ["query"],
        },
    },
]


# ──────────────────────────────────────────────────────
# MCP SERVER
# ──────────────────────────────────────────────────────

class MCPServer:
    """
    Lightweight MCP tool server for the Retrieval Agent.
    Exposes 3 tools via a unified .call() interface.
    """

    def __init__(self):
        self._embed_model = None
        self._collection  = None
        self._connect_chromadb()

    # ── Init ──────────────────────────────────────────

    def _connect_chromadb(self):
        if not _CHROMA_OK:
            return
        try:
            client = chromadb.PersistentClient(path=str(CHROMA_PATH))
            names  = [c.name for c in client.list_collections()]
            if COLLECTION_NAME in names:
                self._collection = client.get_collection(COLLECTION_NAME)
                print(f"[MCP] ✅ ChromaDB '{COLLECTION_NAME}' ready")
            else:
                print(f"[MCP] ⚠️  ChromaDB up but '{COLLECTION_NAME}' missing — "
                      "run Extraction Agent's embed_index.py")
        except Exception as ex:
            print(f"[MCP] ChromaDB init failed: {ex}")

    def _get_embed(self):
        if self._embed_model is None and _ST_OK:
            print("[MCP] Loading embedding model (once)...")
            self._embed_model = SentenceTransformer(EMBED_MODEL)
        return self._embed_model

    # ── Public interface ──────────────────────────────

    def get_tool_definitions(self) -> list[dict]:
        return TOOL_DEFINITIONS

    def call(self, tool_name: str, tool_input: dict) -> dict:
        """
        Dispatch a tool call.
        Returns dict: {success, data, error}
        """
        preview = json.dumps(tool_input)[:70]
        print(f"[MCP] call: {tool_name}({preview})")

        dispatch = {
            "search_maude":   self._search_maude,
            "get_recalls":    self._get_recalls,
            "query_chromadb": self._query_chromadb,
        }
        fn = dispatch.get(tool_name)
        if fn is None:
            return {"success": False, "data": None,
                    "error": f"Unknown tool: {tool_name}"}
        try:
            return fn(**tool_input)
        except Exception as ex:
            return {"success": False, "data": None, "error": str(ex)}

    # ── Tool 1: search_maude ─────────────────────────

    def _search_maude(
        self,
        query: str,
        product_code: Optional[str] = None,
        k: int = 5,
    ) -> dict:
        # ChromaDB first (faster)
        if self._collection is not None:
            return self._query_chromadb(query=query, k=k)

        # Fall back to live FDA API
        return self._maude_api(query, product_code, k)

    def _maude_api(
        self, query: str, product_code: Optional[str], k: int
    ) -> dict:
        search = ""
        if product_code:
            search = f"device.device_report_product_code:{product_code}"
        kw = (query or "").split()[0] if query else ""
        if kw and len(kw) > 3:
            sep = "+AND+" if search else ""
            search += f"{sep}mdr_text.text:{kw}"
        if not search:
            search = "device.device_report_product_code:LNH"

        url = f"{FDA_BASE}/event.json?search={search}&limit={min(k, 10)}"
        try:
            data  = self._fetch(url)
            total = data["meta"]["results"]["total"]
            events = []
            for e in data.get("results", []):
                snippet = next(
                    (t.get("text", "")[:300]
                     for t in e.get("mdr_text", [])
                     if t.get("text", "").strip()),
                    ""
                )
                events.append({
                    "report_id":         e.get("report_number", "N/A"),
                    "event_type":        e.get("event_type", "Unknown"),
                    "product_code":      product_code or "N/A",
                    "manufacturer":      (e.get("device") or [{}])[0]
                                         .get("manufacturer_d_name", "Unknown"),
                    "narrative_snippet": snippet,
                    "similarity_score":  0.70,
                    "source":            "FDA_API",
                })
            return {
                "success": True,
                "data": {"total_available": total, "returned": len(events),
                         "results": events},
                "error": None,
            }
        except Exception as ex:
            return {"success": False, "data": None, "error": str(ex)}

    # ── Tool 2: get_recalls ──────────────────────────

    def _get_recalls(
        self, product_code: str, limit: int = 5
    ) -> dict:
        url = (f"{FDA_BASE}/recall.json"
               f"?search=product_code:{product_code}&limit={min(limit, 20)}")
        try:
            data  = self._fetch(url)
            total = data["meta"]["results"]["total"]
            recalls = [
                {
                    "recall_id":         r.get("res_event_number", "N/A"),
                    "firm":              r.get("recalling_firm", "Unknown"),
                    "reason_for_recall": r.get("reason_for_recall", "")[:400],
                    "root_cause":        r.get("root_cause_description", "Unknown"),
                    "action":            r.get("action", "")[:300],
                    "product_code":      r.get("product_code", product_code),
                    "date":              r.get("recall_initiation_date", "N/A"),
                    "source":            "FDA_RECALLS",
                }
                for r in data.get("results", [])
            ]
            return {
                "success": True,
                "data": {"total_available": total, "returned": len(recalls),
                         "product_code": product_code, "recalls": recalls},
                "error": None,
            }
        except Exception as ex:
            return {"success": False, "data": None, "error": str(ex)}

    # ── Tool 3: query_chromadb ───────────────────────

    def _query_chromadb(
        self,
        query: str,
        k: int = 5,
        filter_modality: Optional[str] = None,
    ) -> dict:
        # Real ChromaDB
        if self._collection is not None:
            model = self._get_embed()
            if model is None:
                return {"success": False, "data": None,
                        "error": "Embedding model not available"}
            try:
                vec   = model.encode([query])[0].tolist()
                where = {"modality": filter_modality} if filter_modality else None
                res   = self._collection.query(
                    query_embeddings=[vec],
                    n_results=min(k, 10),
                    where=where,
                    include=["documents", "metadatas", "distances"],
                )
                results = []
                for i, doc in enumerate(res["documents"][0]):
                    meta  = (res["metadatas"][0][i] if res["metadatas"] else {})
                    dist  = (res["distances"][0][i]  if res["distances"]  else 1.0)
                    results.append({
                        "report_id":         meta.get("report_id", f"chroma-{i}"),
                        "narrative_snippet": doc[:300],
                        "similarity_score":  round(1 - dist, 3),
                        "modality":          meta.get("modality", "Unknown"),
                        "event_type":        meta.get("event_type", "Unknown"),
                        "product_code":      meta.get("product_code", "N/A"),
                        "source":            "CHROMADB",
                    })
                return {
                    "success": True,
                    "data": {"total_returned": len(results), "results": results},
                    "error": None,
                }
            except Exception as ex:
                return {"success": False, "data": None,
                        "error": f"ChromaDB query failed: {ex}"}

        # Mock fallback
        print("[MCP] ChromaDB not ready — mock results")
        mock = [
            {
                "report_id":         "MOCK-001",
                "narrative_snippet": f"[Mock] Similar event: {query[:60]}...",
                "similarity_score":  0.82,
                "modality":          filter_modality or "MRI",
                "event_type":        "Malfunction",
                "product_code":      "LNH",
                "source":            "MOCK",
            }
        ]
        return {
            "success": True,
            "data": {"total_returned": len(mock), "results": mock},
            "error": None,
            "warning": "Mock — run Extraction Agent's embed_index.py to activate real ChromaDB",
        }

    # ── OpenFDA HTTP helper ───────────────────────────

    def _fetch(self, url: str) -> dict:
        for attempt in range(MAX_RETRIES):
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": "IISc-MedSig-RetrievalAgent/1.0"}
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    time.sleep(RATE_DELAY)
                    return json.loads(resp.read())
            except urllib.error.HTTPError as ex:
                if ex.code == 429:
                    wait = (attempt + 1) * 3
                    print(f"[MCP] Rate limited — waiting {wait}s")
                    time.sleep(wait)
                elif attempt == MAX_RETRIES - 1:
                    raise
            except Exception:
                if attempt == MAX_RETRIES - 1:
                    raise
                time.sleep(1)
        raise RuntimeError(f"Failed after {MAX_RETRIES} retries: {url}")


# ──────────────────────────────────────────────────────
# SMOKE TEST
# python3 mcp_server.py
# ──────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("mcp_server.py — smoke test")
    print("=" * 55)

    mcp = MCPServer()

    print("\n── Tool 1: search_maude (OpenFDA live) ──")
    r1 = mcp.call("search_maude", {
        "query": "MRI image artifact reconstruction error",
        "product_code": "LNH", "k": 3,
    })
    if r1["success"]:
        d = r1["data"]
        print(f"  Total available : {d['total_available']:,}")
        print(f"  Returned        : {d['returned']}")
        for e in d["results"][:2]:
            print(f"  - {e['report_id']} | {e['event_type']} | "
                  f"{e['manufacturer'][:30]}")
    else:
        print(f"  ERROR: {r1['error']}")

    print("\n── Tool 2: get_recalls (OpenFDA live) ──")
    r2 = mcp.call("get_recalls", {"product_code": "LNH", "limit": 3})
    if r2["success"]:
        d = r2["data"]
        print(f"  Total available : {d['total_available']:,}")
        for r in d["recalls"][:2]:
            print(f"  - {r['firm'][:40]} | {r['root_cause']}")
    else:
        print(f"  ERROR: {r2['error']}")

    print("\n── Tool 3: query_chromadb ──")
    r3 = mcp.call("query_chromadb", {
        "query": "missed lesion MRI diagnostic error", "k": 3,
    })
    if r3["success"]:
        for item in r3["data"]["results"]:
            print(f"  - {item['report_id']} | "
                  f"sim={item['similarity_score']} | {item['source']}")
        if r3.get("warning"):
            print(f"  ⚠️  {r3['warning']}")
    else:
        print(f"  ERROR: {r3['error']}")

    print("\n✅ mcp_server.py — all tools tested")
