from __future__ import annotations

from threading import Lock
from typing import Dict, Optional


class ClusterAssignmentAgent:
    """Assigns an incoming complaint to a pre-built HDBSCAN reference cluster.

    The reference index (BGE embeddings + HDBSCAN clusters) is built offline by
    ``src.build_clusters`` over the archive in ``signal_intelligence_ml.db``. At
    request time this agent embeds the complaint narrative with the SAME BGE model
    and assigns it to the nearest cluster centroid (cosine), returning the cluster
    label, size, 30-day growth, and the nearest prior events.

    Embedding + clustering are vector operations, not LLM calls; extraction still
    runs through the Anthropic client upstream. If the index or model is
    unavailable the agent returns ``None`` so the report flags the section as
    "Not available" instead of failing the workflow.
    """

    def __init__(self):
        self.last_backend = "cluster_index"
        self.last_fallback_reason: Optional[str] = None
        self._lock = Lock()
        self._ready = False
        self._embedder = None
        self._analyzer = None
        self._conn = None

    def _ensure_ready(self) -> bool:
        if self._ready:
            return True
        with self._lock:
            if self._ready:
                return True
            try:
                from src.pipeline.signal_intelligence_db import get_connection
                from src.pipeline.signal_intelligence_embeddings import EmbeddingGenerator
                from src.pipeline.signal_intelligence_trend import TrendAnalyzer

                embeddings, report_numbers = EmbeddingGenerator.load_embeddings()
                embedder = EmbeddingGenerator()
                if embedder.model is None:
                    raise RuntimeError("BGE embedding model unavailable")
                # Guard against a stale low-dim index (e.g. the 32-dim hash cache).
                if embeddings.ndim != 2 or embeddings.shape[1] != embedder.embedding_dim:
                    raise RuntimeError(
                        f"Cluster index dim {getattr(embeddings, 'shape', None)} != "
                        f"model dim {embedder.embedding_dim}; rebuild via `python -m src.build_clusters`"
                    )

                analyzer = TrendAnalyzer()
                analyzer.fit_clusters(embeddings, report_numbers)

                self._embedder = embedder
                self._analyzer = analyzer
                self._conn = get_connection()
                self._ready = True
                self.last_fallback_reason = None
            except Exception as exc:  # noqa: BLE001 — surface the reason to the report
                self.last_fallback_reason = f"Cluster index unavailable: {exc}"
                self._ready = False
            return self._ready

    def assign(self, narrative: str) -> Optional[Dict]:
        if not narrative or not narrative.strip():
            self.last_fallback_reason = "Empty narrative; cannot assign cluster"
            return None
        if not self._ensure_ready():
            return None
        try:
            with self._lock:
                vector = self._embedder.embed_single(narrative)
                result = self._analyzer.assign_complaint(vector, self._conn, top_k=8)
            self.last_fallback_reason = None
            return result.model_dump()
        except Exception as exc:  # noqa: BLE001
            self.last_fallback_reason = f"Cluster assignment failed: {exc}"
            return None
