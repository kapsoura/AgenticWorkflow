# US-13: Report Assembly Agent (Agent 5)

| Field | Value |
|---|---|
| Epic | B. Components |
| Owner | M3 |
| Sprint | Week 2–3 |
| Priority | P0 |
| Estimate | 4 days |
| Status | Not started |
| Autonomy | L2: Evaluator-Optimizer (self-critique loop, cap 2 rounds / 20s) |

## User Story
As a **Quality Manager**, I want all the agent outputs assembled into one ISO-13485-formatted signal report with traceable citations and a clear uncertainty section, so that I can review, approve, and bring it straight to the Quality Review Board.

## Context
`System_Design.md` §Agent 5. Output is a controlled document (§4.2.4 fields: Document ID, Revision, Prepared by, Reviewed by, etc.) with an AI-transparency footer. Self-critique rubric gates release.

## Scope
- **In**: assemble structured markdown report from all upstream outputs; ISO 13485 controlled-document fields; self-critique loop with explicit stopping rubric; LLM-as-Judge self-score.
- **Out**: human approval workflow (the QM acts outside the system), DPO tuning (US-17).

## Inputs / Outputs
- **Input**: `ExtractionOutput`, `SimilarityOutput`, `RetrievalOutput`, `RiskCapaOutput`.
- **Output**: `ReportOutput` — markdown report (`SR-YYYY-NNNN`) + a `quality` block (citation_count, unsupported_claims, self_score, review_needed_flag). Persist to `signal_reports` table.

## Acceptance Criteria
- [ ] Given all upstream outputs, when assembled, then the report contains the six sections (extracted fields, pattern match, FDA evidence, risk assessment, CAPA, report quality) plus ISO 13485 header fields and the AI-transparency footer.
- [ ] Given the self-critique rubric (citation coverage, schema compliance, uncertainty disclosure, risk/CAPA consistency), when any check fails, then the report is revised (max 2 rounds), then accepted with a `REVIEW NEEDED` flag if still failing.
- [ ] Given every factual claim, then it carries a source reference traceable to a real FDA record id; `unsupported_claims` counts those without one.
- [ ] Given the gold benchmark, then hallucination rate (**% claims without citation) < 15%** (target).
- [ ] Given the report, then the `Reviewed by` field is left empty (populated only after human approval — decision support, not automation).

## Technical Approach
1. Template-driven markdown (`configs/report_template.md`) filled from upstream JSON.
2. Self-critique: second pass scores against the 4-point rubric (US-14 stopping rule); revise ≤2 rounds.
3. LLM-as-Judge self-score recorded for evaluation calibration (US-16).
4. Persist report + quality block to `signal_reports` (also serves episodic memory).

## Dependencies
Blocked by: US-06, US-12. Blocks: US-14, US-17 (preference pairs come from report drafts).

## Test Plan
- Unit: assembles schema-valid report from mocks; rubric loop terminates ≤2 rounds; missing-citation claim increments `unsupported_claims`.
- Eval: hallucination rate vs gold; self-score vs human score correlation (feeds US-16).

## Definition of Done
- [ ] Schema-valid ISO-13485 report produced; self-critique loop bounded; hallucination rate reported.
- [ ] Persisted to `signal_reports`; `Reviewed by` left for human.
