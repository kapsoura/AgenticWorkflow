from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List

from src.agents.structured_extraction import StructuredExtractionAgent
from src.pipeline.signal_intelligence_db import (
    get_unextracted_events,
    init_db,
    load_project_events,
    update_extraction_fields,
)
from src.pipeline.signal_intelligence_embeddings import EmbeddingGenerator
from src.pipeline.signal_intelligence_schemas import validate_handoff
from src.pipeline.signal_intelligence_trend import TrendAnalyzer


class SignalIntelligencePipeline:
    """Integrated extraction, embedding, and clustering pipeline for trend analysis."""

    def __init__(
        self,
        model: str = "mistral-small",
        base_url: str = "http://localhost:11434",
        num_workers: int = 2,
    ):
        self.conn = init_db()
        self.num_workers = max(1, num_workers)
        try:
            self.extractor = StructuredExtractionAgent(model=model, base_url=base_url)
            self._extractors = [
                StructuredExtractionAgent(model=model, base_url=base_url) for _ in range(self.num_workers)
            ]
        except Exception:
            self.extractor = None
            self._extractors = []
        self.embedder = EmbeddingGenerator()
        self.trend_analyzer = TrendAnalyzer()

    def ingest_project_events(self, events_by_code: Dict[str, List[dict]]) -> int:
        return load_project_events(self.conn, events_by_code)

    def run_extraction(self, batch_size: int = 20, reflect: bool = False, max_events: int = 0) -> int:
        if self.extractor is None or not self._extractors:
            return 0

        total_extracted = 0
        workers = self.num_workers

        while True:
            if max_events > 0 and total_extracted >= max_events:
                break
            remaining = batch_size if max_events == 0 else min(batch_size, max_events - total_extracted)
            events = get_unextracted_events(self.conn, limit=remaining)
            if not events:
                break

            def _extract_one(args):
                idx, event = args
                extractor = self._extractors[idx % workers]
                report_id = event["report_number"]
                narrative = event["narrative"]
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
                    report_id, result = future.result()
                    validate_handoff("extraction", result.model_dump())
                    update_extraction_fields(self.conn, report_id, result.model_dump())
                    total_extracted += 1

        return total_extracted

    def run_embedding(self, limit: int = 0, batch_size: int = 32):
        embeddings, report_numbers = self.embedder.build_embeddings(self.conn, limit=limit, batch_size=batch_size)
        self.embedder.save_embeddings(embeddings, report_numbers)
        return embeddings, report_numbers

    def run_trend_analysis(self, embeddings=None, report_numbers=None):
        if embeddings is None or report_numbers is None:
            embeddings, report_numbers = EmbeddingGenerator.load_embeddings()

        self.trend_analyzer.fit_clusters(embeddings, report_numbers)
        self.trend_analyzer.compute_umap()
        self.trend_analyzer.save_clusters_to_db(self.conn)
        return self.trend_analyzer

    def process_similarity(self, narrative: str) -> dict:
        if self.trend_analyzer.embeddings is None:
            embeddings, report_numbers = EmbeddingGenerator.load_embeddings()
            self.trend_analyzer.fit_clusters(embeddings, report_numbers)

        embedding = self.embedder.embed_single(narrative)
        similarity = self.trend_analyzer.assign_complaint(embedding=embedding, conn=self.conn, top_k=10)
        return similarity.model_dump()

    def close(self):
        self.conn.close()
