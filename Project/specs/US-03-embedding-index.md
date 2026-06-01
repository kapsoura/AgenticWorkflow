# US-03: Embedding Index (ChromaDB)

| Field | Value |
|---|---|
| Epic | A. Foundation |
| Owner | M1 + M4 |
| Sprint | Week 1 |
| Priority | P0 |
| Estimate | 2 days |
| Status | Not started |

## User Story
As a **similarity and retrieval developer**, I want all event narratives and recall reasons embedded and stored in a persistent vector index with metadata filtering, so that clustering (US-09) and RAG retrieval (US-11) share one consistent embedding space.

## Context
`Data_Architecture_and_Context.md` §4 specifies ChromaDB with 3 collections. Embeddings are the shared artifact (distributed via cloud storage so members don't recompute).

## Scope
- **In**: embed narratives with `all-MiniLM-L6-v2`; populate 3 ChromaDB collections with metadata; persist to disk.
- **Out**: contrastive fine-tuning (stretch, separate), re-ranking (US-11).

## Inputs / Outputs
- **Input**: `events.narrative`, `recalls.reason_for_recall` (+ `action`) from SQLite.
- **Output**: persistent ChromaDB at `data/embeddings/` with collections:
  - `event_narratives` — meta: `product_code, event_type, manufacturer_normalized, date, modality`
  - `recall_reasons` — meta: `product_code, root_cause, classification, manufacturer_normalized`
  - `combined_regulatory` — both, for cross-domain search
  - Each doc id = `report_number` / `recall_number`; `embedding_id` written back to SQLite.

## Acceptance Criteria
- [ ] Given ~14–20K narratives, when embedded, then all three collections persist and reload without recompute (cosine space).
- [ ] Given a query string, when `event_narratives` is queried with a `product_code` filter, then only that code's events return.
- [ ] Given an event row, then its `embedding_id` in SQLite resolves to the matching ChromaDB doc.
- [ ] Given narratives < 32 chars, when embedding, then they are flagged low-quality (not dropped) per the data-quality rules.

## Technical Approach
1. Batch-embed with sentence-transformers (GPU if available, else CPU; batch ≥ 64).
2. `chromadb.PersistentClient`; `get_or_create_collection(metadata={"hnsw:space":"cosine"})`.
3. Upsert in batches with ids + metadata; write `embedding_id` back to SQLite.

## Dependencies
Blocked by: US-01. Blocks: US-09, US-11.

## Test Plan
- Unit: embed 5 narratives → vectors of expected dim (384).
- Integration: metadata-filtered query returns correct subset; reload persists.

## Definition of Done
- [ ] 3 collections populated and persisted; reload verified.
- [ ] `embedding_id` linkage SQLite↔Chroma verified; embeddings shared to cloud.
