# US-10: Signal Dashboard (Streamlit)

| Field | Value |
|---|---|
| Epic | B. Components |
| Owner | M4 |
| Sprint | Week 2–3 |
| Priority | P1 |
| Estimate | 3 days |
| Status | Not started |

## User Story
As a **Quality Manager**, I want an interactive dashboard showing the failure-mode landscape, where a new complaint lands, and which clusters are trending, so that I can visually triage signals and bring evidence to the Quality Review Board.

## Context
`System_Design.md` §Similarity Module dashboard output + Observability dashboard page. Visualizes US-09 output and (later) US-15 cost/latency.

## Scope
- **In**: UMAP scatter colored by failure mode/modality; temporal slider; cluster growth indicators; new-complaint highlight; paste-a-complaint → run pipeline view.
- **Out**: auth, multi-user, production deployment.

## Inputs / Outputs
- **Input**: cached UMAP projection + `clusters`/`events` (US-09); pipeline output (US-14) for the single-complaint view; trace stats (US-15).
- **Output**: `src/dashboard/app.py` Streamlit app.

## Acceptance Criteria
- [ ] Given the projection, when the dashboard loads, then a UMAP scatter renders, colorable by failure mode and by modality.
- [ ] Given the temporal slider, when moved, then the plot shows cluster evolution over time windows.
- [ ] Given a pasted complaint, when submitted, then its position is highlighted on the map and the generated signal report is shown.
- [ ] Given trending clusters, then growth-rate indicators / an "emerging" badge are visible.
- [ ] Given the observability page, then cost/latency/completion-rate per day are displayed (depends on US-15).

## Technical Approach
1. Plotly scatter from cached UMAP; Streamlit widgets for color-by + time slider.
2. Single-complaint tab calls the orchestrator (US-14); render `ReportOutput` markdown.
3. Stats tab reads aggregated traces (US-15).

## Dependencies
Blocked by: US-09. Soft-depends: US-14 (single-complaint view), US-15 (stats). Blocks: demo.

## Test Plan
- Smoke: app launches; scatter + slider interact without error on the real dataset.
- Manual: 5 demo complaints render correctly.

## Definition of Done
- [ ] Dashboard runs locally; all four panels functional (stats panel gated on US-15).
- [ ] Used in Week-4 demo rehearsal.
