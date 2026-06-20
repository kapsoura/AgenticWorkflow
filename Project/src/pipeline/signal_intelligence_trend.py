from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np

from src.config import RUNTIME_DIR
from src.pipeline.signal_intelligence_db import get_connection
from src.pipeline.signal_intelligence_schemas import SimilarEvent, SimilarityOutput, TrendFlag

UMAP_CACHE_PATH = RUNTIME_DIR / "signal_intelligence" / "umap_projection.npy"
# Per-event HDBSCAN labels persisted by the offline build so the online agent can
# assign complaints to existing clusters without ever re-running HDBSCAN.
CLUSTER_LABELS_PATH = RUNTIME_DIR / "signal_intelligence" / "cluster_labels.npz"


class TrendAnalyzer:
    """Deterministic ML pipeline for pattern detection and trend analysis."""

    def __init__(
        self,
        min_cluster_size: int = 15,
        min_samples: int = 5,
        umap_n_neighbors: int = 15,
        umap_min_dist: float = 0.1,
    ):
        self.min_cluster_size = min_cluster_size
        self.min_samples = min_samples
        self.umap_n_neighbors = umap_n_neighbors
        self.umap_min_dist = umap_min_dist

        self.clusterer = None
        self.labels: Optional[np.ndarray] = None
        self.umap_projection: Optional[np.ndarray] = None
        self.embeddings: Optional[np.ndarray] = None
        self.report_numbers: Optional[list[str]] = None
        self.cluster_centroids: dict[int, np.ndarray] = {}

    def fit_clusters(self, embeddings: np.ndarray, report_numbers: list[str]) -> np.ndarray:
        self.embeddings = embeddings
        self.report_numbers = report_numbers
        try:
            import hdbscan

            self.clusterer = hdbscan.HDBSCAN(
                min_cluster_size=self.min_cluster_size,
                min_samples=self.min_samples,
                metric="euclidean",
                cluster_selection_method="eom",
            )
            self.labels = self.clusterer.fit_predict(embeddings)
        except Exception:
            self.clusterer = None
            self.labels = np.zeros((len(embeddings),), dtype=int)
        self._compute_centroids()
        return self.labels

    def load_clusters(
        self,
        embeddings: np.ndarray,
        report_numbers: list[str],
        labels: np.ndarray,
    ) -> np.ndarray:
        """Restore a pre-built cluster index without re-running HDBSCAN.

        Used at request time: the offline build already fit HDBSCAN and persisted
        the per-event labels, so the online agent only needs to recompute the
        (cheap) centroids and is ready to assign new complaints by nearest
        centroid. No clustering happens here.
        """
        self.embeddings = embeddings
        self.report_numbers = report_numbers
        self.labels = np.asarray(labels)
        self.clusterer = None
        self._compute_centroids()
        return self.labels

    def save_labels(self, path: Optional[Path] = None) -> None:
        """Persist the per-event HDBSCAN labels alongside the embeddings index."""
        if self.labels is None or self.report_numbers is None:
            return
        save_path = path or CLUSTER_LABELS_PATH
        save_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            str(save_path),
            labels=np.asarray(self.labels),
            report_numbers=np.array(self.report_numbers),
        )

    @staticmethod
    def load_labels(path: Optional[Path] = None) -> Optional[tuple[np.ndarray, list[str]]]:
        """Load persisted labels, or None when the artifact is absent/unreadable."""
        load_path = path or CLUSTER_LABELS_PATH
        if not Path(load_path).exists():
            return None
        try:
            data = np.load(str(load_path))
            return data["labels"], data["report_numbers"].tolist()
        except Exception:
            return None

    def _compute_centroids(self):
        self.cluster_centroids = {}
        if self.labels is None or self.embeddings is None:
            return
        for cid in set(self.labels):
            if cid == -1:
                continue
            mask = self.labels == cid
            centroid = self.embeddings[mask].mean(axis=0)
            norm = np.linalg.norm(centroid) or 1.0
            self.cluster_centroids[cid] = centroid / norm

    def compute_umap(self, embeddings: Optional[np.ndarray] = None) -> np.ndarray:
        emb = embeddings if embeddings is not None else self.embeddings
        if emb is None:
            raise ValueError("No embeddings available. Run fit_clusters first.")

        try:
            import umap

            reducer = umap.UMAP(
                n_neighbors=self.umap_n_neighbors,
                min_dist=self.umap_min_dist,
                n_components=2,
                metric="cosine",
                random_state=42,
            )
            self.umap_projection = reducer.fit_transform(emb)
        except Exception:
            if emb.shape[1] >= 2:
                self.umap_projection = emb[:, :2]
            else:
                self.umap_projection = np.column_stack([emb[:, 0], np.zeros((emb.shape[0],))])
        UMAP_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        np.save(str(UMAP_CACHE_PATH), self.umap_projection)
        return self.umap_projection

    @staticmethod
    def _cosine_pair(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
        qn = np.linalg.norm(query, axis=1, keepdims=True)
        mn = np.linalg.norm(matrix, axis=1, keepdims=True).T
        denom = np.clip(qn * mn, 1e-9, None)
        return (query @ matrix.T) / denom

    def label_clusters(self, conn) -> dict[int, str]:
        if self.labels is None or self.report_numbers is None:
            raise ValueError("Run fit_clusters first.")

        cluster_labels = {}
        for cid in set(self.labels):
            if cid == -1:
                continue
            mask = self.labels == cid
            rns = [self.report_numbers[i] for i in range(len(self.report_numbers)) if mask[i]]
            placeholders = ",".join(["?"] * len(rns))
            rows = conn.execute(
                f"""SELECT e.modality, ep.problem_code
                    FROM events e
                    LEFT JOIN event_problems ep ON e.id = ep.event_id
                    WHERE e.report_number IN ({placeholders})""",
                rns,
            ).fetchall()

            modalities = Counter()
            problems = Counter()
            for row in rows:
                if row["modality"]:
                    modalities[row["modality"]] += 1
                if row["problem_code"]:
                    problems[row["problem_code"]] += 1

            top_modality = modalities.most_common(1)[0][0] if modalities else "Mixed"
            top_problem = problems.most_common(1)[0][0] if problems else "Unknown"
            cluster_labels[cid] = f"{top_modality} - {top_problem}"

        return cluster_labels

    def compute_growth_rates(self, conn) -> dict[int, float]:
        if self.labels is None or self.report_numbers is None:
            return {}

        growth_rates = {}
        now = datetime.now()
        cutoff_30 = (now - timedelta(days=30)).strftime("%Y%m%d")
        cutoff_60 = (now - timedelta(days=60)).strftime("%Y%m%d")

        for cid in set(self.labels):
            if cid == -1:
                continue
            mask = self.labels == cid
            rns = [self.report_numbers[i] for i in range(len(self.report_numbers)) if mask[i]]
            placeholders = ",".join(["?"] * len(rns))

            recent = conn.execute(
                f"""SELECT COUNT(*) FROM events
                    WHERE report_number IN ({placeholders})
                    AND date_received >= ?""",
                rns + [cutoff_30],
            ).fetchone()[0]

            prior = conn.execute(
                f"""SELECT COUNT(*) FROM events
                    WHERE report_number IN ({placeholders})
                    AND date_received >= ? AND date_received < ?""",
                rns + [cutoff_60, cutoff_30],
            ).fetchone()[0]

            if prior > 0:
                growth = (recent - prior) / prior * 100
            elif recent > 0:
                growth = 100.0
            else:
                growth = 0.0
            growth_rates[cid] = round(growth, 1)

        return growth_rates

    @staticmethod
    def _classify_trend(growth_rate: float) -> TrendFlag:
        if growth_rate > 20:
            return TrendFlag.EMERGING
        if growth_rate < -20:
            return TrendFlag.DECLINING
        return TrendFlag.STABLE

    def assign_complaint(self, embedding: np.ndarray, conn, top_k: int = 10) -> SimilarityOutput:
        if self.embeddings is None or self.labels is None or self.report_numbers is None:
            raise ValueError("Trend analyzer must be fitted before assignment")

        emb = embedding.reshape(1, -1)

        best_cluster = -1
        best_cluster_score = -1.0
        for cid, centroid in self.cluster_centroids.items():
            score = float(self._cosine_pair(emb, centroid.reshape(1, -1))[0][0])
            if score > best_cluster_score:
                best_cluster_score = score
                best_cluster = int(cid)

        if best_cluster == -1:
            best_cluster = 0
            cluster_label = "Unassigned"
        else:
            cluster_label = self.label_clusters(conn).get(best_cluster, f"Cluster {best_cluster}")

        scores = self._cosine_pair(emb, self.embeddings)[0]
        top_idx = np.argsort(scores)[::-1][:top_k]
        similar_events: list[SimilarEvent] = []
        for idx in top_idx:
            report_number = self.report_numbers[int(idx)]
            row = conn.execute(
                "SELECT narrative FROM events WHERE report_number = ?",
                (report_number,),
            ).fetchone()
            snippet = row["narrative"][:160] if row and row["narrative"] else None
            similar_events.append(
                SimilarEvent(
                    report_number=report_number,
                    similarity_score=float(max(0.0, min(1.0, scores[int(idx)]))),
                    narrative_snippet=snippet,
                )
            )

        cluster_size = int(sum(1 for label in self.labels if int(label) == int(best_cluster)))
        growth_rate = self.compute_growth_rates(conn).get(best_cluster, 0.0)
        trend_flag = self._classify_trend(growth_rate)

        return SimilarityOutput(
            cluster_id=int(best_cluster),
            cluster_label=cluster_label,
            similar_events=similar_events,
            trend_flag=trend_flag,
            cluster_size=cluster_size,
            growth_rate_30d=float(growth_rate),
            cluster_daily_counts={},
        )

    def save_clusters_to_db(self, conn) -> None:
        if self.labels is None:
            return
        labels_map = self.label_clusters(conn)
        growth_map = self.compute_growth_rates(conn)

        for cid in set(self.labels):
            if cid == -1:
                continue
            csize = int(sum(1 for x in self.labels if int(x) == int(cid)))
            label = labels_map.get(int(cid), f"Cluster {int(cid)}")
            growth = float(growth_map.get(int(cid), 0.0))
            trend = self._classify_trend(growth).value
            conn.execute(
                """INSERT OR REPLACE INTO clusters(id, label, size, growth_rate_30d, trend_flag)
                   VALUES (?, ?, ?, ?, ?)""",
                (int(cid), label, csize, growth, trend),
            )
        conn.commit()


def run_trend_pipeline(embeddings: np.ndarray, report_numbers: list[str]):
    conn = get_connection()
    analyzer = TrendAnalyzer()
    analyzer.fit_clusters(embeddings, report_numbers)
    analyzer.save_labels()
    analyzer.compute_umap()
    analyzer.save_clusters_to_db(conn)
    conn.close()
    return analyzer
