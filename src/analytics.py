"""Deterministic analytics for the dashboard.

No LLM and no free-form SQL. Every aggregation here is either a fixed,
parameterized query against the SQLite report store or an in-memory tally over
the real loaded FDA archive. Dimensions, grains and filters are allow-listed --
an unknown value raises ``ValueError`` (surfaced by the API as HTTP 400) instead
of being interpolated into a query.

Empty data sources return empty series. Nothing on this path fabricates,
estimates or back-fills values, so the dashboard only ever shows numbers that are
actually present in the archive or in the generated-report table.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

from src.agents.archive_trend import ArchiveTrendAnalyzer
from src.config import PRODUCT_CODES

# Single source of truth for the "software-like" problem heuristic.
_SOFTWARE_HINTS = ArchiveTrendAnalyzer.SOFTWARE_HINTS

# Dimensions whose counts come from the in-memory FDA adverse-event archive.
_EVENT_DIMENSIONS = {
    "product_code",
    "event_type",
    "manufacturer",
    "product_problem",
    "year",
    "month",
    "quarter",
}
# Dimensions whose counts come from the generated-report SQLite table.
_REPORT_DIMENSIONS = {
    "risk_bucket",
    "report_type",
    "report_year",
    "report_month",
}
_TIME_DIMENSIONS = {"year", "month", "quarter", "report_year", "report_month"}

ALLOWED_DIMENSIONS = _EVENT_DIMENSIONS | _REPORT_DIMENSIONS
_VALID_PRODUCT_CODES = set(PRODUCT_CODES)

# How many bars to keep for high-cardinality categorical dimensions.
_DEFAULT_TOP_N = 12


# --------------------------------------------------------------------------- #
# Event field accessors -- tolerant of the real openFDA record shape.
# --------------------------------------------------------------------------- #
def _event_manufacturer(event: dict) -> str:
    device = event.get("device") or [{}]
    name = (device[0].get("manufacturer_d_name") or "").strip()
    return name or "Unknown"


def _event_date(event: dict) -> str:
    return str(event.get("date_received", "") or "")


def _event_period(event: dict, grain: str) -> Optional[str]:
    """Return a sortable period label (YYYY / YYYY-MM / YYYY-Qn) or None."""
    raw = _event_date(event)
    if len(raw) < 4 or not raw[:4].isdigit():
        return None
    year = raw[:4]
    if grain == "year":
        return year
    if len(raw) < 6 or not raw[4:6].isdigit():
        return None
    month = raw[4:6]
    if grain == "month":
        return f"{year}-{month}"
    if grain == "quarter":
        quarter = (int(month) - 1) // 3 + 1
        return f"{year}-Q{quarter}"
    return None


def _is_software_event(event: dict) -> bool:
    problems = " ".join(str(p) for p in (event.get("product_problems") or [])).lower()
    return any(hint in problems for hint in _SOFTWARE_HINTS)


# --------------------------------------------------------------------------- #
# Filter validation / application
# --------------------------------------------------------------------------- #
def _clean_filters(filters: Optional[dict]) -> dict:
    filters = filters or {}
    product_code = filters.get("product_code")
    if product_code:
        if product_code not in _VALID_PRODUCT_CODES:
            raise ValueError(
                f"Unknown product_code '{product_code}'. "
                f"Allowed: {sorted(_VALID_PRODUCT_CODES)}"
            )
    else:
        product_code = None

    event_type = filters.get("event_type") or None

    software = filters.get("software_related")
    if software is not None and not isinstance(software, bool):
        raise ValueError("software_related must be a boolean.")

    return {
        "product_code": product_code,
        "event_type": event_type,
        "software_related": software,
    }


def _flatten_events(events_by_code: Dict[str, List[dict]], filters: dict):
    """Yield (product_code, event) pairs after applying the event filters."""
    code_filter = filters["product_code"]
    type_filter = filters["event_type"]
    software_filter = filters["software_related"]
    for code, events in events_by_code.items():
        if code_filter and code != code_filter:
            continue
        for event in events:
            if type_filter and (event.get("event_type") or "Unknown") != type_filter:
                continue
            if software_filter is not None and _is_software_event(event) != software_filter:
                continue
            yield code, event


# --------------------------------------------------------------------------- #
# Report store (SQLite) -- fixed, parameterized queries only.
# --------------------------------------------------------------------------- #
# Map each report dimension to the exact column / expression it aggregates.
# Values are constants defined in this module, never user input.
_REPORT_SELECT = {
    "risk_bucket": "risk_bucket",
    "report_type": "report_type",
    "report_year": "substr(created_at, 1, 4)",
    "report_month": "substr(created_at, 1, 7)",
}


def _report_breakdown(db_path: Path, dimension: str) -> List[dict]:
    select_expr = _REPORT_SELECT[dimension]
    query = (
        f"SELECT {select_expr} AS label, COUNT(*) AS count "
        "FROM signal_reports "
        f"WHERE {select_expr} IS NOT NULL AND {select_expr} != '' "
        "GROUP BY label"
    )
    try:
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(query).fetchall()
        finally:
            conn.close()
    except sqlite3.OperationalError:
        # Table not created yet (no report ever persisted) -> no data.
        return []
    return [{"label": str(label), "count": int(count)} for label, count in rows]


def _report_stats(db_path: Path) -> dict:
    try:
        conn = sqlite3.connect(db_path)
        try:
            total = conn.execute("SELECT COUNT(*) FROM signal_reports").fetchone()[0]
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return {"reports_generated": 0, "risk_bucket_breakdown": [], "report_type_breakdown": []}
    return {
        "reports_generated": int(total),
        "risk_bucket_breakdown": _sorted_desc(_report_breakdown(db_path, "risk_bucket")),
        "report_type_breakdown": _sorted_desc(_report_breakdown(db_path, "report_type")),
    }


# --------------------------------------------------------------------------- #
# Ordering helpers
# --------------------------------------------------------------------------- #
def _sorted_desc(series: List[dict]) -> List[dict]:
    return sorted(series, key=lambda item: (-item["count"], item["label"]))


def _sorted_chrono(series: List[dict]) -> List[dict]:
    return sorted(series, key=lambda item: item["label"])


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def compute_stats(
    events_by_code: Dict[str, List[dict]],
    recalls: List[dict],
    db_path: Path,
) -> dict:
    """Headline counts for the dashboard, computed only from real loaded data."""
    all_events = [event for events in events_by_code.values() for event in events]
    total = len(all_events)

    events_by_code_series = _sorted_desc(
        [{"label": code, "count": len(events)} for code, events in events_by_code.items()]
    )

    manufacturers = (
        len({_event_manufacturer(event) for event in all_events}) if all_events else 0
    )
    software = sum(1 for event in all_events if _is_software_event(event))

    years = sorted({p for event in all_events if (p := _event_period(event, "year"))})
    date_range = {
        "min": years[0] if years else None,
        "max": years[-1] if years else None,
    }

    event_types = Counter(
        (event.get("event_type") or "Unknown") for event in all_events
    )

    report_stats = _report_stats(db_path)

    return {
        "total_events": total,
        "events_by_code": events_by_code_series,
        "distinct_manufacturers": manufacturers,
        "software_related_events": software,
        "software_related_pct": round(100 * software / total, 1) if total else 0.0,
        "event_type_breakdown": _sorted_desc(
            [{"label": label, "count": count} for label, count in event_types.items()]
        ),
        "recalls": len(recalls),
        "date_range": date_range,
        **report_stats,
    }


def compute_trends(
    events_by_code: Dict[str, List[dict]],
    db_path: Path,
    dimension: str,
    filters: Optional[dict] = None,
    top_n: int = _DEFAULT_TOP_N,
) -> dict:
    """Aggregate one allow-listed dimension into a chart-ready series.

    Time dimensions are returned in chronological order; categorical dimensions
    are returned most-frequent-first and truncated to ``top_n``.
    """
    if dimension not in ALLOWED_DIMENSIONS:
        raise ValueError(
            f"Unknown dimension '{dimension}'. Allowed: {sorted(ALLOWED_DIMENSIONS)}"
        )

    if dimension in _REPORT_DIMENSIONS:
        # Report dimensions ignore event filters (different data source).
        series = _report_breakdown(db_path, dimension)
        source = "reports"
    else:
        clean = _clean_filters(filters)
        series = _event_trends(events_by_code, dimension, clean)
        source = "events"

    if dimension in _TIME_DIMENSIONS:
        series = _sorted_chrono(series)
    else:
        series = _sorted_desc(series)[:top_n]

    return {
        "dimension": dimension,
        "metric": "count",
        "source": source,
        "filters": _clean_filters(filters) if source == "events" else {},
        "total": sum(item["count"] for item in series),
        "series": series,
    }


def _event_trends(
    events_by_code: Dict[str, List[dict]],
    dimension: str,
    filters: dict,
) -> List[dict]:
    counter: Counter = Counter()
    for code, event in _flatten_events(events_by_code, filters):
        if dimension == "product_problem":
            for problem in event.get("product_problems") or []:
                label = str(problem).strip()
                if label:
                    counter[label] += 1
            continue

        if dimension == "product_code":
            key: Optional[str] = code
        elif dimension == "event_type":
            key = event.get("event_type") or "Unknown"
        elif dimension == "manufacturer":
            key = _event_manufacturer(event)
        elif dimension in ("year", "month", "quarter"):
            key = _event_period(event, dimension)
        else:  # pragma: no cover - guarded by ALLOWED_DIMENSIONS
            key = None

        if key:
            counter[key] += 1

    return [{"label": label, "count": count} for label, count in counter.items()]
