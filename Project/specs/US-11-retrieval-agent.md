# US-11: FDA Evidence Retrieval (Agent 3)

| Field | Value |
|---|---|
| Epic | B. Components |
| Owner | M2 |
| Sprint | Week 2 |
| Priority | P0 |
| Estimate | 4 days |
| Status | Not started |
| Autonomy | L1 Augmented LLM → **upgrade to ReAct only if single-pass RAG underperforms** |

## User Story
As a **Quality Manager**, I want the system to pull comparable FDA adverse events and recalls (across our manufacturer and competitors) for a given complaint, so that my risk assessment and CAPA are grounded in real precedent instead of memory.

## Context
`System_Design.md` §Agent 3. Combines vector RAG (US-03) with Graph RAG (US-04). Honors the restraint principle: build single-pass RAG first; add the ReAct loop (cap 5 iters / 30s, US-14) only if Precision@5 is insufficient.

## Scope
- **In**: vector retrieval over `event_narratives` + `recall_reasons`; graph traversal for same-code/manufacturer/root-cause recalls; semantic re-ranking; relevance scoring; output `RetrievalOutput`.
- **Out**: knowledge-graph build (US-04), MCP packaging (stretch).

## Inputs / Outputs
- **Input**: `ExtractionOutput` (device, modality, failure mode, manufacturer).
- **Output**: `RetrievalOutput` — `matching_events[]` (report_number, relevance_score, snippet), `matching_recalls[]` (recall_id, reason, root_cause, action), `regulatory_context`, and `react_trace[]` if ReAct used.

## Acceptance Criteria
- [ ] Given an extracted record, when retrieving, then top-K events + recalls return with relevance scores, filtered by product code/modality.
- [ ] Given the gold relevance judgments, when evaluated, then **Precision@5 > 0.65** (target; baseline measured first).
- [ ] Given Graph RAG enabled, when a same-manufacturer/root-cause recall exists, then it is surfaced even if lexically dissimilar (cross-product linking via US-04).
- [ ] Given an openFDA live call (if used), when it 429s/times out, then it retries with backoff and degrades to local-only retrieval rather than failing.
- [ ] Given retrieval results, then items below relevance 0.3 are dropped before handoff (Gate 2 alignment) and only summarized top-5 are passed downstream.

## Technical Approach
1. **Baseline**: ChromaDB cosine query with metadata filter → measure Precision@5.
2. Add Graph RAG: union vector hits with graph-traversed recalls (US-04 helpers); re-rank by hybrid score.
3. Optional **ReAct** upgrade: Thought→Action(query)→Observation loop, deterministic stop on evidence sufficiency, capped (US-14). Log `react_trace`.
4. Sanitize retrieved narratives before they enter any downstream prompt (delimiters).

## Dependencies
Blocked by: US-03, US-04, US-06. Blocks: US-12, US-14.

## Test Plan
- Unit: query returns schema-valid `RetrievalOutput`; relevance filter drops low scores.
- Eval: Precision@5 vs gold; Graph-RAG-on vs -off recall comparison (feeds ablation #1).
- Resilience: simulate 429 → graceful local fallback.

## Definition of Done
- [ ] Single-pass RAG measured; Graph RAG integrated; ReAct upgrade gated on measured need.
- [ ] Precision@5 reported; resilience + sanitization verified.
