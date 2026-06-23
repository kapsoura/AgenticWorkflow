# Multi-Agent Quality Intelligence Pipeline

A multi-agent AI system for medical device signal intelligence. Given a raw FDA adverse event complaint, four specialized agents collaborate to extract structured facts, retrieve supporting evidence, assess ISO 14971 risk, and generate a regulatory-grade report.

**IISc Bangalore · Deep Learning (DA225o) · June 2026**


---

### Deployed App Link : https://multi-agent-quality-intellience-ui.vercel.app/dashboard

--- 

## Team

|  Members |
|---|
|  Mohammad Ayan Khan |
| Pothukanuri Sai Venkat |
|  Kashinath Alias Kapil Subhash Naik  |
|  Pranav N |
| Ritesh Patil |
| Anish Vijaykumar |

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
```

Open `.env` and fill in the values relevant to your setup:

| Variable | Required for | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | Report generation (Agent 4), risk analysis (Agent 2) | Get one at console.anthropic.com |
| `CLAUDE_CLI_PATH` | All LLM agents via CLI backend | See step 5 below |
| `OLLAMA_API_BASE` | Extraction via Ollama (Agent 1 variant) | Default: `http://localhost:11434` |
| `ANTHROPIC_MODEL` | Report generation model | Default: `claude-3-5-sonnet-latest` |
| `LANGCHAIN_API_KEY` | LangSmith tracing (optional) | Free at smith.langchain.com |

> **Fallback behaviour**: every LLM-backed agent degrades gracefully to deterministic
> rule-based output when its backend is not configured. The pipeline never hard-crashes —
> you will see `NOT_AVAILABLE` in LLM fields instead.

### 3. Install and start Ollama (Agent 1 — extraction variant)

```bash
# Install from https://ollama.com, then:
ollama pull mistral-small
ollama serve
```

### 4. Install the OpenFDA MCP Server (Agent 3 — Node.js required)

Agent 3's retrieval tools make all OpenFDA API calls through an MCP server that runs
as a separate Node.js process. **Node.js ≥ 18 must be installed before this step.**

```bash
# Install Node.js 18+ from https://nodejs.org if not already present:
node --version   # must be v18 or higher

# Clone and build the MCP server:
git clone https://github.com/Augmented-Nature/OpenFDA-MCP-Server openfda-mcp-server
cd openfda-mcp-server
npm install && npm run build
cd ..
```

The Python side (`mcp_client.py`) launches this server automatically as a subprocess
over stdio — you do **not** need to start it manually unless running `retrieval_agent.py`
standalone.

### 5. Set up the Claude Code CLI (`claude`) for LLM tool-use

Agents 1, 2, 3, and 4 all use the Claude Code CLI (`claude -p`) as their LLM backend.
This lets them run without a direct Anthropic API key by routing calls through the CLI.

```bash
# Install Claude Code CLI (requires Node.js):
npm install -g @anthropic-ai/claude-code

# Log in:
claude login

# Find the binary path:
which claude          # macOS / Linux  → e.g. /usr/local/bin/claude
(Get-Command claude).Source  # Windows PowerShell → e.g. C:\...\claude.cmd

# Add to .env:
CLAUDE_CLI_PATH=/usr/local/bin/claude
ANTHROPIC_MODEL_NAME=haiku   # or sonnet, opus — controls cost vs quality
```

Once `CLAUDE_CLI_PATH` is set, all agents switch from deterministic fallback to
full LLM-backed output automatically — no other changes needed.

---

## Running the Pipeline

### Demo — all 4 agents in one command (recommended)

```bash
python demo.py                          # offline — uses pre-ingested SQLite archive
python demo.py --product-code JAK       # CT Scanner variant
python demo.py --live                   # live OpenFDA API via MCP (see setup below)
```

**What each run shows:**

| Agent | Output |
|---|---|
| 1 — Extraction | LLM classifies complaint → QMS category, confidence, ISO 13485 clauses |
| 3 — Retrieval | Fuzzy-match against 9,840 FDA MAUDE events (offline) or live OpenFDA API |
| 2 — Risk | Two-pass ISO 14971:2019 assessment → severity × probability → ACCEPTABLE / ALARP / UNACCEPTABLE |
| 4 — Report | LLM drafts PSUR / CAPA / Incident report + self-critique loop flags weak citations |

**Supported device types:**

| `--product-code` | Device |
|---|---|
| `LNH` (default) | MRI System |
| `JAK` | CT Scanner |
| `LLZ` | Ultrasound |
| `IYE` | CT X-ray |
| `IZL` | Digital X-ray |
| `MQB` | Molecular Dx Instrument |
| `GKZ` | Hematology Analyzer |
| `QKO` | PCR System |

**Live MCP setup** (required only for `--live`):

```bash
# Clone and build the OpenFDA MCP server next to the project:
git clone https://github.com/Augmented-Nature/OpenFDA-MCP-Server openfda-mcp-server
cd openfda-mcp-server
npm install && npm run build
cd ..

# Then run:
python demo.py --live
```

The `--live` flag switches Agent 3 from the offline SQLite archive to real-time FDA data
via Sai's MCP client (`mcp_client.py` → `node openfda-mcp-server/build/index.js` subprocess).
No separate terminal needed — the Node.js process is launched and managed automatically.

**`Review Needed: YES` is expected behaviour** — the self-critique loop intentionally flags
sections where LLM claims lack grounded FDA citations, so a human QM officer can review
before sign-off. This is the evaluator-optimizer loop working as designed.

---

### Full app — web UI (React + Vite) + FastAPI backend

The app is split into a **FastAPI backend** (`api/server.py`) and a **React + Vite
frontend** (`ui/`). The frontend dev server proxies `/api` and `/health` to the
backend on port 8000 (see `ui/vite.config.ts`).

**1. Start the backend** (terminal 1, from the repo root):

```bash
# Windows (PowerShell, project venv):
.\.venv-1\Scripts\python.exe -m uvicorn api.server:app --reload --host 127.0.0.1 --port 8000

# macOS/Linux:
uvicorn api.server:app --reload --host 127.0.0.1 --port 8000
```

> The pipeline backend calls a local **Ollama** server (`mistral-small` at
> `http://localhost:11434`) for extraction. `/health`, `/api/stats` and
> `/api/trends` work without it; `/api/process` (complaint analysis) needs Ollama running.
> To enable **live OpenFDA** evidence, set `OPENFDA_LIVE_RETRIEVAL=1` before starting
> the backend (`$env:OPENFDA_LIVE_RETRIEVAL = "1"` on PowerShell).

**2. Start the frontend** (terminal 2):

```bash
cd ui
npm install      # first run only
npm run dev
```

Then open **http://localhost:5173** in a browser.

**Backend API endpoints** (base `http://127.0.0.1:8000`):

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/health` | Liveness check |
| `GET`  | `/api/meta` | Build/metadata info |
| `GET`  | `/api/stats` | FDA archive statistics |
| `GET`  | `/api/trends` | Trend/cluster summaries |
| `GET`  | `/api/clusters` | Pre-built HDBSCAN clusters |
| `GET`  | `/api/templates` | Report templates |
| `POST` | `/api/process` | Run the full pipeline on a complaint |
| `POST` | `/api/analyze` | Analyze a complaint |

Example — process a complaint directly via the API:

```bash
curl -X POST http://127.0.0.1:8000/api/process \
  -H "Content-Type: application/json" \
  -d '{"narrative": "MRI system showed banding artifacts during cardiac sequence", "report_id": "UI-001"}'
```

> **Production note:** the container image (`Dockerfile`) serves the backend with
> `uvicorn api.server:app`; the built frontend is deployed separately (GitHub Pages).

### Agent 1 only — Extraction + Trend Analysis

```bash
python main.py --complaint "MRI system showed banding artifacts during cardiac sequence"
python main.py --full    # full extraction pipeline on the local FDA database
python main.py --stats   # database statistics
```

### Agent 3 only — Retrieval smoke test

```bash
python mcp_client.py      # smoke test: calls all 4 OpenFDA tools and prints results
python retrieval_agent.py # full standalone Agent 3 run with mock ExtractionOutput
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
