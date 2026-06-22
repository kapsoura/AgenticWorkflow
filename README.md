# Multi-Agent Quality Intelligence Pipeline

A multi-agent AI system for medical device signal intelligence. Given a raw FDA adverse event complaint, four specialized agents collaborate to extract structured facts, retrieve supporting evidence, assess ISO 14971 risk, and generate a regulatory-grade report.

**IISc Bangalore · Deep Learning (DA225o) · June 2026**

---

## Pipeline Overview

```
Raw MAUDE Complaint Narrative
        │
        ▼
┌─────────────────────────────┐
│  Agent 1 — Extraction       │  Mohammad Ayan Khan
│  Ollama/LLM → structured    │  src/extraction/agent.py
│  QMS complaint record       │  src/pipeline/
└────────────┬────────────────┘
             │  ExtractionOutput
             ▼
┌─────────────────────────────┐
│  Agent 3 — Retrieval        │  Pothukanuri Sai Venkat
│  LLM decides which tools    │  retrieval_agent.py
│  to call → OpenFDA evidence │  mcp_client.py / mcp_server.py
└────────────┬────────────────┘
             │  RetrievalEvidence (similar events, recalls, device info)
             ▼
┌─────────────────────────────┐
│  Agent 2 — Risk Assessment  │  Kapil (via OrchestrationAgent)
│  ISO 14971 risk bucketing   │  src/agents/risk_analysis.py
│  ACCEPTABLE / ALARP /       │
│  UNACCEPTABLE               │
└────────────┬────────────────┘
             │  RiskAssessment
             ▼
┌─────────────────────────────┐
│  Agent 4 — Report           │  Kapil
│  Generation                 │  src/agents/report_generation.py
│  LLM drafts + self-critique │  src/agents/report_sections.py
│  loop → PSUR / CAPA /       │
│  Incident Assessment report │
└─────────────────────────────┘
             │
             ▼
     Regulatory Report (Markdown + DOCX)
```

The **Orchestration Agent** (`src/agents/orchestration.py`) wires all four agents together with demand-driven section selection — it only runs the agents a given report type actually needs.

---

## Prerequisites

| Requirement | Purpose |
|---|---|
| Python ≥ 3.11 | Core runtime |
| Node.js ≥ 18 | OpenFDA MCP Server (Agent 3) |
| [Ollama](https://ollama.com) | Local LLM for Agent 1 (extraction) |
| Anthropic API key | Agent 4 report generation + risk analysis |
| Claude Code CLI (`claude`) | LLM tool-use backend (optional — degrades gracefully) |

---

## Setup

### 1. Clone and install Python dependencies

```bash
git clone <repo-url>
cd AgenticWorkflow
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — set at minimum:
#   ANTHROPIC_API_KEY  (for report generation)
#   OLLAMA_API_BASE    (for extraction — default: http://localhost:11434)
```

### 3. Install and start Ollama (Agent 1)

```bash
# Install from https://ollama.com, then:
ollama pull mistral-small
ollama serve
```

### 4. Install the OpenFDA MCP Server (Agent 3)

```bash
git clone https://github.com/Augmented-Nature/OpenFDA-MCP-Server openfda-mcp-server
cd openfda-mcp-server
npm install && npm run build
cd ..
```

---

## Running the Pipeline

### Full pipeline via FastAPI (all 4 agents)

```bash
cd Project
uvicorn src.api:app --reload --host 127.0.0.1 --port 8000
```

Then open `http://127.0.0.1:8000` in a browser, or POST a complaint:

```bash
curl -X POST http://127.0.0.1:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"narrative": "MRI system showed banding artifacts during cardiac sequence", "product_code": "LNH"}'
```

### Agent 1 only — Extraction + Trend Analysis (Ollama, no Anthropic key needed)

```bash
# Process a single complaint
python main.py --complaint "MRI system showed banding artifacts during cardiac sequence"

# Run full extraction pipeline on the local FDA database
python main.py --full

# Show database statistics
python main.py --stats
```

### Agent 3 only — Retrieval smoke test

```bash
# Start the MCP server first (in a separate terminal):
node openfda-mcp-server/build/index.js

# Then run the retrieval agent:
python retrieval_agent.py
```

### Run all tests

```bash
python -m pytest tests/ -v
# Expected: 47 passed
```

---

## Project Structure

```
AgenticWorkflow/
├── src/
│   ├── agents/               # All four agent implementations
│   │   ├── extraction.py     # Agent 1 — Anthropic-backed extraction
│   │   ├── retrieval.py      # Agent 3 — OpenFDA retrieval
│   │   ├── risk_analysis.py  # Agent 2 — ISO 14971 risk bucketing
│   │   ├── report_generation.py  # Agent 4 — report drafting + self-critique
│   │   ├── report_sections.py    # Section builders (demand-driven)
│   │   ├── orchestration.py  # Orchestration Agent — wires all four
│   │   └── archive_trend.py  # Trend analysis sub-agent
│   ├── extraction/           # Agent 1 (Ollama/LangChain variant)
│   ├── pipeline/             # Schemas, database, ingest, orchestrator
│   ├── embeddings/           # Sentence-transformer embedding generator
│   ├── trend/                # HDBSCAN cluster + trend analysis
│   ├── evaluation/           # Gold benchmark harness
│   ├── tools/                # Anthropic tool specs + tool loop
│   ├── observability/        # LangSmith tracing
│   └── utils/                # LLM client, prompt store, storage
├── configs/prompts/          # All LLM prompt templates (Markdown)
├── data/
│   ├── signal_intelligence.db    # Pre-ingested MAUDE adverse events (SQLite)
│   ├── embeddings.npz            # Pre-computed sentence embeddings
│   └── evaluation/gold_complaints.json  # Gold benchmark cases
├── tests/                    # 47 unit tests across all agents
├── main.py                   # Entry point for Agent 1 + trend pipeline
├── retrieval_agent.py        # Entry point for Agent 3 standalone
├── mcp_client.py             # OpenFDA MCP client
├── mcp_server.py             # MCP tool server
├── requirements.txt
└── .env.example
```

---

## Supported Device Types

| Product Code | Device |
|---|---|
| LNH | MRI System |
| JAK | CT Scanner |
| IYE | CT Scanner (variant) |
| LLZ | Ultrasound |
| IZL | Digital X-Ray |
| MQB | Molecular Dx Instrument |
| GKZ | Hematology Analyzer |
| QKO | PCR System |

---

## Key Design Decisions

- **MCP for OpenFDA**: Agent 3 makes all FDA API calls exclusively through an MCP server (JSON-RPC over stdio) — no direct HTTP calls from Python. This makes the tool interface swappable.
- **Demand-driven orchestration**: The Orchestration Agent selects only the sections each report type needs — a PSUR and a CAPA report run different agent subsets.
- **Evaluator-optimizer loop**: The Report Generation Agent runs a bounded self-critique loop (max 2 rounds) grading its draft against a citation rubric before finalizing.
- **Deterministic fallback**: Every LLM-backed path degrades gracefully to rule-based output when no API key or CLI is configured — the pipeline never hard-crashes.
- **ISO 14971 risk matrix**: Risk is bucketed into ACCEPTABLE / ALARP / UNACCEPTABLE using severity × probability, with LLM-backed rationale surfaced in the report.

---

## Team

| Agent | Owner |
|---|---|
| Agent 1 — Data Extraction + Trend | Mohammad Ayan Khan |
| Agent 3 — FDA Evidence Retrieval | Pothukanuri Sai Venkat |
| Agent 2/4 — Risk + Report Generation + Orchestration | Kapil |
| Integration + Merger | Pranav N |
