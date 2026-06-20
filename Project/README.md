# Multi-Agent-Quality-Intelligence

An AI-agentic decision-support tool for medical-device post-market surveillance. It
ingests FDA adverse-event and recall data, simulates incoming complaints, and runs a
LangGraph multi-agent workflow that extracts structure, retrieves precedent, assesses
ISO 14971 risk, runs quality-intelligence analytics, and assembles a **section-driven,
report-type-specific** signal report for Quality Manager review.

> Decision support only. Every report is advisory; final disposition stays with the Quality Manager.

---

## 1. What it does (at a glance)

```
FDA data  ─▶  simulate complaints  ─▶  LangGraph agents  ─▶  signal report (.md) + trace (.jsonl)
```

- **Extraction agent** — structures the complaint (category, key issues, ISO 13485/14971 tags, confidence).
- **Subquery planner (orchestrator)** — decomposes the complaint into focused retrieval subqueries.
- **Retrieval agent** — multi-query search over MAUDE events + recalls + a local vector index; each hit is tagged with the subquery that found it.
- **Risk agent** — severity × probability → ISO 14971 bucket → routed report type.
- **Quality analytics toolbox** — runs theme-specific tools (pattern, root-cause, resource, predictive).
- **Orchestrator + report agent** — the report *type* selects which sections run, and each section drives the relevant agent on demand.

---

## 2. Products in scope

The active workflow scope is **fixed to three imaging product codes** (`src/config.py` → `PRODUCT_CODES`):

| Code | Device type   |
|------|---------------|
| LNH  | MRI System    |
| JAK  | CT Scanner    |
| LLZ  | Ultrasound Imaging System |

The downloader (`data/download_imaging_data.py`) also pulls additional codes (IYE, IZL,
MQB, GKZ, QKO) for exploration, but the running pipeline only processes LNH / JAK / LLZ.

---

## 3. Report types the system generates

Routing is deterministic (`src/agents/risk_analysis.py`):

| Report type            | When it is chosen                                        | Lead sections |
|------------------------|---------------------------------------------------------|---------------|
| `VIGILANCE_ESCALATION` | event type is injury/death **or** risk = UNACCEPTABLE   | Regulatory Notification, Risk, Subqueries, Evidence, Quality Intelligence, Immediate CAPA |
| `CAPA_INVESTIGATION`   | risk bucket = ALARP                                      | Risk, Subqueries, Evidence, Quality Intelligence, Trend, CAPA Plan |
| `TREND_MONITORING`     | everything else (ACCEPTABLE)                             | Trend, Subqueries, Evidence, Quality Intelligence, Monitoring Recommendation |

**Risk buckets** come from severity × probability score: `>=16` UNACCEPTABLE, `>=8` ALARP, else ACCEPTABLE.

### Is the report standardised?

Yes — **standardised in contract, adaptive in content**:

- Every report is built from a shared **section registry** and a **per-type blueprint**
  (`src/agents/report_sections.py`), so section titles, ordering, and the data contract
  (`SignalReport` in `src/pipeline/schemas.py`) are consistent and predictable.
- The *set* of sections varies by report type — a vigilance escalation is not padded with
  the same boilerplate as a trend report. This is the agentic, demand-driven behaviour:
  the report's structure decides which agents run.
- Every report carries a `trace_id`, evidence citations (source + score + subquery facet),
  and a compliance footer with review flags.

---

## 4. Prerequisites

- Python 3.13 (a virtual environment is expected; this repo uses `.venv-1`).
- Dependencies from the workspace-root `requirements.txt` (key ones: `langgraph`,
  `anthropic`, `chromadb`, `rapidfuzz`, `fastapi`, `uvicorn`, `python-dotenv`).
- Optional: the `claude` CLI (set `CLAUDE_CLI_PATH` in a `.env` file) to enable
  LLM-assisted extraction, tool-driven retrieval/trend analysis, and subquery
  enrichment. **Without it the system runs fully offline** using deterministic
  heuristics and local embeddings. No `ANTHROPIC_API_KEY` is required.

```powershell
# from the workspace root: d:\2025\personal\M.Tech\Course_May-June\Tutorial
..\.venv-1\Scripts\python.exe -m pip install -r requirements.txt
```

Optional `.env` (place in `Project/`):

```
CLAUDE_CLI_PATH=/path/to/claude
ANTHROPIC_MODEL_NAME=haiku
```

---

## 5. Step 1 — Download the data

Run the downloader from the `Project/data` folder. It calls the public openFDA API
(no key required) and writes per-batch JSON files plus recalls.

```powershell
cd Project\data
..\..\.venv-1\Scripts\python.exe download_imaging_data.py
```

This produces:

- `data/imaging_events/{CODE}_batch{n}.json` — adverse events (the pipeline reads these).
- `data/molecular_dx_events/...` — molecular Dx events (exploration only).
- `data/recalls/all_imaging_moldx_recalls.json` — combined recalls.

> **Important:** the pipeline's loader expects the recalls file at
> `data/recalls/all_recalls.json` (`src/config.py` → `RECALLS_FILE`), but the downloader
> writes `all_imaging_moldx_recalls.json`. After downloading, copy/rename it:
>
> ```powershell
> Copy-Item data\recalls\all_imaging_moldx_recalls.json data\recalls\all_recalls.json -Force
> ```
>
> A pre-downloaded `all_recalls.json` and `*_batch*.json` files are already committed, so
> you can skip Step 1 entirely and go straight to Step 2 (initialize the database).

---

## 6. Step 2 — Initialize the database (archive extraction)

Provision the runtime stores from the local FDA archive **before** running the
workflow. This creates the SQLite schema and extracts the adverse-event archive
into the Chroma vector index, so retrieval is ready on the first run.

```powershell
cd Project
..\.venv-1\Scripts\python.exe -m src.init_db --max-events-per-code 250
```

What it does (`src/init_db.py`):

- Loads events for the in-scope codes (LNH / JAK / LLZ) from `data/imaging_events/`.
- Creates the SQLite schema at `outputs/runtime/signal_intelligence.db`
  (`complaint_archive` + `signal_reports` tables).
- Extracts each event's product-problem text into the Chroma vector store at
  `outputs/runtime/chroma/` (one upsert pass per code).
- Prints a summary: events loaded per code, total events, and vectors indexed.

| Flag                    | Default | Meaning |
|-------------------------|---------|---------|
| `--max-events-per-code` | 300     | Archive events loaded and indexed per code |
| `--reset`               | off     | Delete the existing runtime DB + vector store, then rebuild |

> The workflow (Step 3) also initializes these stores lazily if you skip this
> step, but running `init_db` first makes provisioning explicit and lets you
> rebuild the vector index on its own (e.g. after refreshing the archive with
> `--reset`). The runtime stores under `outputs/runtime/` are git-ignored,
> regenerable artifacts.

---

## 7. Step 3 — Run / simulate the workflow

Run from the `Project` folder so `src` is importable as a package.

```powershell
cd Project
..\.venv-1\Scripts\python.exe -m src.run_workflow --complaints-per-code 1 --max-events-per-code 80 --seed 42
```

CLI options (`src/run_workflow.py`):

| Flag                    | Default | Meaning |
|-------------------------|---------|---------|
| `--complaints-per-code` | 6       | Complaints simulated per product code |
| `--max-events-per-code` | 250     | Archive events loaded per code |
| `--seed`                | 42      | Deterministic complaint simulation |

A successful run prints a JSON summary with `generated_report_paths` and
`generated_trace_paths`, and writes:

- **Reports** → `Project/outputs/reports/SR-<CODE>-<n>-<YYYYMMDD>.md`
- **Traces** → `Project/logs/<trace_id>.jsonl`
- **State** → SQLite at `Project/outputs/runtime/signal_intelligence.db`, vectors at `Project/outputs/runtime/chroma/`

### Optional — run as an API

```powershell
cd Project
..\.venv-1\Scripts\python.exe -m uvicorn src.api:app --host 127.0.0.1 --port 8000
```

- `GET /health` — liveness check.
- `POST /run` — body `{ "complaints_per_code": 1, "max_events_per_code": 80, "seed": 42 }`.

---

## 8. Reading the output

Open any file in `Project/outputs/reports/`. Each report contains, depending on its routed
type: metadata, complaint narrative, extraction summary, risk assessment, **investigation
subqueries**, evidence with per-facet citations, a **quality-intelligence** block, trend
context, CAPA/monitoring guidance, decision questions, and a compliance footer.

The matching `Project/logs/<trace_id>.jsonl` records per-agent latency, gate results, and
which sections were built — useful for observability and debugging.

### Optional — LangSmith tracing

The pipeline is a LangGraph workflow, so it can export full trace trees to
[LangSmith](https://smith.langchain.com) (one span per node, with the Claude calls
nested as `llm` spans). Tracing is **off by default**; the local `.jsonl` trace always
works without it.

To enable, add to `Project/.env` (get a free key at smith.langchain.com — never commit it):

```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=<your key>
LANGCHAIN_PROJECT=regulatory-signal-intelligence
```

On the next run the console prints `[langsmith] tracing enabled -> project '...'` and each
run appears in LangSmith named by its `trace_id`, so the cloud trace and the local
`logs/<trace_id>.jsonl` line up one-to-one. If the key or package is missing, tracing is
skipped with a notice and the run continues normally.

---

## 9. Project layout

```
Project/
  data/                       # openFDA downloaders + downloaded JSON
    download_imaging_data.py   # main data download script
    evaluation/                # gold benchmark (gold_complaints.json)
  src/
    run_workflow.py            # CLI entrypoint (simulate + run)
    init_db.py                 # provision SQLite + Chroma from the archive
    api.py                     # FastAPI entrypoint
    config.py                  # product codes, paths, model config
    pipeline/
      orchestrator.py          # top-level run loop (load, simulate, persist)
      langgraph_flow.py        # LangGraph graph + gates + tracing
      service.py               # single-complaint service (web/API path)
      schemas.py               # dataclass contracts + handoff validation
    agents/
      extraction.py            # complaint -> structured signal
      orchestration.py         # subquery planner + section-driven driver
      retrieval.py             # multi-query evidence retrieval
      risk_analysis.py         # ISO 14971 risk + report-type routing
      archive_trend.py         # trend summary
      report_sections.py       # section registry + per-type blueprints
      report_generation.py     # assembles the report from sections
    tools/                     # model-callable tools + tool-loop engine
      tool_loop.py             # Anthropic tool-calling loop (iteration + time caps)
      agent_tools.py           # tool-spec builders bound to agent context
      quality_tools.py         # quality-intelligence toolbox
    evaluation/                # gold-benchmark harness (metrics, gold, run_eval)
    observability/tracer.py    # JSONL trace logger
    utils/                     # data loader, storage (SQLite + Chroma), LLM client
  outputs/reports/             # generated reports (gitignored)
  outputs/runtime/             # SQLite DB + Chroma vector store (gitignored)
  logs/                        # trace logs (gitignored)
  specs/                       # user stories US-01..US-18 + coverage
```

---

## 10. Quick start (TL;DR)

```powershell
# 1. install deps (workspace root)
..\.venv-1\Scripts\python.exe -m pip install -r requirements.txt

# 2. (optional) refresh data — pre-downloaded data is already committed
cd Project\data
..\..\.venv-1\Scripts\python.exe download_imaging_data.py
Copy-Item recalls\all_imaging_moldx_recalls.json recalls\all_recalls.json -Force

# 3. initialize the database from the archive (creates SQLite + vector index)
cd ..
..\.venv-1\Scripts\python.exe -m src.init_db --max-events-per-code 250

# 4. run the workflow
..\.venv-1\Scripts\python.exe -m src.run_workflow --complaints-per-code 1 --max-events-per-code 80 --seed 42

# 5. read reports in Project/outputs/reports/
```

### Optional — evaluate against the gold benchmark

```powershell
cd Project
..\.venv-1\Scripts\python.exe -m src.evaluation.run_eval --max-events 250 --k 5
```

Writes a scored report to `outputs/evaluation/` (rejection accuracy, schema
validity, retrieval grounding, and — when an LLM backend is configured —
extraction / risk / escalation accuracy). Add `--strict` to exit non-zero on a
threshold miss.
