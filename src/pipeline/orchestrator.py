"""
Pipeline Orchestrator — ties together ingestion, extraction, embedding, and trend analysis.
Autonomy Level: L2 (Workflow/Assembly Line) — fixed pipeline, engineer-defined control flow.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from src.embeddings.generator import EmbeddingGenerator, run_embedding_pipeline
from src.extraction.agent import ExtractionAgent
from src.pipeline.database import (
    get_connection,
    get_db_stats,
    get_unextracted_events,
    init_db,
    update_extraction_fields,
)
from src.pipeline.schemas import ExtractionOutput, validate_handoff
from src.trend.analyzer import TrendAnalyzer, run_trend_pipeline


class Pipeline:
    """
    Main extraction + trend analysis pipeline.

    Flow:
        1. Ingest data (download from openFDA → SQLite)   [run separately]
        2. Extract structured fields from narratives       [LLM-based]
        3. Embed narratives with BGE-large                 [sentence-transformers]
        4. Cluster + trend analysis                        [HDBSCAN + UMAP]
        5. Assign new complaints to clusters               [cosine similarity]
    """

    def __init__(
        self,
        model: str = "mistral-small",
        base_url: str = "http://localhost:11434",
        db_path: Optional[Path] = None,
        num_workers: int = 4,
    ):
        self.db_path = db_path
        self.conn = init_db(db_path)
        self.num_workers = num_workers
        self.extractor = ExtractionAgent(model=model, base_url=base_url)
        # Create per-worker extractors to avoid connection contention
        self._extractors = [ExtractionAgent(model=model, base_url=base_url) for _ in range(num_workers)]
        self.embedder = EmbeddingGenerator()
        self.trend_analyzer = TrendAnalyzer()

    # --- Step 2: Extraction ----------------------------------------------────

    def run_extraction(self, batch_size: int = 10, reflect: bool = False, max_events: int = 0) -> int:
        """
        Process unextracted events through Agent 1.

        Args:
            batch_size: Number of events to process per batch.
            reflect: Whether to run self-reflection pass (default False for speed).
            max_events: Max events to process (0 = unlimited).

        Returns:
            Number of successfully extracted events.
        """
        total_extracted = 0
        workers = self.num_workers

        while True:
            if max_events > 0 and total_extracted >= max_events:
                break
            remaining = batch_size if max_events == 0 else min(batch_size, max_events - total_extracted)
            events = get_unextracted_events(self.conn, limit=remaining)
            if not events:
                break

            print(f"\n-- Extracting batch of {len(events)} events (workers={workers}) --")

            def _extract_one(args):
                idx, event = args
                extractor = self._extractors[idx % workers]
                report_id = event["report_number"]
                narrative = event["narrative"]
                # Truncate very long narratives to speed up inference
                if len(narrative) > 1500:
                    narrative = narrative[:1500]
                product_hint = event.get("modality") or event.get("product_code")
                result = extractor.extract(
                    narrative=narrative,
                    report_id=report_id,
                    product_hint=product_hint,
                    reflect=reflect,
                )
                return report_id, result

            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(_extract_one, (i, ev)): ev for i, ev in enumerate(events)}
                for future in as_completed(futures):
                    try:
                        report_id, result = future.result()

                        # Gate 1: confidence check
                        if result.confidence < 0.5:
                            print(f"  [GATE1] {report_id}: Low confidence ({result.confidence:.2f}) — flagged for human review")

                        # Validate handoff
                        validate_handoff("extraction", result.model_dump())

                        # Write back to DB
                        update_extraction_fields(self.conn, report_id, result.model_dump())
                        total_extracted += 1
                        print(f"  [OK] {report_id}: {result.qms_complaint_category.value} | "
                              f"severity={result.severity_indicator.value} | "
                              f"confidence={result.confidence:.2f}")

                    except Exception as e:
                        ev = futures[future]
                        print(f"  [FAIL] {ev['report_number']}: {e}")
                        continue

        print(f"\nExtraction complete. {total_extracted} events processed.")
        return total_extracted

    # --- Step 3: Embedding -----------------------------------------------

    def run_embedding(self, limit: int = 0, batch_size: int = 32):
        """Generate BGE-large embeddings for all narratives."""
        embeddings, report_numbers = self.embedder.build_embeddings(
            self.conn, limit=limit, batch_size=batch_size
        )
        self.embedder.save_embeddings(embeddings, report_numbers)
        return embeddings, report_numbers

    # ─── Step 4: Trend Analysis ──────────────────────────────────────────

    def run_trend_analysis(self, embeddings=None, report_numbers=None):
        """Run HDBSCAN clustering + trend scoring."""
        if embeddings is None or report_numbers is None:
            embeddings, report_numbers = EmbeddingGenerator.load_embeddings()

        labels = self.trend_analyzer.fit_clusters(embeddings, report_numbers)
        self.trend_analyzer.compute_umap()
        self.trend_analyzer.save_clusters_to_db(self.conn)
        return self.trend_analyzer

    # --- Step 5: Process New Complaint ------------------------------------────

    def process_complaint(self, narrative: str, report_id: str = "NEW-001") -> dict:
        """
        Full pipeline for a new incoming complaint:
        1. Extract structured fields
        2. Embed the narrative
        3. Assign to nearest cluster + find similar events

        Returns dict with extraction + similarity results.
        """
        # Ensure trend analyzer is fitted
        if self.trend_analyzer.embeddings is None:
            embeddings, report_numbers = EmbeddingGenerator.load_embeddings()
            self.trend_analyzer.fit_clusters(embeddings, report_numbers)

        # 1. Extract
        print(f"\n-- Processing complaint {report_id} --")
        extraction = self.extractor.extract(narrative=narrative, report_id=report_id)
        print(f"  Extraction: {extraction.qms_complaint_category.value} | "
              f"{extraction.severity_indicator.value} | confidence={extraction.confidence:.2f}")

        # Gate 1
        gate1_passed = extraction.confidence >= 0.5
        if not gate1_passed:
            print(f"  [GATE1] Low confidence — flagged for human review")

        # 2. Embed
        embedding = self.embedder.embed_single(narrative)

        # 3. Assign cluster + find similar
        similarity = self.trend_analyzer.assign_complaint(
            embedding=embedding, conn=self.conn, top_k=10
        )
        print(f"  Cluster: {similarity.cluster_label} (#{similarity.cluster_id}) | "
              f"trend={similarity.trend_flag.value} | growth={similarity.growth_rate_30d:+.1f}%")

        return {
            "extraction": extraction.model_dump(),
            "similarity": similarity.model_dump(),
            "gate1_passed": gate1_passed,
        }

    # --- Full Pipeline Run ------------------------------------------------────

    def run_full_pipeline(self, extract_batch_size: int = 10, embed_limit: int = 0):
        """Run the complete pipeline: extract → embed → cluster."""
        stats = get_db_stats(self.conn)
        print(f"\n{'=' * 70}")
        print("Pipeline Status:")
        print(f"  Events in DB:       {stats['total_events']}")
        print(f"  With narratives:    {stats['events_with_narrative']}")
        print(f"  Already extracted:  {stats['extracted_events']}")
        print(f"  Recalls:            {stats['total_recalls']}")
        print(f"  Clusters:           {stats['total_clusters']}")
        print(f"{'=' * 70}")

        # Step 2: Extract
        if stats["events_with_narrative"] > stats["extracted_events"]:
            print("\n-- Step 2: Extraction --")
            self.run_extraction(batch_size=extract_batch_size)

        # Step 3: Embed
        print("\n-- Step 3: Embedding --")
        embeddings, report_numbers = self.run_embedding(limit=embed_limit)

        # Step 4: Trend
        print("\n-- Step 4: Trend Analysis --")
        self.run_trend_analysis(embeddings, report_numbers)

        # Final stats
        stats = get_db_stats(self.conn)
        print(f"\n{'=' * 70}")
        print("Pipeline Complete:")
        print(f"  Extracted events:   {stats['extracted_events']}")
        print(f"  Clusters found:     {stats['total_clusters']}")
        print(f"{'=' * 70}")

    def close(self):
        self.conn.close()
