from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List


ALLOWED_RISK_BUCKETS = {"ACCEPTABLE", "ALARP", "UNACCEPTABLE"}


@dataclass
class Complaint:
    complaint_id: str
    product_code: str
    manufacturer: str
    event_type: str
    date_received: str
    narrative: str
    source_report_number: str
    ground_truth_problems: List[str] = field(default_factory=list)


@dataclass
class ExtractedSignal:
    complaint_id: str
    qms_complaint_category: str
    key_issues: List[str]
    confidence: float
    safety_flags: Dict[str, bool]
    iso_13485_clauses: List[str] = field(default_factory=list)
    iso_14971_hazard_tags: List[str] = field(default_factory=list)


@dataclass
class RetrievalEvidence:
    evidence_id: str
    source_type: str
    product_code: str
    snippet: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskAssessment:
    complaint_id: str
    severity_level: str
    probability_level: str
    risk_bucket: str
    escalation_required: bool
    prrc_notification_required: bool
    capa_recommendation: str
    report_type: str
    iso_14971_rationale: str
    # --- richer ISO 14971 fields from the two-pass risk agent (optional) ---
    hazardous_situation: str = ""
    harm: str = ""
    severity_rationale: str = ""
    probability_rationale: str = ""
    evidence_basis: List[Dict[str, Any]] = field(default_factory=list)
    uncertainty: str = ""
    capa_immediate: str = ""
    capa_investigation: str = ""
    capa_corrective: str = ""
    capa_preventive: str = ""
    capa_verification: str = ""
    capa_effectiveness: str = ""
    capa_precedent: str = ""
    fsca_required: bool = False
    llm_backed: bool = False


@dataclass
class TrendSummary:
    product_code: str
    total_events: int
    software_problem_events: int
    latest_year_events: int
    previous_year_events: int
    trend_direction: str
    # One-sentence justification for the direction. Produced by the LLM (tool or
    # JSON path) and surfaced in the report; empty when no model verdict is available.
    trend_rationale: str = ""


@dataclass
class SignalReport:
    report_id: str
    created_at: str
    trace_id: str
    complaint: Complaint
    extraction: ExtractedSignal
    retrieval: List[RetrievalEvidence]
    risk: RiskAssessment
    trend: TrendSummary
    report_type: str
    orchestrator_questions: List[str]
    report_markdown: str
    review_needed: bool = False
    review_reasons: List[str] = field(default_factory=list)


@dataclass
class PipelineRunResult:
    run_id: str
    started_at: datetime
    completed_at: datetime
    selected_product_codes: List[str]
    processed_complaints: int
    generated_report_paths: List[str]
    generated_trace_paths: List[str] = field(default_factory=list)


def validate_handoff(stage_name: str, payload: Any) -> List[str]:
    errors: List[str] = []

    if stage_name == "extraction":
        if not isinstance(payload, ExtractedSignal):
            return ["Extraction payload has wrong type"]
        if not payload.qms_complaint_category:
            errors.append("qms_complaint_category is required")
        if not payload.key_issues:
            errors.append("key_issues must not be empty")
        if not (0.0 <= payload.confidence <= 1.0):
            errors.append("confidence must be in range [0,1]")

    elif stage_name == "retrieval":
        if not isinstance(payload, list):
            return ["Retrieval payload has wrong type"]
        for idx, item in enumerate(payload):
            if not isinstance(item, RetrievalEvidence):
                errors.append(f"retrieval[{idx}] has wrong type")
                continue
            if not (0.0 <= item.score <= 1.0):
                errors.append(f"retrieval[{idx}].score must be in range [0,1]")

    elif stage_name == "risk":
        if not isinstance(payload, RiskAssessment):
            return ["Risk payload has wrong type"]
        if payload.risk_bucket not in ALLOWED_RISK_BUCKETS:
            errors.append("risk_bucket must be ACCEPTABLE, ALARP, or UNACCEPTABLE")

    return errors
