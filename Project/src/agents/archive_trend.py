from collections import Counter
from datetime import datetime
import os
from threading import Lock
from typing import Dict, List

from src.pipeline.schemas import TrendSummary
from src.pipeline.signal_intelligence_pipeline import SignalIntelligencePipeline


_PIPELINE_LOCK = Lock()
_SHARED_PIPELINE = None


def _get_shared_pipeline() -> SignalIntelligencePipeline:
    global _SHARED_PIPELINE
    with _PIPELINE_LOCK:
        if _SHARED_PIPELINE is None:
            _SHARED_PIPELINE = SignalIntelligencePipeline(
                model=os.getenv("EXTRACTION_MODEL", "mistral-small"),
                base_url=os.getenv("EXTRACTION_BASE_URL", "http://localhost:11434"),
            )
        return _SHARED_PIPELINE


class ArchiveTrendAnalyzer:
    """Trend analyzer with integrated backend only.

    If integrated trend analysis is unavailable, return an explicit
    not-available summary instead of heuristic trend classification.
    """

    SOFTWARE_HINTS = ("software", "application", "algorithm", "image", "dicom")

    def __init__(self):
        self.backend = os.getenv("TREND_BACKEND", "integrated").strip().lower()
        self.last_backend = "integrated"
        self.last_fallback_reason = None
        self._hdbscan = None
        self._np = None
        self._vectorizer = None
        self._pipeline = None

        try:
            self._pipeline = _get_shared_pipeline()
            self.backend = "integrated"
        except Exception as exc:
            self.last_fallback_reason = f"Integrated trend backend unavailable: {exc}"
            self.backend = "integrated_unavailable"

    def summarize(self, product_code: str, events: List[dict]) -> TrendSummary:
        if self.backend == "integrated" and self._pipeline is not None and len(events) >= 1:
            try:
                result = self._summarize_integrated(product_code, events)
                self.last_backend = "integrated"
                self.last_fallback_reason = None
                return result
            except Exception as exc:
                self.last_backend = "integrated_unavailable"
                self.last_fallback_reason = f"Integrated trend unavailable: {exc}"
                return self._not_available_summary(product_code)

        self.last_backend = "integrated_unavailable"
        if not self.last_fallback_reason:
            self.last_fallback_reason = "Integrated trend backend not configured"
        return self._not_available_summary(product_code)

    @staticmethod
    def _not_available_summary(product_code: str) -> TrendSummary:
        return TrendSummary(
            product_code=product_code,
            total_events=0,
            software_problem_events=0,
            latest_year_events=0,
            previous_year_events=0,
            trend_direction="not_available",
        )

    def _summarize_internal(self, product_code: str, events: List[dict]) -> TrendSummary:
        year_counter = Counter()
        software_problem_events = 0

        for event in events:
            date_received = event.get("date_received", "")
            if len(date_received) >= 4 and date_received[:4].isdigit():
                year_counter[date_received[:4]] += 1

            problems = " ".join(event.get("product_problems") or []).lower()
            if any(term in problems for term in self.SOFTWARE_HINTS):
                software_problem_events += 1

        if year_counter:
            years = sorted(year_counter.keys())
            latest_year = years[-1]
            previous_year = years[-2] if len(years) > 1 else years[-1]
            latest_count = year_counter[latest_year]
            previous_count = year_counter[previous_year]
        else:
            latest_count = 0
            previous_count = 0

        if latest_count > previous_count:
            direction = "upward"
        elif latest_count < previous_count:
            direction = "downward"
        else:
            direction = "flat"

        return TrendSummary(
            product_code=product_code,
            total_events=len(events),
            software_problem_events=software_problem_events,
            latest_year_events=latest_count,
            previous_year_events=previous_count,
            trend_direction=direction,
        )

    def _summarize_integrated(self, product_code: str, events: List[dict]) -> TrendSummary:
        with _PIPELINE_LOCK:
            self._pipeline.ingest_project_events({product_code: events})
            try:
                self._pipeline.run_extraction(batch_size=50, reflect=False, max_events=200)
            except Exception:
                pass
            embeddings, report_numbers = self._pipeline.run_embedding(limit=0, batch_size=64)
            self._pipeline.run_trend_analysis(embeddings, report_numbers)

        year_counter = Counter()
        software_problem_events = 0

        docs: List[str] = []
        for event in events:
            date_received = str(event.get("date_received", ""))
            if len(date_received) >= 4 and date_received[:4].isdigit():
                year_counter[date_received[:4]] += 1

            problems = " ".join(event.get("product_problems") or [])
            narrative = str(event.get("narrative") or "")
            combined = f"{problems} {narrative}".strip()
            docs.append(combined if combined else "unknown event")

            if any(term in problems.lower() for term in self.SOFTWARE_HINTS):
                software_problem_events += 1

        query_narrative = " ".join(docs)[:4000] if docs else ""
        with _PIPELINE_LOCK:
            similarity = self._pipeline.process_similarity(query_narrative)
        cluster_size = int(similarity.get("cluster_size", 0))
        growth_rate = float(similarity.get("growth_rate_30d", 0.0))

        if year_counter:
            years = sorted(year_counter.keys())
            latest_year = years[-1]
            previous_year = years[-2] if len(years) > 1 else years[-1]
            latest_count = year_counter[latest_year]
            previous_count = year_counter[previous_year]
        else:
            latest_count = 0
            previous_count = 0

        # Integrated semantics: combine temporal growth and cluster signal.
        if (latest_count > previous_count and cluster_size >= max(3, len(events) // 10)) or growth_rate > 20:
            direction = "upward"
        elif latest_count < previous_count or growth_rate < -20:
            direction = "downward"
        else:
            direction = "flat"

        return TrendSummary(
            product_code=product_code,
            total_events=len(events),
            software_problem_events=software_problem_events,
            latest_year_events=latest_count,
            previous_year_events=previous_count,
            trend_direction=direction,
        )

    def yearly_breakdown(self, events: List[dict]) -> List[Dict[str, int]]:
        """Return events-per-year, sorted ascending, for trend plotting."""
        year_counter: Counter = Counter()
        for event in events:
            date_received = event.get("date_received", "")
            if len(date_received) >= 4 and date_received[:4].isdigit():
                year_counter[date_received[:4]] += 1
        return [{"year": year, "count": year_counter[year]} for year in sorted(year_counter)]

    def problem_breakdown(self, events: List[dict], top_n: int = 8) -> List[Dict[str, int]]:
        """Return the most frequent reported product problems for plotting."""
        problem_counter: Counter = Counter()
        for event in events:
            for problem in event.get("product_problems") or []:
                label = str(problem).strip()
                if label:
                    problem_counter[label] += 1
        return [
            {"problem": label, "count": count}
            for label, count in problem_counter.most_common(top_n)
        ]
