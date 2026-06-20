from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from src.config import RUNTIME_DIR
from src.pipeline.signal_intelligence_db import get_connection, get_narratives
from src.utils.storage import embed_text

EMBEDDINGS_DIR = RUNTIME_DIR / "signal_intelligence"
EMBEDDINGS_FILE = EMBEDDINGS_DIR / "embeddings.npz"
MODEL_NAME = "BAAI/bge-large-en-v1.5"


class EmbeddingGenerator:
    """Generate and manage BGE-large embeddings for event narratives."""

    def __init__(self, model_name: str = MODEL_NAME, device: Optional[str] = None):
        self.model_name = model_name
        self._model = None
        self._device = device
        self._model_load_attempted = False

    @property
    def model(self):
        # Attempt the (potentially network-bound) model load at most once per
        # instance. Without this guard a failed load is retried on every embed
        # call, repeatedly triggering download/SSL retry storms.
        if self._model is None and not self._model_load_attempted:
            self._model_load_attempted = True
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.model_name, device=self._device)
            except Exception:
                self._model = None
        return self._model

    @property
    def embedding_dim(self) -> int:
        if self.model is None:
            return 32
        return self.model.get_sentence_embedding_dimension()

    def embed_texts(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        if self.model is None:
            return np.array([embed_text(text, dims=32) for text in texts], dtype=np.float32)

        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return np.array(embeddings, dtype=np.float32)

    def embed_single(self, text: str) -> np.ndarray:
        if self.model is None:
            return np.array(embed_text(text, dims=32), dtype=np.float32)

        embedding = self.model.encode([text], normalize_embeddings=True)
        return np.array(embedding[0], dtype=np.float32)

    def build_embeddings(
        self,
        conn=None,
        limit: int = 0,
        batch_size: int = 32,
        incremental: bool = True,
    ) -> tuple[np.ndarray, list[str]]:
        if conn is None:
            conn = get_connection()

        events = get_narratives(conn, limit=limit)
        if not events:
            raise ValueError("No narratives found in signal intelligence DB.")

        narratives = [e["narrative"] for e in events]
        report_numbers = [e["report_number"] for e in events]

        if incremental:
            incremental_result = self._build_embeddings_incremental(
                narratives, report_numbers, batch_size=batch_size
            )
            if incremental_result is not None:
                return incremental_result

        # Full rebuild: no usable cache, or cache dimension is incompatible
        # with the current embedding backend.
        embeddings = self.embed_texts(narratives, batch_size=batch_size)
        return embeddings, report_numbers

    def _build_embeddings_incremental(
        self, narratives: list[str], report_numbers: list[str], batch_size: int = 32
    ) -> Optional[tuple[np.ndarray, list[str]]]:
        """Reuse cached vectors and embed only events missing from the cache.

        Returns the assembled (embeddings, report_numbers) aligned to the DB
        order, or None when the cache is unusable / dimensionally incompatible
        (signalling the caller to perform a full rebuild).
        """
        cache = self._load_cache_map()
        if cache is None:
            return None
        cached_map, cached_dim = cache

        missing = [
            (rn, narrative)
            for rn, narrative in zip(report_numbers, narratives)
            if rn not in cached_map
        ]

        if missing:
            new_embeddings = self.embed_texts(
                [narrative for _, narrative in missing], batch_size=batch_size
            )
            if new_embeddings.ndim != 2 or new_embeddings.shape[1] != cached_dim:
                # Active backend produces a different dimension than the cache
                # (e.g. cached BGE-1024 vs. hash-fallback 32). Cannot mix.
                return None
            for (rn, _), vector in zip(missing, new_embeddings):
                cached_map[rn] = vector

        embeddings = np.array([cached_map[rn] for rn in report_numbers], dtype=np.float32)
        return embeddings, report_numbers

    @classmethod
    def _load_cache_map(cls, path: Optional[Path] = None) -> Optional[tuple[dict, int]]:
        load_path = path or EMBEDDINGS_FILE
        if not load_path.exists():
            return None
        try:
            embeddings, report_numbers = cls.load_embeddings(load_path)
        except Exception:
            return None
        if embeddings.ndim != 2 or len(report_numbers) != embeddings.shape[0]:
            return None
        cached_map = {rn: embeddings[i] for i, rn in enumerate(report_numbers)}
        return cached_map, embeddings.shape[1]

    def save_embeddings(self, embeddings: np.ndarray, report_numbers: list[str], path: Optional[Path] = None):
        save_path = path or EMBEDDINGS_FILE
        save_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(str(save_path), embeddings=embeddings, report_numbers=np.array(report_numbers))

    @staticmethod
    def load_embeddings(path: Optional[Path] = None) -> tuple[np.ndarray, list[str]]:
        load_path = path or EMBEDDINGS_FILE
        data = np.load(str(load_path))
        return data["embeddings"], data["report_numbers"].tolist()


def run_embedding_pipeline(limit: int = 0, batch_size: int = 32):
    gen = EmbeddingGenerator()
    conn = get_connection()
    embeddings, report_numbers = gen.build_embeddings(conn, limit=limit, batch_size=batch_size)
    gen.save_embeddings(embeddings, report_numbers)
    conn.close()
    return embeddings, report_numbers
