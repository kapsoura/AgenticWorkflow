from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

from src.config import RUNTIME_DIR

DB_PATH = RUNTIME_DIR / "signal_intelligence_ml.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    report_number TEXT UNIQUE NOT NULL,
    date_received DATE,
    event_type TEXT,
    product_code TEXT NOT NULL,
    device_name TEXT,
    manufacturer TEXT,
    brand_name TEXT,
    narrative TEXT,
    narrative_length INTEGER,
    domain TEXT,
    modality TEXT,
    software_related BOOLEAN,
    is_safety_related BOOLEAN,
    usability_concern BOOLEAN,
    security_concern BOOLEAN,
    affected_countries TEXT,
    complaint_source TEXT,
    qms_complaint_category TEXT,
    severity_indicator TEXT,
    extraction_confidence REAL,
    extraction_json TEXT,
    cluster_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS event_problems (
    event_id INTEGER REFERENCES events(id),
    problem_code TEXT NOT NULL,
    PRIMARY KEY (event_id, problem_code)
);

CREATE TABLE IF NOT EXISTS clusters (
    id INTEGER PRIMARY KEY,
    label TEXT,
    size INTEGER,
    first_seen DATE,
    last_event_date DATE,
    growth_rate_30d REAL,
    dominant_problem TEXT,
    dominant_modality TEXT,
    trend_flag TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_product_code ON events(product_code);
CREATE INDEX IF NOT EXISTS idx_events_cluster ON events(cluster_id);
"""


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: the shared SignalIntelligencePipeline connection is
    # created in one thread but used by LangGraph nodes running on worker threads.
    # All access is serialized through _PIPELINE_LOCK, so cross-thread use is safe.
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    conn = get_connection(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


def insert_event(conn: sqlite3.Connection, row: dict) -> Optional[int]:
    try:
        cur = conn.execute(
            """INSERT OR REPLACE INTO events
               (report_number, date_received, event_type, product_code,
                device_name, manufacturer, brand_name, narrative,
                narrative_length, domain, modality, software_related)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                row.get("report_number", ""),
                row.get("date_received", ""),
                row.get("event_type", "Unknown"),
                row.get("product_code", ""),
                row.get("device_name", ""),
                row.get("manufacturer", ""),
                row.get("brand_name", ""),
                row.get("narrative", ""),
                int(row.get("narrative_length", len(row.get("narrative", "")))),
                row.get("domain", "unknown"),
                row.get("modality", "Unknown"),
                bool(row.get("software_related", False)),
            ),
        )
        event_id = cur.lastrowid
        for prob in row.get("problems", []):
            conn.execute(
                "INSERT OR IGNORE INTO event_problems (event_id, problem_code) VALUES (?,?)",
                (event_id, str(prob)),
            )
        return event_id
    except sqlite3.Error:
        return None


def update_extraction_fields(conn: sqlite3.Connection, report_number: str, extraction: dict) -> None:
    conn.execute(
        """UPDATE events SET
            is_safety_related = ?,
            usability_concern = ?,
            security_concern = ?,
            affected_countries = ?,
            complaint_source = ?,
            qms_complaint_category = ?,
            severity_indicator = ?,
            extraction_confidence = ?,
            extraction_json = ?
           WHERE report_number = ?""",
        (
            extraction.get("is_safety_related"),
            extraction.get("usability_concern"),
            extraction.get("security_concern"),
            json.dumps(extraction.get("affected_countries", ["unknown"])),
            extraction.get("complaint_source", "unknown"),
            extraction.get("qms_complaint_category"),
            extraction.get("severity_indicator"),
            extraction.get("confidence"),
            json.dumps(extraction),
            report_number,
        ),
    )
    conn.commit()


def get_narratives(conn: sqlite3.Connection, limit: int = 0) -> list[dict]:
    sql = (
        "SELECT id, report_number, narrative, product_code, modality, manufacturer "
        "FROM events WHERE narrative IS NOT NULL AND narrative != ''"
    )
    if limit > 0:
        sql += f" LIMIT {int(limit)}"
    rows = conn.execute(sql).fetchall()
    return [dict(r) for r in rows]


def get_unextracted_events(conn: sqlite3.Connection, limit: int = 100) -> list[dict]:
    rows = conn.execute(
        """SELECT id, report_number, narrative, product_code, modality, manufacturer, brand_name
           FROM events
           WHERE narrative IS NOT NULL AND narrative != ''
             AND extraction_json IS NULL
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_db_stats(conn: sqlite3.Connection) -> dict:
    return {
        "total_events": conn.execute("SELECT COUNT(*) FROM events").fetchone()[0],
        "events_with_narrative": conn.execute(
            "SELECT COUNT(*) FROM events WHERE narrative IS NOT NULL AND narrative != ''"
        ).fetchone()[0],
        "extracted_events": conn.execute(
            "SELECT COUNT(*) FROM events WHERE extraction_json IS NOT NULL"
        ).fetchone()[0],
        "total_clusters": conn.execute("SELECT COUNT(*) FROM clusters").fetchone()[0],
    }


def load_project_events(
    conn: sqlite3.Connection,
    events_by_code: Dict[str, List[dict]],
    manufacturer_hint: str = "Unknown",
) -> int:
    inserted = 0
    for code, events in events_by_code.items():
        for ev in events:
            report_number = str(ev.get("report_number") or ev.get("mdr_report_key") or f"{code}-{inserted}")
            problems = ev.get("product_problems") or []
            narrative = " ".join(str(x) for x in problems if x).strip()
            row = {
                "report_number": report_number,
                "date_received": str(ev.get("date_received", "")),
                "event_type": str(ev.get("event_type", "Unknown")),
                "product_code": code,
                "device_name": str(ev.get("device_name", "")),
                "manufacturer": str(ev.get("manufacturer") or manufacturer_hint),
                "brand_name": str(ev.get("brand_name", "")),
                "narrative": narrative,
                "narrative_length": len(narrative),
                "domain": "imaging",
                "modality": str(ev.get("modality", "Unknown")),
                "software_related": any(
                    k in narrative.lower() for k in ("software", "algorithm", "application", "dicom", "image")
                ),
                "problems": [str(p) for p in problems],
            }
            if insert_event(conn, row) is not None:
                inserted += 1
    conn.commit()
    return inserted
