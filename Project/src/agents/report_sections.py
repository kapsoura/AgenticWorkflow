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
    cluster: Optional[dict] = None
    # LLM-generated narrative prose per narrative section (filled lazily by
    # ``OrchestrationAgent.ensure_section_narratives``). Keyed by section name.
    section_narratives: Optional[Dict[str, str]] = None
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


def _na(value) -> str:
    if value is None:
        return "Not available"
    if isinstance(value, str):
        text = value.strip()
        if text.lower() in {"", "not_available", "not available", "unknown", "n/a"}:
            return "Not available"
        return text
    if isinstance(value, list):
        values = [str(v).strip() for v in value if str(v).strip()]
        return ", ".join(values) if values else "Not available"
    return str(value)


def _extraction_details(ctx: ReportContext, orch) -> str:
    e = ctx.extraction
    unavailable = str(e.qms_complaint_category).strip().upper() == "NOT_AVAILABLE"
    return "\n".join(
        [
            f"- Category: {_na(e.qms_complaint_category)}",
            f"- Confidence: {'Not available' if unavailable else _na(e.confidence)}",
            f"- Key Issues: {_na(e.key_issues)}",
            f"- Safety Flags: {'Not available' if unavailable else _na(e.safety_flags)}",
            f"- ISO 13485 Clauses: {_na(e.iso_13485_clauses)}",
            f"- ISO 14971 Hazard Tags: {_na(e.iso_14971_hazard_tags)}",
        ]
    )


def _regulatory_notification(ctx: ReportContext, orch) -> str:
    r = ctx.risk
    narrative = orch.ensure_section_narratives(ctx).get("regulatory_notification", "Not available")
    return "\n".join(
        [
            f"- Escalation Required: {r.escalation_required}",
            f"- PRRC Notification Required: {r.prrc_notification_required}",
            f"- Notification Narrative: {narrative}",
        ]
    )


def _risk_assessment(ctx: ReportContext, orch) -> str:
    r = ctx.risk
    lines = [
        f"- Severity: {r.severity_level}",
        f"- Probability: {r.probability_level}",
        f"- Risk Bucket: {r.risk_bucket}",
    ]
    if r.hazardous_situation:
        lines.append(f"- Hazardous Situation: {r.hazardous_situation}")
    if r.harm:
        lines.append(f"- Harm: {r.harm}")
    lines.append(f"- Escalation Required: {r.escalation_required}")
    lines.append(f"- PRRC Notification Required: {r.prrc_notification_required}")
    if r.fsca_required:
        lines.append(f"- FSCA Required: {r.fsca_required}")
    lines.append(f"- ISO 14971 Rationale: {r.iso_14971_rationale}")
    if r.uncertainty:
        lines.append(f"- Uncertainty: {r.uncertainty}")
    if r.evidence_basis:
        lines.append("- Evidence Basis:")
        for ev in r.evidence_basis[:6]:
            lines.append(
                f"  - [{ev.get('source')}] {ev.get('id')} — {ev.get('relevance', '')}"
            )
    return "\n".join(lines)


def _evidence_precedent(ctx: ReportContext, orch) -> str:
    evidence = orch.ensure_evidence(ctx)
    if not evidence:
        return "Not available"
    return "\n".join(
        f"- [{item.source_type}] {item.evidence_id} | score={item.score}"
        f"{(' | facet: ' + item.metadata['subquery']) if item.metadata.get('subquery') else ''}"
        f" | {item.snippet}"
        for item in evidence
    )


def _subquery_plan(ctx: ReportContext, orch) -> str:
    subqueries = orch.ensure_subqueries(ctx)
    if not subqueries:
        return "Not available"
    return "\n".join(f"- {q}" for q in subqueries)


def _quality_intelligence(ctx: ReportContext, orch) -> str:
    results = orch.ensure_quality_intelligence(ctx)
    if not results:
        return "Not available"
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
    r = ctx.risk
    lines: List[str] = []
    staged = [
        ("Immediate Containment", r.capa_immediate),
        ("Root-Cause Investigation", r.capa_investigation),
        ("Corrective Action (ISO 13485 §8.5.2)", r.capa_corrective),
        ("Preventive Action (ISO 13485 §8.5.3)", r.capa_preventive),
        ("Verification", r.capa_verification),
        ("Effectiveness Criteria", r.capa_effectiveness),
    ]
    populated = [(label, value) for label, value in staged if value]
    if populated:
        lines.extend(f"- {label}: {value}" for label, value in populated)
        if r.capa_precedent:
            lines.append(f"- CAPA Precedent: {r.capa_precedent}")
    else:
        lines.append(f"- CAPA Recommendation: {r.capa_recommendation}")
    lines.append(f"- ISO 13485 Clauses: {', '.join(ctx.extraction.iso_13485_clauses) or 'None'}")
    return "\n".join(lines)


def _trend_context(ctx: ReportContext, orch) -> str:
    t = orch.ensure_trend(ctx)
    unavailable = str(t.trend_direction).strip().lower() == "not_available"
    lines = [
        f"- Total Events in Working Archive: {'Not available' if unavailable else _na(t.total_events)}",
        f"- Software-like Problem Events: {'Not available' if unavailable else _na(t.software_problem_events)}",
        f"- Previous Year Event Count: {'Not available' if unavailable else _na(t.previous_year_events)}",
        f"- Latest Year Event Count: {'Not available' if unavailable else _na(t.latest_year_events)}",
        f"- Trend Direction: {'Not available' if unavailable else _na(t.trend_direction)}",
    ]
    rationale = getattr(t, "trend_rationale", "")
    if not unavailable and rationale:
        lines.append(f"- Trend Rationale: {rationale}")
    return "\n".join(lines)


def _monitoring_recommendation(ctx: ReportContext, orch) -> str:
    t = orch.ensure_trend(ctx)
    direction = str(t.trend_direction).strip().lower()
    display_direction = "Not available" if direction == "not_available" else _na(t.trend_direction)
    narrative = orch.ensure_section_narratives(ctx).get("monitoring_recommendation", "Not available")
    return "\n".join(
        [
            f"- Current Trend Direction: {display_direction}",
            f"- Recommendation: {narrative}",
        ]
    )


def _orchestrator_questions(ctx: ReportContext, orch) -> str:
    questions = orch.ensure_questions(ctx)
    if not questions:
        return "Not available"
    return "\n".join(f"- {q}" for q in questions)


def _cluster_assignment(ctx: ReportContext, orch) -> str:
    """Assign this complaint to a pre-built HDBSCAN reference cluster of prior FDA events."""
    data = orch.ensure_cluster(ctx)
    if not data:
        return "Not available"
    lines = [
        f"- Assigned Cluster: {_na(data.get('cluster_label'))} (id {_na(data.get('cluster_id'))})",
        f"- Cluster Size (prior similar events): {_na(data.get('cluster_size'))}",
        f"- 30-Day Cluster Growth Rate: {_na(data.get('growth_rate_30d'))}%",
        f"- Cluster Trend Flag: {_na(data.get('trend_flag'))}",
    ]
    similar = data.get("similar_events") or []
    if similar:
        lines.append("- Nearest Prior Events:")
        for ev in similar[:5]:
            score = ev.get("similarity_score")
            score_s = f"{score:.2f}" if isinstance(score, (int, float)) else "n/a"
            lines.append(
                f"  - {_na(ev.get('report_number'))} (similarity {score_s}): {_na(ev.get('narrative_snippet'))}"
            )
    lines.append(
        "- Note: cluster membership is similarity-based grouping of prior FDA events; "
        "it supports pattern context and does not imply causation."
    )
    return "\n".join(lines)


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
    """PSUR-style executive summary; the benefit-risk statement is LLM-written.

    The risk bucket (the auditable ISO 14971 verdict) is rendered deterministically;
    the interpretive benefit-risk statement is generated by the section-narrative
    agent, grounded in that verdict and cited FDA evidence.
    """
    r = ctx.risk
    e = ctx.extraction
    narrative = orch.ensure_section_narratives(ctx).get("executive_summary", "Not available")
    return "\n".join(
        [
            f"- Device / Product Code: {ctx.complaint.product_code}",
            f"- Complaint Category: {e.qms_complaint_category}",
            f"- Risk Bucket: {r.risk_bucket} (severity {r.severity_level}, probability {r.probability_level})",
            f"- Benefit-Risk Statement: {narrative}",
        ]
    )


def _benefit_risk(ctx: ReportContext, orch) -> str:
    """Benefit-risk acceptability conclusion (PSUR section 8).

    The risk bucket is the deterministic ISO 14971 verdict; the acceptability
    conclusion prose is LLM-written and grounded in that verdict plus cited
    evidence (the model does not change the bucket).
    """
    r = ctx.risk
    narrative = orch.ensure_section_narratives(ctx).get("benefit_risk", "Not available")
    return "\n".join(
        [
            f"- Risk Bucket: {r.risk_bucket}",
            f"- ISO 14971 Rationale: {r.iso_14971_rationale}",
            f"- Conclusion: {narrative}",
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
    narrative = orch.ensure_section_narratives(ctx).get("incident_reportability", "Not available")
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
            f"- Assessment: {narrative}",
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
    "cluster_assignment": _cluster_assignment,
    "monitoring_recommendation": _monitoring_recommendation,
    "orchestrator_questions": _orchestrator_questions,
    "compliance_footer": _compliance_footer,
    "unmapped": _template_unmapped,
}


# --- Narrative sections (LLM-written prose, deterministic verdicts kept) ----
# These sections render their auditable regulatory verdict deterministically and
# delegate the interpretive prose to the section-narrative agent. The brief tells
# the agent what each section's narrative must cover; it must NOT alter the verdict.
NARRATIVE_SECTIONS: Dict[str, str] = {
    "executive_summary": (
        "One- to two-sentence benefit-risk statement for the device, interpreting the given "
        "risk bucket against the cited FDA precedent. Do not restate the numeric severity/"
        "probability and do not change the bucket."
    ),
    "benefit_risk": (
        "ISO 14971 benefit-risk acceptability conclusion: state whether residual risk is "
        "acceptable given the deterministic risk bucket, citing the FDA evidence that supports "
        "the conclusion. Do not change the bucket."
    ),
    "incident_reportability": (
        "Justify the MDR serious-incident determination in 1-2 sentences, grounded in the event "
        "type, the given risk bucket, and cited precedent. Do not change the YES/NO verdict."
    ),
    "regulatory_notification": (
        "Describe the regulatory vigilance/notification actions warranted, grounded in the given "
        "escalation/PRRC flags and event type, citing precedent where relevant."
    ),
    "monitoring_recommendation": (
        "Recommend the post-market monitoring action warranted by the given trend direction and "
        "event counts, citing the trend figures or FDA precedent."
    ),
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
        SectionSpec("cluster_assignment", "Similar-Signal Cluster Assignment"),
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
        SectionSpec("cluster_assignment", "Similar-Signal Cluster Assignment"),
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
        SectionSpec("cluster_assignment", "Recurrence Cluster Assignment"),
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
    "cluster_assignment": ["cluster", "grouping", "nearest", "signal cluster"],
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
