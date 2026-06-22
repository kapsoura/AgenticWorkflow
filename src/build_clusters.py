"""Offline cluster-index build.

Rebuilds the reference cluster index over the archive already in
``signal_intelligence_ml.db``:

    narratives -> BGE embeddings -> HDBSCAN clusters (+ UMAP) -> persisted

Run once (and whenever the archive changes):

    python -m src.build_clusters

The resulting ``embeddings.npz`` + ``clusters`` table are what the online
``ClusterAssignmentAgent`` loads to assign each incoming complaint to an
existing cluster. Embeddings are BGE-large (not the 32-dim hash) so the index
and the live query embeddings share the same space.
"""

from __future__ import annotations

import sys
import time

import numpy as np

from src.pipeline.signal_intelligence_db import get_narratives, init_db
from src.pipeline.signal_intelligence_embeddings import EMBEDDINGS_FILE, EmbeddingGenerator
from src.pipeline.signal_intelligence_trend import TrendAnalyzer


def main() -> int:
    conn = init_db()
    gen = EmbeddingGenerator()

    model = gen.model  # forces the (download-on-first-use) model load
    if model is None:
        print("ERROR: embedding model unavailable (sentence-transformers not usable).")
        return 1
    print(f"Embedding model loaded: {gen.model_name} (dim={gen.embedding_dim})")

    rows = get_narratives(conn, limit=0)
    narratives = [r["narrative"] for r in rows]
    report_numbers = [r["report_number"] for r in rows]
    total = len(narratives)
    if total == 0:
        print("ERROR: no narratives in the ML DB to embed.")
        return 1

    print(f"Embedding {total} narratives with BGE ...")
    t0 = time.time()
    chunk = 256
    parts = []
    for i in range(0, total, chunk):
        batch = narratives[i : i + chunk]
        vecs = model.encode(batch, batch_size=64, normalize_embeddings=True, show_progress_bar=False)
        parts.append(np.asarray(vecs, dtype=np.float32))
        done = min(i + chunk, total)
        print(f"  {done}/{total}  ({time.time() - t0:.0f}s)", flush=True)

    embeddings = np.vstack(parts)
    gen.save_embeddings(embeddings, report_numbers)
    print(f"Saved embeddings {embeddings.shape} -> {EMBEDDINGS_FILE}")

    analyzer = TrendAnalyzer()
    analyzer.fit_clusters(embeddings, report_numbers)
    labels = [int(x) for x in (analyzer.labels if analyzer.labels is not None else [])]
    n_clusters = len({c for c in labels if c != -1})
    n_noise = sum(1 for c in labels if c == -1)
    print(f"HDBSCAN: {n_clusters} clusters, {n_noise} noise points")

    analyzer.save_labels()
    analyzer.compute_umap()
    analyzer.save_clusters_to_db(conn)
    print("Saved clusters + per-event labels to DB/disk. Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
