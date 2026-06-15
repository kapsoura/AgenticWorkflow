from collections import Counter
from datetime import datetime
from typing import Dict, List

from src.pipeline.schemas import TrendSummary


class ArchiveTrendAnalyzer:
    """Simple archive trend analyzer for baseline signal direction."""

    SOFTWARE_HINTS = ("software", "application", "algorithm", "image", "dicom")

    def summarize(self, product_code: str, events: List[dict]) -> TrendSummary:
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
