# Retrieval Agent — Agent 3
### Multi-Agent-Quality-Intelligence Pipeline

---

## Overview

The Retrieval Agent is **Agent 3** of the Medical Device Signal Intelligence pipeline.

Given a structured complaint from the Extraction Agent, it searches the FDA database for evidence — similar adverse events, recall records, and device background — and passes the findings to the Risk Agent for ISO 14971 risk assessment.

> **"It is not like a sequential path always"**
> The LLM decides which tools to call based on the complaint — not a hardcoded sequence.

---

## What It Does

```
Extraction Agent (Agent 1)
        │
        │  ExtractionOutput from shared pipeline state
        ▼
  Retrieval Agent (Agent 3)  ← you are here
        │
        │  LLM reads complaint → decides which tools to call
        │
        ├── search_device_adverse_events  →  MCP  →  OpenFDA /device/event
        ├── search_device_recalls         →  MCP  →  OpenFDA /device/recall
        ├── count_events_by_problem       →  MCP  →  OpenFDA /device/event (count)
        ├── search_chromadb              →  Local ChromaDB vector index
        └── get_device_info              →  MCP  →  OpenFDA /device/510k
        │
        │  RetrievalOutput written to shared pipeline state
        ▼
  Risk Agent (Agent 2)
```

---

## Architecture

### MCP Integration
All OpenFDA calls go **exclusively** through the OpenFDA MCP Server — no direct HTTP calls.

```
retrieval_agent.py
    │
    │  self.mcp.call("search_device_adverse_events", {...})
    ▼
mcp_client.py  (OpenFDAMCPClient)
    │
    │  JSON-RPC over stdio
    ▼
OpenFDA MCP Server (Node.js)
    │
    ▼
api.fda.gov
```

Source: [https://github.com/Augmented-Nature/OpenFDA-MCP-Server](https://github.com/Augmented-Nature/OpenFDA-MCP-Server)

### LangGraph State

The agent reads and writes to a shared `PipelineState` dictionary:

```python
# READS from state (set by Extraction Agent)
state["extraction_output"]   # structured complaint facts
state["product_code"]        # e.g. "LNH" for MRI

# WRITES to state (read by Risk Agent)
state["retrieval_output"]    # evidence bundle
state["tools_called"]        # which tools ran
state["similar_event_count"] # total FDA events found (used for P-level)
state["retrieval_status"]    # "success" | "partial" | "failed"
```

---

## Files

| File | Purpose |
|------|---------|
| `retrieval_agent.py` | Main agent — LLM planner + 5 tools + LangGraph node |
| `mcp_client.py` | MCP client — bridges Python to OpenFDA MCP Server |
| `mcp_server.py` | MCP tool server — exposes tools to external callers |

---

## OpenFDA Product Codes

| Code | Device |
|------|--------|
| LNH  | MRI System |
| JAK  | CT Scanner |
| LLZ  | Ultrasound |
| IZL  | Digital X-ray |
| QKO  | PCR / Molecular Dx |

---

## Setup

### 1. Install Python dependencies
```bash
pip install sentence-transformers chromadb
```

### 2. Install Node.js (for MCP Server)
```bash
brew install node
```

### 3. Set up OpenFDA MCP Server
```bash
git clone https://github.com/Augmented-Nature/OpenFDA-MCP-Server openfda-mcp-server
cd openfda-mcp-server
npm install
npm run build
cd ..
```

### 4. Optional — Install Ollama for real LLM tool planning
```bash
brew install ollama
ollama pull llama3.2
ollama serve
```

---

## Run

### Smoke test — MCP client
```bash
python3 mcp_client.py
```

### Smoke test — full agent
```bash
python3 retrieval_agent.py
```

### Expected output
```
[MCP Client] ✅ OpenFDA MCP Server ready (Node.js)
[Retrieval]  🧠 Tool plan: [search_device_adverse_events, search_device_recalls, ...]
[Retrieval]  🔧 search_device_adverse_events
[Retrieval]  🔧 search_device_recalls
[Retrieval]  ✅ Done — 125 total events | 5 returned | 5 recalls

── Test B: retrieval_node(state) — LangGraph style ──
  retrieval_status : success
  similar_event_count : 125
  retrieval_output set : True
```

---

## LangGraph Integration

Orchestrator imports and wires the node in `graph.py`:

```python
from retrieval_agent import retrieval_node

graph.add_node("retrieval", retrieval_node)
graph.add_edge("extraction", "retrieval")
graph.add_edge("retrieval",  "risk")
```

---

## US-11 Compliance

| Requirement | Implementation |
|-------------|---------------|
| Precision@5 > 0.65 | Relevance gate — items below 0.30 dropped |
| Top-5 only downstream | Events sorted by score, capped at 5 |
| 429 resilience | MCP Server handles retries internally |
| Single-pass RAG | ChromaDB + MCP, no ReAct loop by default |

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `sentence-transformers` | ≥ 3.0 | Text → embeddings for ChromaDB |
| `chromadb` | ≥ 0.5 | Local vector database |
| `node` | ≥ 18 | Runs OpenFDA MCP Server |

---

*IISc Bangalore · Deep Learning Project · Submission June 24, 2026*
