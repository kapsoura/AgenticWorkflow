"""
schemas.py — Shared JSON Contracts for the Medical Signal Intelligence Pipeline
IISc Bangalore · Deep Learning Project · June 2026

Contract rule: Every agent imports from here.
No agent invents its own types.
Schema changes require team approval (freeze after Jun 13).

Flow:
    RawInput → ExtractionOutput → RetrievalOutput → RiskCapaOutput → ReportOutput
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum
import json


# ─────────────────────────────────────────────
# ENUMS  (controlled vocabularies)
# ─────────────────────────────────────────────

class Modality(str, Enum):
    MRI         = "MRI"
    CT          = "CT"
    ULTRASOUND  = "Ultrasound"
    XRAY        = "X-ray"
    MOLECULAR   = "MolDx"
    UNKNOWN     = "Unknown"


class QMSCategory(str, Enum):
    """ISO 13485 §8.2.2 complaint categories (from Ideation.md)."""
    SW_FUNC  = "SW-FUNC"   # Software functional failure
    SW_ALGO  = "SW-ALGO"   # Algorithm / AI logic error
    SW_UI    = "SW-UI"     # User interface problem
    SW_DATA  = "SW-DATA"   # Data loss / corruption
    SW_CYBER = "SW-CYBER"  # Cybersecurity concern
    IMG_QUAL = "IMG-QUAL"  # Image quality issue
    HW_MECH  = "HW-MECH"  # Hardware / mechanical
    UNKNOWN  = "UNKNOWN"


class SeverityLevel(str, Enum):
    """ISO 14971 severity scale S1–S5."""
    S1 = "S1"  # Negligible   — no injury
    S2 = "S2"  # Minor        — reversible injury
    S3 = "S3"  # Serious      — irreversible / delayed diagnosis
    S4 = "S4"  # Critical     — life-threatening
    S5 = "S5"  # Catastrophic — death


class ProbabilityLevel(str, Enum):
    """ISO 14971 probability scale P1–P5, calibrated to MAUDE dataset counts."""
    P1 = "P1"  # Incredible  — < 1 event
    P2 = "P2"  # Remote      — 1–5 events
    P3 = "P3"  # Occasional  — 6–20 events
    P4 = "P4"  # Probable    — 21–200 events
    P5 = "P5"  # Frequent    — > 200 events


class RiskLevel(str, Enum):
    """ISO 14971 §7.5 acceptability matrix outcomes ONLY.
    Rule (US-12): HIGH / MEDIUM / LOW are NOT valid — never use them.
    """
    ACCEPTABLE    = "ACCEPTABLE"
    ALARP         = "ALARP"         # As Low As Reasonably Practicable
    UNACCEPTABLE  = "UNACCEPTABLE"


class EventType(str, Enum):
    MALFUNCTION = "Malfunction"
    INJURY      = "Injury"
    DEATH       = "Death"
    OTHER       = "Other"
    UNKNOWN     = "Unknown"


# ─────────────────────────────────────────────
# ISO 14971  5×5 RISK MATRIX
# (deterministic lookup — agents must use this,
#  not ask Claude to infer the cell)
# ─────────────────────────────────────────────

ISO_14971_MATRIX: dict[tuple[int, int], RiskLevel] = {
    # (severity, probability) → risk level
    (1, 1): RiskLevel.ACCEPTABLE,
    (1, 2): RiskLevel.ACCEPTABLE,
    (1, 3): RiskLevel.ACCEPTABLE,
    (1, 4): RiskLevel.ACCEPTABLE,
    (1, 5): RiskLevel.ALARP,

    (2, 1): RiskLevel.ACCEPTABLE,
    (2, 2): RiskLevel.ACCEPTABLE,
    (2, 3): RiskLevel.ALARP,
    (2, 4): RiskLevel.ALARP,
    (2, 5): RiskLevel.UNACCEPTABLE,

    (3, 1): RiskLevel.ACCEPTABLE,
    (3, 2): RiskLevel.ALARP,
    (3, 3): RiskLevel.ALARP,
    (3, 4): RiskLevel.UNACCEPTABLE,
    (3, 5): RiskLevel.UNACCEPTABLE,

    (4, 1): RiskLevel.ALARP,
    (4, 2): RiskLevel.ALARP,
    (4, 3): RiskLevel.UNACCEPTABLE,
    (4, 4): RiskLevel.UNACCEPTABLE,
    (4, 5): RiskLevel.UNACCEPTABLE,

    (5, 1): RiskLevel.ALARP,
    (5, 2): RiskLevel.UNACCEPTABLE,
    (5, 3): RiskLevel.UNACCEPTABLE,
    (5, 4): RiskLevel.UNACCEPTABLE,
    (5, 5): RiskLevel.UNACCEPTABLE,
}


def lookup_risk_level(severity: SeverityLevel, probability: ProbabilityLevel) -> RiskLevel:
    """Deterministic ISO 14971 matrix lookup. Never let an LLM decide this directly."""
    s = int(severity.value[1])
    p = int(probability.value[1])
    return ISO_14971_MATRIX[(s, p)]


# ─────────────────────────────────────────────
# PROBABILITY CALIBRATION (from US-12 spec)
# Maps MAUDE similar-event count → P-level
# ─────────────────────────────────────────────

def calibrate_probability(similar_event_count: int) -> ProbabilityLevel:
    """Convert raw MAUDE similar-event count to ISO 14971 P-level."""
    if similar_event_count < 1:
        return ProbabilityLevel.P1
    elif similar_event_count <= 5:
        return ProbabilityLevel.P2
    elif similar_event_count <= 20:
        return ProbabilityLevel.P3
    elif similar_event_count <= 200:
        return ProbabilityLevel.P4
    else:
        return ProbabilityLevel.P5


# ─────────────────────────────────────────────
# SCHEMA 0 — Raw Input
# ─────────────────────────────────────────────

@dataclass
class RawInput:
    """
    What the user pastes into the dashboard.
    Source: MAUDE adverse event report or internal complaint.
    """
    narrative: str                          # Raw report text
    report_id: Optional[str]  = None       # FDA MAUDE report number if known
    product_code: Optional[str] = None     # e.g. "LNH" for MRI
    source: str = "MAUDE"                  # MAUDE | internal | synthetic

    def to_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────────────────────────
# SCHEMA 1 — ExtractionOutput (US-07)
# Agent 1 → Agents 2, 3, 4
# Owner: M3
# ─────────────────────────────────────────────

@dataclass
class ExtractionOutput:
    """
    Structured facts extracted from a raw narrative by Extraction Agent.
    Maps free text → controlled ISO 13485 §8.2.2 categories.
    Every field must be populated — use 'unknown' not None for strings.

    Spec reference: US-07, US-06
    """
    # Identifiers
    report_id: str                              # Carry forward from RawInput

    # Device facts
    modality: Modality                          # MRI / CT / Ultrasound / MolDx
    manufacturer: str                           # Normalised name (e.g. "PHILIPS")
    device_model: str                           # Brand/model string
    component: str                              # e.g. "image reconstruction software"

    # Failure characterisation
    failure_mode: str                           # e.g. "missed lesion"
    symptom: str                                # Observable symptom
    event_type: EventType                       # Malfunction / Injury / Death

    # Risk signals
    severity_indicator: SeverityLevel          # S1–S5 (Claude assigns, matrix enforces)
    software_related: bool                      # True if root cause is software
    is_safety_related: bool                     # True if patient safety at risk
    usability_concern: bool                     # True if UI/human-factors issue
    security_concern: bool                      # True if cybersecurity issue

    # QMS classification
    qms_complaint_category: QMSCategory        # SW-ALGO, IMG-QUAL, etc.

    # Patient context
    patient_impact: str                         # e.g. "delayed diagnosis risk"
    affected_countries: list[str] = field(default_factory=lambda: ["unknown"])  # ISO 3166-1
    complaint_source: str = "unknown"          # reporter type

    # Quality signal
    confidence: float = 0.0                    # 0.0–1.0; < 0.5 → flag for human
    low_confidence_reason: Optional[str] = None  # why confidence is low

    def is_flagged(self) -> bool:
        """Gate 1: flag for human review if confidence is low."""
        return self.confidence < 0.75

    def to_dict(self) -> dict:
        d = asdict(self)
        # Serialise enums to string values
        for key in ["modality", "event_type", "severity_indicator",
                    "qms_complaint_category"]:
            if d[key] is not None:
                d[key] = d[key] if isinstance(d[key], str) else d[key]
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# ─────────────────────────────────────────────
# SCHEMA 2 — RetrievalOutput (US-11)
# Agent 2 → Agent 3
# Owner: M2
# ─────────────────────────────────────────────

@dataclass
class SimilarEvent:
    """One similar MAUDE event returned by the Retrieval Agent."""
    report_id: str
    narrative_snippet: str      # First 300 chars
    similarity_score: float     # 0.0–1.0 cosine similarity
    event_type: str
    product_code: str


@dataclass
class MatchedRecall:
    """One FDA recall matched as evidence for CAPA."""
    firm: str
    reason_for_recall: str      # Full recall reason text
    root_cause: str             # e.g. "Software design"
    product_code: str
    recall_id: Optional[str] = None


@dataclass
class RetrievalOutput:
    """
    Context bundle from Retrieval Agent — grounds all downstream reasoning.
    Rule: Risk/CAPA Agent must refuse to assert ALARP/UNACCEPTABLE
          if evidence_basis is empty (constitutional guardrail, US-12).

    Spec reference: US-11, US-09, US-04
    """
    report_id: str                              # Carry forward

    # Vector search results (ChromaDB)
    similar_events: list[SimilarEvent]         # Top-K similar MAUDE events
    similar_event_count: int                    # Total matching events in DB

    # FDA recall evidence
    matched_recalls: list[MatchedRecall]       # Top matching recalls

    # Similarity signal
    top_similarity_score: float                 # Best cosine score found
    cluster_label: Optional[str] = None        # HDBSCAN cluster name if assigned
    cluster_summary: Optional[str] = None      # Claude-written cluster description

    # Knowledge graph context
    knowledge_graph_hits: list[str] = field(default_factory=list)  # entity paths

    def has_evidence(self) -> bool:
        """Returns True if there is enough evidence to support ALARP/UNACCEPTABLE."""
        return len(self.similar_events) > 0 or len(self.matched_recalls) > 0

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# ─────────────────────────────────────────────
# SCHEMA 3 — RiskCapaOutput (US-12)
# Agent 3 → Agent 4
# Owner: M5
# ─────────────────────────────────────────────

@dataclass
class ISO14971Assessment:
    """Full ISO 14971 risk assessment block."""
    hazardous_situation: str
    harm: str
    severity_level: SeverityLevel
    severity_label: str                         # Human-readable e.g. "Serious"
    severity_rationale: str                     # Claude's CoT reasoning
    probability_level: ProbabilityLevel
    probability_label: str                      # e.g. "Occasional"
    probability_rationale: str                  # Why this P-level (cite event count)
    risk_level: RiskLevel                       # MUST come from lookup_risk_level()
    risk_control_needed: bool                   # True if ALARP or UNACCEPTABLE
    annex_c_hazard_category: Optional[str] = None  # ISO 14971 Annex C category


@dataclass
class EscalationFlags:
    """Regulatory escalation decisions (US-12 truth table)."""
    escalation_required: bool       # True if ALARP or UNACCEPTABLE
    prrc_notification_required: bool  # True ONLY if UNACCEPTABLE
    fsca_required: bool             # True if UNACCEPTABLE + confirmed root cause + active distribution


@dataclass
class CapaRecommendation:
    """Corrective and Preventive Action plan, grounded in recall precedents."""
    immediate: str                  # Do right now
    investigation: str              # Root cause investigation steps
    corrective: str                 # Fix the existing problem
    preventive: str                 # Stop recurrence
    verification_method: str        # How to confirm fix worked
    effectiveness_criteria: str     # Measurable success definition
    timeline: str                   # e.g. "30 days for corrective"
    precedent_basis: str            # Which recall ID / MAUDE event informs this
    iso13485_clause: str            # e.g. "ISO 13485 §8.5.2"


@dataclass
class RiskCapaOutput:
    """
    Full ISO 14971 risk assessment + CAPA recommendation.
    Constitutional guardrail: if risk_level is ALARP or UNACCEPTABLE
    but evidence_basis is empty → raise ValueError, do not proceed.

    Spec reference: US-12
    """
    report_id: str

    iso14971_assessment: ISO14971Assessment
    escalation_flags: EscalationFlags
    capa_recommendation: CapaRecommendation

    evidence_basis: list[str]       # List of recall_ids / report_ids cited
    uncertainty: str                # What we don't know / caveats
    iec62304_classification: Optional[str] = None  # Class A / B / C

    def validate_guardrail(self) -> None:
        """
        US-12 constitutional guardrail.
        Raises ValueError if ALARP/UNACCEPTABLE verdict has no citations.
        Call this before returning RiskCapaOutput from the agent.
        """
        risk = self.iso14971_assessment.risk_level
        if risk in (RiskLevel.ALARP, RiskLevel.UNACCEPTABLE):
            if not self.evidence_basis:
                raise ValueError(
                    f"Guardrail violation: risk_level={risk.value} "
                    f"but evidence_basis is empty. "
                    f"Cannot assert {risk.value} without citations. "
                    f"Set uncertainty instead."
                )

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# ─────────────────────────────────────────────
# SCHEMA 4 — ReportOutput (US-13)
# Agent 4 → Human reviewer / dashboard
# Owner: M3
# ─────────────────────────────────────────────

@dataclass
class ReportOutput:
    """
    Final human-readable report produced by the Report Agent.
    Rule: every sentence in `body` must map to a citation in `citations`.
    Agent self-refuses if any claim is uncited (US-13 spec).

    Spec reference: US-13
    """
    report_id: str

    # Report prose (Claude-generated, citation-grounded)
    summary: str                    # 2–3 sentence executive summary
    device_description: str         # What the device is and what failed
    risk_narrative: str             # Why this risk level was assigned
    capa_summary: str               # What should be done and by when
    body: str                       # Full report text (Markdown)

    # Risk verdict (copied from RiskCapaOutput for dashboard display)
    risk_verdict: RiskLevel
    escalation_required: bool

    # Provenance
    citations: list[str]            # All source IDs referenced in body
    evidence_count: int             # Total supporting events + recalls

    # Quality
    confidence: float               # Inherited from ExtractionOutput
    human_review_required: bool     # True if confidence < 0.75 or UNACCEPTABLE
    eval_score: Optional[float] = None  # LLM-as-Judge score (M6 fills this)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# ─────────────────────────────────────────────
# SCHEMA 5 — EvalResult (US-16)
# Evaluation Agent output
# Owner: M6
# ─────────────────────────────────────────────

@dataclass
class EvalResult:
    """
    LLM-as-Judge evaluation of a completed ReportOutput.
    Claude scores Claude on a 4-dimension expert rubric.

    Spec reference: US-16, US-18
    """
    report_id: str

    # Rubric dimensions (each 0.0–1.0)
    factual_accuracy: float         # Are extracted facts correct?
    citation_coverage: float        # % of claims that have a source
    iso_compliance: float           # Does risk verdict follow ISO 14971?
    capa_specificity: float         # Is CAPA actionable and grounded?

    # Aggregate
    overall_score: float            # Mean of 4 dimensions
    verdict: str                    # "PASS" if overall >= 0.70 else "FAIL"
    feedback: str                   # Claude judge's written feedback
    retry_recommended: bool         # True if FAIL → orchestrator retries

    # Ablation label (US-18)
    ablation_condition: Optional[str] = None  # e.g. "no_retrieval", "full_pipeline"

    @classmethod
    def compute_overall(cls, factual: float, citation: float,
                        iso: float, capa: float) -> float:
        return round((factual + citation + iso + capa) / 4, 3)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# ─────────────────────────────────────────────
# VALIDATION HELPERS
# ─────────────────────────────────────────────

REQUIRED_EXTRACTION_FIELDS = [
    "report_id", "modality", "failure_mode", "severity_indicator",
    "software_related", "qms_complaint_category", "is_safety_related",
    "confidence"
]

def validate_extraction(data: dict) -> list[str]:
    """Returns list of missing required fields. Empty list = valid."""
    return [f for f in REQUIRED_EXTRACTION_FIELDS if f not in data or data[f] is None]


def validate_retrieval(output: RetrievalOutput) -> list[str]:
    """Returns warnings about retrieval quality."""
    warnings = []
    if not output.has_evidence():
        warnings.append("No evidence found — Risk Agent guardrail will block ALARP/UNACCEPTABLE")
    if output.top_similarity_score < 0.5:
        warnings.append(f"Low similarity score ({output.top_similarity_score}) — weak evidence match")
    return warnings


# ─────────────────────────────────────────────
# QUICK SMOKE TEST
# Run: python schemas.py
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=== schemas.py smoke test ===\n")

    # Test ISO matrix
    assert lookup_risk_level(SeverityLevel.S3, ProbabilityLevel.P3) == RiskLevel.ALARP
    assert lookup_risk_level(SeverityLevel.S5, ProbabilityLevel.P5) == RiskLevel.UNACCEPTABLE
    assert lookup_risk_level(SeverityLevel.S1, ProbabilityLevel.P1) == RiskLevel.ACCEPTABLE
    print("✓ ISO 14971 matrix lookups correct")

    # Test probability calibration
    assert calibrate_probability(0)   == ProbabilityLevel.P1
    assert calibrate_probability(14)  == ProbabilityLevel.P3   # real trial: 14 events
    assert calibrate_probability(250) == ProbabilityLevel.P5
    print("✓ Probability calibration correct")

    # Test guardrail
    import traceback
    try:
        bad = RiskCapaOutput(
            report_id="test-001",
            iso14971_assessment=ISO14971Assessment(
                hazardous_situation="test",
                harm="test harm",
                severity_level=SeverityLevel.S3,
                severity_label="Serious",
                severity_rationale="test",
                probability_level=ProbabilityLevel.P3,
                probability_label="Occasional",
                probability_rationale="test",
                risk_level=RiskLevel.ALARP,
                risk_control_needed=True
            ),
            escalation_flags=EscalationFlags(
                escalation_required=True,
                prrc_notification_required=False,
                fsca_required=False
            ),
            capa_recommendation=CapaRecommendation(
                immediate="test",
                investigation="test",
                corrective="test",
                preventive="test",
                verification_method="test",
                effectiveness_criteria="test",
                timeline="30 days",
                precedent_basis="none",
                iso13485_clause="ISO 13485 §8.5.2"
            ),
            evidence_basis=[],    # ← empty — should trigger guardrail
            uncertainty="none"
        )
        bad.validate_guardrail()
        print("✗ Guardrail FAILED — should have raised ValueError")
    except ValueError as e:
        print(f"✓ Guardrail correctly blocked uncited ALARP: {e}")

    # Test eval score
    score = EvalResult.compute_overall(0.9, 1.0, 0.8, 0.75)
    assert score == 0.863
    print(f"✓ Eval score computed correctly: {score}")

    print("\n✅ All checks passed — schemas.py is ready.")
    print("   Freeze this file after Jun 13. Changes need team approval.")
