# US-02: Manufacturer Entity Resolution

| Field | Value |
|---|---|
| Epic | A. Foundation |
| Owner | M1 |
| Sprint | Week 2 |
| Priority | P1 |
| Estimate | 2 days |
| Status | Not started |

## User Story
As a **retrieval/graph developer**, I want manufacturer names normalized to canonical entities, so that the knowledge graph and evidence retrieval don't fragment one vendor (e.g. Philips) across a dozen spellings.

## Context
The data shows the same vendor under many names — "PHILIPS MEDICAL SYSTEMS NEDERLAND B.V.", "PHILIPS ELECTRONICS NEDERLAND B.V.", "PHILIPS MEDICAL SYSTEMS DMC GMBH", "SIEMENS HEALTHCARE GMBH" vs "SIEMENS HEALTHINEERS AG", etc. Without resolution, graph nodes and cross-product linking break.

## Scope
- **In**: build a manufacturer alias→canonical map; add `manufacturer_normalized` to `events` and `recalls`; cover the top ~30 manufacturers (long tail acceptable).
- **Out**: device-model normalization (future), fuzzy product-code mapping.

## Inputs / Outputs
- **Input**: distinct `manufacturer` / `recalling_firm` values from `signal_intelligence.db`.
- **Output**: `configs/manufacturer_aliases.json` (alias → canonical); `manufacturer_normalized` column populated on `events` and `recalls`.

## Acceptance Criteria
- [ ] Given the top-30 manufacturers by event count, when normalized, then all Philips/Siemens/GE/Beckman/Abbott variants collapse to one canonical each (manually verified).
- [ ] Given an unseen manufacturer string, when normalized, then it falls back to a cleaned (upper-cased, punctuation-stripped) form rather than erroring.
- [ ] Given normalization runs, then a before/after distinct-count report shows the reduction (target: top-30 raw names → ≤15 canonical entities).

## Technical Approach
1. Export distinct names + counts; seed a rules map for the top vendors (prefix matching on "PHILIPS", "SIEMENS", "GE ", "BECKMAN", "ABBOTT", "FUJIFILM").
2. Add fuzzy matching (rapidfuzz token_set_ratio ≥ 90) to catch near-duplicates; human-review the merges into `configs/manufacturer_aliases.json`.
3. Apply map in a migration that backfills `manufacturer_normalized`.

## Dependencies
Blocked by: US-01. Blocks: US-04 (graph quality), US-11 (retrieval recall).

## Test Plan
- Unit: alias map resolves 10 known variant strings to expected canonicals.
- Regression: row count unchanged; null `manufacturer_normalized` = 0.

## Definition of Done
- [ ] Alias map committed and peer-reviewed; columns backfilled.
- [ ] Reduction report produced; top-30 vendors verified by a second team member.
