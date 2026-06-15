# SPEC V1 — Basic 5-Agent Workflow (Fixed 3 Products)

## 1. Scope

Build a runnable baseline for the Multi-Agent Regulatory Signal Intelligence System using these fixed product codes:

- LNH
- JAK
- LLZ

This V1 implements 6 parts:

1. Complaint simulation
2. Extract agent + archive + ML trend
3. Orchestration agent
4. Report generation agent
5. Risk analysis agent
6. Retrieval agent from OpenFDA data

## 2. User Story Mapping (Current V1 Reality)

Implemented or substantially covered in this baseline:

- US-05 (partial): complaint simulation dataset path using local MAUDE archive
- US-07 (partial): extraction agent with ISO-oriented metadata and fallback behavior
- US-09 (partial): deterministic trend summary (non-LLM), without HDBSCAN/UMAP pipeline
- US-11 (partial): retrieval over local MAUDE/recalls with fuzzy + vector augmentation
- US-12 (partial): risk + CAPA baseline using ISO 14971-style severity/probability scoring
- US-13 (partial): report assembly with orchestrator questions and ISO references

Partially scaffolded but not acceptance-complete:

- US-03 (partial): Chroma persistence and vector upsert/query exist, but embedding model/spec differs from story target.
- US-06 (partial): shared contracts exist, but as dataclasses (not frozen Pydantic v2 schemas with strict validators).
- US-14 (partial): LangGraph orchestration flow exists, but validation gates/loop caps/retry-timeout policy are not fully implemented.

Not covered in V1 implementation:

- US-01, US-02, US-04, US-08, US-10, US-15, US-16, US-17, US-18

## 3. AI Stack and Infra

Mandatory stack used:

- anthropic (optional runtime if key available)
- langgraph (state-machine orchestration)
- fastapi (service layer)
- uvicorn (API runtime)
- python-dotenv (env loading)
- mcp (tool endpoint)
- rapidfuzz (retrieval fuzzy scoring)

Infra:

- SQLite for archive and report persistence
- Chroma vector DB for retrieval augmentation

## 4. Orchestration Pattern

Pattern: baseline state machine with routed report-type questions

Input complaint -> extract -> retrieve -> trend -> risk -> route questions -> generate report

Routing rules:

- event_type death/injury OR UNACCEPTABLE risk -> VIGILANCE_ESCALATION
- ALARP risk -> CAPA_INVESTIGATION
- else -> TREND_MONITORING

Report generation agent receives route-specific orchestrator questions and writes report content accordingly.

Note: Similarity and retrieval are not yet parallel branches in this V1 baseline, and US-14 gate/cap behavior is still pending.

## 5. ISO Grounding (V1)

- ISO 13485 complaint process cues in extraction metadata
- ISO 14971 risk matrix and rationale in risk output
- IEC 62304 references can be expanded in V2 for software lifecycle verification links

## 6. Acceptance Criteria (V1 Baseline)

1. CLI run produces reports for simulated complaints across all 3 fixed products.
2. SQLite DB created and populated with complaint archive + signal reports.
3. Chroma collection initialized and receives event vectors using deterministic local embeddings for offline reliability.
4. FastAPI endpoint can execute a workflow run.
5. MCP tool can execute a workflow run.
6. Reports include:
   - report type
   - orchestrator questions
   - extraction ISO clauses/tags
   - risk ISO rationale

## 7. Out of Scope for V1

- Human annotation UI
- DSPy optimization loop
- Advanced eval harness and ablation automation
- Full OpenFDA live API retrieval

## 8. Plan Alignment and Contradictions

This V1 is intentionally a baseline, but there are known differences from the full story-map plan:

1. US-14 was previously implied as implemented; in code it is only partially scaffolded (graph flow exists, full reliability gates do not).
2. US-06 target calls for strict Pydantic contract validation; current code uses dataclasses without strict handoff validators.
3. US-09 target expects HDBSCAN/UMAP cluster analytics; V1 currently provides deterministic trend summaries only.
4. US-11 story allows live openFDA fallback; V1 currently uses local archives as primary evidence source.
5. US-15/16/17/18 evaluation and observability stack is still pending.

## 9. Next Step (V1.1)

Implement reliability and traceability minimums first:

- schema guard per node (US-06 + US-14)
- retry with bounded loops and timeout caps (US-14)
- trace_id propagation and structured JSONL logs (US-15)

Then implement evaluation and experimentation layers:

- evaluation harness (US-16)
- DPO study wiring (US-17)
- feature-flag ablation runner (US-18)
