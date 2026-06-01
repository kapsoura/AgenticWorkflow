# US-08: DSPy Extraction Optimization

| Field | Value |
|---|---|
| Epic | B. Components |
| Owner | M3 |
| Sprint | Week 2–3 |
| Priority | P2 (enhancement) |
| Estimate | 2–3 days |
| Status | Not started |

## User Story
As an **extraction developer**, I want extraction prompts compiled/optimized automatically against labeled examples, so that I improve F1 without hand-tuning prompts and can report a programmatic-prompt-engineering contribution.

## Context
Tier-2 technique. Enhancement on top of US-07; only pursue once the baseline + manual-prompt version is measured (restraint principle — prove the manual prompt is insufficient first).

## Scope
- **In**: define DSPy signature for extraction; optimize few-shot examples/instructions against extraction F1 on a validation split.
- **Out**: optimizing other agents (could extend later).

## Inputs / Outputs
- **Input**: 10–30 labeled examples from `gold_labels.json`; held-out validation split.
- **Output**: compiled DSPy program saved to `configs/dspy_extraction.json`; before/after F1 report.

## Acceptance Criteria
- [ ] Given a labeled train split, when DSPy compiles, then a saved program is produced and reloadable.
- [ ] Given the validation split, when compared to the manual prompt (US-07), then F1 is reported (improvement expected; if none, document and keep manual prompt — that is an acceptable, honest result).
- [ ] Given DSPy fails to converge/improve, then the system falls back to the US-07 manual prompt with no regression.

## Technical Approach
1. `dspy.Signature` mapping narrative → structured fields; metric = field-level F1.
2. Optimizer (e.g. BootstrapFewShot) over the train split; evaluate on validation.
3. Persist compiled artifact; wire a flag in extraction to load it.

## Dependencies
Blocked by: US-05, US-07. Blocks: feeds US-16 ablation (technique on/off).

## Test Plan
- Reproducibility: recompiling with fixed seed gives stable validation F1.
- Fallback: with DSPy artifact absent, US-07 still runs.

## Definition of Done
- [ ] Compiled program committed; before/after F1 table in the report.
- [ ] Fallback path verified.
