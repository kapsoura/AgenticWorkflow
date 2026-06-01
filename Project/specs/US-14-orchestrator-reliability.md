# US-14: Orchestrator + Validation Gates + Loop Safety

| Field | Value |
|---|---|
| Epic | C. Integration |
| Owner | M2 |
| Sprint | Week 3 |
| Priority | P0 |
| Estimate | 4 days |
| Status | Not started |
| Autonomy | L2: Workflow (assembly line — engineer-defined control flow, no LLM routing) |

## User Story
As a **Quality Manager / the dev team**, I want the six components wired into one reliable pipeline with validation checkpoints and loop caps, so that a single complaint flows end-to-end and a bad intermediate output is caught instead of silently corrupting the final report.

## Context
`System_Design.md` §Validation Gates, §Loop Safety. Implements the assembly-line orchestrator plus the three gates and iteration/timeout caps that prevent cascading failures and unbounded loops.

## Scope
- **In**: LangGraph orchestrator running Extraction → (Similarity ∥ Retrieval) → Risk+CAPA → Report; schema validation at each handoff; the 3 validation gates; loop caps + timeouts + fallbacks; state summarization between hops.
- **Out**: component internals (their own stories).

## Inputs / Outputs
- **Input**: raw complaint + `trace_id`.
- **Output**: `ReportOutput` (or a partial report with `REVIEW NEEDED`); `src/pipeline/orchestrator.py`.

## Acceptance Criteria
- [ ] Given a complaint, when run, then all components execute in order (Similarity and Retrieval may run in parallel) and a final report is returned.
- [ ] **Gate 1** (post-extraction): `confidence < 0.5`, unknown modality, or missing `failure_mode`/`severity_indicator` → flag for human review / retry once / don't silently proceed.
- [ ] **Gate 2** (post-retrieval): 0 results → inject "no FDA evidence" warning downstream; all relevance < 0.3 → mark low-confidence; drop items < 0.3.
- [ ] **Gate 3** (post-risk): HIGH risk + 0 citations → reject; LOW risk but Death in evidence → escalate to human; nonexistent recall reference → strip + flag.
- [ ] **Loop caps**: Retrieval ReAct ≤ 5 iters / 30s (fallback: best-so-far); Report critique ≤ 2 rounds / 20s (fallback: accept + "unchecked"); pipeline ≤ 120s total (fallback: partial report).
- [ ] Given any handoff, then the payload is schema-validated (US-06) before the next component runs; failures are loud, not silent.
- [ ] Given state handoff, then only summarized state (top-5 retrieval, not raw payloads) is forwarded.

## Technical Approach
1. LangGraph `StateGraph`; nodes = components; edges enforce order; parallel branch for Similarity ∥ Retrieval then join.
2. Gate functions between nodes call `validate_handoff` + the gate rules; route to retry/escalate/abort.
3. Per-node timeout wrappers + iteration counters; deterministic stop conditions.
4. Inject `trace_id` (US-15) into shared state, propagated to all nodes.

## Dependencies
Blocked by: US-06, US-07, US-09, US-11, US-12, US-13. Blocks: US-16, US-18, demo.

## Test Plan
- Integration: 5 gold complaints run end-to-end → schema-valid reports.
- **Known-bad-input tests**: low-confidence extraction triggers Gate 1; empty retrieval triggers Gate 2; uncited HIGH risk triggers Gate 3; a runaway ReAct loop hits the cap.
- Timeout: simulated slow node → pipeline returns partial within 120s.

## Definition of Done
- [ ] End-to-end pipeline runs on the benchmark; all 3 gates + all loop caps verified by tests.
- [ ] Cascading-failure test (inject bad extraction) demonstrably stops at a gate.
