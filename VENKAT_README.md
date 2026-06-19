# Agent 3 — FDA Evidence Retrieval Agent
**Owner:** Pothukanuri Sai Venkat (`saivenkatp@iisc.ac.in`)  
**GitHub:** [@Pothukanuri](https://github.com/Pothukanuri)  
**Project:** IISc Bangalore · Deep Learning · June 2026  
**Spec:** [US-11 Retrieval Agent](specs/US-11-retrieval-agent.md)

---

## What This Agent Does

Given a structured complaint (from Extraction Agent (Agent 1)), this agent:

1. **Plans** — LLM decides which tools to call based on the complaint *(not hardcoded)*
2. **Retrieves** — hits OpenFDA adverse event database for similar cases
3. **Recalls** — fetches FDA recall records as CAPA precedents
4. **Counts** — measures event frequency for ISO 14971 probability calibration
5. **Searches** — queries Extraction Agent's local ChromaDB vector index for semantic matches
6. **Writes** — stores results in Orchestrator's shared `pipeline_state`

> → The LLM decides which tools to call. Different complaints → different tool plans.

---

## Files

| File | Description |
|------|-------------|
| `retrieval_agent.py` | Main agent — LLM planner + 5 tools + output builder |
| `mcp_server.py` | MCP tool server — exposes 3 tools to external callers |

---

## Architecture

```
ExtractionOutput
        │
        ▼
  LLM Tool Planner  ←── decides non-sequentially
        │
   ┌────┴────────────────────────────────┐
   │  search_adverse_events()            │  OpenFDA /device/event
   │  search_recalls()                   │  OpenFDA /device/recall
   │  count_events_by_problem()          │  OpenFDA count query
   │  search_chromadb()                  │  Extraction Agent's ChromaDB index
   │  get_device_info()                  │  OpenFDA /device/510k
   └─────────────────────────────────────┘
        │
        ▼
  RetrievalOutput  ──► pipeline_state  ──► **Risk Agent**
```

---

## OpenFDA Endpoints Used

| Tool | Endpoint | Purpose |
|------|----------|---------|
| `search_adverse_events` | `/device/event` | Similar MAUDE reports |
| `search_recalls` | `/device/recall` | CAPA precedents |
| `count_events_by_problem` | `/device/event` (count) | Probability calibration |
| `get_device_info` | `/device/510k` | Device background |
| `search_chromadb` | Local ChromaDB | Semantic similarity |

---

## Product Codes

| Code | Device | Used when |
|------|--------|-----------|
| LNH | MRI System | `modality = "MRI"` |
| JAK | CT Scanner | `modality = "CT"` |
| LLZ | Ultrasound | `modality = "Ultrasound"` |
| IZL | Digital X-ray | `modality = "X-ray"` |
| QKO | PCR / Molecular Dx | `modality = "MolDx"` |

---

## Setup & Run

```bash
# No API key needed — uses OpenFDA public API

# Install dependencies
pip install sentence-transformers chromadb

# Smoke test — MCP tools
python3 mcp_server.py

# Smoke test — full agent
python3 retrieval_agent.py
```

---

## Integration Points

| Dependency | From/To | What's needed |
|------------|---------|---------------|
| `ExtractionOutput` | ← | Output of `extraction_agent.py` |
| ChromaDB index | ←  | Run `embed_index.py` → share `data/chromadb/` folder |
| `pipeline_state` dict | ← | Pass `{}` into `agent.run(extraction, pipeline_state=state)` |
| `RetrievalOutput` | → | Feeds into `risk_agent.py` |

---

## Live Test Results

```
✅ search_adverse_events  →  125 real MRI MAUDE events (live FDA API)
✅ search_recalls         →  699 total recalls available (Hitachi, Philips...)
✅ count_events_by_problem → calibrated probability level
✅ search_chromadb        →  mock until embed_index.py is run
✅ pipeline_state written  →  keys: retrieval_output, tools_called, similar_event_count
```

---

## US-11 Compliance

| Requirement | Implementation |
|-------------|---------------|
| Precision@5 > 0.65 | Relevance gate: items < 0.30 dropped before handoff |
| Top-5 only downstream | `similar_events` capped at 5 most relevant |
| 429 resilience | Exponential backoff, falls back to local-only |
| Single-pass RAG first | ChromaDB query + FDA API, no ReAct loop by default |
| ReAct upgrade gated | Added only if Precision@5 measured < 0.65 |

---
