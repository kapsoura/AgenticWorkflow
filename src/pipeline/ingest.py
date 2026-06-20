"""
FDA Data Downloader (US-01).
Downloads adverse events + recalls from openFDA for all 8 product codes
and loads them into the SQLite database.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tqdm import tqdm

from src.pipeline.database import (
    PRODUCT_CODE_TO_DOMAIN,
    init_db,
    insert_event,
    insert_recall,
    get_db_stats,
    parse_event,
)

# Product codes to download
PRODUCT_CODES = [
    ("LNH", "MRI System"),
    ("JAK", "CT Scanner"),
    ("IYE", "CT X-ray System"),
    ("LLZ", "Ultrasound Imaging"),
    ("IZL", "Digital X-ray"),
    ("MQB", "Molecular Dx Instrument"),
    ("GKZ", "Hematology Analyzer"),
    ("QKO", "PCR Platform"),
]

BASE_EVENT_URL = "https://api.fda.gov/device/event.json"
BASE_RECALL_URL = "https://api.fda.gov/device/recall.json"
BATCH_SIZE = 100
MAX_SKIP = 25000  # openFDA limit: skip + limit <= 26000


def fetch_json(url: str, retries: int = 3, delay: float = 2.0) -> dict | None:
    """Fetch JSON with retry + backoff for 429 rate limits."""
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "MTech-SignalIntel/1.0"})
            with urlopen(req, timeout=45) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as e:
            if e.code == 429:
                wait = delay * (2 ** attempt)
                print(f"    Rate limited (429). Waiting {wait:.0f}s...")
                time.sleep(wait)
            elif e.code == 404:
                return None
            else:
                print(f"    HTTP {e.code}: {e.reason}")
                if attempt == retries - 1:
                    return None
        except (URLError, Exception) as e:
            print(f"    Error: {e}")
            if attempt == retries - 1:
                return None
        time.sleep(delay)
    return None


def download_events_for_code(
    product_code: str,
    desc: str,
    date_from: str = "20190101",
    date_to: str = "20261231",
    max_events: int = 5000,
) -> list[dict]:
    """Download adverse events for a single product code with pagination."""
    print(f"\n  [{product_code}] {desc}")
    all_events = []
    skip = 0

    while skip < MAX_SKIP and len(all_events) < max_events:
        url = (
            f"{BASE_EVENT_URL}?"
            f"search=device.device_report_product_code:{product_code}"
            f"+AND+date_received:[{date_from}+TO+{date_to}]"
            f"&limit={BATCH_SIZE}&skip={skip}"
        )
        data = fetch_json(url)
        if not data or "results" not in data:
            break

        batch = data["results"]
        total_available = data.get("meta", {}).get("results", {}).get("total", 0)
        all_events.extend(batch)

        print(f"    Batch {skip // BATCH_SIZE + 1}: {len(batch)} results "
              f"(got {len(all_events)}/{min(total_available, max_events)})")

        if len(batch) < BATCH_SIZE:
            break
        skip += BATCH_SIZE
        time.sleep(0.5)  # Be polite to API

    print(f"    Total downloaded for {product_code}: {len(all_events)}")
    return all_events


def download_recalls_for_code(product_code: str) -> list[dict]:
    """Download all recalls for a product code."""
    all_recalls = []
    skip = 0

    while skip < MAX_SKIP:
        url = (
            f"{BASE_RECALL_URL}?"
            f"search=product_code:{product_code}"
            f"&limit={BATCH_SIZE}&skip={skip}"
        )
        data = fetch_json(url)
        if not data or "results" not in data:
            break

        batch = data["results"]
        # Tag each recall with product_code for easier loading
        for r in batch:
            r["product_code"] = product_code
        all_recalls.extend(batch)

        if len(batch) < BATCH_SIZE:
            break
        skip += BATCH_SIZE
        time.sleep(0.5)

    return all_recalls


def run_download(max_events_per_code: int = 3000):
    """Main download + load pipeline."""
    print("=" * 70)
    print("FDA Data Ingestion Pipeline")
    print("=" * 70)

    conn = init_db()

    # ── Download Events ──────────────────────────────────────────────────
    print("\n── Downloading Adverse Events ──")
    total_loaded = 0
    for code, desc in PRODUCT_CODES:
        raw_events = download_events_for_code(code, desc, max_events=max_events_per_code)
        loaded = 0
        for raw in raw_events:
            parsed = parse_event(raw)
            if parsed["report_number"]:
                insert_event(conn, parsed)
                loaded += 1
        conn.commit()
        total_loaded += loaded
        print(f"    Loaded {loaded} events into DB")

    # ── Download Recalls ─────────────────────────────────────────────────
    print("\n── Downloading Recalls ──")
    total_recalls = 0
    for code, desc in PRODUCT_CODES:
        print(f"  [{code}] {desc}")
        raw_recalls = download_recalls_for_code(code)
        loaded = 0
        for raw in raw_recalls:
            insert_recall(conn, raw)
            loaded += 1
        conn.commit()
        total_recalls += loaded
        print(f"    {loaded} recalls loaded")

    # ── Summary ──────────────────────────────────────────────────────────
    stats = get_db_stats(conn)
    print("\n" + "=" * 70)
    print("INGESTION COMPLETE")
    print(f"  Events:              {stats['total_events']}")
    print(f"  With narratives:     {stats['events_with_narrative']}")
    print(f"  Recalls:             {stats['total_recalls']}")
    print(f"  DB path:             {conn.execute('PRAGMA database_list').fetchone()[2]}")
    print("=" * 70)

    conn.close()


if __name__ == "__main__":
    run_download()
