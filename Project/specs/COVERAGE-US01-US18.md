# Coverage Audit: US-01 to US-18 (Current Workspace State)

## Legend

- Covered: implementation is present and broadly aligned with story acceptance intent.
- Partial: implementation exists but key acceptance criteria are still missing.
- Not covered: no implementation evidence found in the current codebase.

## Story-by-Story Status

| Story | Status | Notes |
|---|---|---|
| US-01 Data ingestion | Partial | Local loaders and simulation exist; full openFDA ingestion hardening, normalized schema load, and quality-report workflow are not complete in current baseline. |
| US-02 Entity resolution | Not covered | No manufacturer alias map pipeline or normalization backfill found. |
| US-03 Embedding index | Partial | Chroma persistence and vector upsert/query are implemented; target sentence-transformers and strict embedding linkage flow are not complete. |
| US-04 Knowledge graph | Not covered | No NetworkX GraphML build/traversal helper implementation found. |
| US-05 Synthetic + benchmark | Partial | Synthetic complaint simulation exists; full 200-synthetic + 100 gold benchmark dataset and labeling workflow not complete. |
| US-06 Schema contracts | Partial | Shared handoff contracts exist via dataclasses; strict Pydantic v2 validation, frozen contract governance, and gate helper are pending. |
| US-07 Extraction agent | Partial | Extraction works with heuristic + optional LLM fallback; full schema requirements and benchmarked F1 target workflow are pending. |
| US-08 DSPy optimization | Not covered | No DSPy compile/eval flow found. |
| US-09 Similarity module | Partial | Trend summary logic exists; HDBSCAN clustering, UMAP projection, and emergence scoring are pending. |
| US-10 Streamlit dashboard | Not covered | No dashboard app implementation found. |
| US-11 Retrieval agent | Partial | Local evidence retrieval with fuzzy and vector augmentation exists; Graph RAG and measured Precision@5 harness are pending. |
| US-12 Risk + CAPA | Partial | ISO-style risk bucket and CAPA baseline exist; full evidence guardrails/truth-table enforcement and rubric scoring are pending. |
| US-13 Report agent | Partial | Report assembly and persistence exist; self-critique loop, quality block, and hallucination metric path are pending. |
| US-14 Orchestrator reliability | Partial | LangGraph pipeline now includes Gate1/2/3 checks, relevance filtering, schema handoff validation, and per-complaint runtime deadline checks. Parallel branching and richer retry/cap policies are still pending. |
| US-15 Observability | Partial | Per-report `trace_id` propagation and JSONL step logs are implemented (`logs/<trace_id>.jsonl`). Aggregation metrics and full replay tooling are still pending. |
| US-16 Evaluation harness | Not covered | No unified outcome + trajectory harness found. |
| US-17 DPO alignment | Not covered | No preference-pair pipeline or DPO training artifact flow found. |
| US-18 Ablation studies | Not covered | No feature-flag ablation runner or ablation results pipeline found. |

## Contradiction Check: V1 vs Initial Plan

The current V1 baseline is useful and runnable, but does not equal full completion of the initial US-01..US-18 plan.

Main mismatches that were corrected in documentation:

1. Prior wording implied US-14 implementation completion; reliability gates are now partially implemented but not acceptance-complete.
2. Prior wording loosely mapped US-06 completion; strict schema validation behavior is still pending.
3. Similarity story (US-09) was represented as complete in spirit, but current implementation is trend summarization baseline only.
4. Evaluation and alignment stories (US-16 to US-18) remain pending; US-15 now has baseline trace logging but needs aggregation and analytics.

## Recommended Implementation Order From Here

1. US-14 minimum reliability gates with strict handoff checks (plus US-06 hardening).
2. US-15 trace_id logging and replayable JSONL traces.
3. US-16 evaluation harness wired to current baseline.
4. US-09 cluster analytics completion (HDBSCAN/UMAP).
5. US-11 Graph RAG extension.
6. US-17 and US-18 after stable metrics are in place.