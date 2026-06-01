# US-04: Knowledge Graph Construction

| Field | Value |
|---|---|
| Epic | A. Foundation |
| Owner | M2 |
| Sprint | Week 1–2 |
| Priority | P1 |
| Estimate | 2–3 days |
| Status | Not started |

## User Story
As a **retrieval developer**, I want a knowledge graph linking devices, product codes, manufacturers, recalls, and root causes, so that Agent 3 can traverse non-obvious connections (Graph RAG) instead of relying on flat vector search alone.

## Context
`Data_Architecture_and_Context.md` §4 specifies a NetworkX graph (~3.4K nodes) built from the 3,299 recalls + events. This is the structured backbone of US-11's Graph RAG.

## Scope
- **In**: build directed graph; node types ProductCode, Manufacturer, Recall, RootCause, (optional Device/Brand); serialize to GraphML; expose query helpers.
- **Out**: Neo4j (explicitly out of scope — overkill for 3.4K nodes), embedding-hybrid ranking (US-11).

## Inputs / Outputs
- **Input**: `recalls` + `events` (with `manufacturer_normalized` from US-02).
- **Output**: `data/knowledge_graph.graphml`; `src/agents/retrieval_graph.py` helper API:
  - `recalls_for(product_code, root_cause=None, manufacturer=None) -> list`
  - `other_codes_for(manufacturer) -> list`
  - `top_root_causes(product_code) -> list[(cause,count)]`

## Acceptance Criteria
- [ ] Given the recalls, when the graph builds, then edges encode `Recall–affects→ProductCode`, `Manufacturer–issued→Recall`, `Recall–caused_by→RootCause`, and `Manufacturer–also_makes→ProductCode`.
- [ ] Given product code LNH + manufacturer Philips + root cause "Software design", when queried, then only matching recalls return.
- [ ] Given a manufacturer, when `other_codes_for` is called, then all product codes that manufacturer has recalls under are returned (cross-product linking).
- [ ] Given the graph is serialized and reloaded, then node/edge counts are stable.

## Technical Approach
1. `networkx.DiGraph`; add typed nodes (store `type`, `classification`, `reason` as attrs).
2. Iterate recalls → add nodes+edges using `manufacturer_normalized`.
3. `nx.write_graphml` / `read_graphml`; helper functions wrap traversals.

## Dependencies
Blocked by: US-01, US-02. Blocks: US-11.

## Test Plan
- Unit: build graph from 10 sample recalls → assert expected edges + a 2-hop traversal (manufacturer → recalls → root causes).
- Integration: reload GraphML → counts match.

## Definition of Done
- [ ] GraphML committed-by-script (regeneratable); helper API + tests pass.
- [ ] Node/edge count report (~3.4K nodes) documented.
