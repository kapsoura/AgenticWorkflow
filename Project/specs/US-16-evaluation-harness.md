# US-16: Evaluation Harness (Outcome + Trajectory)

| Field | Value |
|---|---|
| Epic | D. Evaluation |
| Owner | M6 |
| Sprint | Week 3–4 |
| Priority | P0 |
| Estimate | 4 days |
| Status | Not started |

## User Story
As the **research lead**, I want one harness that scores the system on outcome and trajectory metrics against the gold benchmark, so that we can report defensible numbers, calibrate the LLM-judge, and run regression checks as we iterate.

## Context
`System_Design.md` §Evaluation. Two metric families: **outcome** (was the result good?) and **trajectory** (was the process good?). Uses US-05 benchmark + US-15 traces. Also calibrates LLM-as-Judge against human scores.

## Scope
- **In**: outcome metrics (extraction F1, retrieval P@5, cluster silhouette, risk/CAPA rubric, hallucination rate, LLM-judge↔human kappa); trajectory metrics (task completion, step efficiency, tool accuracy, error recovery, cost/task, latency); reporting.
- **Out**: DPO training (US-17), ablation orchestration (US-18, consumes this harness).

## Inputs / Outputs
- **Input**: `gold_labels.json` (US-05), pipeline outputs (US-14), traces (US-15).
- **Output**: `src/evaluation/` runner; `data/evaluation/results_<date>.json` + a metrics report table.

## Acceptance Criteria
- [ ] Given the benchmark, when run, then all outcome metrics are computed vs targets (F1>0.80, P@5>0.65, silhouette>0.40, rubric>3.0, hallucination<15%, kappa>0.60) and reported in one table.
- [ ] Given traces, when computing trajectory metrics, then tool accuracy (correct/total openFDA calls), step efficiency vs oracle (20 cases), error-recovery rate (injected 429s/empties), cost/task, and latency are reported.
- [ ] Given LLM-as-Judge scores and human scores on a shared subset, then Cohen's kappa is computed and reported.
- [ ] Given a re-run after a code change, then results are comparable (regression mode), fixed seeds where applicable.

## Technical Approach
1. Metric modules: extraction F1 (field-level), retrieval P@5 (vs relevance judgments), silhouette (from US-09), rubric scoring (LLM-judge + human), hallucination (uncited-claim count from US-13).
2. Trajectory: parse US-15 traces; tool-call labeling; oracle step counts on 20 hand-labeled retrieval cases; fault injection harness.
3. Judge calibration: run judge + collect human scores on a subset → kappa.
4. One CLI: `python -m evaluation.run --benchmark gold_labels.json`.

## Dependencies
Blocked by: US-05, US-13, US-14, US-15. Blocks: US-18.

## Test Plan
- Unit: each metric on a tiny fixture with known answer.
- Integration: full benchmark run produces the complete results table.

## Definition of Done
- [ ] One-command eval producing outcome + trajectory tables; judge↔human kappa reported.
- [ ] Results feed the final report's evaluation section.
