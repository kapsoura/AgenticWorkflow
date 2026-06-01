# US-05: Synthetic Complaints & Gold Benchmark

| Field | Value |
|---|---|
| Epic | A. Foundation |
| Owner | M3 + M6 |
| Sprint | Week 1 |
| Priority | P0 |
| Estimate | 3 days |
| Status | Not started |

## User Story
As the **evaluation lead**, I want a set of realistic synthetic complaints plus a hand-labeled gold benchmark, so that every component can be measured against ground truth and the demo has compelling, varied inputs.

## Context
Per `Data_Architecture_and_Context.md` §2 (three-tier input strategy) and `System_Design.md` evaluation section. The benchmark is the measurement substrate for US-08, US-16, US-17, US-18.

## Scope
- **In**: (a) 200 synthetic internal complaints generated from MAUDE narratives via the rephrase prompt; (b) gold benchmark: 50 real MAUDE narratives + 20 recall notices + 30 synthetic, with team labels.
- **Out**: reward-model training data (US-17), automated labeling.

## Inputs / Outputs
- **Input**: MAUDE narratives + recall reasons from SQLite.
- **Output**:
  - `data/synthetic/complaints.json` — 200 complaints with hidden `_ground_truth` (event_type, product_problems, manufacturer, product_code).
  - `data/evaluation/gold_labels.json` — 100 cases with labeled extraction fields, retrieval relevance judgments, and CAPA-quality notes.

## Acceptance Criteria
- [ ] Given the rephrase prompt, when generating, then synthetic complaints preserve the original failure mode/severity (no invented problems) and read as internal-style text (100–300 words).
- [ ] Given the modality mix target, then synthetic set ≈ 80 MRI / 50 CT / 40 Ultrasound / 30 MolDx.
- [ ] Given each gold case, then extraction fields are labeled by ≥1 member and a 20-case subset is double-labeled with inter-annotator agreement recorded.
- [ ] Given a synthetic complaint, then its `_ground_truth` is never exposed to any agent at inference (only to the evaluator).

## Technical Approach
1. Sampling: stratify by product code + event_type; prefer narratives > 200 chars.
2. Generation: `REPHRASE_PROMPT` (Data_Architecture §2) via GPT-4-class model; validate length + that key entities persist.
3. Labeling: lightweight Streamlit or JSON form; store labels with labeler id + timestamp.

## Dependencies
Blocked by: US-01. Blocks: US-08, US-16, US-17, US-18.

## Test Plan
- Validation: schema-check both JSON files; assert no `_ground_truth` leakage in the agent-facing view.
- Quality: spot-check 10 synthetic complaints for fidelity.

## Definition of Done
- [ ] 200 synthetic + 100 gold cases committed (synthetic/labels are derived, not raw data — OK to commit).
- [ ] Inter-annotator agreement (Cohen's kappa) recorded for the double-labeled subset.
