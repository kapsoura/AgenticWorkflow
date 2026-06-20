from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


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
    SW_FUNC = "SW-FUNC"
    SW_ALGO = "SW-ALGO"
    SW_UI = "SW-UI"
    SW_DATA = "SW-DATA"
    SW_CYBER = "SW-CYBER"
    HW_MECH = "HW-MECH"
    HW_ELEC = "HW-ELEC"
    IMG_QUAL = "IMG-QUAL"
    IMG_PROC = "IMG-PROC"
    PERF_ACC = "PERF-ACC"
    SAFE_PAT = "SAFE-PAT"
    SAFE_USR = "SAFE-USR"
    DOC_LABEL = "DOC-LABEL"


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


class ExtractionOutput(BaseModel):
    report_id: str
    modality: Modality
    component: str
    failure_mode: str
    symptom: str
    severity_indicator: SeverityCode
    manufacturer: Optional[str] = None
    device_model: Optional[str] = None
    patient_impact: Optional[str] = None
    discovery_phase: Optional[str] = None
    software_related: bool
    is_safety_related: bool
    usability_concern: bool
    security_concern: bool
    affected_countries: list[str] = Field(default_factory=lambda: ["unknown"])
    complaint_source: ComplaintSource = ComplaintSource.UNKNOWN
    qms_complaint_category: QMSCategory
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: Optional[str] = None


class SimilarEvent(BaseModel):
    report_number: str
    similarity_score: float = Field(..., ge=0.0, le=1.0)
    narrative_snippet: Optional[str] = None


class SimilarityOutput(BaseModel):
    cluster_id: int
    cluster_label: str
    similar_events: list[SimilarEvent] = Field(default_factory=list)
    trend_flag: TrendFlag
    cluster_size: int
    growth_rate_30d: float
    cluster_daily_counts: dict[str, int] = Field(default_factory=dict)


def validate_handoff(stage_name: str, payload: dict) -> BaseModel:
    schema_map = {
        "extraction": ExtractionOutput,
        "similarity": SimilarityOutput,
    }
    model_cls = schema_map.get(stage_name)
    if model_cls is None:
        raise ValueError(f"Unknown stage: {stage_name}. Valid: {list(schema_map.keys())}")
    return model_cls.model_validate(payload)
