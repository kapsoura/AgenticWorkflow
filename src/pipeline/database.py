"""
Database layer — SQLite schema + helpers (US-01).
Creates signal_intelligence.db with tables for events, recalls, clusters, etc.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "signal_intelligence.db"

# ─── Schema DDL ──────────────────────────────────────────────────────────────

SCHEMA_SQL = """
-- Core event table (parsed from openFDA JSON)
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
    -- Extraction agent fields (NULL until Agent 1 processes)
    is_safety_related BOOLEAN,
    usability_concern BOOLEAN,
    security_concern BOOLEAN,
    affected_countries TEXT,
    complaint_source TEXT,
    qms_complaint_category TEXT,
    severity_indicator TEXT,
    extraction_confidence REAL,
    extraction_json TEXT,
    -- Similarity module fields
    cluster_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Product problems (many-to-many)
CREATE TABLE IF NOT EXISTS event_problems (
    event_id INTEGER REFERENCES events(id),
    problem_code TEXT NOT NULL,
    PRIMARY KEY (event_id, problem_code)
);

-- Recalls
CREATE TABLE IF NOT EXISTS recalls (
    id INTEGER PRIMARY KEY,
    recall_number TEXT UNIQUE,
    product_code TEXT NOT NULL,
    reason_for_recall TEXT,
    root_cause TEXT,
    classification TEXT,
    action TEXT,
    recalling_firm TEXT,
    recall_date DATE,
    software_related BOOLEAN
);

-- Clusters (from HDBSCAN)
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

-- Indexes
CREATE INDEX IF NOT EXISTS idx_events_product_code ON events(product_code);
CREATE INDEX IF NOT EXISTS idx_events_cluster ON events(cluster_id);
CREATE INDEX IF NOT EXISTS idx_events_qms_category ON events(qms_complaint_category);
CREATE INDEX IF NOT EXISTS idx_recalls_product_code ON recalls(product_code);
CREATE INDEX IF NOT EXISTS idx_recalls_root_cause ON recalls(root_cause);
"""


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Get a SQLite connection with row factory enabled."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: the API server (FastAPI) holds one shared
    # pipeline.conn that is reused across anyio threadpool worker threads.
    # Access is read-heavy and WAL is enabled, so relaxing the thread guard
    # is safe here. (Per-request endpoints still open+close their own conn.)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Create tables and indexes if they don't exist."""
    conn = get_connection(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


# ─── Data loading helpers ────────────────────────────────────────────────────

PRODUCT_CODE_TO_MODALITY = {
    "LNH": "MRI", "JAK": "CT", "IYE": "CT",
    "LLZ": "Ultrasound", "IZL": "DigitalXray",
    "MQB": "MolDxInstrument", "GKZ": "Hematology", "QKO": "PCR",
}

PRODUCT_CODE_TO_DOMAIN = {
    "LNH": "imaging", "JAK": "imaging", "IYE": "imaging",
    "LLZ": "imaging", "IZL": "imaging",
    "MQB": "molecular_dx", "GKZ": "molecular_dx", "QKO": "molecular_dx",
}


def parse_narrative(event: dict) -> str:
    """Extract narrative text from MAUDE mdr_text array."""
    texts = event.get("mdr_text", [])
    if not texts:
        return ""
    parts = [t.get("text", "") for t in texts if t.get("text")]
    return " ".join(parts).strip()


def parse_event(event: dict) -> dict:
    """Parse a raw openFDA event JSON into a flat row dict."""
    narrative = parse_narrative(event)
    report_number = event.get("report_number", "")

    # Get product code from device array
    devices = event.get("device", [])
    product_code = ""
    device_name = ""
    manufacturer = ""
    brand_name = ""
    if devices:
        d = devices[0]
        product_code = d.get("device_report_product_code", "")
        device_name = d.get("generic_name", "")
        manufacturer = d.get("manufacturer_d_name", "")
        brand_name = d.get("brand_name", "")

    # Product problems
    problems = event.get("product_problems", [])

    modality = PRODUCT_CODE_TO_MODALITY.get(product_code, "Unknown")
    domain = PRODUCT_CODE_TO_DOMAIN.get(product_code, "unknown")

    # Heuristic: is this software-related?
    sw_keywords = {"software", "algorithm", "application", "display", "data", "cyber"}
    narrative_lower = narrative.lower()
    problems_lower = " ".join(problems).lower()
    software_related = any(kw in narrative_lower or kw in problems_lower for kw in sw_keywords)

    return {
        "report_number": report_number,
        "date_received": event.get("date_received", ""),
        "event_type": event.get("event_type", ""),
        "product_code": product_code,
        "device_name": device_name,
        "manufacturer": manufacturer,
        "brand_name": brand_name,
        "narrative": narrative,
        "narrative_length": len(narrative),
        "domain": domain,
        "modality": modality,
        "software_related": software_related,
        "problems": problems,
    }


def insert_event(conn: sqlite3.Connection, row: dict) -> Optional[int]:
    """Insert or replace an event row. Returns the row ID."""
    try:
        cur = conn.execute(
            """INSERT OR REPLACE INTO events
               (report_number, date_received, event_type, product_code,
                device_name, manufacturer, brand_name, narrative,
                narrative_length, domain, modality, software_related)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                row["report_number"], row["date_received"], row["event_type"],
                row["product_code"], row["device_name"], row["manufacturer"],
                row["brand_name"], row["narrative"], row["narrative_length"],
                row["domain"], row["modality"], row["software_related"],
            ),
        )
        event_id = cur.lastrowid

        # Insert problems
        for prob in row.get("problems", []):
            conn.execute(
                "INSERT OR IGNORE INTO event_problems (event_id, problem_code) VALUES (?,?)",
                (event_id, prob),
            )
        return event_id
    except sqlite3.Error:
        return None


def insert_recall(conn: sqlite3.Connection, recall: dict) -> Optional[int]:
    """Insert or replace a recall row."""
    recall_number = recall.get("recall_number") or recall.get("res_event_number", "")
    product_code = recall.get("product_code", "")
    if not product_code:
        # Try to extract from product_res or openfda
        openfda = recall.get("openfda", {})
        codes = openfda.get("device_report_product_code", [])
        product_code = codes[0] if codes else ""

    reason = recall.get("reason_for_recall", "")
    root_cause = recall.get("root_cause_description", "")
    classification = recall.get("classification", "")
    action = recall.get("action", "")
    firm = recall.get("recalling_firm", "")
    recall_date = recall.get("recall_initiation_date", "")

    sw_keywords = {"software", "algorithm", "code", "firmware", "update"}
    text = f"{reason} {root_cause}".lower()
    software_related = any(kw in text for kw in sw_keywords)

    try:
        cur = conn.execute(
            """INSERT OR REPLACE INTO recalls
               (recall_number, product_code, reason_for_recall, root_cause,
                classification, action, recalling_firm, recall_date, software_related)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (recall_number, product_code, reason, root_cause,
             classification, action, firm, recall_date, software_related),
        )
        return cur.lastrowid
    except sqlite3.Error:
        return None


def update_extraction_fields(conn: sqlite3.Connection, report_number: str, extraction: dict):
    """Write Agent 1 extraction results back to the events table."""
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
    """Fetch events that have narratives (for extraction/embedding)."""
    sql = "SELECT id, report_number, narrative, product_code, modality, manufacturer FROM events WHERE narrative IS NOT NULL AND narrative != ''"
    if limit > 0:
        sql += f" LIMIT {int(limit)}"
    rows = conn.execute(sql).fetchall()
    return [dict(r) for r in rows]


def get_unextracted_events(conn: sqlite3.Connection, limit: int = 100) -> list[dict]:
    """Fetch events that haven't been processed by the extraction agent yet."""
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
    """Get basic database statistics."""
    stats = {}
    stats["total_events"] = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    stats["events_with_narrative"] = conn.execute(
        "SELECT COUNT(*) FROM events WHERE narrative IS NOT NULL AND narrative != ''"
    ).fetchone()[0]
    stats["extracted_events"] = conn.execute(
        "SELECT COUNT(*) FROM events WHERE extraction_json IS NOT NULL"
    ).fetchone()[0]
    stats["total_recalls"] = conn.execute("SELECT COUNT(*) FROM recalls").fetchone()[0]
    stats["total_clusters"] = conn.execute("SELECT COUNT(*) FROM clusters").fetchone()[0]
    return stats
