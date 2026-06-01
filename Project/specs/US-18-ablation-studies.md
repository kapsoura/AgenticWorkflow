# US-18: Ablation Studies

| Field | Value |
|---|---|
| Epic | D. Evaluation |
| Owner | M6 |
| Sprint | Week 4 |
| Priority | P1 |
| Estimate | 3 days |
| Status | Not started |

## User Story
As the **research lead**, I want to remove one component/technique at a time and measure the impact, so that we can show each design choice is justified — the rigorous experimental evidence that makes this MTech-level.

## Context
`System_Design.md` §Ablation Studies. Uses the US-16 harness with feature flags to toggle components/techniques. Also realizes the restraint argument: baseline (single LLM call) vs full pipeline quantifies what the added complexity buys.

## Scope
- **In**: run the defined ablations, each vs the full system, on the benchmark; produce comparison tables + narrative.
- **Out**: new metrics (reuse US-16).

## Inputs / Outputs
- **Input**: full pipeline (US-14) with toggles; US-16 harness; benchmark.
- **Output**: `data/evaluation/ablation_results.json` + report tables.

## Acceptance Criteria
- [ ] **A1 Remove Graph RAG** → retrieval Precision@5 drop measured.
- [ ] **A2 Remove self-reflection** → hallucination-rate increase measured.
- [ ] **A3 Remove DPO** (baseline vs US-17 adapter) → report-quality delta measured.
- [ ] **A4 Remove temporal scoring** → signal-detection loss measured.
- [ ] **A5 Baseline (single LLM call) vs full pipeline** → overall quality + cost/latency/predictability trade-off measured (the restraint argument).
- [ ] Given each ablation, then results are reported in one comparison table with the metric deltas and a one-line interpretation.

## Technical Approach
1. Feature flags in the orchestrator (US-14) for Graph RAG, reflection, DPO adapter, temporal scoring; a `--baseline` single-call mode.
2. Run each config through US-16; collect deltas; tabulate.
3. Interpret: does each component earn its complexity?

## Dependencies
Blocked by: US-14, US-16 (and US-17 for A3). Blocks: final report.

## Test Plan
- Each flag toggles cleanly (config-level test); full ablation suite runs unattended.

## Definition of Done
- [ ] All 5 ablations executed; comparison tables + interpretations in the final report.
