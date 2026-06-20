from dataclasses import dataclass, field
from typing import List, Tuple

from src.tools.agent_tools import quality_tool_specs, retrieval_tool_specs, trend_tool_specs
from src.agents.archive_trend import ArchiveTrendAnalyzer
from src.agents.extraction import ExtractionAgent
from src.tools.quality_tools import QualityAnalyticsToolbox, ToolResult
from src.agents.report_generation import ReportGenerationAgent
from src.agents.report_sections import (
    NARRATIVE_SECTIONS,
    ReportContext,
    blueprint_for,
    SECTION_BUILDERS,
)
from src.agents.retrieval import RetrievalAgent
from src.agents.risk_analysis import RiskAnalysisAgent
from src.pipeline.schemas import Complaint, ExtractedSignal, RetrievalEvidence, RiskAssessment, TrendSummary
from src.utils.prompt_store import render_prompt
from src.tools.tool_loop import AnthropicToolClient

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
    cluster_agent: "object | None" = None
    # Real Anthropic tool-use client over the claude CLI; when disabled (no
    # CLAUDE_CLI_PATH) every tool-driven path below falls back to the
    # deterministic behaviour.
    tool_client: AnthropicToolClient = field(default_factory=AnthropicToolClient)
    # Search queries the model issued during the last tool-driven evidence gather
    # (surfaced as "subqueries" in the trace).
    last_evidence_queries: List[str] = field(default_factory=list)

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

    def ensure_cluster(self, ctx: ReportContext) -> dict:
        """Assign the complaint to a pre-built HDBSCAN cluster (lazy, cached on ctx)."""
        if ctx.cluster is None:
            if self.cluster_agent is None:
                ctx.cluster = {}
            else:
                ctx.cluster = self.cluster_agent.assign(ctx.complaint.narrative) or {}
        return ctx.cluster

    def ensure_subqueries(self, ctx: ReportContext) -> List[str]:
        if ctx.subqueries is None:
            if str(ctx.extraction.qms_complaint_category).strip().upper() == "NOT_AVAILABLE" or ctx.extraction.confidence <= 0.0:
                ctx.subqueries = []
                return ctx.subqueries
            ctx.subqueries = self.plan_subqueries(ctx.complaint, ctx.extraction, ctx.risk)
        return ctx.subqueries

    def ensure_evidence(self, ctx: ReportContext) -> List[RetrievalEvidence]:
        if ctx.retrieval is None:
            # Preferred path: let the model search the archive on demand via tools.
            if self.tool_client.enabled:
                evidence = self.gather_evidence(
                    complaint=ctx.complaint,
                    extraction=ctx.extraction,
                    events_by_code=ctx.events_by_code,
                    recalls=[],
                    report_type=ctx.report_type,
                )
                if evidence:
                    ctx.retrieval = evidence
                    return ctx.retrieval
            # Deterministic fallback: single fixed retrieve() over planned subqueries.
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
            if str(ctx.extraction.qms_complaint_category).strip().upper() == "NOT_AVAILABLE" or ctx.extraction.confidence <= 0.0:
                ctx.quality_intelligence = []
                return ctx.quality_intelligence
            events = ctx.events_by_code.get(ctx.complaint.product_code, [])
            retrieved_count = len(self.ensure_evidence(ctx))

            # Preferred path: the model chooses which analyses to run as tools.
            if self.tool_client.enabled:
                results = self._quality_intelligence_via_tools(ctx, events, retrieved_count)
                if results:
                    ctx.quality_intelligence = results
                    return ctx.quality_intelligence

            # Deterministic fallback: run the theme-mapped analyses offline.
            themes = REPORT_THEME_MAP.get(ctx.report_type)
            ctx.quality_intelligence = self.toolbox.run_for_themes(
                events=events,
                key_issues=ctx.extraction.key_issues,
                retrieved_count=retrieved_count,
                themes=themes,
            )
        return ctx.quality_intelligence

    # --- Tool-driven helpers (real Anthropic tool use) ---------------------
    def _quality_intelligence_via_tools(
        self, ctx: ReportContext, events: List[dict], retrieved_count: int
    ) -> List[ToolResult]:
        """Let the model pick and run the analytics tools relevant to this report.

        Returns the ``ToolResult``s the model actually invoked (empty on failure,
        so the caller falls back to the deterministic theme map).
        """
        specs, captured = quality_tool_specs(
            self.toolbox, events, ctx.extraction.key_issues, retrieved_count
        )
        recommended = REPORT_THEME_MAP.get(ctx.report_type) or []
        try:
            self.tool_client.run(
                system_prompt=render_prompt("quality_intel_system"),
                user_prompt=render_prompt(
                    "quality_intel_user",
                    product_code=ctx.complaint.product_code,
                    report_type=ctx.report_type,
                    category=ctx.extraction.qms_complaint_category,
                    key_issues=", ".join(ctx.extraction.key_issues) or "None",
                    recommended_themes=", ".join(recommended) if recommended else "any",
                    retrieved_count=retrieved_count,
                    total_events=len(events),
                ),
                tools=specs,
                max_tokens=900,
            )
        except Exception:  # noqa: BLE001 — fall back to the deterministic path
            return []
        return captured

    def gather_evidence(
        self,
        complaint: Complaint,
        extraction: ExtractedSignal,
        events_by_code,
        recalls: "List[dict] | None" = None,
        vector_collection=None,
        report_type: str = "signal review",
        top_k: int = 5,
    ) -> List[RetrievalEvidence]:
        """Model-driven evidence gathering: the model searches MAUDE/recalls via tools.

        Returns the deduped, score-sorted evidence the model surfaced (empty when
        the tool client is disabled or errors, so callers use the fixed retrieve()).
        Records the issued search queries on ``last_evidence_queries`` for tracing.
        """
        self.last_evidence_queries = []
        if not self.tool_client.enabled:
            return []
        specs, captured = retrieval_tool_specs(
            self.retrieval_agent,
            complaint.product_code,
            events_by_code,
            recalls or [],
            vector_collection,
        )
        try:
            result = self.tool_client.run(
                system_prompt=render_prompt("retrieval_tools_system"),
                user_prompt=render_prompt(
                    "retrieval_tools_user",
                    product_code=complaint.product_code,
                    report_type=report_type,
                    category=extraction.qms_complaint_category,
                    key_issues=", ".join(extraction.key_issues) or "None",
                    narrative=complaint.narrative[:600],
                ),
                tools=specs,
                max_tokens=900,
            )
        except Exception:  # noqa: BLE001 — fall back to the deterministic retrieve()
            return []
        self.last_evidence_queries = [
            str(inv.arguments.get("query", "")).strip()
            for inv in result.invocations
            if inv.name == "search_maude_events" and inv.arguments.get("query")
        ]
        captured.sort(key=lambda item: item.score, reverse=True)
        return captured[:top_k]

    def ensure_questions(self, ctx: ReportContext) -> List[str]:
        if ctx.report_questions is None:
            if str(ctx.extraction.qms_complaint_category).strip().upper() == "NOT_AVAILABLE" or ctx.extraction.confidence <= 0.0:
                ctx.report_questions = []
                return ctx.report_questions
            ctx.report_questions = self.select_report_questions(
                ctx.complaint, ctx.risk, report_type=ctx.report_type
            )
        return ctx.report_questions

    # --- Section-narrative agent (de-hardcodes the prose sections) ----------
    def ensure_section_narratives(self, ctx: ReportContext) -> "dict[str, str]":
        """Generate the interpretive prose for this report's narrative sections.

        One model pass drafts the narrative for *every* narrative section in the
        active blueprint at once (tool-calling preferred, plain JSON fallback). The
        regulatory VERDICTS (risk bucket, escalation/PRRC/FSCA flags, MDR reportable
        YES/NO) are passed in as deterministic facts and rendered separately by the
        section builders — the model writes only the surrounding justification and
        must ground every claim in a cited FDA record or a given fact.

        Cached on ``ctx``. When no model backend is available, each section is
        ``"Not available"`` so the report never falls back to hardcoded prose.
        """
        if ctx.section_narratives is not None:
            return ctx.section_narratives

        targets = [s.name for s in blueprint_for(ctx.report_type) if s.name in NARRATIVE_SECTIONS]
        if not targets:
            ctx.section_narratives = {}
            return ctx.section_narratives

        # No usable extraction => surface Not available instead of inventing prose.
        if str(ctx.extraction.qms_complaint_category).strip().upper() == "NOT_AVAILABLE" or ctx.extraction.confidence <= 0.0:
            ctx.section_narratives = {name: "Not available" for name in targets}
            return ctx.section_narratives

        facts = self._narrative_facts(ctx)
        evidence = self.ensure_evidence(ctx)
        allowed = {e.evidence_id for e in evidence if getattr(e, "evidence_id", "")}
        evidence_block = (
            "\n".join(f"- {e.evidence_id} [{e.source_type}] {e.snippet}" for e in evidence)
            or "None retrieved"
        )
        sections_block = "\n".join(f"- {name}: {NARRATIVE_SECTIONS[name]}" for name in targets)

        system = render_prompt("section_narratives_system")
        user = render_prompt(
            "section_narratives_user",
            evidence_block=evidence_block,
            sections_block=sections_block,
            **facts,
        )

        data: "dict" = {}
        # Preferred path: a single tool-calling pass so the model can pull more
        # MAUDE/recall/trend grounding before writing.
        if self.tool_client.enabled:
            events = ctx.events_by_code.get(ctx.complaint.product_code, [])
            specs, captured = retrieval_tool_specs(
                self.retrieval_agent, ctx.complaint.product_code, ctx.events_by_code, [], None
            )
            specs = specs + trend_tool_specs(self.trend_analyzer, events)
            try:
                result = self.tool_client.run(
                    system_prompt=system, user_prompt=user, tools=specs, max_tokens=1200
                )
                data = result.json_object()
            except Exception:  # noqa: BLE001 — fall through to the JSON fallback
                data = {}
            for item in captured:
                if getattr(item, "evidence_id", ""):
                    allowed.add(item.evidence_id)

        # Fallback path: plain JSON completion (no tools) on the augmented client.
        if not data:
            llm = getattr(self.extraction_agent, "llm", None)
            if llm is not None and getattr(llm, "enabled", False):
                data = llm.complete_json(system_prompt=system, user_prompt=user, fallback={})

        ctx.section_narratives = self._finalize_narratives(ctx, targets, data, allowed)
        return ctx.section_narratives

    def _narrative_facts(self, ctx: ReportContext) -> "dict[str, str]":
        """Build the deterministic-facts block the narrative agent must respect."""
        r = ctx.risk
        c = ctx.complaint
        e = ctx.extraction
        event = c.event_type.lower()
        reportable = event in {"injury", "death"} or r.risk_bucket == "UNACCEPTABLE"
        trend = self.ensure_trend(ctx)

        def _txt(value) -> str:
            text = str(value).strip() if value is not None else ""
            return text or "Not available"

        return {
            "product_code": c.product_code,
            "event_type": c.event_type,
            "narrative": (c.narrative or "")[:600],
            "category": _txt(e.qms_complaint_category),
            "key_issues": ", ".join(e.key_issues) or "None",
            "risk_bucket": r.risk_bucket,
            "severity": r.severity_level,
            "probability": r.probability_level,
            "escalation_required": str(r.escalation_required),
            "prrc_required": str(r.prrc_notification_required),
            "fsca_required": str(r.fsca_required),
            "reportable": "YES" if reportable else "NO",
            "hazardous_situation": _txt(r.hazardous_situation),
            "harm": _txt(r.harm),
            "iso_14971_rationale": _txt(r.iso_14971_rationale),
            "trend_direction": _txt(trend.trend_direction),
            "total_events": str(trend.total_events),
            "software_events": str(trend.software_problem_events),
            "latest_year": str(trend.latest_year_events),
            "previous_year": str(trend.previous_year_events),
        }

    def _finalize_narratives(
        self, ctx: ReportContext, targets: List[str], data: "dict", allowed: "set"
    ) -> "dict[str, str]":
        """Coerce the model output and enforce citation grounding per section.

        When FDA evidence was available, a narrative that cites none of it is
        appended with an uncited flag and routed to QM review (Validation Gate 3
        style), keeping the anti-hallucination guarantee.
        """
        finalized: "dict[str, str]" = {}
        for name in targets:
            text = str(data.get(name, "")).strip() if isinstance(data, dict) else ""
            if not text:
                finalized[name] = "Not available"
                continue
            if allowed and not any(token in text for token in allowed):
                text = f"{text}  (uncited — flagged for QM review)"
                ctx.review_needed = True
                reason = f"SectionNarrative '{name}' cites no retrieved FDA record."
                if reason not in ctx.review_reasons:
                    ctx.review_reasons.append(reason)
            finalized[name] = text
        return finalized

    # --- Subquery planning (closes the research-pattern gap) ---------------
    def plan_subqueries(
        self, complaint: Complaint, extraction: ExtractedSignal, risk: "RiskAssessment | None" = None
    ) -> List[str]:
        """Decompose a complaint into focused retrieval subqueries using an LLM only.

        If the model is unavailable, return no subqueries so the report can
        surface Not available instead of inventing deterministic facets.
        """
        llm = getattr(self.extraction_agent, "llm", None)
        if llm is None or not getattr(llm, "enabled", False):
            return []

        result = llm.complete_json(
            system_prompt=render_prompt("subqueries_system"),
            user_prompt=render_prompt(
                "subqueries_user",
                product_code=complaint.product_code,
                report_type=risk.report_type if risk is not None else "UNKNOWN",
                category=extraction.qms_complaint_category,
                key_issues=", ".join(extraction.key_issues) or "None",
                narrative=complaint.narrative[:600],
            ),
            fallback={"subqueries": []},
        )
        subqueries = result.get("subqueries", [])
        return [str(q) for q in subqueries if isinstance(q, str) and q.strip()][:4]

    def _llm_subqueries(self, complaint: Complaint, extraction: ExtractedSignal) -> List[str]:
        return self.plan_subqueries(complaint, extraction)

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
        llm = getattr(self.extraction_agent, "llm", None)
        if llm is None or not getattr(llm, "enabled", False):
            return []

        report_type = report_type or risk.report_type
        result = llm.complete_json(
            system_prompt=render_prompt("questions_system"),
            user_prompt=render_prompt(
                "questions_user",
                report_type=report_type,
                event_type=complaint.event_type,
                risk_bucket=risk.risk_bucket,
                severity=risk.severity_level,
                probability=risk.probability_level,
                product_code=complaint.product_code,
                narrative=complaint.narrative[:600],
            ),
            fallback={"questions": []},
        )
        questions = result.get("questions", [])
        return [str(q) for q in questions if isinstance(q, str) and q.strip()][:4]
