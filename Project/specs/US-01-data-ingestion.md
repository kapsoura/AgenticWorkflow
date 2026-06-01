# US-01: FDA Data Ingestion & Local Store

| Field | Value |
|---|---|
| Epic | A. Foundation |
| Owner | M1 |
| Sprint | Week 1 |
| Priority | P0 |
| Estimate | 3 days |
| Status | Not started |

## User Story
As a **data engineer on the team**, I want a reproducible pipeline that downloads the imaging + molecular-dx adverse events and recalls from openFDA and loads them into a clean local store, so that every other component has consistent, query-ready data without re-hitting the API.

## Context
`data/download_imaging_data.py` already pulls a 3,701-event + 3,299-recall sample. This story hardens it into the full working set (~14–20K events, 2019+) and the SQLite schema defined in `Data_Architecture_and_Context.md` §4. Data is **git-ignored**; the script is the reproducible artifact.

## Scope
- **In**: paginated download for all 8 product codes (LNH, JAK, IYE, LLZ, IZL, MQB, GKZ, QKO); parse JSON → normalized rows; load SQLite; dedupe by `report_number`; quality report.
- **Out**: embeddings (US-03), entity resolution (US-02), knowledge graph (US-04).

## Inputs / Outputs
- **Input**: openFDA `device/event.json` and `device/recall.json` endpoints.
- **Output**: `data/signal_intelligence.db` (SQLite) with tables `events`, `event_problems`, `recalls` per the schema in `Data_Architecture_and_Context.md`; `data/analysis/data_analysis_report.md` regenerated.

## Acceptance Criteria
- [ ] Given the script is run on a clean checkout, when it completes, then `signal_intelligence.db` contains ≥14K events (2019+, all 8 codes) and the 3,299 recalls.
- [ ] Given API pagination limits (1000/query, skip≤25000), when a code exceeds 26K (LLZ), then the script splits into date-ranged queries and logs coverage.
- [ ] Given duplicate initial+followup MAUDE reports, when loading, then rows are deduplicated by `report_number` (latest kept) and the dedupe count is logged.
- [ ] Given a 429/timeout, when fetching, then the script retries with backoff (existing `fetch_json`) and never silently drops a batch.
- [ ] Given the load finishes, then every event row has `product_code`, `domain` (imaging|molecular_dx), `modality`, and `narrative` populated (narrative nullable but flagged).

## Technical Approach
1. Reuse/extend `fetch_json` retry logic; add per-code date-range chunking for LLZ/GKZ.
2. Parse: flatten `mdr_text[].text` → `narrative`; map `device_report_product_code` → `modality`/`domain`; explode `product_problems` into `event_problems`.
3. SQLite via `sqlite3`; create tables + indexes (`idx_events_product_code`, `idx_recalls_root_cause`).
4. Idempotent load: `INSERT OR REPLACE` on unique `report_number`/`recall_number`.

## Dependencies
Blocked by: none. Blocks: US-02, US-03, US-04, US-05.

## Test Plan
- Unit: parser on 3 sample event JSONs (narrative join, problem explode, modality mapping).
- Data quality: assert narrative coverage ≥95%, recall `root_cause` coverage = 100%.
- Idempotency: run twice → row counts stable.

## Definition of Done
- [ ] Script runnable end-to-end with one command; README note added.
- [ ] DB loads ≥14K events + 3,299 recalls; quality report regenerated and committed (report only, not data).
- [ ] Indexes created; dedupe + coverage logged.
