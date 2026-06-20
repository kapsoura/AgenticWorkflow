# Regulatory Signal Intelligence — Agentic Workflow

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
- Optional: an `ANTHROPIC_API_KEY` in a `.env` file to enable LLM-assisted extraction and
  subquery enrichment. **Without a key the system runs fully offline** using deterministic
  heuristics and local embeddings.

```powershell
# from the workspace root: d:\2025\personal\M.Tech\Course_May-June\Tutorial
..\.venv-1\Scripts\python.exe -m pip install -r requirements.txt
```

Optional `.env` (place in `Project/`):

```
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-3-5-sonnet-latest
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
> you can skip Step 1 entirely and go straight to simulation.

---

## 6. Step 2 — Run / simulate the workflow

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

## 7. Reading the output

Open any file in `Project/outputs/reports/`. Each report contains, depending on its routed
type: metadata, complaint narrative, extraction summary, risk assessment, **investigation
subqueries**, evidence with per-facet citations, a **quality-intelligence** block, trend
context, CAPA/monitoring guidance, decision questions, and a compliance footer.

The matching `Project/logs/<trace_id>.jsonl` records per-agent latency, gate results, and
which sections were built — useful for observability and debugging.

---

## 8. Project layout

```
Project/
  data/                       # openFDA downloaders + downloaded JSON
    download_imaging_data.py   # main data download script
  src/
    run_workflow.py            # CLI entrypoint
    api.py                     # FastAPI entrypoint
    config.py                  # product codes, paths, model config
    pipeline/
      orchestrator.py          # top-level run loop (load, simulate, persist)
      langgraph_flow.py        # LangGraph graph + gates + tracing
      schemas.py               # dataclass contracts + handoff validation
    agents/
      extraction.py            # complaint -> structured signal
      orchestration.py         # subquery planner + section-driven driver
      retrieval.py             # multi-query evidence retrieval
      risk_analysis.py         # ISO 14971 risk + report-type routing
      archive_trend.py         # trend summary
      quality_tools.py         # quality-intelligence toolbox
      report_sections.py       # section registry + per-type blueprints
      report_generation.py     # assembles the report from sections
    observability/tracer.py    # JSONL trace logger
    utils/                     # data loader, storage (SQLite + Chroma), LLM client
  outputs/reports/             # generated reports (gitignored)
  logs/                        # trace logs (gitignored)
  specs/                       # user stories US-01..US-18 + coverage
```

---

## 9. Quick start (TL;DR)

```powershell
# 1. install deps (workspace root)
..\.venv-1\Scripts\python.exe -m pip install -r requirements.txt

# 2. (optional) refresh data — pre-downloaded data is already committed
cd Project\data
..\..\.venv-1\Scripts\python.exe download_imaging_data.py
Copy-Item recalls\all_imaging_moldx_recalls.json recalls\all_recalls.json -Force

# 3. run the workflow
cd ..
..\.venv-1\Scripts\python.exe -m src.run_workflow --complaints-per-code 1 --max-events-per-code 80 --seed 42

# 4. read reports in Project/outputs/reports/
```
