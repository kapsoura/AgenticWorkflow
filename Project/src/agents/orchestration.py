from dataclasses import dataclass, field
from typing import List, Tuple

from src.agents.archive_trend import ArchiveTrendAnalyzer
from src.agents.extraction import ExtractionAgent
from src.agents.quality_tools import QualityAnalyticsToolbox, ToolResult
from src.agents.report_generation import ReportGenerationAgent
from src.agents.report_sections import ReportContext, blueprint_for, SECTION_BUILDERS
from src.agents.retrieval import RetrievalAgent
from src.agents.risk_analysis import RiskAnalysisAgent
from src.pipeline.schemas import Complaint, ExtractedSignal, RetrievalEvidence, RiskAssessment, TrendSummary

# Report type -> quality-intelligence themes the toolbox should run for that report.
REPORT_THEME_MAP = {
    # Active taxonomy
    "PSUR": ["pattern_recognition", "predictive_capability"],
    "INCIDENT_ASSESSMENT": ["predictive_capability", "pattern_recognition"],
    "CAPA": ["root_cause_effectiveness", "pattern_recognition", "resource_allocation"],
    # Legacy taxonomy
    "VIGILANCE_ESCALATION": ["predictive_capability", "pattern_recognition"],
    "CAPA_INVESTIGATION": ["root_cause_effectiveness", "pattern_recognition", "resource_allocation"],
    "TREND_MONITORING": ["pattern_recognition", "predictive_capability"],
}


@dataclass
class OrchestrationAgent:
    """Drives sub-agents on demand to assemble the sections a report type needs."""

    extraction_agent: ExtractionAgent
    retrieval_agent: RetrievalAgent
    risk_agent: RiskAnalysisAgent
    report_agent: ReportGenerationAgent
    trend_analyzer: ArchiveTrendAnalyzer
    toolbox: QualityAnalyticsToolbox = field(default_factory=QualityAnalyticsToolbox)

    # --- Report-set decision (drives which reports are generated) ----------
    def decide_report_types(
        self,
        complaint: Complaint,
        extraction: ExtractedSignal,
        risk: RiskAssessment,
        evidence: "List[RetrievalEvidence] | None" = None,
        tracer=None,
    ) -> List[str]:
        """Decide which reports a complaint warrants, in priority order.

        This is the agent's routing decision: a single complaint may require
        several deliverables. PSUR is the always-on post-market safety summary;
        a serious/escalated event additionally needs an Incident Assessment; an
        actionable quality issue additionally needs a CAPA. The returned order is
        most-urgent-first so the first element is the primary report.
        """
        event = complaint.event_type.lower()
        evidence = evidence or []
        recall_precedent = any(getattr(e, "source_type", "") == "FDA_RECALL" for e in evidence)

        selected: List[str] = []
        # Incident Assessment: MDR serious-incident path.
        if event in {"injury", "death"} or risk.escalation_required or risk.risk_bucket == "UNACCEPTABLE":
            selected.append("INCIDENT_ASSESSMENT")
        # CAPA: an actionable corrective/preventive action is warranted.
        if risk.risk_bucket in {"ALARP", "UNACCEPTABLE"} or risk.escalation_required or recall_precedent:
            selected.append("CAPA")
        # PSUR: always produced as the aggregate post-market safety summary.
        selected.append("PSUR")

        # De-duplicate while preserving priority order.
        seen = set()
        ordered = [t for t in selected if not (t in seen or seen.add(t))]

        if tracer is not None:
            tracer.log(
                agent="orchestrator",
                event="reports_decided",
                gate_result="pass",
                metadata={
                    "report_types": ordered,
                    "event_type": complaint.event_type,
                    "risk_bucket": risk.risk_bucket,
                    "recall_precedent": recall_precedent,
                },
            )
        return ordered

    # --- Lazy agent drivers (called by section builders) -------------------
    def ensure_trend(self, ctx: ReportContext) -> TrendSummary:
        if ctx.trend is None:
            ctx.trend = self.trend_analyzer.summarize(
                product_code=ctx.complaint.product_code,
                events=ctx.events_by_code.get(ctx.complaint.product_code, []),
            )
        return ctx.trend

    def ensure_subqueries(self, ctx: ReportContext) -> List[str]:
        if ctx.subqueries is None:
            ctx.subqueries = self.plan_subqueries(ctx.complaint, ctx.extraction, ctx.risk)
        return ctx.subqueries

    def ensure_evidence(self, ctx: ReportContext) -> List[RetrievalEvidence]:
        if ctx.retrieval is None:
            ctx.retrieval = self.retrieval_agent.retrieve(
                extracted=ctx.extraction,
                complaint_product_code=ctx.complaint.product_code,
                events_by_code=ctx.events_by_code,
                recalls=[],
                subqueries=self.ensure_subqueries(ctx),
            )
        return ctx.retrieval

    def ensure_quality_intelligence(self, ctx: ReportContext) -> List[ToolResult]:
        if ctx.quality_intelligence is None:
            events = ctx.events_by_code.get(ctx.complaint.product_code, [])
            themes = REPORT_THEME_MAP.get(ctx.report_type)
            ctx.quality_intelligence = self.toolbox.run_for_themes(
                events=events,
                key_issues=ctx.extraction.key_issues,
                retrieved_count=len(self.ensure_evidence(ctx)),
                themes=themes,
            )
        return ctx.quality_intelligence

    def ensure_questions(self, ctx: ReportContext) -> List[str]:
        if ctx.report_questions is None:
            ctx.report_questions = self.select_report_questions(
                ctx.complaint, ctx.risk, report_type=ctx.report_type
            )
        return ctx.report_questions

    # --- Subquery planning (closes the research-pattern gap) ---------------
    def plan_subqueries(
        self, complaint: Complaint, extraction: ExtractedSignal, risk: "RiskAssessment | None" = None
    ) -> List[str]:
        """Decompose a complaint into focused retrieval subqueries.

        Deterministic by default: one facet per key issue / hazard tag, plus
        report-type-specific facets when a risk assessment is available. Optionally
        enriched by an LLM when a key is present (mirrors the extraction agent's
        offline-first pattern).
        """
        facets: List[str] = []
        for issue in extraction.key_issues:
            if issue:
                facets.append(f"{complaint.product_code} {issue} failure precedent")
        for tag in extraction.iso_14971_hazard_tags:
            if tag:
                facets.append(f"{tag} hazard similar events")

        report_type = risk.report_type if risk is not None else None
        if report_type in {"INCIDENT_ASSESSMENT", "VIGILANCE_ESCALATION"}:
            facets.append(f"{complaint.product_code} serious injury or death precedent")
            facets.append(f"{complaint.product_code} recall related to {extraction.qms_complaint_category}")
        elif report_type in {"CAPA", "CAPA_INVESTIGATION"}:
            facets.append(f"{complaint.product_code} recurring root cause {extraction.qms_complaint_category}")
            facets.append(f"{complaint.product_code} corrective action effectiveness")
        elif report_type in {"PSUR", "TREND_MONITORING"}:
            facets.append(f"{complaint.product_code} trend over time {extraction.qms_complaint_category}")

        enriched = self._llm_subqueries(complaint, extraction)
        for q in enriched:
            if q and q not in facets:
                facets.append(q)

        # De-duplicate, preserve order, cap to keep retrieval bounded.
        seen = set()
        ordered: List[str] = []
        for q in facets:
            key = q.lower()
            if key not in seen:
                seen.add(key)
                ordered.append(q)
        return ordered[:6] or [f"{complaint.product_code} {extraction.qms_complaint_category}"]

    def _llm_subqueries(self, complaint: Complaint, extraction: ExtractedSignal) -> List[str]:
        llm = getattr(self.extraction_agent, "llm", None)
        if llm is None or not getattr(llm, "enabled", False):
            return []
        result = llm.complete_json(
            system_prompt=(
                "You decompose a medical device complaint into 2-4 focused search subqueries "
                "for retrieving similar FDA MAUDE events and recalls. Return JSON "
                '{"subqueries": ["...", "..."]}.'
            ),
            user_prompt=(
                f"Product code: {complaint.product_code}\n"
                f"Category: {extraction.qms_complaint_category}\n"
                f"Key issues: {', '.join(extraction.key_issues)}\n"
                f"Narrative: {complaint.narrative[:600]}"
            ),
            fallback={"subqueries": []},
        )
        subqueries = result.get("subqueries", [])
        return [str(q) for q in subqueries if isinstance(q, (str,)) and q.strip()][:4]

    # --- Section-driven assembly -------------------------------------------
    def build_sections(self, ctx: ReportContext, tracer=None, section_specs=None) -> List[Tuple[str, str]]:
        """Walk the active blueprint and build each section.

        ``section_specs`` overrides the report-type blueprint (used when an uploaded
        template supplies the structure). The report agent calls this; each builder
        may drive a sub-agent through the ``ensure_*`` helpers above, so the work
        performed is decided by the report's own structure rather than a fixed
        linear pipeline.
        """
        specs = section_specs or blueprint_for(ctx.report_type)
        sections: List[Tuple[str, str]] = []
        for spec in specs:
            builder = SECTION_BUILDERS[spec.name]
            body = builder(ctx, self)
            sections.append((spec.title, body))
            if tracer is not None:
                tracer.log(
                    agent="orchestrator",
                    event="section_built",
                    gate_result="pass",
                    metadata={"section": spec.name, "title": spec.title, "report_type": ctx.report_type},
                )
        return sections

    def select_report_questions(
        self, complaint: Complaint, risk: RiskAssessment, report_type: "str | None" = None
    ) -> List[str]:
        report_type = report_type or risk.report_type
        questions: List[str] = []
        if report_type in {"INCIDENT_ASSESSMENT", "VIGILANCE_ESCALATION"}:
            questions.extend(
                [
                    "Does this complaint meet the MDR serious-incident criteria for mandatory reporting?",
                    "What immediate containment actions are mandatory within 24h?",
                ]
            )
        elif report_type in {"CAPA", "CAPA_INVESTIGATION"}:
            questions.extend(
                [
                    "Which root-cause branch should be tested first?",
                    "What verification evidence is needed before release decision?",
                ]
            )
        else:
            questions.extend(
                [
                    "Is recurrence trending above baseline for this product code?",
                    "Should this complaint be monitored in monthly management review?",
                ]
            )

        if complaint.event_type.lower() in {"injury", "death"}:
            questions.append("Has PRRC and clinical safety been notified with trace ID?")
        return questions
