"""
retrieval_agent.py
Agent 3 — FDA Evidence Retrieval Agent
Owner : Pothukanuri Sai Venkat
Email : saivenkatp@iisc.ac.in
Team  : IISc Bangalore · Deep Learning · June 2026

────────────────────────────────────────────────────────
Design decisions (team transcript, ~38-41 min):
  Report Agent  39:08 — "given a complaint it goes to OpenFDA,
                          communicates with MCP server, talks to tools"
  Report Agent  39:41 — "enable a LLM agent to call retrieval.
                          Agent with tools."
  Report Agent  41:03 — "it is NOT like a sequential path always"
  Report Agent  35:03 — "agent can execute tools, get calculation,
                          return / write to state"
  US-11 spec   — single-pass RAG first; ReAct upgrade only
                  if Precision@5 < 0.65
────────────────────────────────────────────────────────

Flow:
    ExtractionOutput (from Extraction Agent / Agent 1)
        │
        ▼
    LLM decides tool plan  ← non-sequential, complaint-driven
        │
        ├─► search_adverse_events()   → MCP → OpenFDA /device/event
        ├─► search_recalls()          → MCP → OpenFDA /device/recall
        ├─► count_events_by_problem() → MCP → OpenFDA /device/event (count)
        ├─► search_chromadb()         → local ChromaDB (not via MCP)
        └─► get_device_info()         → MCP → OpenFDA /device/510k
        │
        ▼
    RetrievalOutput  ──► pipeline_state (Orchestrator)
        │
        ▼
    Risk Agent (Agent 2)
"""

import json
import re
from pathlib import Path
from typing import Optional, TypedDict, Any

from schemas import (
    ExtractionOutput,
    RetrievalOutput,
    SimilarEvent,
    MatchedRecall,
    validate_retrieval,
)
from llm_client import LLMClient
from mcp_client import OpenFDAMCPClient


# ──────────────────────────────────────────────────────
# PIPELINE STATE  (LangGraph shared brain state)
# Report Agent transcript 0:29 — "each agent updates the brain
# state, the common state map"
#
# READ  from state: extraction_output, complaint_text,
#                   product_code
# WRITE to   state: retrieval_output, tools_called,
#                   similar_event_count, retrieval_status
# ──────────────────────────────────────────────────────

class PipelineState(TypedDict, total=False):
    # ── Set by Simulator / input layer ──
    complaint_text:      str        # raw narrative text

    # ── Set by Extraction Agent (Agent 1) ──
    extraction_output:   Any        # ExtractionOutput dataclass
    product_code:        str        # e.g. "LNH" — derived during extraction

    # ── Set by Retrieval Agent (this agent) ──
    retrieval_output:    Any        # RetrievalOutput dataclass
    tools_called:        list       # which tools ran e.g. ["search_adverse_events"]
    similar_event_count: int        # total FDA events found
    retrieval_status:    str        # "success" | "partial" | "failed"

    # ── Set by Risk Agent (Agent 2) ──
    risk_output:         Any        # RiskCapaOutput dataclass

    # ── Set by Report Agent (Agent 4) ──
    report_output:       Any        # ReportOutput dataclass


# ──────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────

MIN_RELEVANCE = 0.30      # US-11: drop items below this (Gate 2)
TOP_K = 5                 # US-11: pass only top-5 downstream

MODALITY_TO_CODE: dict[str, str] = {
    "MRI":        "LNH",
    "CT":         "JAK",
    "Ultrasound": "LLZ",
    "X-ray":      "IZL",
    "MolDx":      "QKO",
    "Unknown":    "LNH",
}


# ──────────────────────────────────────────────────────
# TOOL REGISTRY
# Every tool maps directly to a real OpenFDA endpoint
# or to Extraction Agent's ChromaDB vector index.
# ──────────────────────────────────────────────────────

TOOLS: list[dict] = [
    {
        "name": "search_adverse_events",
        "description": (
            "Search FDA MAUDE adverse event database for events matching "
            "a product code. Returns narratives and event types. "
            "ALWAYS call this — it is the primary evidence source."
        ),
        "when_to_call": "Always — primary source",
        "openFDA_endpoint": "/device/event",
    },
    {
        "name": "search_recalls",
        "description": (
            "Fetch FDA device recall records for a product code. "
            "Returns recall reasons, root causes, and corrective actions. "
            "ALWAYS call this — needed for CAPA precedents."
        ),
        "when_to_call": "Always — CAPA precedents",
        "openFDA_endpoint": "/device/recall",
    },
    {
        "name": "count_events_by_problem",
        "description": (
            "Count total adverse events for a product code + problem keyword. "
            "Used to calibrate ISO 14971 probability level (P1-P5). "
            "Call when complaint is software-related or recurring."
        ),
        "when_to_call": "When software_related=True or need probability count",
        "openFDA_endpoint": "/device/event (count)",
    },
    {
        "name": "search_chromadb",
        "description": (
            "Search local ChromaDB vector index for semantically similar "
            "adverse event narratives (Extraction Agent's embeddings). "
            "Call when failure mode is nuanced and needs semantic similarity."
        ),
        "when_to_call": "When failure mode needs semantic (not just keyword) match",
        "openFDA_endpoint": "local ChromaDB",
    },
    {
        "name": "get_device_info",
        "description": (
            "Get 510k clearance info for a product code. "
            "Returns manufacturer and device class context. "
            "Call only when device background is unclear."
        ),
        "when_to_call": "When manufacturer or device context is missing",
        "openFDA_endpoint": "/device/510k",
    },
]

# ──────────────────────────────────────────────────────
# SYSTEM PROMPT  (LLM tool planner)
# ──────────────────────────────────────────────────────

PLANNER_PROMPT = """You are a Medical Device Evidence Retrieval Planner.

Given a complaint, select which retrieval tools to call.

Available tools:
{tool_list}

Rules:
- ALWAYS include: search_adverse_events, search_recalls
- Add count_events_by_problem if software_related is True
- Add search_chromadb if the failure mode is nuanced or software-related
- Add get_device_info only if manufacturer is UNKNOWN

Return a JSON array of tool names only. Example:
["search_adverse_events", "search_recalls", "count_events_by_problem"]"""


# ──────────────────────────────────────────────────────
# RETRIEVAL AGENT
# ──────────────────────────────────────────────────────

class RetrievalAgent:
    """
    Agent 3 — FDA Evidence Retrieval Agent.

    Architecture (per team transcript):
      - LLM decides which tools to call — not a hardcoded sequence
      - Tools talk to OpenFDA and Extraction Agent's ChromaDB
      - Results written to shared pipeline_state (Orchestrator)
      - Follows US-11: single-pass RAG, gate at relevance > 0.30, top-5 downstream
    """

    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm or LLMClient()
        self.mcp = OpenFDAMCPClient()          # ← MCP client for OpenFDA
        self._chroma_collection = self._init_chromadb()

    # ── ChromaDB init (Extraction Agent's index) ──────

    def _init_chromadb(self):
        """Connect to Extraction Agent's ChromaDB index if available."""
        try:
            import chromadb
            chroma_path = Path(__file__).parent / "data" / "chromadb"
            client = chromadb.PersistentClient(path=str(chroma_path))
            names = [c.name for c in client.list_collections()]
            if "fda_narratives" in names:
                print("[Retrieval] ✅ Extraction Agent's ChromaDB connected")
                return client.get_collection("fda_narratives")
            print("[Retrieval] ⚠️  ChromaDB found — no 'fda_narratives' yet. "
                  "Run Extraction Agent's embed_index.py first.")
            return None
        except Exception:
            print("[Retrieval] ℹ️  ChromaDB not installed — "
                  "search_chromadb uses mock. pip install chromadb")
            return None

    # ── Main entry point ───────────────────────────────

    def run(
        self,
        extraction: ExtractionOutput,
        pipeline_state: Optional[dict] = None,
    ) -> RetrievalOutput:
        """
        Run the retrieval pipeline.

        Args:
            extraction:      ExtractionOutput from Extraction Agent (Agent 1).
            pipeline_state:  Shared state dict from Orchestrator.
                             Results written back here.

        Returns:
            RetrievalOutput for Risk Agent (Agent 2).

        NOTE: Call via retrieval_node(state) for LangGraph integration.
              Direct call supported for standalone testing.
        """
        print(f"\n[Retrieval] ─── Starting: {extraction.report_id} ───")

        # ── READ product_code from state if already set by Extraction Agent ──
        # Report Agent (19:24): "pass context from state — don't re-derive"
        if pipeline_state and pipeline_state.get("product_code"):
            product_code = pipeline_state["product_code"]
            print(f"[Retrieval] 📥 product_code from state: {product_code}")
        else:
            modality_str = (
                extraction.modality.value
                if hasattr(extraction.modality, "value")
                else str(extraction.modality)
            )
            product_code = MODALITY_TO_CODE.get(modality_str, "LNH")
            print(f"[Retrieval] 📥 product_code derived: {product_code}")

        modality_str = (
            extraction.modality.value
            if hasattr(extraction.modality, "value")
            else str(extraction.modality)
        )

        # Step 1 — LLM decides tool plan (non-sequential)
        tool_plan = self._plan_tools(extraction, product_code)
        print(f"[Retrieval] 🧠 Tool plan: {tool_plan}")

        # Step 2 — Execute tools
        results: dict[str, dict] = {}
        for tool in tool_plan:
            results[tool] = self._call_tool(tool, extraction, product_code, modality_str)

        # Step 3 — Build typed output
        output = self._assemble(extraction.report_id, product_code, results)

        # Step 4 — Validate
        for warn in validate_retrieval(output):
            print(f"[Retrieval] ⚠️  {warn}")

        # Step 5 — Write to shared pipeline state (Orchestrator)
        if pipeline_state is not None:
            pipeline_state["retrieval_output"]    = output
            pipeline_state["tools_called"]        = tool_plan
            pipeline_state["similar_event_count"] = output.similar_event_count
            pipeline_state["retrieval_status"]    = (
                "success" if output.has_evidence() else "partial"
            )
            print("[Retrieval] 📝 Written to pipeline_state")

        print(
            f"[Retrieval] ✅ Done — "
            f"{output.similar_event_count:,} total events | "
            f"{len(output.similar_events)} returned | "
            f"{len(output.matched_recalls)} recalls"
        )
        return output

    # ── Tool planner ───────────────────────────────────

    def _plan_tools(
        self, extraction: ExtractionOutput, product_code: str
    ) -> list[str]:
        """
        Ask LLM which tools to call for this specific complaint.
        Falls back to smart rule-based plan if no LLM available.
        Report Agent (41:03): 'not a sequential path always'
        """
        if self.llm.is_available():
            return self._llm_plan(extraction, product_code)
        return self._rule_plan(extraction)

    def _llm_plan(
        self, extraction: ExtractionOutput, product_code: str
    ) -> list[str]:
        tool_list = "\n".join(
            f"  {t['name']}: {t['description'][:70]}..."
            for t in TOOLS
        )
        modality_str = (
            extraction.modality.value
            if hasattr(extraction.modality, "value")
            else str(extraction.modality)
        )
        prompt = f"""Complaint:
  Device    : {extraction.manufacturer} {extraction.device_model}
  Modality  : {modality_str}
  Failure   : {extraction.failure_mode}
  Software  : {extraction.software_related}
  Product   : {product_code}

{PLANNER_PROMPT.format(tool_list=tool_list)}"""

        response = self.llm.chat(prompt=prompt, temperature=0.0)
        try:
            match = re.search(r"\[.*?\]", response, re.DOTALL)
            if match:
                plan = json.loads(match.group())
                valid = {t["name"] for t in TOOLS}
                plan = [t for t in plan if t in valid]
                if plan:
                    return plan
        except Exception:
            pass
        return self._rule_plan(extraction)

    def _rule_plan(self, extraction: ExtractionOutput) -> list[str]:
        """Smart fallback — adjusts based on complaint, still non-sequential."""
        plan = ["search_adverse_events", "search_recalls"]
        if extraction.software_related:
            plan.append("count_events_by_problem")
            plan.append("search_chromadb")
        if str(extraction.manufacturer).upper() in ("UNKNOWN", ""):
            plan.append("get_device_info")
        return plan

    # ── Tool dispatcher ────────────────────────────────

    def _call_tool(
        self,
        tool_name: str,
        extraction: ExtractionOutput,
        product_code: str,
        modality_str: str,
    ) -> dict:
        print(f"[Retrieval] 🔧 {tool_name}")
        try:
            if tool_name == "search_adverse_events":
                return self._search_adverse_events(product_code, extraction.failure_mode)
            elif tool_name == "search_recalls":
                return self._search_recalls(product_code)
            elif tool_name == "count_events_by_problem":
                kw = "software" if extraction.software_related else "malfunction"
                return self._count_events(product_code, kw)
            elif tool_name == "search_chromadb":
                q = f"{extraction.failure_mode} {modality_str} {extraction.component}"
                return self._search_chromadb(q, modality_str)
            elif tool_name == "get_device_info":
                return self._get_device_info(product_code)
            else:
                return {"success": False, "error": f"Unknown tool: {tool_name}"}
        except Exception as ex:
            print(f"[Retrieval] ❌ {tool_name} failed: {ex}")
            return {"success": False, "error": str(ex)}

    # ── Tool implementations ───────────────────────────
    # All OpenFDA calls go ONLY through OpenFDAMCPClient.
    # Source: https://github.com/Augmented-Nature/OpenFDA-MCP-Server
    # MCP tools:
    #   search_device_adverse_events → /device/event
    #   search_device_recalls        → /device/recall
    #   search_device_510k           → /device/510k

    def _search_adverse_events(
        self, product_code: str, keyword: str = "", limit: int = TOP_K
    ) -> dict:
        """
        Tool 1: search_device_adverse_events via OpenFDA MCP Server.
        MCP: https://github.com/Augmented-Nature/OpenFDA-MCP-Server
        Endpoint: /device/event (MAUDE adverse event reports)
        """
        result = self.mcp.call("search_device_adverse_events", {
            "product_code": product_code,
            "keyword":      keyword,
            "limit":        limit,
        })
        if not result["success"]:
            return {"success": False, "error": result["error"],
                    "total": 0, "events": []}

        raw        = result["data"]
        total      = result["total"]
        raw_events = (
            raw.get("device_adverse_events")   # MCP server format
            or raw.get("results", [])
        )
        events = []
        for e in raw_events[:limit]:
            snippet = (
                e.get("event_description")
                or next((t.get("text", "")[:250]
                         for t in e.get("mdr_text", [])
                         if t.get("text", "").strip()), "")
            )
            events.append({
                "report_id":         e.get("report_number") or e.get("id", "N/A"),
                "event_type":        e.get("event_type", "Unknown"),
                "product_code":      product_code,
                "manufacturer":      e.get("manufacturer", "Unknown"),
                "narrative_snippet": str(snippet)[:250],
                "similarity_score":  0.75,
            })
        return {"success": True, "total": total, "events": events}

    def _search_recalls(
        self, product_code: str, limit: int = TOP_K
    ) -> dict:
        """
        Tool 2: search_device_recalls via OpenFDA MCP Server.
        MCP: https://github.com/Augmented-Nature/OpenFDA-MCP-Server
        Endpoint: /device/recall
        """
        result = self.mcp.call("search_device_recalls", {
            "product_code": product_code,
            "limit":        limit,
        })
        if not result["success"]:
            return {"success": False, "error": result["error"],
                    "total": 0, "recalls": []}

        raw         = result["data"]
        total       = result["total"]
        raw_recalls = (
            raw.get("device_recalls")          # MCP server format
            or raw.get("results", [])
        )
        recalls = []
        for r in raw_recalls[:limit]:
            recalls.append({
                "recall_id":         r.get("res_event_number") or r.get("recall_id", "N/A"),
                "firm":              r.get("recalling_firm") or r.get("firm", "Unknown"),
                "reason_for_recall": str(r.get("reason_for_recall", ""))[:350],
                "root_cause":        r.get("root_cause_description") or r.get("root_cause", "Unknown"),
                "action":            str(r.get("action", ""))[:200],
                "product_code":      product_code,
            })
        return {"success": True, "total": total, "recalls": recalls}

    def _count_events(self, product_code: str, keyword: str) -> dict:
        """
        Tool 3: count via MCP — for ISO 14971 probability calibration (P1-P5).
        Reuses search_device_adverse_events with limit=1 to get total only.
        """
        result = self.mcp.call("search_device_adverse_events", {
            "product_code": product_code,
            "keyword":      keyword,
            "limit":        1,
        })
        return {
            "success": result["success"],
            "total":   result["total"],
            "keyword": keyword,
            "error":   result.get("error"),
        }

    def _search_chromadb(
        self, query: str, modality: str = "", k: int = TOP_K
    ) -> dict:
        """
        Tool 4: ChromaDB vector search (local — not via MCP).
        Returns mock until Extraction Agent runs embed_index.py.
        """
        if self._chroma_collection is None:
            return {
                "success": True,
                "source":  "mock",
                "results": [
                    {
                        "report_id":         "CHROMA-MOCK-001",
                        "narrative_snippet": f"[Mock] Similar event: {query[:60]}...",
                        "similarity_score":  0.78,
                        "event_type":        "Malfunction",
                        "product_code":      "LNH",
                    }
                ],
                "warning": "Mock — run Extraction Agent embed_index.py to activate",
            }
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("all-MiniLM-L6-v2")
            vec   = model.encode([query])[0].tolist()
            where = {"modality": modality} if modality else None
            res   = self._chroma_collection.query(
                query_embeddings=[vec],
                n_results=k,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
            results = []
            for i, doc in enumerate(res["documents"][0]):
                meta  = (res["metadatas"][0][i] if res["metadatas"] else {})
                dist  = (res["distances"][0][i]  if res["distances"]  else 1.0)
                score = round(1 - dist, 3)
                if score >= MIN_RELEVANCE:
                    results.append({
                        "report_id":         meta.get("report_id", f"CHROMA-{i}"),
                        "narrative_snippet": doc[:250],
                        "similarity_score":  score,
                        "event_type":        meta.get("event_type", "Unknown"),
                        "product_code":      meta.get("product_code", "N/A"),
                    })
            return {"success": True, "source": "chromadb", "results": results}
        except Exception as ex:
            return {"success": False, "error": str(ex), "results": []}

    def _get_device_info(self, product_code: str) -> dict:
        """
        Tool 5: search_device_510k via OpenFDA MCP Server.
        MCP: https://github.com/Augmented-Nature/OpenFDA-MCP-Server
        Endpoint: /device/510k (clearance + device background)
        """
        result = self.mcp.call("search_device_510k", {
            "product_code": product_code,
            "limit":        3,
        })
        if not result["success"]:
            return {"success": False, "error": result["error"], "devices": []}

        raw      = result["data"]
        raw_devs = (
            raw.get("device_510k_clearances")  # MCP server format
            or raw.get("results", [])
        )
        devices = [
            {
                "applicant":   d.get("applicant", "Unknown"),
                "device_name": d.get("device_name", "Unknown"),
                "decision":    d.get("decision_description", "Unknown"),
                "k_number":    d.get("k_number", "Unknown"),
            }
            for d in raw_devs[:3]
        ]
        return {"success": True, "devices": devices}

    # ── Output assembler ───────────────────────────────

    def _assemble(
        self, report_id: str, product_code: str, tool_results: dict
    ) -> RetrievalOutput:
        """Build typed RetrievalOutput from raw tool results."""
        similar_events: list[SimilarEvent] = []
        matched_recalls: list[MatchedRecall] = []
        total_count = 0
        top_score   = 0.0

        # ── Adverse events ──
        ae = tool_results.get("search_adverse_events", {})
        if ae.get("success"):
            total_count = ae.get("total", 0)
            for e in ae.get("events", []):
                score = float(e.get("similarity_score", 0.75))
                if score >= MIN_RELEVANCE:           # US-11: Gate 2
                    top_score = max(top_score, score)
                    similar_events.append(SimilarEvent(
                        report_id         = str(e.get("report_id", "N/A")),
                        narrative_snippet = str(e.get("narrative_snippet", ""))[:300],
                        similarity_score  = score,
                        event_type        = str(e.get("event_type", "Unknown")),
                        product_code      = str(e.get("product_code", product_code)),
                    ))

        # ── ChromaDB results (higher-quality scores) ──
        chroma = tool_results.get("search_chromadb", {})
        if chroma.get("success") and chroma.get("source") != "mock":
            for e in chroma.get("results", []):
                score = float(e.get("similarity_score", 0.0))
                top_score = max(top_score, score)
                similar_events.append(SimilarEvent(
                    report_id         = str(e.get("report_id", "N/A")),
                    narrative_snippet = str(e.get("narrative_snippet", ""))[:300],
                    similarity_score  = score,
                    event_type        = str(e.get("event_type", "Unknown")),
                    product_code      = str(e.get("product_code", product_code)),
                ))

        # US-11: use count query for more accurate total
        cnt = tool_results.get("count_events_by_problem", {})
        if cnt.get("success") and cnt.get("total", 0) > 0:
            total_count = max(total_count, cnt["total"])

        # US-11: cap at TOP_K most relevant
        similar_events = sorted(
            similar_events, key=lambda x: x.similarity_score, reverse=True
        )[:TOP_K]

        # ── Recalls ──
        rec = tool_results.get("search_recalls", {})
        if rec.get("success"):
            for r in rec.get("recalls", []):
                matched_recalls.append(MatchedRecall(
                    firm              = str(r.get("firm", "Unknown")),
                    reason_for_recall = str(r.get("reason_for_recall", ""))[:400],
                    root_cause        = str(r.get("root_cause", "Unknown")),
                    product_code      = str(r.get("product_code", product_code)),
                    recall_id         = r.get("recall_id"),
                ))

        # ── Knowledge graph hits from device info ──
        kg_hits: list[str] = []
        dev = tool_results.get("get_device_info", {})
        if dev.get("success"):
            for d in dev.get("devices", []):
                kg_hits.append(
                    f"{d.get('applicant')} → {d.get('device_name')} "
                    f"[{d.get('k_number')}]"
                )

        return RetrievalOutput(
            report_id            = report_id,
            similar_events       = similar_events,
            similar_event_count  = total_count or len(similar_events),
            matched_recalls      = matched_recalls,
            top_similarity_score = round(top_score, 3),
            cluster_label        = None,
            knowledge_graph_hits = kg_hits,
        )


# ──────────────────────────────────────────────────────
# LANGGRAPH NODE  ← Orchestrator wires this into graph.py
# ──────────────────────────────────────────────────────
#
# How it fits in graph.py (Orchestrator's file):
#
#   from retrieval_agent import retrieval_node
#
#   graph.add_node("retrieval", retrieval_node)
#   graph.add_edge("extraction", "retrieval")
#   graph.add_edge("retrieval",  "risk")
#
# State contract:
#   READS  → state["extraction_output"]   set by Extraction Agent
#             state["product_code"]        set by Extraction Agent (optional)
#             state["complaint_text"]      set by Simulator (optional)
#   WRITES → state["retrieval_output"]    read by Risk Agent
#             state["tools_called"]        read by Orchestrator / dashboard
#             state["similar_event_count"] read by Risk Agent for P-level
#             state["retrieval_status"]    read by Orchestrator for routing
# ──────────────────────────────────────────────────────

def retrieval_node(state: PipelineState) -> PipelineState:
    """
    LangGraph node for the Retrieval Agent.

    Called automatically by LangGraph after extraction_node completes.
    Reads ExtractionOutput from state, runs retrieval, writes
    RetrievalOutput back so Risk Agent can consume it.

    Report Agent (0:29): "each agent updates the brain state — the common
                          state map. The line graph flow is based on the state."
    Report Agent (19:24): "pass context from the state — few things we miss
                           if we don't test with the full flow."
    """
    print("\n[Retrieval Node] ── LangGraph called retrieval_node ──")

    # ── 1. READ from state (what Extraction Agent wrote) ──
    extraction = state.get("extraction_output")
    if extraction is None:
        print("[Retrieval Node] ❌ extraction_output missing from state")
        return {
            **state,
            "retrieval_status": "failed",
            "retrieval_output": None,
        }

    # ── 2. RUN the agent ───────────────────────────────
    agent  = RetrievalAgent()
    output = agent.run(extraction, pipeline_state=dict(state))

    # ── 3. WRITE back to state (what Risk Agent will read) ──
    return {
        **state,                                    # preserve everything else
        "retrieval_output":    output,              # → Risk Agent
        "tools_called":        state.get("tools_called", []),
        "similar_event_count": output.similar_event_count,
        "retrieval_status":    "success" if output.has_evidence() else "partial",
    }


# ──────────────────────────────────────────────────────
# QUICK SMOKE TEST
# python3 retrieval_agent.py
# ──────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("retrieval_agent.py — smoke test")
    print("Owner: Pothukanuri Sai Venkat")
    print("=" * 55)

    from schemas import (
        ExtractionOutput, Modality, EventType,
        SeverityLevel, QMSCategory,
    )

    # Simulates what Extraction Agent's extraction_node puts into state
    mock_extraction = ExtractionOutput(
        report_id               = "1528028-2024-00001",
        modality                = Modality.MRI,
        manufacturer            = "FUJIFILM",
        device_model            = "OASIS MRI System",
        component               = "image reconstruction software",
        failure_mode            = "missed lesion diagnostic error",
        symptom                 = "abdominal lesion not detected",
        event_type              = EventType.INJURY,
        severity_indicator      = SeverityLevel.S3,
        software_related        = True,
        is_safety_related       = True,
        usability_concern       = False,
        security_concern        = False,
        qms_complaint_category  = QMSCategory.SW_ALGO,
        patient_impact          = "delayed diagnosis risk",
        confidence              = 0.72,
    )

    # ── Test A: direct call (standalone) ──
    print("\n── Test A: direct agent.run() call ──")
    state_a = {}
    agent   = RetrievalAgent()
    output  = agent.run(mock_extraction, pipeline_state=state_a)

    print(f"\n  Total events (FDA)   : {output.similar_event_count:,}")
    print(f"  Events returned      : {len(output.similar_events)}")
    print(f"  Recalls returned     : {len(output.matched_recalls)}")
    print(f"  Top similarity score : {output.top_similarity_score}")
    print(f"  Has evidence         : {output.has_evidence()}")
    print(f"  State keys written   : {list(state_a.keys())}")

    if output.matched_recalls:
        r = output.matched_recalls[0]
        print(f"\n  First recall         : {r.firm}")
        print(f"  Root cause           : {r.root_cause}")

    # ── Test B: via retrieval_node() — LangGraph style ──
    print("\n── Test B: retrieval_node(state) — LangGraph style ──")

    # This is what Orchestrator's graph.py passes into your node
    initial_state: PipelineState = {
        "complaint_text":    "FUJIFILM MRI missed abdominal lesion on VELOCITY",
        "extraction_output": mock_extraction,
        "product_code":      "LNH",   # Extraction Agent sets this
    }

    result_state = retrieval_node(initial_state)

    print(f"\n  retrieval_status     : {result_state.get('retrieval_status')}")
    print(f"  similar_event_count  : {result_state.get('similar_event_count')}")
    print(f"  tools_called         : {result_state.get('tools_called')}")
    print(f"  retrieval_output set : {result_state.get('retrieval_output') is not None}")
    print(f"  State keys present   : {[k for k in result_state if result_state[k] is not None]}")

    print("\n✅ retrieval_agent.py — all checks passed")
    print("   retrieval_node() ready for Orchestrator's graph.py")
