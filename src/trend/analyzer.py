"""
Trend & Similarity Module (US-09) — Non-LLM deterministic ML pipeline.
HDBSCAN clustering + UMAP projection + temporal anomaly scoring.
No LLM calls anywhere in this module.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import hdbscan
import numpy as np
import umap
from sklearn.metrics import silhouette_score
from sklearn.metrics.pairwise import cosine_similarity

from src.pipeline.database import get_connection
from src.pipeline.schemas import SimilarEvent, SimilarityOutput, TrendFlag

UMAP_CACHE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "umap_projection.npy"
CLUSTER_CACHE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "cluster_cache.npz"


class TrendAnalyzer:
    """
    Deterministic ML pipeline for pattern detection and trend analysis.

    Pipeline:
        1. HDBSCAN clustering over BGE-large embeddings
        2. UMAP 2D projection (cached for dashboard)
        3. Cluster labeling from dominant problem/modality
        4. Temporal growth rate scoring
        5. New complaint → nearest cluster assignment + top-K similar events
    """

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

        self.clusterer: Optional[hdbscan.HDBSCAN] = None
        self.labels: Optional[np.ndarray] = None
        self.umap_projection: Optional[np.ndarray] = None
        self.embeddings: Optional[np.ndarray] = None
        self.report_numbers: Optional[list[str]] = None
        self.cluster_centroids: dict[int, np.ndarray] = {}

    # ─── Clustering ──────────────────────────────────────────────────────

    def fit_clusters(self, embeddings: np.ndarray, report_numbers: list[str]) -> np.ndarray:
        """
        Run HDBSCAN clustering on the embedding matrix.

        Args:
            embeddings: (N, 1024) normalized embedding matrix.
            report_numbers: aligned list of report_number strings.

        Returns:
            labels: (N,) cluster labels (-1 = noise).
        """
        self.embeddings = embeddings
        self.report_numbers = report_numbers

        print(f"Clustering {len(embeddings)} embeddings with HDBSCAN "
              f"(min_cluster_size={self.min_cluster_size})...")

        self.clusterer = hdbscan.HDBSCAN(
            min_cluster_size=self.min_cluster_size,
            min_samples=self.min_samples,
            metric="euclidean",
            cluster_selection_method="eom",
        )
        self.labels = self.clusterer.fit_predict(embeddings)

        n_clusters = len(set(self.labels)) - (1 if -1 in self.labels else 0)
        n_noise = (self.labels == -1).sum()
        print(f"  Found {n_clusters} clusters, {n_noise} noise points "
              f"({n_noise / len(self.labels) * 100:.1f}%)")

        # Compute silhouette (excluding noise)
        if n_clusters > 1:
            mask = self.labels != -1
            if mask.sum() > n_clusters:
                score = silhouette_score(embeddings[mask], self.labels[mask], metric="cosine")
                print(f"  Silhouette score: {score:.3f}")

        # Compute centroids
        self._compute_centroids()

        # Save cache to disk
        self._save_cache()

        return self.labels

    def _save_cache(self):
        """Persist cluster labels and centroids to disk."""
        if self.labels is None or not self.cluster_centroids:
            return
        CLUSTER_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        centroid_ids = sorted(self.cluster_centroids.keys())
        centroid_matrix = np.array([self.cluster_centroids[cid] for cid in centroid_ids])
        np.savez(
            str(CLUSTER_CACHE_PATH),
            labels=self.labels,
            centroid_ids=np.array(centroid_ids),
            centroid_matrix=centroid_matrix,
        )
        print(f"  Cluster cache saved to {CLUSTER_CACHE_PATH}")

    def load_cache(self, embeddings: np.ndarray, report_numbers: list[str]) -> bool:
        """Load cached cluster data from disk. Returns True if loaded successfully."""
        if not CLUSTER_CACHE_PATH.exists():
            return False
        try:
            data = np.load(str(CLUSTER_CACHE_PATH))
            labels = data["labels"]
            if len(labels) != len(embeddings):
                print("  Cluster cache size mismatch, will recompute.")
                return False
            self.embeddings = embeddings
            self.report_numbers = report_numbers
            self.labels = labels
            centroid_ids = data["centroid_ids"]
            centroid_matrix = data["centroid_matrix"]
            self.cluster_centroids = {int(cid): centroid_matrix[i] for i, cid in enumerate(centroid_ids)}
            n_clusters = len(self.cluster_centroids)
            print(f"  Loaded {n_clusters} clusters from cache ({CLUSTER_CACHE_PATH})")
            return True
        except Exception as e:
            print(f"  Failed to load cluster cache: {e}")
            return False

    def _compute_centroids(self):
        """Compute mean embedding per cluster (excluding noise)."""
        self.cluster_centroids = {}
        if self.labels is None or self.embeddings is None:
            return
        for cid in set(self.labels):
            if cid == -1:
                continue
            mask = self.labels == cid
            centroid = self.embeddings[mask].mean(axis=0)
            # Normalize
            centroid = centroid / np.linalg.norm(centroid)
            self.cluster_centroids[cid] = centroid

    # ─── UMAP Projection ────────────────────────────────────────────────

    def compute_umap(self, embeddings: Optional[np.ndarray] = None) -> np.ndarray:
        """Compute 2D UMAP projection for visualization."""
        emb = embeddings if embeddings is not None else self.embeddings
        if emb is None:
            raise ValueError("No embeddings available. Run fit_clusters first.")

        print("Computing UMAP 2D projection...")
        reducer = umap.UMAP(
            n_neighbors=self.umap_n_neighbors,
            min_dist=self.umap_min_dist,
            n_components=2,
            metric="cosine",
            random_state=42,
        )
        self.umap_projection = reducer.fit_transform(emb)

        # Cache for dashboard
        UMAP_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        np.save(str(UMAP_CACHE_PATH), self.umap_projection)
        print(f"  UMAP projection cached to {UMAP_CACHE_PATH}")

        return self.umap_projection

    # ─── Cluster Labeling ────────────────────────────────────────────────

    def label_clusters(self, conn: sqlite3.Connection) -> dict[int, str]:
        """
        Generate human-readable labels for each cluster.
        Label = dominant product_problem + modality by frequency.
        """
        if self.labels is None or self.report_numbers is None:
            raise ValueError("Run fit_clusters first.")

        cluster_labels = {}
        for cid in set(self.labels):
            if cid == -1:
                continue

            # Get report_numbers in this cluster
            mask = self.labels == cid
            rns = [self.report_numbers[i] for i in range(len(self.report_numbers)) if mask[i]]

            # Query DB for problems + modality
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

            label = f"{top_modality} - {top_problem}"
            cluster_labels[cid] = label

        return cluster_labels

    # ─── Temporal Growth Rate ────────────────────────────────────────────

    def compute_growth_rates(self, conn: sqlite3.Connection) -> dict[int, float]:
        """
        Compute 30-day growth rate for each cluster.
        growth_rate = (events_last_30d - events_prior_30d) / events_prior_30d * 100
        """
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

            # Events in last 30 days
            recent = conn.execute(
                f"""SELECT COUNT(*) FROM events
                    WHERE report_number IN ({placeholders})
                    AND date_received >= ?""",
                rns + [cutoff_30],
            ).fetchone()[0]

            # Events in prior 30 days (30-60 days ago)
            prior = conn.execute(
                f"""SELECT COUNT(*) FROM events
                    WHERE report_number IN ({placeholders})
                    AND date_received >= ? AND date_received < ?""",
                rns + [cutoff_60, cutoff_30],
            ).fetchone()[0]

            if prior > 0:
                growth = (recent - prior) / prior * 100
            elif recent > 0:
                growth = 100.0  # New cluster, all events are recent
            else:
                growth = 0.0

            growth_rates[cid] = round(growth, 1)

        return growth_rates

    def _classify_trend(self, growth_rate: float) -> TrendFlag:
        """Classify trend based on growth rate."""
        if growth_rate > 20:
            return TrendFlag.EMERGING
        elif growth_rate < -20:
            return TrendFlag.DECLINING
        else:
            return TrendFlag.STABLE

    # ─── New Complaint Assignment ────────────────────────────────────────

    def assign_complaint(
        self,
        embedding: np.ndarray,
        conn: sqlite3.Connection,
        top_k: int = 10,
    ) -> SimilarityOutput:
        """
        Assign a new complaint to the nearest cluster and find similar events.

        Args:
            embedding: (1024,) normalized embedding of the new complaint.
            conn: DB connection for cluster labels and growth rates.
            top_k: Number of similar events to return.

        Returns:
            SimilarityOutput with cluster info, similar events, and trend.
        """
        if not self.cluster_centroids or self.embeddings is None:
            raise ValueError("Run fit_clusters first.")

        # Find similar events by cosine similarity to all embeddings
        similarities = cosine_similarity(embedding.reshape(1, -1), self.embeddings)[0]

        # Use a larger neighbor window for voting (skip noise points)
        vote_k = min(50, len(self.embeddings))
        vote_indices = np.argsort(similarities)[::-1][:vote_k]

        # Weighted majority vote using only clustered (non-noise) neighbors
        # Weight by similarity score so closer neighbors have more influence
        label_weights: dict[int, float] = {}
        for idx in vote_indices:
            lbl = self.labels[idx]
            if lbl == -1:
                continue
            weight = float(similarities[idx]) ** 2  # Square to emphasize closer neighbors
            label_weights[lbl] = label_weights.get(lbl, 0.0) + weight

        if label_weights:
            best_cluster = max(label_weights, key=label_weights.get)
        else:
            # Fallback to centroid similarity
            best_cluster = -1
            best_sim = -1.0
            for cid, centroid in self.cluster_centroids.items():
                sim = float(cosine_similarity(embedding.reshape(1, -1), centroid.reshape(1, -1))[0, 0])
                if sim > best_sim:
                    best_sim = sim
                    best_cluster = cid

        # Return top-K similar events for display
        top_indices = np.argsort(similarities)[::-1][:top_k]
        similar_events = []
        for idx in top_indices:
            similar_events.append(
                SimilarEvent(
                    report_number=self.report_numbers[idx],
                    similarity_score=round(float(similarities[idx]), 4),
                )
            )

        # Get cluster metadata
        cluster_labels = self.label_clusters(conn)
        growth_rates = self.compute_growth_rates(conn)

        cluster_label = cluster_labels.get(best_cluster, "Unassigned")
        cluster_size = int((self.labels == best_cluster).sum()) if best_cluster != -1 else 0
        growth_rate = growth_rates.get(best_cluster, 0.0)
        trend = self._classify_trend(growth_rate)

        # Compute daily event counts for this cluster over last 30 days
        daily_counts = self._compute_cluster_daily_counts(best_cluster, conn)

        return SimilarityOutput(
            cluster_id=best_cluster,
            cluster_label=cluster_label,
            similar_events=similar_events,
            trend_flag=trend,
            cluster_size=cluster_size,
            growth_rate_30d=growth_rate,
            cluster_daily_counts=daily_counts,
        )

    # ─── Cluster Daily Counts ───────────────────────────────────────────

    def _compute_cluster_daily_counts(self, cluster_id: int, conn: sqlite3.Connection) -> dict[str, int]:
        """
        Get daily event counts for a cluster over the past 30 days.
        Returns {YYYY-MM-DD: count} for days with events.
        """
        if cluster_id == -1 or self.labels is None or self.report_numbers is None:
            return {}

        mask = self.labels == cluster_id
        rns = [self.report_numbers[i] for i in range(len(self.report_numbers)) if mask[i]]
        if not rns:
            return {}

        cutoff = int((datetime.now() - timedelta(days=30)).strftime("%Y%m%d"))
        placeholders = ",".join(["?"] * len(rns))

        rows = conn.execute(
            f"""SELECT date_received, COUNT(*) as cnt
                FROM events
                WHERE report_number IN ({placeholders})
                  AND date_received >= ?
                GROUP BY date_received
                ORDER BY date_received""",
            rns + [cutoff],
        ).fetchall()

        daily_counts = {}
        for row in rows:
            dr = str(row["date_received"])
            date_str = f"{dr[:4]}-{dr[4:6]}-{dr[6:8]}"
            daily_counts[date_str] = row["cnt"]

        return daily_counts

    # ─── Persist Clusters to DB ──────────────────────────────────────────

    def save_clusters_to_db(self, conn: sqlite3.Connection):
        """Write cluster assignments + metadata to the database."""
        if self.labels is None or self.report_numbers is None:
            raise ValueError("Run fit_clusters first.")

        cluster_labels = self.label_clusters(conn)
        growth_rates = self.compute_growth_rates(conn)

        # Update events with cluster_id
        for i, rn in enumerate(self.report_numbers):
            conn.execute(
                "UPDATE events SET cluster_id = ? WHERE report_number = ?",
                (int(self.labels[i]), rn),
            )

        # Upsert clusters table
        for cid in set(self.labels):
            if cid == -1:
                continue

            cid_int = int(cid)
            mask = self.labels == cid
            size = int(mask.sum())
            label = cluster_labels.get(cid, f"Cluster {cid}")
            growth = float(growth_rates.get(cid, 0.0))
            trend = self._classify_trend(growth).value

            # Get dominant modality/problem from label
            parts = label.split(" - ", 1)
            dominant_modality = parts[0] if len(parts) > 0 else ""
            dominant_problem = parts[1] if len(parts) > 1 else ""

            conn.execute(
                """INSERT OR REPLACE INTO clusters
                   (id, label, size, growth_rate_30d, dominant_problem,
                    dominant_modality, trend_flag)
                   VALUES (?,?,?,?,?,?,?)""",
                (cid_int, label, size, growth, dominant_problem, dominant_modality, trend),
            )

        conn.commit()
        print(f"Saved {len(cluster_labels)} clusters to DB")


def run_trend_pipeline(embeddings: np.ndarray, report_numbers: list[str]):
    """End-to-end trend analysis pipeline."""
    conn = get_connection()
    analyzer = TrendAnalyzer()

    # 1. Cluster
    labels = analyzer.fit_clusters(embeddings, report_numbers)

    # 2. UMAP projection
    analyzer.compute_umap()

    # 3. Label + growth rates
    cluster_labels = analyzer.label_clusters(conn)
    growth_rates = analyzer.compute_growth_rates(conn)

    print("\n── Cluster Summary ──")
    for cid, label in sorted(cluster_labels.items()):
        size = int((labels == cid).sum())
        growth = growth_rates.get(cid, 0.0)
        trend = analyzer._classify_trend(growth)
        print(f"  Cluster {cid}: {label} | size={size} | growth={growth:+.1f}% | {trend.value}")

    # 4. Persist
    analyzer.save_clusters_to_db(conn)

    conn.close()
    return analyzer
