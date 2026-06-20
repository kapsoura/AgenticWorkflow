"""Quality analytics toolbox.

A set of discrete, callable tools that agents (via the orchestrator) use to answer
the four quality-intelligence themes the program cares about:

  - PATTERN RECOGNITION   -> recurrence_scan, cross_dimension_trend
  - ROOT CAUSE EFFECTIVE. -> recurrence_rate_12m, systemic_vs_immediate
  - RESOURCE ALLOCATION   -> analysis_readiness
  - PREDICTIVE CAPABILITY -> factor_cooccurrence, leading_indicators

Each tool reads the working event archive (the same MAUDE records the retrieval
agent uses) and returns a ``ToolResult`` carrying a human-readable headline, the
supporting metrics, and the specific program questions it answers. The results are
deterministic and run fully offline.

Honesty note: FDA MAUDE/recall data does not contain internal CAPA timestamps,
shift logs, or engineer effort. Tools that touch those questions (resource
allocation) return measurable *proxies* and label the limitation explicitly.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

SERIOUS_EVENT_TYPES = {"injury", "death"}


@dataclass
class ToolResult:
    tool: str
    theme: str
    headline: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    answers: List[str] = field(default_factory=list)


def _year(event: dict) -> Optional[str]:
    date_received = str(event.get("date_received", ""))
    if len(date_received) >= 4 and date_received[:4].isdigit():
        return date_received[:4]
    return None


def _parse_date(event: dict) -> Optional[datetime]:
    date_received = str(event.get("date_received", ""))
    if len(date_received) >= 8 and date_received[:8].isdigit():
        try:
            return datetime.strptime(date_received[:8], "%Y%m%d")
        except ValueError:
            return None
    return None


def _problem_terms(event: dict) -> List[str]:
    return [p.strip().lower() for p in (event.get("product_problems") or []) if p and p.strip()]


def _matches_issue(terms: List[str], key_issues: List[str]) -> bool:
    if not key_issues:
        return True
    joined = " ".join(terms)
    return any(issue.lower() in joined for issue in key_issues if issue)


class QualityAnalyticsToolbox:
    """Demand-driven analytics over the working event archive."""

    # --- PATTERN RECOGNITION ------------------------------------------------
    def recurrence_scan(self, events: List[dict], key_issues: List[str]) -> ToolResult:
        """Related deviations that surface *after* an initial event window."""
        dated = sorted(
            (
                (d, _problem_terms(e))
                for e in events
                if (d := _parse_date(e)) is not None and _matches_issue(_problem_terms(e), key_issues)
            ),
            key=lambda x: x[0],
        )
        late_recurrences = 0
        first_seen: Dict[str, datetime] = {}
        for when, terms in dated:
            for term in terms:
                if term not in first_seen:
                    first_seen[term] = when
                elif (when - first_seen[term]).days > 365:
                    late_recurrences += 1

        total = len(dated)
        headline = (
            f"{late_recurrences} related deviation(s) recurred more than 12 months after a first "
            f"matching event across {total} archive records "
            "(signals deviations that would surface after an individual CAPA is closed)."
        )
        return ToolResult(
            tool="recurrence_scan",
            theme="pattern_recognition",
            headline=headline,
            metrics={"matching_events": total, "late_recurrences": late_recurrences},
            answers=["How often do related deviations appear weeks/months after closing individual CAPAs?"],
        )

    def cross_dimension_trend(self, events: List[dict]) -> ToolResult:
        """Trends across time periods and event types (department/shift proxies)."""
        by_year = Counter(y for e in events if (y := _year(e)))
        by_type = Counter((e.get("event_type") or "Unknown") for e in events)
        peak_year = by_year.most_common(1)[0] if by_year else ("n/a", 0)
        headline = (
            f"Peak activity in {peak_year[0]} ({peak_year[1]} events); "
            f"event-type mix: {dict(by_type)} "
            "(supports cross-period and cross-category trend identification)."
        )
        return ToolResult(
            tool="cross_dimension_trend",
            theme="pattern_recognition",
            headline=headline,
            metrics={"by_year": dict(by_year), "by_event_type": dict(by_type)},
            answers=["Can the quality team identify trends across departments, shifts, and time periods?"],
        )

    # --- ROOT CAUSE EFFECTIVENESS ------------------------------------------
    def recurrence_rate_12m(self, events: List[dict], key_issues: List[str]) -> ToolResult:
        """Share of matching deviations that recur within 12 months."""
        dated = sorted(
            (d for e in events if (d := _parse_date(e)) is not None and _matches_issue(_problem_terms(e), key_issues))
        )
        if len(dated) < 2:
            rate = 0.0
            recurring = 0
        else:
            first = dated[0]
            recurring = sum(1 for d in dated[1:] if (d - first).days <= 365)
            rate = round(recurring / len(dated), 3)
        headline = (
            f"{int(rate * 100)}% of matching deviations recurred within 12 months "
            f"({recurring}/{len(dated)}) — a high rate suggests prior CAPAs addressed symptoms, not systemic causes."
        )
        return ToolResult(
            tool="recurrence_rate_12m",
            theme="root_cause_effectiveness",
            headline=headline,
            metrics={"matching_events": len(dated), "recurring_within_12m": recurring, "recurrence_rate": rate},
            answers=["How many closed CAPAs have recurring similar deviations within 12 months?"],
        )

    def systemic_vs_immediate(self, events: List[dict], key_issues: List[str]) -> ToolResult:
        """Classify problem signatures as systemic vs one-off/immediate."""
        term_years: Dict[str, set] = defaultdict(set)
        term_counts: Counter = Counter()
        for e in events:
            terms = _problem_terms(e)
            if not _matches_issue(terms, key_issues):
                continue
            year = _year(e)
            for term in terms:
                term_counts[term] += 1
                if year:
                    term_years[term].add(year)

        systemic = [t for t, c in term_counts.items() if c >= 3 or len(term_years[t]) >= 2]
        total_signatures = len(term_counts)
        pct = round(len(systemic) / total_signatures, 3) if total_signatures else 0.0
        headline = (
            f"{int(pct * 100)}% of distinct problem signatures look systemic "
            f"({len(systemic)}/{total_signatures}: recurring across ≥3 events or ≥2 years); "
            "the remainder appear as immediate/one-off event causes."
        )
        return ToolResult(
            tool="systemic_vs_immediate",
            theme="root_cause_effectiveness",
            headline=headline,
            metrics={
                "systemic_signatures": systemic[:10],
                "systemic_share": pct,
                "distinct_signatures": total_signatures,
            },
            answers=["What percentage of CAPAs address true systemic issues vs. immediate event causes?"],
        )

    # --- RESOURCE ALLOCATION (proxy) ---------------------------------------
    def analysis_readiness(self, events: List[dict], retrieved_count: int) -> ToolResult:
        """Proxy for time spent hunting vs analysing: how much evidence is pre-indexed."""
        archive = len(events)
        coverage = round(retrieved_count / archive, 3) if archive else 0.0
        headline = (
            f"{retrieved_count} relevant precedent(s) were auto-surfaced from {archive} archived records "
            f"(coverage {int(coverage * 100)}%), removing manual search effort. "
            "Note: internal RCA-cycle time and reactive/proactive split require QMS/CAPA integration (not in FDA data)."
        )
        return ToolResult(
            tool="analysis_readiness",
            theme="resource_allocation",
            headline=headline,
            metrics={"archive_size": archive, "auto_surfaced": retrieved_count, "coverage": coverage},
            answers=[
                "How much time do quality engineers spend hunting for data vs. analyzing it?",
                "What is the average time from deviation to completed root cause analysis? (requires QMS integration)",
            ],
        )

    # --- PREDICTIVE CAPABILITY ---------------------------------------------
    def factor_cooccurrence(self, events: List[dict]) -> ToolResult:
        """Factor combinations historically associated with serious outcomes."""
        combos: Counter = Counter()
        for e in events:
            if (e.get("event_type") or "").lower() not in SERIOUS_EVENT_TYPES:
                continue
            etype = (e.get("event_type") or "Unknown")
            for term in _problem_terms(e):
                combos[(etype, term)] += 1
        top = combos.most_common(5)
        if top:
            (lead_type, lead_term), lead_n = top[0]
            headline = (
                f"Strongest serious-outcome factor combination: '{lead_term}' + {lead_type} "
                f"({lead_n} occurrences) — a candidate leading indicator for non-conformance."
            )
        else:
            headline = "No serious-outcome (injury/death) factor combinations found in the current archive slice."
        return ToolResult(
            tool="factor_cooccurrence",
            theme="predictive_capability",
            headline=headline,
            metrics={"top_combinations": [{"factors": list(k), "count": n} for k, n in top]},
            answers=["Which combinations of factors historically lead to non-conformances?"],
        )

    def leading_indicators(self, events: List[dict], key_issues: List[str]) -> ToolResult:
        """Problem categories rising in the latest year vs the prior year (early warning)."""
        by_year_term: Dict[str, Counter] = defaultdict(Counter)
        for e in events:
            year = _year(e)
            if not year:
                continue
            for term in _problem_terms(e):
                by_year_term[year][term] += 1
        years = sorted(by_year_term.keys())
        rising: List[str] = []
        if len(years) >= 2:
            latest, prev = years[-1], years[-2]
            for term, count in by_year_term[latest].items():
                if count > by_year_term[prev].get(term, 0):
                    rising.append(term)
        rising = rising[:10]
        headline = (
            f"{len(rising)} problem categor(y/ies) are rising year-over-year "
            f"({', '.join(rising) if rising else 'none'}) — early-warning candidates to act on before deviations occur."
        )
        return ToolResult(
            tool="leading_indicators",
            theme="predictive_capability",
            headline=headline,
            metrics={"rising_categories": rising},
            answers=["Do we identify quality risks before they become deviations, or only investigate after events?"],
        )

    # --- Orchestration helper ----------------------------------------------
    def run_for_themes(
        self,
        events: List[dict],
        key_issues: List[str],
        retrieved_count: int,
        themes: Optional[List[str]] = None,
    ) -> List[ToolResult]:
        """Run the tools relevant to the requested themes (all themes by default)."""
        catalog = {
            "pattern_recognition": [
                lambda: self.recurrence_scan(events, key_issues),
                lambda: self.cross_dimension_trend(events),
            ],
            "root_cause_effectiveness": [
                lambda: self.recurrence_rate_12m(events, key_issues),
                lambda: self.systemic_vs_immediate(events, key_issues),
            ],
            "resource_allocation": [
                lambda: self.analysis_readiness(events, retrieved_count),
            ],
            "predictive_capability": [
                lambda: self.factor_cooccurrence(events),
                lambda: self.leading_indicators(events, key_issues),
            ],
        }
        selected = themes or list(catalog.keys())
        results: List[ToolResult] = []
        for theme in selected:
            for run in catalog.get(theme, []):
                results.append(run())
        return results
