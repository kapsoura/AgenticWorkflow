"""Initialize the runtime stores from the local FDA archive (provisioning step).

Creates the SQLite schema and extracts the adverse-event archive into the Chroma
vector index, independently of running the full workflow. Run this once after
downloading data so the database and vector store are populated and ready:

    python -m src.init_db                         # default scope + event cap
    python -m src.init_db --max-events-per-code 250
    python -m src.init_db --reset                 # rebuild from scratch

The stores live under ``outputs/runtime/`` (``signal_intelligence.db`` and
``chroma/``) and are git-ignored, regenerable artifacts.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from src.config import (
    CHROMA_DIR,
    DEFAULT_MAX_EVENTS_PER_CODE,
    IMAGING_EVENTS_DIR,
    PRODUCT_CODES,
    RUNTIME_DIR,
    SQLITE_DB_PATH,
)
from src.utils.data_loader import load_events_for_codes
from src.utils.storage import init_chroma, init_sqlite, upsert_event_vectors


def _collection_count(collection) -> int:
    if collection is None:
        return 0
    try:
        return int(collection.count())
    except Exception:  # noqa: BLE001 - count is best-effort telemetry only
        return -1


def initialize(max_events_per_code: int, reset: bool = False) -> dict:
    """Provision SQLite + Chroma from the archive; return a summary dict."""
    if reset:
        if SQLITE_DB_PATH.exists():
            SQLITE_DB_PATH.unlink()
        if CHROMA_DIR.exists():
            shutil.rmtree(CHROMA_DIR, ignore_errors=True)

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    events_by_code = load_events_for_codes(
        imaging_events_dir=IMAGING_EVENTS_DIR,
        product_codes=PRODUCT_CODES,
        max_events_per_code=max_events_per_code,
    )

    # 1. SQLite schema (complaint_archive + signal_reports tables).
    init_sqlite(SQLITE_DB_PATH)

    # 2. Archive extraction → vector index (one upsert pass per product code).
    collection = init_chroma(CHROMA_DIR)
    per_code_loaded = {}
    for code in PRODUCT_CODES:
        events = events_by_code.get(code, [])
        per_code_loaded[code] = len(events)
        upsert_event_vectors(collection, events)

    return {
        "sqlite_db": str(SQLITE_DB_PATH),
        "chroma_dir": str(CHROMA_DIR),
        "chroma_available": collection is not None,
        "events_loaded_per_code": per_code_loaded,
        "events_loaded_total": sum(per_code_loaded.values()),
        "vectors_indexed": _collection_count(collection),
        "reset": reset,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Initialize SQLite + Chroma from the local FDA archive."
    )
    parser.add_argument(
        "--max-events-per-code",
        type=int,
        default=DEFAULT_MAX_EVENTS_PER_CODE,
        help="Archive events loaded and indexed per product code.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the existing runtime DB + vector store before rebuilding.",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    summary = initialize(max_events_per_code=args.max_events_per_code, reset=args.reset)

    print("Database initialized from archive:")
    print(f"  SQLite:  {summary['sqlite_db']}")
    print(f"  Chroma:  {summary['chroma_dir']} (available={summary['chroma_available']})")
    for code, count in summary["events_loaded_per_code"].items():
        print(f"    {code}: {count} events loaded")
    print(f"  Total events loaded: {summary['events_loaded_total']}")
    print(f"  Vectors indexed:     {summary['vectors_indexed']}")
    if not summary["chroma_available"]:
        print("  NOTE: Chroma unavailable — vector retrieval will fall back to keyword search.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
