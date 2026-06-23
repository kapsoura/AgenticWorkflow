import json
import random
from pathlib import Path
from typing import Dict, Iterable, List

from src.pipeline.schemas import Complaint


def _read_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_events_for_codes(
    imaging_events_dir: Path,
    product_codes: Iterable[str],
    max_events_per_code: int,
) -> Dict[str, List[dict]]:
    events_by_code: Dict[str, List[dict]] = {}

    for code in product_codes:
        code_events: List[dict] = []
        pattern = f"{code}_batch*.json"
        for file_path in sorted(imaging_events_dir.glob(pattern)):
            payload = _read_json(file_path)
            results = payload.get("results", [])
            code_events.extend(results)
            if len(code_events) >= max_events_per_code:
                break
        events_by_code[code] = code_events[:max_events_per_code]

    return events_by_code


def load_recalls(recalls_file: Path, product_codes: Iterable[str]) -> List[dict]:
    recalls = _read_json(recalls_file)
    allowed = set(product_codes)
    return [r for r in recalls if r.get("product_code") in allowed]


def _collect_narrative(event: dict) -> str:
    texts = [t.get("text", "") for t in event.get("mdr_text", []) if t.get("text")]
    narrative = " ".join(texts).strip()
    if narrative:
        return narrative

    problems = event.get("product_problems") or []
    event_type = event.get("event_type", "Unknown")
    manufacturer = "Unknown"
    if event.get("device"):
        manufacturer = event["device"][0].get("manufacturer_d_name", "Unknown")
    fallback = f"Event type: {event_type}. Problems: {', '.join(problems) if problems else 'Not provided'}. Manufacturer: {manufacturer}."
    return fallback


def simulate_complaints(
    events_by_code: Dict[str, List[dict]],
    complaints_per_code: int,
    seed: int,
) -> List[Complaint]:
    rng = random.Random(seed)
    complaints: List[Complaint] = []

    for code, events in events_by_code.items():
        if not events:
            continue
        picked = events[:]
        rng.shuffle(picked)
        picked = picked[:complaints_per_code]

        for idx, event in enumerate(picked, start=1):
            device = (event.get("device") or [{}])[0]
            report_number = event.get("report_number", f"unknown-{idx}")
            complaint_id = f"SIM-{code}-{idx:03d}"
            complaints.append(
                Complaint(
                    complaint_id=complaint_id,
                    product_code=code,
                    manufacturer=device.get("manufacturer_d_name", "Unknown"),
                    event_type=event.get("event_type", "Unknown"),
                    date_received=event.get("date_received", ""),
                    narrative=_collect_narrative(event),
                    source_report_number=report_number,
                    ground_truth_problems=event.get("product_problems") or [],
                )
            )

    return complaints
