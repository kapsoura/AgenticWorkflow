# US-09: Similarity & Trend Module (Non-LLM)

| Field | Value |
|---|---|
| Epic | B. Components |
| Owner | M4 |
| Sprint | Week 1–2 |
| Priority | P0 |
| Estimate | 4 days |
| Status | Not started |
| Autonomy | **Non-LLM pipeline** (deterministic ML — not an agent) |

## User Story
As a **Quality Manager**, I want to know whether a new complaint matches an existing cluster of failures and whether that cluster is growing, so that I can tell a one-off from an emerging post-market signal.

## Context
`System_Design.md` §Similarity Module. Deliberately **no LLM** (lecture: "for fixed data transformation, use a non-LLM pipeline"). Consumes US-03 embeddings; outputs `SimilarityOutput`. Backs ISO 13485 §8.2.1 / IEC 62304 §9.6 trend monitoring.

## Scope
- **In**: HDBSCAN clustering over embeddings; UMAP projection; assign new complaint to nearest cluster; temporal growth/anomaly scoring; trend flag.
- **Out**: dashboard rendering (US-10), contrastive embeddings (stretch).

## Inputs / Outputs
- **Input**: `ExtractionOutput` (for the new complaint, embedded on the fly) + historical embeddings (US-03) + event dates.
- **Output**: `SimilarityOutput` — `cluster_id, cluster_label, similar_events[], trend_flag (emerging|stable|declining), cluster_size, growth_rate_30d`. Persist clusters to the `clusters` SQLite table.

## Acceptance Criteria
- [ ] Given all narratives, when clustered, then HDBSCAN yields labeled clusters with **silhouette > 0.40** (target) and noise handled.
- [ ] Given a new complaint embedding, when assigned, then it returns the nearest cluster + top-K similar `report_number`s.
- [ ] Given events with dates, when scoring, then `growth_rate_30d` is computed and `trend_flag = emerging` when growth exceeds a defined threshold (e.g. >2σ over baseline).
- [ ] Given a cluster, then a human-readable `cluster_label` is derived (dominant problem/modality), not just an integer.
- [ ] No LLM call exists anywhere in this module (verified by code review).

## Technical Approach
1. HDBSCAN on the embedding matrix; persist assignments to `clusters` + `events.cluster_id`.
2. UMAP 2D projection cached for the dashboard.
3. Cluster label = top product_problem + modality by frequency.
4. Temporal: events per 30-day window per cluster; z-score / IQR anomaly; (stretch) changepoint (PELT) for emergence.
5. New-complaint assignment: cosine nearest centroid or `approximate_predict`.

## Dependencies
Blocked by: US-03, US-06. Blocks: US-10, feeds US-12 (cluster context), US-14.

## Test Plan
- Unit: cluster a small synthetic embedding set → expected groupings; growth-rate math on a toy time series.
- Eval: silhouette score reported; injected synthetic spike flips a cluster to `emerging`.

## Definition of Done
- [ ] Clusters persisted; new-complaint assignment + trend flag working; silhouette reported.
- [ ] Confirmed LLM-free; UMAP projection cached for US-10.
