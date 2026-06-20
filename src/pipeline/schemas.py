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
