"""Gold benchmark loader for the evaluation harness (US-05).

Reads ``data/evaluation/gold_complaints.json`` into typed ``GoldCase`` records.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from src.config import DATA_DIR


GOLD_PATH = DATA_DIR / "evaluation" / "gold_complaints.json"


@dataclass
class GoldCase:
    """One labeled benchmark complaint plus its expected pipeline behavior."""

    case_id: str
    product_code: str
    narrative: str
    event_type: str = "Malfunction"
    manufacturer: str = "Unknown"
    expect_rejected: bool = False
    software_related: Optional[bool] = None
    gold_categories: List[str] = field(default_factory=list)
    key_issue_keywords: List[str] = field(default_factory=list)
    expected_risk_buckets: List[str] = field(default_factory=list)
    expect_escalation: Optional[bool] = None
    relevant_keywords: List[str] = field(default_factory=list)
    mentions_death: bool = False
    mentions_injury: bool = False

    @classmethod
    def from_dict(cls, raw: dict) -> "GoldCase":
        return cls(
            case_id=raw["case_id"],
            product_code=raw["product_code"],
            narrative=raw["narrative"],
            event_type=raw.get("event_type", "Malfunction"),
            manufacturer=raw.get("manufacturer", "Unknown"),
            expect_rejected=bool(raw.get("expect_rejected", False)),
            software_related=raw.get("software_related"),
            gold_categories=list(raw.get("gold_categories", [])),
            key_issue_keywords=list(raw.get("key_issue_keywords", [])),
            expected_risk_buckets=list(raw.get("expected_risk_buckets", [])),
            expect_escalation=raw.get("expect_escalation"),
            relevant_keywords=list(raw.get("relevant_keywords", [])),
            mentions_death=bool(raw.get("mentions_death", False)),
            mentions_injury=bool(raw.get("mentions_injury", False)),
        )


def load_gold_cases(path: Optional[Path] = None) -> List[GoldCase]:
    """Load and parse the gold benchmark; raises if the file is missing."""
    gold_path = Path(path) if path else GOLD_PATH
    if not gold_path.exists():
        raise FileNotFoundError(f"Gold benchmark not found at {gold_path}")
    payload = json.loads(gold_path.read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    return [GoldCase.from_dict(c) for c in cases]
