# Implementation Specs — Story Map

This directory decomposes the Multi-Agent Regulatory Signal Intelligence System into **18 user stories** grouped into 5 epics, each with a self-contained spec for efficient parallel implementation. Specs are grounded in `System_Design.md`, `Ideation.md`, and `Data_Architecture_and_Context.md` — those remain the source of truth for deep detail; specs here are the implementable units of work.

**Primary user**: the Quality Manager (QM). **Secondary users**: the dev team (M1–M6), the evaluation/research lead. Stories are written from whichever role actually receives the value.

## Epics & Stories

| ID | Story | Epic | Owner | Week | Priority |
|----|-------|------|-------|------|----------|
| [US-01](US-01-data-ingestion.md) | FDA data ingestion & local store | A. Foundation | M1 | 1 | P0 |
| [US-02](US-02-entity-resolution.md) | Manufacturer entity resolution | A. Foundation | M1 | 2 | P1 |
| [US-03](US-03-embedding-index.md) | Embedding index (ChromaDB) | A. Foundation | M1+M4 | 1 | P0 |
| [US-04](US-04-knowledge-graph.md) | Knowledge graph construction | A. Foundation | M2 | 1–2 | P1 |
| [US-05](US-05-synthetic-and-benchmark.md) | Synthetic complaints & gold benchmark | A. Foundation | M3+M6 | 1 | P0 |
| [US-06](US-06-schema-contracts.md) | Shared JSON schema contracts | A. Foundation | M2 | 1 | P0 |
| [US-07](US-07-extraction-agent.md) | Extraction Agent (Agent 1) | B. Components | M3 | 1–2 | P0 |
| [US-08](US-08-dspy-optimization.md) | DSPy extraction optimization | B. Components | M3 | 2–3 | P2 |
| [US-09](US-09-similarity-module.md) | Similarity & trend module (non-LLM) | B. Components | M4 | 1–2 | P0 |
| [US-10](US-10-signal-dashboard.md) | Signal dashboard (Streamlit) | B. Components | M4 | 2–3 | P1 |
| [US-11](US-11-retrieval-agent.md) | FDA evidence retrieval (Agent 3) | B. Components | M2 | 2 | P0 |
| [US-12](US-12-risk-capa-agent.md) | Risk + CAPA agent (Agent 4) | B. Components | M5 | 2–3 | P0 |
| [US-13](US-13-report-agent.md) | Report assembly agent (Agent 5) | B. Components | M3 | 2–3 | P0 |
| [US-14](US-14-orchestrator-reliability.md) | Orchestrator + gates + loop safety | C. Integration | M2 | 3 | P0 |
| [US-15](US-15-observability.md) | Observability & tracing | C. Integration | M6 | 1–4 | P1 |
| [US-16](US-16-evaluation-harness.md) | Evaluation harness (outcome+trajectory) | D. Evaluation | M6 | 3–4 | P0 |
| [US-17](US-17-dpo-alignment.md) | DPO alignment study | D. Evaluation | M5 | 3 | P1 |
| [US-18](US-18-ablation-studies.md) | Ablation studies | D. Evaluation | M6 | 4 | P1 |
| [US-19](US-19-memory-parallel-guardrails.md) | Memory + parallel + explicit guardrails | C. Integration | M2 | 3-4 | P0 |
| [US-20](US-20-structured-extraction-clustering-integration.md) | Integrate structured extraction + clustering | C. Integration | M2+M3+M4 | 4 | P1 |

Priority: **P0** = critical path (system doesn't work without it) · **P1** = important · **P2** = enhancement / stretch.

## Dependency Graph

```
US-06 (schemas) ─────────────────────────► blocks all component stories (07,09,11,12,13,14)
US-01 (ingest) ──┬─► US-02 (entity res) ──► US-04 (graph)
                 ├─► US-03 (embeddings) ──► US-09, US-11
                 ├─► US-04 (graph) ───────► US-11
                 └─► US-05 (benchmark) ───► US-08, US-16, US-17, US-18
US-07 (extract) ─┬─► US-12 (risk+capa) ──► US-13 (report) ──► US-14 (orchestrator)
US-09 (similar) ─┤                                              ▲
US-11 (retrieve) ┘──────────────────────────────────────────────┘
US-15 (observability) ── cross-cutting, supports US-14, US-16
US-14 + US-16 ──► US-18 (ablation)
US-13 + reviewer prefs ──► US-17 (DPO)
```

## Sprint Allocation (mirrors the 4-week plan)

- **Week 1 — Foundation + baseline**: US-01, US-03, US-05, US-06; baseline single-LLM-call version of US-07/12 (this *is* ablation baseline #5); US-15 logging skeleton.
- **Week 2 — Core components**: US-02, US-04, US-07, US-09, US-11; start US-08, US-12.
- **Week 3 — Integration + alignment**: US-10, US-12, US-13, US-14, US-17; US-16 scaffolding.
- **Week 4 — Evaluation + ablation**: US-16, US-18; polish, demo, report.

## Cross-Cutting Constraints (apply to every story)

These come from the agentic-AI audit and the QMS framework; each spec restates the ones it must honor:

1. **Architectural restraint** — implement the lowest-autonomy version that passes acceptance; only upgrade (e.g. single-pass RAG → ReAct) when a measured baseline fails.
2. **Schema-validated handoffs** — every component validates its output against `schemas.py` before returning (US-06).
3. **Pass summarized state only** — never forward raw retrieval payloads; top-K + summaries.
4. **Grounding/guardrails** — no HIGH/UNACCEPTABLE risk or regulatory claim without a cited FDA record.
5. **Human-in-the-loop** — the system drafts; the QM approves. No irreversible action.
6. **Traceable** — every LLM/tool call logged under one `trace_id` per report (US-15).

## Spec Template

Each spec follows: metadata table → User Story → Context → Scope → Inputs/Outputs → Acceptance Criteria → Technical Approach → Dependencies → Test Plan → Definition of Done.

## Current Build Snapshot

- [SPEC-V1-5-agent-workflow.md](SPEC-V1-5-agent-workflow.md): executable baseline for the fixed 3-product, 5-agent workflow with LangGraph orchestration.
- [COVERAGE-US01-US18.md](COVERAGE-US01-US18.md): explicit coverage matrix and contradiction check against the full US-01..US-18 plan.
