"""Unit tests for the deterministic dashboard analytics (Option A).

Pure-function tests over synthetic in-memory archives and a temporary SQLite
report store. No LLM backend or downloaded data archive is required.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src import analytics


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def _event(code_problems, event_type, manufacturer, date_received):
    return {
        "event_type": event_type,
        "date_received": date_received,
        "product_problems": code_problems,
        "device": [{"manufacturer_d_name": manufacturer}],
    }


def _events_by_code():
    return {
        "LNH": [
            _event(["Image artifact"], "Malfunction", "Philips", "20190115"),
            _event(["Overheating"], "Injury", "Philips", "20200620"),
            _event(["Software problem"], "Death", "GE", "20200815"),
        ],
        "JAK": [
            _event(["Display error"], "Malfunction", "Siemens", "20210101"),
            _event([], "Malfunction", "Siemens", "bad-date"),
        ],
    }


def _seed_reports(db_path: Path):
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE signal_reports (
            report_id TEXT PRIMARY KEY,
            trace_id TEXT,
            complaint_id TEXT NOT NULL,
            report_type TEXT NOT NULL,
            risk_bucket TEXT NOT NULL,
            review_needed INTEGER,
            review_reasons_json TEXT,
            created_at TEXT NOT NULL,
            report_markdown TEXT NOT NULL,
            retrieval_json TEXT NOT NULL
        )
        """
    )
    rows = [
        ("R1", "T1", "C1", "PSUR", "ACCEPTABLE", "2026-06-01T10:00:00Z"),
        ("R2", "T2", "C2", "CAPA", "ALARP", "2026-06-02T10:00:00Z"),
        ("R3", "T3", "C3", "PSUR", "UNACCEPTABLE", "2026-07-03T10:00:00Z"),
    ]
    conn.executemany(
        "INSERT INTO signal_reports "
        "(report_id, trace_id, complaint_id, report_type, risk_bucket, created_at, "
        " report_markdown, retrieval_json) "
        "VALUES (?, ?, ?, ?, ?, ?, '', '[]')",
        rows,
    )
    conn.commit()
    conn.close()


# --------------------------------------------------------------------------- #
# compute_stats
# --------------------------------------------------------------------------- #
def test_stats_counts_only_real_data(tmp_path):
    db = tmp_path / "reports.db"
    _seed_reports(db)
    stats = analytics.compute_stats(_events_by_code(), [{"x": 1}, {"x": 2}], db)

    assert stats["total_events"] == 5
    assert stats["recalls"] == 2
    assert stats["distinct_manufacturers"] == 3  # Philips, GE, Siemens
    assert stats["software_related_events"] == 2  # "Image artifact", "Software problem"
    assert stats["software_related_pct"] == 40.0
    assert stats["date_range"] == {"min": "2019", "max": "2021"}
    assert stats["reports_generated"] == 3
    assert {b["label"]: b["count"] for b in stats["events_by_code"]} == {"LNH": 3, "JAK": 2}


def test_stats_empty_archive_has_no_fabricated_values(tmp_path):
    stats = analytics.compute_stats({}, [], tmp_path / "missing.db")
    assert stats["total_events"] == 0
    assert stats["distinct_manufacturers"] == 0
    assert stats["software_related_pct"] == 0.0
    assert stats["date_range"] == {"min": None, "max": None}
    assert stats["reports_generated"] == 0
    assert stats["risk_bucket_breakdown"] == []


# --------------------------------------------------------------------------- #
# compute_trends -- event dimensions
# --------------------------------------------------------------------------- #
def test_trends_event_type_is_sorted_desc(tmp_path):
    res = analytics.compute_trends(_events_by_code(), tmp_path / "db", "event_type")
    assert res["source"] == "events"
    assert res["series"][0] == {"label": "Malfunction", "count": 3}
    assert res["total"] == 5


def test_trends_year_is_chronological_and_skips_bad_dates(tmp_path):
    res = analytics.compute_trends(_events_by_code(), tmp_path / "db", "year")
    labels = [item["label"] for item in res["series"]]
    assert labels == ["2019", "2020", "2021"]  # "bad-date" dropped
    assert res["total"] == 4


def test_trends_product_filter_scopes_results(tmp_path):
    res = analytics.compute_trends(
        _events_by_code(), tmp_path / "db", "event_type", {"product_code": "LNH"}
    )
    assert {item["label"]: item["count"] for item in res["series"]} == {
        "Malfunction": 1,
        "Injury": 1,
        "Death": 1,
    }


def test_trends_software_filter(tmp_path):
    res = analytics.compute_trends(
        _events_by_code(), tmp_path / "db", "product_code", {"software_related": True}
    )
    assert {item["label"]: item["count"] for item in res["series"]} == {"LNH": 2}


def test_trends_product_problem_counts_each_label(tmp_path):
    res = analytics.compute_trends(_events_by_code(), tmp_path / "db", "product_problem")
    labels = {item["label"] for item in res["series"]}
    assert "Image artifact" in labels
    assert "Software problem" in labels


# --------------------------------------------------------------------------- #
# compute_trends -- report dimensions
# --------------------------------------------------------------------------- #
def test_trends_risk_bucket_from_reports(tmp_path):
    db = tmp_path / "reports.db"
    _seed_reports(db)
    res = analytics.compute_trends({}, db, "risk_bucket")
    assert res["source"] == "reports"
    assert {item["label"]: item["count"] for item in res["series"]} == {
        "ACCEPTABLE": 1,
        "ALARP": 1,
        "UNACCEPTABLE": 1,
    }


def test_trends_report_month_chronological(tmp_path):
    db = tmp_path / "reports.db"
    _seed_reports(db)
    res = analytics.compute_trends({}, db, "report_month")
    labels = [item["label"] for item in res["series"]]
    assert labels == ["2026-06", "2026-07"]


def test_trends_reports_dimension_with_no_table_is_empty(tmp_path):
    res = analytics.compute_trends({}, tmp_path / "missing.db", "risk_bucket")
    assert res["series"] == []
    assert res["total"] == 0


# --------------------------------------------------------------------------- #
# Validation / allow-listing
# --------------------------------------------------------------------------- #
def test_unknown_dimension_raises(tmp_path):
    with pytest.raises(ValueError):
        analytics.compute_trends(_events_by_code(), tmp_path / "db", "drop_table")


def test_unknown_product_code_filter_raises(tmp_path):
    with pytest.raises(ValueError):
        analytics.compute_trends(
            _events_by_code(), tmp_path / "db", "event_type", {"product_code": "ZZZ"}
        )
