"""
Embedding Generator — BGE-large-en-v1.5 (US-03).
Embeds complaint narratives and stores vectors as NumPy arrays.
No vector DB needed at 20K scale.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

import numpy as np
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

from src.pipeline.database import get_connection, get_narratives

EMBEDDINGS_DIR = Path(__file__).resolve().parent.parent.parent / "data"
EMBEDDINGS_FILE = EMBEDDINGS_DIR / "embeddings.npz"
MODEL_NAME = "BAAI/bge-large-en-v1.5"


class EmbeddingGenerator:
    """Generate and manage BGE-large embeddings for event narratives."""

    def __init__(self, model_name: str = MODEL_NAME, device: Optional[str] = None):
        """
        Args:
            model_name: HuggingFace model ID for sentence-transformers.
            device: "cuda", "cpu", or None (auto-detect).
        """
        self.model_name = model_name
        self._model = None
        self._device = device

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(self.model_name, device=self._device)
        return self._model

    @property
    def embedding_dim(self) -> int:
        return self.model.get_sentence_embedding_dimension()

    def embed_texts(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        """Embed a list of texts. Returns (N, 1024) normalized array."""
        # BGE models recommend prepending "Represent this sentence: " for retrieval
        # but for clustering, raw encoding works well
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=True,
            normalize_embeddings=True,
        )
        return np.array(embeddings, dtype=np.float32)

    def embed_single(self, text: str) -> np.ndarray:
        """Embed a single text. Returns (1024,) normalized vector."""
        embedding = self.model.encode(
            [text],
            normalize_embeddings=True,
        )
        return np.array(embedding[0], dtype=np.float32)

    def build_embeddings(
        self,
        conn: Optional[sqlite3.Connection] = None,
        limit: int = 0,
        batch_size: int = 32,
    ) -> tuple[np.ndarray, list[str]]:
        """
        Embed all narratives from the database.

        Returns:
            embeddings: (N, 1024) array
            report_numbers: list of report_number strings (aligned with rows)
        """
        if conn is None:
            conn = get_connection()

        events = get_narratives(conn, limit=limit)
        if not events:
            raise ValueError("No narratives found in database. Run ingestion first.")

        narratives = [e["narrative"] for e in events]
        report_numbers = [e["report_number"] for e in events]

        print(f"Embedding {len(narratives)} narratives with {self.model_name}...")
        embeddings = self.embed_texts(narratives, batch_size=batch_size)

        return embeddings, report_numbers

    def save_embeddings(
        self,
        embeddings: np.ndarray,
        report_numbers: list[str],
        path: Optional[Path] = None,
    ):
        """Save embeddings + report_numbers to a compressed .npz file."""
        save_path = path or EMBEDDINGS_FILE
        save_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            str(save_path),
            embeddings=embeddings,
            report_numbers=np.array(report_numbers),
        )
        size_mb = save_path.stat().st_size / (1024 * 1024)
        print(f"Saved embeddings to {save_path} ({size_mb:.1f} MB)")

    @staticmethod
    def load_embeddings(path: Optional[Path] = None) -> tuple[np.ndarray, list[str]]:
        """Load saved embeddings. Returns (embeddings, report_numbers)."""
        load_path = path or EMBEDDINGS_FILE
        data = np.load(str(load_path))
        embeddings = data["embeddings"]
        report_numbers = data["report_numbers"].tolist()
        print(f"Loaded {len(report_numbers)} embeddings, dim={embeddings.shape[1]}")
        return embeddings, report_numbers


def run_embedding_pipeline(limit: int = 0, batch_size: int = 32):
    """End-to-end: load narratives → embed → save."""
    gen = EmbeddingGenerator()
    conn = get_connection()
    embeddings, report_numbers = gen.build_embeddings(conn, limit=limit, batch_size=batch_size)
    gen.save_embeddings(embeddings, report_numbers)
    conn.close()
    return embeddings, report_numbers


if __name__ == "__main__":
    run_embedding_pipeline()
