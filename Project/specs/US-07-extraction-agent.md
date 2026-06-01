# US-07: Extraction Agent (Agent 1)

| Field | Value |
|---|---|
| Epic | B. Components |
| Owner | M3 |
| Sprint | Week 1 (baseline) → Week 2 (full) |
| Priority | P0 |
| Estimate | 4 days |
| Status | Not started |
| Autonomy | L1: Augmented LLM (single-pass + 1 reflection round) |

## User Story
As a **Quality Manager**, I want a pasted complaint narrative turned into a structured, QMS-categorized record with a confidence score, so that I get consistent machine-readable fields instead of re-typing them by hand.

## Context
First pipeline stage. `System_Design.md` §Agent 1 defines the output schema, including QMS/regulatory flags (`is_safety_related`, `usability_concern`, `security_concern`, `affected_countries`, `complaint_source`, `qms_complaint_category`). Maps free text → controlled ISO 13485 §8.2.2 categories (defined in `Ideation.md` QMS section).

## Scope
- **In**: CoT extraction → `ExtractionOutput`; QMS category mapping; confidence estimation; 1-pass self-reflection; constrained JSON output.
- **Out**: DSPy optimization (US-08), downstream gates (US-14).

## Inputs / Outputs
- **Input**: raw complaint text (string), optional product hint.
- **Output**: `ExtractionOutput` (US-06) — fields per `System_Design.md` Agent 1 schema. Prompt-injection rule: narrative wrapped in `<user_narrative>…</user_narrative>`.

## Acceptance Criteria
- [ ] Given a MAUDE-style narrative, when extracted, then `modality`, `failure_mode`, `severity_indicator` (S1–S5 code), `software_related`, `qms_complaint_category`, `is_safety_related`, `usability_concern`, `security_concern`, `affected_countries` (ISO 3166-1 codes or `unknown`), and `complaint_source` are populated and schema-valid per [US-06](US-06-schema-contracts.md).
- [ ] Given the gold benchmark, when evaluated, then field-level **F1 > 0.80** (target; baseline measured first).
- [ ] Given an ambiguous/short narrative, then `confidence < 0.5` is returned (so Gate 1 can flag it) rather than a fabricated high-confidence guess.
- [ ] Given a narrative containing injected instructions ("ignore previous instructions…"), then the agent ignores them (delimiter + system-prompt defense) and extracts normally.
- [ ] Given a first-pass extraction, when self-reflection runs once, then obvious schema/consistency errors are corrected before return.
- [ ] Given a narrative with no jurisdictional info, then `affected_countries = ["unknown"]` and `complaint_source = "unknown"` rather than fabricated values.

## Technical Approach
1. **Baseline (Week 1)**: single LLM call with schema in prompt → measure F1. This feeds ablation #5.
2. Add CoT reasoning steps (component → failure mode → symptom → severity); tool-calling/structured-output for JSON.
3. QMS category: few-shot map to `SW-FUNC/SW-ALGO/SW-UI/SW-DATA/SW-CYBER/IMG-QUAL/HW-MECH/...` (Ideation table).
4. Confidence: self-reported + logprob/consistency signal; reflection pass (≤1 round) checks required fields + enum validity.
5. Prompts in `configs/prompts/extraction.md` (version-controlled).

## Dependencies
Blocked by: US-06. (Benchmark US-05 needed to measure F1.) Blocks: US-12, US-14.

## Test Plan
- Unit: 5 sample narratives → schema-valid output; injection test; short-narrative low-confidence test.
- Eval: F1 vs gold labels; confusion matrix on `qms_complaint_category`.

## Definition of Done
- [ ] Standalone runnable with mock input; prompts version-controlled.
- [ ] F1 measured vs gold (baseline + optimized); injection + low-confidence behaviors verified.
