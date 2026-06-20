import json
import sqlite3
from pathlib import Path
from typing import Iterable, List

from src.pipeline.schemas import Complaint, SignalReport


def embed_text(text: str, dims: int = 32) -> List[float]:
    """Deterministic lightweight embedding for offline/local development."""
    vec = [0.0] * dims
    if not text:
        return vec
    for idx, ch in enumerate(text.lower()):
        bucket = idx % dims
        vec[bucket] += (ord(ch) % 97) / 97.0
    norm = sum(abs(x) for x in vec) or 1.0
    return [x / norm for x in vec]


def init_sqlite(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS complaint_archive (
                complaint_id TEXT PRIMARY KEY,
                product_code TEXT NOT NULL,
                manufacturer TEXT,
                event_type TEXT,
                date_received TEXT,
                narrative TEXT,
                source_report_number TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS signal_reports (
                report_id TEXT PRIMARY KEY,
                trace_id TEXT,
                complaint_id TEXT NOT NULL,
                report_type TEXT NOT NULL,
                risk_bucket TEXT NOT NULL,
                review_needed INTEGER NOT NULL DEFAULT 0,
                review_reasons_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                report_markdown TEXT NOT NULL,
                retrieval_json TEXT NOT NULL
            )
            """
        )
        _ensure_column(cur, "signal_reports", "trace_id", "TEXT")
        _ensure_column(cur, "signal_reports", "review_needed", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(cur, "signal_reports", "review_reasons_json", "TEXT NOT NULL DEFAULT '[]'")
        conn.commit()
    finally:
        conn.close()


def archive_complaints(db_path: Path, complaints: Iterable[Complaint]) -> None:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        for c in complaints:
            cur.execute(
                """
                INSERT OR REPLACE INTO complaint_archive (
                    complaint_id, product_code, manufacturer, event_type,
                    date_received, narrative, source_report_number
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    c.complaint_id,
                    c.product_code,
                    c.manufacturer,
                    c.event_type,
                    c.date_received,
                    c.narrative,
                    c.source_report_number,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def persist_signal_report(db_path: Path, report: SignalReport) -> None:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO signal_reports (
                report_id, trace_id, complaint_id, report_type, risk_bucket,
                review_needed, review_reasons_json, created_at, report_markdown, retrieval_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report.report_id,
                report.trace_id,
                report.complaint.complaint_id,
                report.report_type,
                report.risk.risk_bucket,
                1 if report.review_needed else 0,
                json.dumps(report.review_reasons),
                report.created_at,
                report.report_markdown,
                json.dumps([r.__dict__ for r in report.retrieval]),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def init_chroma(chroma_dir: Path):
    chroma_dir.mkdir(parents=True, exist_ok=True)
    try:
        import chromadb

        client = chromadb.PersistentClient(path=str(chroma_dir))
        collection = client.get_or_create_collection(name="openfda_events")
        return collection
    except Exception:
        return None


def upsert_event_vectors(collection, events: List[dict]) -> None:
    if collection is None:
        return

    ids = []
    docs = []
    metas = []
    embeddings = []
    for event in events:
        report_number = event.get("report_number")
        if not report_number:
            continue
        problems = " ".join(event.get("product_problems") or [])
        if not problems:
            continue
        ids.append(str(report_number))
        docs.append(problems)
        embeddings.append(embed_text(problems))
        metas.append(
            {
                "event_type": str(event.get("event_type", "Unknown")),
                "date_received": str(event.get("date_received", "")),
            }
        )

    if ids:
        collection.upsert(ids=ids, documents=docs, metadatas=metas, embeddings=embeddings)


def _ensure_column(cur: sqlite3.Cursor, table: str, column: str, column_def: str) -> None:
    cur.execute(f"PRAGMA table_info({table})")
    columns = {row[1] for row in cur.fetchall()}
    if column not in columns:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_def}")
