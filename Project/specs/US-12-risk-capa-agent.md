# US-12: Risk + CAPA Agent (Agent 4)

| Field | Value |
|---|---|
| Epic | B. Components |
| Owner | M5 |
| Sprint | Week 2–3 |
| Priority | P0 |
| Estimate | 5 days |
| Status | Not started |
| Autonomy | L1: Augmented LLM (risk + CAPA **merged** to avoid over-orchestration) |

## User Story
As a **Quality Manager**, I want a draft ISO 14971 risk assessment and a CAPA recommendation grounded in the retrieved FDA evidence, so that I can review a defensible severity/probability rationale and corrective plan instead of building it from scratch.

## Context
`System_Design.md` §Agent 4 — the regulatory core. Encodes the **ISO 14971 severity (S1–S5), probability (P1–P5 calibrated to dataset counts), and 5×5 acceptability matrix** (ACCEPTABLE/ALARP/UNACCEPTABLE), IEC 62304 classification, and escalation flags (PRRC/FSCA). Risk and CAPA are one call by design.

## Scope
- **In**: CoT reasoning through ISO 14971 methodology; evidence-grounded risk estimation; CAPA generation from recall precedents; escalation flag logic; constitutional guardrail (refuse `ALARP`/`UNACCEPTABLE` without citations); self-reflection.
- **Out**: report formatting (US-13), DPO alignment (US-17), residual-risk acceptability decision (human, per ISO 14971 §7.3).

## Inputs / Outputs
- **Input**: `ExtractionOutput` + `SimilarityOutput` (cluster context) + `RetrievalOutput` (FDA evidence).
- **Output**: `RiskCapaOutput` — `iso14971_assessment` (hazardous_situation, harm, severity{level,label,rationale}, probability{…}, risk_level, risk_control_needed, annex_c_hazard_category), `evidence_basis[]` (source,id,relevance), `uncertainty`, `iec62304_classification`, `capa_recommendation` (immediate/investigation/corrective/preventive/verification_method/effectiveness_criteria/timeline/precedent_basis/iso13485_clause), `escalation_flags`.

## Acceptance Criteria
- [ ] Given evidence with N similar events, when estimating probability, then the P-level follows the dataset-calibrated bands (e.g. 20–200 events → P4 Occasional).
- [ ] Given severity × probability, when evaluating, then `risk_level` matches the §7.5 acceptability matrix exactly.
- [ ] Given `risk_level ∈ {ALARP, UNACCEPTABLE}` with **zero** `evidence_basis` citations, then the agent refuses / forces `uncertainty` rather than asserting the level (constitutional guardrail). Note: `HIGH`/`MEDIUM`/`LOW` are NOT valid risk levels — only `ACCEPTABLE`/`ALARP`/`UNACCEPTABLE` per ISO 14971 5×5 matrix.
- [ ] Given escalation logic, then `escalation_required` iff risk ∈ {ALARP, UNACCEPTABLE}; `prrc_notification_required` iff UNACCEPTABLE; `fsca_required` only iff confirmed-root-cause flag AND UNACCEPTABLE AND active distribution.
- [ ] Given recall precedents in evidence, then `capa_recommendation.precedent_basis` cites a real recall id (verified against DB).
- [ ] Given the gold benchmark, then risk + CAPA expert rubric **> 3.0/5** (target).

## Technical Approach
1. **Baseline**: single call producing risk+CAPA from evidence-in-context → rubric score (ablation #5 baseline).
2. Encode S/P scales + matrix as a deterministic lookup the prompt must follow (or post-process to enforce matrix consistency).
3. CoT: evidence → hazard → severity → probability → risk_level → control. CAPA RAG over recall `action` fields (top precedents).
4. Guardrail + self-reflection (≤1 round): check every claim has a citation; check matrix consistency; populate `uncertainty`.
5. Prompts in `configs/prompts/risk_capa.md`.

## Dependencies
Blocked by: US-06, US-07, US-11 (and US-09 for cluster context). Blocks: US-13, US-14.

## Test Plan
- Unit: matrix consistency (S3×P4 → UNACCEPTABLE); escalation-flag truth table; guardrail rejects uncited ALARP/UNACCEPTABLE risk; rejects any output where `risk_level` is `HIGH`/`MEDIUM`/`LOW`.
- Eval: rubric scoring on gold; citation-coverage rate.

## Definition of Done
- [ ] Schema-valid output; matrix + escalation logic verified by truth-table tests; guardrail enforced.
- [ ] Rubric score reported; CAPA precedents resolve to real recalls.
