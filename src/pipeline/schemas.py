"""
Shared JSON Schema Contracts (US-06)
Pydantic v2 models defining inter-component contracts.
Frozen after initial definition — changes require team sign-off.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ─── Enums ────────────────────────────────────────────────────────────────────


class Modality(str, Enum):
    MRI = "MRI"
    CT = "CT"
    ULTRASOUND = "Ultrasound"
    DIGITAL_XRAY = "DigitalXray"
    HEMATOLOGY = "Hematology"
    PCR = "PCR"
    MOLDX_INSTRUMENT = "MolDxInstrument"
    UNKNOWN = "Unknown"


class SeverityCode(str, Enum):
    S1_NEGLIGIBLE = "S1_negligible"
    S2_MINOR = "S2_minor"
    S3_SERIOUS = "S3_serious"
    S4_CRITICAL = "S4_critical"
    S5_CATASTROPHIC = "S5_catastrophic"


class QMSCategory(str, Enum):
    SW_FUNC = "SW-FUNC"      # Software functional failure
    SW_ALGO = "SW-ALGO"      # Algorithm/calculation error
    SW_UI = "SW-UI"          # User interface issue
    SW_DATA = "SW-DATA"      # Data integrity/loss
    SW_CYBER = "SW-CYBER"    # Cybersecurity concern
    HW_MECH = "HW-MECH"     # Hardware mechanical failure
    HW_ELEC = "HW-ELEC"     # Hardware electrical failure
    IMG_QUAL = "IMG-QUAL"    # Image quality degradation
    IMG_PROC = "IMG-PROC"    # Image processing error
    PERF_ACC = "PERF-ACC"    # Performance/accuracy issue
    SAFE_PAT = "SAFE-PAT"   # Patient safety concern
    SAFE_USR = "SAFE-USR"   # User/operator safety concern
    DOC_LABEL = "DOC-LABEL"  # Labeling/documentation issue


class ComplaintSource(str, Enum):
    CUSTOMER = "customer"
    FIELD_SERVICE = "field_service"
    INTERNAL = "internal"
    PMS = "PMS"
    PUBLICATION = "publication"
    UNKNOWN = "unknown"


class TrendFlag(str, Enum):
    EMERGING = "emerging"
    STABLE = "stable"
    DECLINING = "declining"


class RiskLevel(str, Enum):
    ACCEPTABLE = "ACCEPTABLE"
    ALARP = "ALARP"
    UNACCEPTABLE = "UNACCEPTABLE"


# ─── Product code → modality mapping ─────────────────────────────────────────

PRODUCT_CODE_TO_MODALITY = {
    "LNH": Modality.MRI,
    "JAK": Modality.CT,
    "IYE": Modality.CT,
    "LLZ": Modality.ULTRASOUND,
    "IZL": Modality.DIGITAL_XRAY,
    "MQB": Modality.MOLDX_INSTRUMENT,
    "GKZ": Modality.HEMATOLOGY,
    "QKO": Modality.PCR,
}

PRODUCT_CODE_TO_DOMAIN = {
    "LNH": "imaging",
    "JAK": "imaging",
    "IYE": "imaging",
    "LLZ": "imaging",
    "IZL": "imaging",
    "MQB": "molecular_dx",
    "GKZ": "molecular_dx",
    "QKO": "molecular_dx",
}


# ─── Extraction Output (Agent 1) ─────────────────────────────────────────────


class ExtractionOutput(BaseModel):
    """Output schema for Agent 1: Extraction Agent.
    Maps raw complaint narrative → structured QMS-categorized record.
    """

    report_id: str = Field(..., description="Unique complaint/event ID")
    modality: Modality
    component: str = Field(..., description="Affected device component")
    failure_mode: str = Field(..., description="What went wrong")
    symptom: str = Field(..., description="Observable symptom reported")
    severity_indicator: SeverityCode
    manufacturer: Optional[str] = None
    device_model: Optional[str] = None
    patient_impact: Optional[str] = None
    discovery_phase: Optional[str] = Field(
        None, description="When discovered: in-use, maintenance, installation, testing"
    )
    software_related: bool
    is_safety_related: bool
    usability_concern: bool
    security_concern: bool
    affected_countries: list[str] = Field(
        default_factory=lambda: ["unknown"],
        description="ISO 3166-1 alpha-2 codes or 'unknown'",
    )
    complaint_source: ComplaintSource = ComplaintSource.UNKNOWN
    qms_complaint_category: QMSCategory
    confidence: float = Field(..., ge=0.0, le=1.0)

    # CoT reasoning trace (for auditability)
    reasoning: Optional[str] = Field(
        None, description="Chain-of-thought reasoning trace from extraction"
    )


# ─── Similarity Output ───────────────────────────────────────────────────────


class SimilarEvent(BaseModel):
    report_number: str
    similarity_score: float = Field(..., ge=0.0, le=1.0)
    narrative_snippet: Optional[str] = None


class SimilarityOutput(BaseModel):
    """Output from the Similarity/Trend Module (non-LLM pipeline)."""

    cluster_id: int
    cluster_label: str
    similar_events: list[SimilarEvent] = Field(default_factory=list)
    trend_flag: TrendFlag
    cluster_size: int
    growth_rate_30d: float = Field(
        ..., description="Percentage growth in cluster over last 30 days"
    )
    cluster_daily_counts: dict[str, int] = Field(
        default_factory=dict,
        description="Daily event counts for this cluster over the past 30 days {YYYY-MM-DD: count}",
    )


# ─── Mock Factories (for standalone testing) ─────────────────────────────────


def mock_extraction() -> ExtractionOutput:
    return ExtractionOutput(
        report_id="EV-2026-0142",
        modality=Modality.MRI,
        component="image reconstruction pipeline",
        failure_mode="image artifact during cardiac sequence",
        symptom="banding artifact visible in reconstructed images",
        severity_indicator=SeverityCode.S3_SERIOUS,
        manufacturer="Philips",
        device_model="Achieva 1.5T dStream",
        patient_impact="repeat scan required (radiation: N/A for MRI)",
        discovery_phase="in-use",
        software_related=True,
        is_safety_related=True,
        usability_concern=False,
        security_concern=False,
        affected_countries=["US", "DE"],
        complaint_source=ComplaintSource.CUSTOMER,
        qms_complaint_category=QMSCategory.IMG_QUAL,
        confidence=0.82,
        reasoning="Component: image reconstruction → Failure: artifact during cardiac → Severity: S3 (repeat scan needed) → Category: IMG-QUAL",
    )


def mock_similarity() -> SimilarityOutput:
    return SimilarityOutput(
        cluster_id=4,
        cluster_label="MRI image artifacts - cardiac sequences",
        similar_events=[
            SimilarEvent(
                report_number="MW5012345",
                similarity_score=0.91,
                narrative_snippet="Banding artifact observed during cardiac MRI...",
            ),
            SimilarEvent(
                report_number="MW5012678",
                similarity_score=0.87,
                narrative_snippet="Image quality degradation in SSFP sequences...",
            ),
        ],
        trend_flag=TrendFlag.EMERGING,
        cluster_size=43,
        growth_rate_30d=12.5,
    )


# ─── Validation helper for orchestrator gates ────────────────────────────────


def validate_handoff(stage_name: str, payload: dict) -> BaseModel:
    """Validate a payload against the schema for a given pipeline stage.
    Used by orchestrator gates to catch malformed data between components.
    """
    schema_map = {
        "extraction": ExtractionOutput,
        "similarity": SimilarityOutput,
    }
    model_cls = schema_map.get(stage_name)
    if model_cls is None:
        raise ValueError(f"Unknown stage: {stage_name}. Valid: {list(schema_map.keys())}")
    return model_cls.model_validate(payload)


# ─── Kapil / Report-Generation Agent schemas (dataclasses) ───────────────────

from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, List as TypingList


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
    ground_truth_problems: TypingList[str] = dc_field(default_factory=list)


@dataclass
class ExtractedSignal:
    complaint_id: str
    qms_complaint_category: str
    key_issues: TypingList[str]
    confidence: float
    safety_flags: Dict[str, bool]
    iso_13485_clauses: TypingList[str] = dc_field(default_factory=list)
    iso_14971_hazard_tags: TypingList[str] = dc_field(default_factory=list)


@dataclass
class RetrievalEvidence:
    evidence_id: str
    source_type: str
    product_code: str
    snippet: str
    score: float
    metadata: Dict[str, Any] = dc_field(default_factory=dict)


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
    hazardous_situation: str = ""
    harm: str = ""
    severity_rationale: str = ""
    probability_rationale: str = ""
    evidence_basis: TypingList[Dict[str, Any]] = dc_field(default_factory=list)
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
    trend_rationale: str = ""


@dataclass
class SignalReport:
    report_id: str
    created_at: str
    trace_id: str
    complaint: Complaint
    extraction: ExtractedSignal
    retrieval: TypingList[RetrievalEvidence]
    risk: RiskAssessment
    trend: TrendSummary
    report_type: str
    orchestrator_questions: TypingList[str]
    report_markdown: str
    review_needed: bool = False
    review_reasons: TypingList[str] = dc_field(default_factory=list)
    quality: Dict[str, Any] = dc_field(default_factory=dict)


@dataclass
class PipelineRunResult:
    run_id: str
    started_at: datetime
    completed_at: datetime
    selected_product_codes: TypingList[str]
    processed_complaints: int
    generated_report_paths: TypingList[str]
    generated_trace_paths: TypingList[str] = dc_field(default_factory=list)


def validate_signal_handoff(stage_name: str, payload: Any) -> TypingList[str]:
    """Validate a signal-pipeline payload; returns a list of error strings (empty = valid).
    Used by the report-generation harness (Kapil's agent).
    """
    errors: TypingList[str] = []
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
