"""Section-driven report model.

A report is no longer a single hardcoded template. Each report *type* declares a
blueprint of ordered sections. Each section has a builder that reads from a
``ReportContext`` and may drive a sub-agent on demand *through the orchestrator*
(e.g. the trend section asks the orchestrator to run the trend agent only if that
section is actually part of the blueprint).

This keeps the work demand-driven: a vigilance escalation and a trend-monitoring
report no longer run the same agents in the same order.
"""

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from src.pipeline.schemas import (
    Complaint,
    ExtractedSignal,
    RetrievalEvidence,
    RiskAssessment,
    TrendSummary,
)


@dataclass
class ReportContext:
    """Mutable working set passed between the orchestrator and section builders.

    ``trend`` and ``report_questions`` start empty and are filled lazily only when
    a section in the active blueprint requires them.
    """

    complaint: Complaint
    extraction: ExtractedSignal
    retrieval: List[RetrievalEvidence]
    risk: RiskAssessment
    report_type: str
    events_by_code: Dict[str, List[dict]] = field(default_factory=dict)
    trend: Optional[TrendSummary] = None
    report_questions: Optional[List[str]] = None
    subqueries: Optional[List[str]] = None
    quality_intelligence: Optional[List["object"]] = None
    review_needed: bool = False
    review_reasons: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class SectionSpec:
    name: str
    title: str


# --- Section builders -------------------------------------------------------
# Each builder takes (context, orchestrator) and returns markdown body text.
# The orchestrator argument is what lets a section "drive other agents".

def _header(ctx: ReportContext, orch) -> str:
    c = ctx.complaint
    return "\n".join(
        [
            f"- Product Code: {c.product_code}",
            f"- Complaint ID: {c.complaint_id}",
            f"- Source MAUDE Report: {c.source_report_number}",
            f"- Event Type: {c.event_type}",
            f"- Routed Report Type: {ctx.report_type}",
        ]
    )


def _complaint_summary(ctx: ReportContext, orch) -> str:
    return ctx.complaint.narrative


def _extraction_details(ctx: ReportContext, orch) -> str:
    e = ctx.extraction
    return "\n".join(
        [
            f"- Category: {e.qms_complaint_category}",
            f"- Confidence: {e.confidence}",
            f"- Key Issues: {', '.join(e.key_issues) or 'None'}",
            f"- Safety Flags: {e.safety_flags}",
            f"- ISO 13485 Clauses: {', '.join(e.iso_13485_clauses) or 'None'}",
            f"- ISO 14971 Hazard Tags: {', '.join(e.iso_14971_hazard_tags) or 'None'}",
        ]
    )


def _regulatory_notification(ctx: ReportContext, orch) -> str:
    r = ctx.risk
    lines = [
        f"- Escalation Required: {r.escalation_required}",
        f"- PRRC Notification Required: {r.prrc_notification_required}",
        "- Action: Prepare regulatory vigilance notification per MDR/regulation timelines.",
    ]
    if ctx.complaint.event_type.lower() in {"death", "injury"}:
        lines.append(
            "- Reportability: Serious-incident criteria potentially met; confirm reporting-clock start date."
        )
    return "\n".join(lines)


def _risk_assessment(ctx: ReportContext, orch) -> str:
    r = ctx.risk
    return "\n".join(
        [
            f"- Severity: {r.severity_level}",
            f"- Probability: {r.probability_level}",
            f"- Risk Bucket: {r.risk_bucket}",
            f"- Escalation Required: {r.escalation_required}",
            f"- PRRC Notification Required: {r.prrc_notification_required}",
            f"- ISO 14971 Rationale: {r.iso_14971_rationale}",
        ]
    )


def _evidence_precedent(ctx: ReportContext, orch) -> str:
    evidence = orch.ensure_evidence(ctx)
    if not evidence:
        return "- No supporting FDA precedent above the relevance threshold; manual evidence review required."
    return "\n".join(
        f"- [{item.source_type}] {item.evidence_id} | score={item.score}"
        f"{(' | facet: ' + item.metadata['subquery']) if item.metadata.get('subquery') else ''}"
        f" | {item.snippet}"
        for item in evidence
    )


def _subquery_plan(ctx: ReportContext, orch) -> str:
    subqueries = orch.ensure_subqueries(ctx)
    if not subqueries:
        return "- No subqueries generated."
    return "\n".join(f"- {q}" for q in subqueries)


def _quality_intelligence(ctx: ReportContext, orch) -> str:
    results = orch.ensure_quality_intelligence(ctx)
    if not results:
        return "- No quality-intelligence findings available for this archive slice."
    lines: List[str] = []
    current_theme = None
    for result in results:
        theme = getattr(result, "theme", "general").replace("_", " ").title()
        if theme != current_theme:
            lines.append(f"**{theme}**")
            current_theme = theme
        lines.append(f"- {getattr(result, 'headline', str(result))}")
    return "\n".join(lines)


def _capa_plan(ctx: ReportContext, orch) -> str:
    return "\n".join(
        [
            f"- CAPA Recommendation: {ctx.risk.capa_recommendation}",
            f"- ISO 13485 Clauses: {', '.join(ctx.extraction.iso_13485_clauses) or 'None'}",
        ]
    )


def _trend_context(ctx: ReportContext, orch) -> str:
    t = orch.ensure_trend(ctx)
    return "\n".join(
        [
            f"- Total Events in Working Archive: {t.total_events}",
            f"- Software-like Problem Events: {t.software_problem_events}",
            f"- Previous Year Event Count: {t.previous_year_events}",
            f"- Latest Year Event Count: {t.latest_year_events}",
            f"- Trend Direction: {t.trend_direction}",
        ]
    )


def _monitoring_recommendation(ctx: ReportContext, orch) -> str:
    t = orch.ensure_trend(ctx)
    if t.trend_direction == "upward":
        rec = "Trend rising; schedule a focused review and consider a CAPA pre-assessment."
    elif t.trend_direction == "downward":
        rec = "Trend declining; continue routine monitoring and confirm prior actions held."
    else:
        rec = "Trend flat; maintain monthly management-review monitoring."
    return "\n".join([f"- Recommendation: {rec}", f"- Current Trend Direction: {t.trend_direction}"])


def _orchestrator_questions(ctx: ReportContext, orch) -> str:
    questions = orch.ensure_questions(ctx)
    if not questions:
        return "- No additional questions generated."
    return "\n".join(f"- {q}" for q in questions)


def _compliance_footer(ctx: ReportContext, orch) -> str:
    lines = [
        "Decision support only. Final disposition remains with the Quality Manager.",
        f"Review Needed: {ctx.review_needed}",
    ]
    if ctx.review_reasons:
        lines.extend(f"- {reason}" for reason in ctx.review_reasons)
    else:
        lines.append("- None")
    return "\n".join(lines)


def _executive_summary(ctx: ReportContext, orch) -> str:
    """PSUR-style executive summary with an explicit benefit-risk statement."""
    r = ctx.risk
    e = ctx.extraction
    verdict = (
        "negatively impacted"
        if r.risk_bucket == "UNACCEPTABLE"
        else "not negatively impacted"
    )
    return "\n".join(
        [
            f"- Device / Product Code: {ctx.complaint.product_code}",
            f"- Complaint Category: {e.qms_complaint_category}",
            f"- Risk Bucket: {r.risk_bucket} (severity {r.severity_level}, probability {r.probability_level})",
            f"- Benefit-Risk Statement: Based on the data reviewed, the benefit-risk ratio is **{verdict}**.",
        ]
    )


def _benefit_risk(ctx: ReportContext, orch) -> str:
    """Benefit-risk acceptability conclusion (PSUR section 8)."""
    r = ctx.risk
    if r.risk_bucket == "UNACCEPTABLE":
        conclusion = (
            "The benefit-risk determination is currently NOT acceptable; risks are not outweighed by "
            "benefits. Immediate risk-control and regulatory action is required."
        )
    elif r.risk_bucket == "ALARP":
        conclusion = (
            "Residual risk is As Low As Reasonably Practicable; benefits continue to outweigh risks "
            "provided the planned corrective actions are implemented and verified."
        )
    else:
        conclusion = (
            "The results demonstrate continuous acceptability of the benefit-risk determination; "
            "the risks associated with use of the device are still outweighed by its benefits."
        )
    return "\n".join(
        [
            f"- ISO 14971 Rationale: {r.iso_14971_rationale}",
            f"- Conclusion: {conclusion}",
        ]
    )


def _incident_reportability(ctx: ReportContext, orch) -> str:
    """MDR serious-incident assessment (the three vigilance criteria)."""
    r = ctx.risk
    event = ctx.complaint.event_type.lower()
    crit1 = True  # an event meeting the definition of an incident has occurred
    crit2 = True  # a causal relationship with the device is reasonably possible
    crit3 = event in {"injury", "death"} or r.risk_bucket == "UNACCEPTABLE"
    reportable = crit1 and crit2 and crit3
    return "\n".join(
        [
            "- Criterion 1 — An incident (malfunction/deterioration/use-error) has occurred: "
            f"{'Yes' if crit1 else 'No'}",
            "- Criterion 2 — Causal relationship between device and event is reasonably possible: "
            f"{'Yes' if crit2 else 'No'}",
            "- Criterion 3 — Event led/might lead to death or serious deterioration in health: "
            f"{'Yes' if crit3 else 'No'}",
            f"- Reportable Serious Incident: **{'YES' if reportable else 'NO'}** "
            f"(event type: {ctx.complaint.event_type}, risk bucket: {r.risk_bucket})",
            "- Reference: MDR Art. 2(64)/(65), Art. 87; MDCG 2023-3; MEDDEV 2.12/1 rev. 8.",
        ]
    )


def _template_unmapped(ctx: ReportContext, orch) -> str:
    """Placeholder for a template heading that maps to no known agent section."""
    ctx.review_needed = True
    return "- No agent is mapped to this template section; manual completion required."


SECTION_BUILDERS: Dict[str, Callable[[ReportContext, object], str]] = {
    "header": _header,
    "complaint_summary": _complaint_summary,
    "executive_summary": _executive_summary,
    "extraction_details": _extraction_details,
    "regulatory_notification": _regulatory_notification,
    "incident_reportability": _incident_reportability,
    "risk_assessment": _risk_assessment,
    "benefit_risk": _benefit_risk,
    "subquery_plan": _subquery_plan,
    "evidence_precedent": _evidence_precedent,
    "quality_intelligence": _quality_intelligence,
    "capa_plan": _capa_plan,
    "trend_context": _trend_context,
    "monitoring_recommendation": _monitoring_recommendation,
    "orchestrator_questions": _orchestrator_questions,
    "compliance_footer": _compliance_footer,
    "unmapped": _template_unmapped,
}


# --- Blueprints per report type --------------------------------------------
# Different report types => different sections, ordering, and driven agents.

REPORT_BLUEPRINTS: Dict[str, List[SectionSpec]] = {
    # --- Active taxonomy (OpenRegulatory-aligned) --------------------------
    "PSUR": [
        SectionSpec("header", "Report Metadata"),
        SectionSpec("executive_summary", "Executive Summary"),
        SectionSpec("extraction_details", "Device and Complaint Information"),
        SectionSpec("trend_context", "Trend Identification and Reporting"),
        SectionSpec("evidence_precedent", "Information about Similar Devices (FDA MAUDE)"),
        SectionSpec("quality_intelligence", "Quality Intelligence"),
        SectionSpec("risk_assessment", "Risk Assessment"),
        SectionSpec("benefit_risk", "Risk Management and Benefit-Risk Assessment"),
        SectionSpec("monitoring_recommendation", "Required Updates to PMS Plan"),
        SectionSpec("compliance_footer", "Compliance Note"),
    ],
    "INCIDENT_ASSESSMENT": [
        SectionSpec("header", "Report Metadata"),
        SectionSpec("complaint_summary", "Event Description"),
        SectionSpec("incident_reportability", "Incident Assessment (MDR Serious-Incident Criteria)"),
        SectionSpec("regulatory_notification", "Regulatory Notification and FSCA"),
        SectionSpec("risk_assessment", "Risk Assessment"),
        SectionSpec("evidence_precedent", "Similar Incidents and Precedent"),
        SectionSpec("orchestrator_questions", "Decision Questions"),
        SectionSpec("compliance_footer", "Compliance Note"),
    ],
    "CAPA": [
        SectionSpec("header", "Report Metadata"),
        SectionSpec("complaint_summary", "Problem Description"),
        SectionSpec("extraction_details", "Classification"),
        SectionSpec("risk_assessment", "Risk Assessment"),
        SectionSpec("subquery_plan", "Investigation Subqueries"),
        SectionSpec("evidence_precedent", "Evidence and Precedent"),
        SectionSpec("quality_intelligence", "Root-Cause and Effectiveness Intelligence"),
        SectionSpec("trend_context", "Recurrence and Trend Context"),
        SectionSpec("capa_plan", "CAPA Plan"),
        SectionSpec("orchestrator_questions", "Investigation Questions"),
        SectionSpec("compliance_footer", "Compliance Note"),
    ],
    # --- Legacy taxonomy (kept for backward compatibility) -----------------
    "VIGILANCE_ESCALATION": [
        SectionSpec("header", "Report Metadata"),
        SectionSpec("complaint_summary", "Complaint Narrative"),
        SectionSpec("regulatory_notification", "Regulatory Notification"),
        SectionSpec("risk_assessment", "Risk Assessment"),
        SectionSpec("subquery_plan", "Investigation Subqueries"),
        SectionSpec("evidence_precedent", "Evidence and Precedent"),
        SectionSpec("quality_intelligence", "Quality Intelligence"),
        SectionSpec("extraction_details", "Extraction Summary"),
        SectionSpec("capa_plan", "Immediate CAPA Plan"),
        SectionSpec("trend_context", "Trend Context"),
        SectionSpec("orchestrator_questions", "Decision Questions"),
        SectionSpec("compliance_footer", "Compliance Note"),
    ],
    "CAPA_INVESTIGATION": [
        SectionSpec("header", "Report Metadata"),
        SectionSpec("complaint_summary", "Complaint Narrative"),
        SectionSpec("extraction_details", "Extraction Summary"),
        SectionSpec("risk_assessment", "Risk Assessment"),
        SectionSpec("subquery_plan", "Investigation Subqueries"),
        SectionSpec("evidence_precedent", "Evidence and Precedent"),
        SectionSpec("quality_intelligence", "Quality Intelligence"),
        SectionSpec("trend_context", "Trend Context"),
        SectionSpec("capa_plan", "CAPA Plan"),
        SectionSpec("orchestrator_questions", "Investigation Questions"),
        SectionSpec("compliance_footer", "Compliance Note"),
    ],
    "TREND_MONITORING": [
        SectionSpec("header", "Report Metadata"),
        SectionSpec("complaint_summary", "Complaint Narrative"),
        SectionSpec("extraction_details", "Extraction Summary"),
        SectionSpec("trend_context", "Trend Context"),
        SectionSpec("subquery_plan", "Monitoring Subqueries"),
        SectionSpec("evidence_precedent", "Evidence and Precedent"),
        SectionSpec("quality_intelligence", "Quality Intelligence"),
        SectionSpec("risk_assessment", "Risk Assessment"),
        SectionSpec("monitoring_recommendation", "Monitoring Recommendation"),
        SectionSpec("orchestrator_questions", "Monitoring Questions"),
        SectionSpec("compliance_footer", "Compliance Note"),
    ],
}


def blueprint_for(report_type: str) -> List[SectionSpec]:
    return REPORT_BLUEPRINTS.get(report_type, REPORT_BLUEPRINTS["PSUR"])


# Short codes used to keep report IDs unique when several reports are produced
# for one complaint.
REPORT_TYPE_ABBR: Dict[str, str] = {
    "PSUR": "PSUR",
    "INCIDENT_ASSESSMENT": "INC",
    "CAPA": "CAPA",
    "VIGILANCE_ESCALATION": "VIG",
    "CAPA_INVESTIGATION": "CAPA",
    "TREND_MONITORING": "TRND",
}


def abbr_for(report_type: str) -> str:
    return REPORT_TYPE_ABBR.get(report_type, "RPT")


# --- Template-driven blueprints --------------------------------------------
# Maps a skeleton heading (from an uploaded .docx) to the section builder that
# should fill it. Keywords are matched case-insensitively against the heading.
SECTION_KEYWORDS: Dict[str, List[str]] = {
    "header": ["metadata", "header", "identification", "report detail"],
    "complaint_summary": ["complaint", "narrative", "description", "event description", "problem statement"],
    "executive_summary": ["executive summary", "summary of psur", "purpose and scope"],
    "extraction_details": ["extraction", "classification", "categor", "device information", "device and complaint"],
    "regulatory_notification": ["regulatory", "notification", "vigilance", "reportab", "mdr", "fsca", "field safety"],
    "incident_reportability": ["incident assessment", "serious incident", "reportability", "incident criteria"],
    "risk_assessment": ["risk", "hazard", "severity", "assessment"],
    "benefit_risk": ["benefit-risk", "benefit risk", "risk management and benefit", "acceptability"],
    "subquery_plan": ["subquer", "search scope", "investigation scope", "query"],
    "evidence_precedent": ["evidence", "precedent", "similar", "history of", "prior event"],
    "quality_intelligence": ["quality intelligence", "analytics", "pattern", "insight", "intelligence"],
    "capa_plan": ["capa", "corrective", "preventive", "action plan"],
    "trend_context": ["trend", "history", "statistic"],
    "monitoring_recommendation": ["monitoring", "recommendation", "surveillance", "pms plan", "updates to pms"],
    "orchestrator_questions": ["question", "decision", "follow-up", "follow up"],
    "compliance_footer": ["compliance", "disposition", "signature", "sign-off", "approval", "conclusion"],
}


def map_heading_to_section(heading: str) -> str:
    """Return the section-builder name best matching a template heading."""
    text = heading.strip().lower()
    for name, keywords in SECTION_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return name
    return "unmapped"


def sections_from_headings(headings: List[str]) -> List[SectionSpec]:
    """Convert ordered template headings into an ordered section blueprint.

    The skeleton's structure becomes the blueprint: each heading keeps its
    original title text but is bound to the agent section that fills it.
    """
    specs: List[SectionSpec] = []
    for heading in headings:
        clean = heading.strip()
        if not clean:
            continue
        specs.append(SectionSpec(map_heading_to_section(clean), clean))
    return specs
