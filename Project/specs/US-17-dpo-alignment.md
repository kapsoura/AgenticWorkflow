# US-17: DPO Alignment Study

| Field | Value |
|---|---|
| Epic | D. Evaluation |
| Owner | M5 |
| Sprint | Week 3 |
| Priority | P1 |
| Estimate | 4 days |
| Status | Not started |

## User Story
As the **research lead**, I want to align the report/CAPA generator to QM preferences using DPO and measure the improvement, so that we can demonstrate a modern alignment contribution in a regulated-report-generation setting.

## Context
`System_Design.md` Tier-2 + alignment. DPO is the primary alignment method (PPO is a stretch comparison — unstable, GPU-heavy). Preference pairs come from QM accept/revise decisions on US-13 report drafts (collection starts Week 2).

## Scope
- **In**: collect ≥50 preference pairs (preferred vs rejected report/CAPA drafts); DPO fine-tune a small model (Phi-3-mini / Llama-3-8B + LoRA) via TRL; before/after evaluation.
- **Out**: PPO (separate stretch), reward-model deployment.

## Inputs / Outputs
- **Input**: preference pairs `data/alignment/preferences.jsonl` (from US-13 drafts + QM/simulated-reviewer choices).
- **Output**: LoRA adapter `models/dpo_report_adapter/`; before/after metrics (report preference win-rate, hallucination, citation density).

## Acceptance Criteria
- [ ] Given ≥50 preference pairs, when DPO-trained, then a LoRA adapter is produced and loads for inference.
- [ ] Given before/after comparison on held-out cases, then **report preference win-rate > 60% vs baseline** (target) is reported, plus hallucination and citation-density deltas.
- [ ] Given insufficient/poor pairs, then the study is reported honestly (no improvement is an acceptable documented outcome) and the baseline model remains the default.
- [ ] Given GPU constraints, then training runs within a single-GPU (Colab Pro) budget.

## Technical Approach
1. Preference collection UI/log on top of US-13 (QM picks preferred draft; early pairs may use a strong LLM as simulated reviewer).
2. TRL `DPOTrainer` + LoRA on the small base; KL control per defaults.
3. Evaluate via US-16 harness (win-rate as pairwise judge; hallucination + citation density).

## Dependencies
Blocked by: US-13, US-16 (for measurement). Blocks: US-18 (DPO-on/off ablation).

## Test Plan
- Repro: training runs to completion with fixed seed; adapter loads.
- Eval: win-rate computed on held-out set; deltas reported.

## Definition of Done
- [ ] Adapter trained; before/after table reported via US-16; default kept safe if no gain.
