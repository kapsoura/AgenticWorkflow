import operator
from time import monotonic
from typing import Annotated, Dict, List, TypedDict

from langgraph.graph import END, START, StateGraph

from src.agents.archive_trend import ArchiveTrendAnalyzer
from src.agents.extraction import ExtractionAgent
from src.agents.orchestration import OrchestrationAgent
from src.agents.report_generation import ReportGenerationAgent
from src.agents.retrieval import RetrievalAgent
from src.agents.risk_analysis import RiskAnalysisAgent
from src.agents.report_sections import ReportContext
from src.observability.tracer import TraceLogger
from src.pipeline.schemas import Complaint, RetrievalEvidence, validate_handoff


class WorkflowState(TypedDict, total=False):
    trace_id: str
    tracer: TraceLogger
    deadline_ts: float
    complaint: Complaint
    events_by_code: Dict[str, List[dict]]
    recalls: List[dict]
    extraction: dict
    retrieval: List[RetrievalEvidence]
    subqueries: List[str]
    trend: dict
    risk: dict
    report_questions: List[str]
    # Reducer channels: every agent contributes its own gate findings and
    # LangGraph merges them, so agents interact through shared state safely even
    # if nodes are added in parallel later.
    review_needed: Annotated[bool, operator.or_]
    review_reasons: Annotated[List[str], operator.add]
    signal_report: dict
    signal_reports: list
    vector_collection: object
    template_sections: list


class LangGraphSignalWorkflow:
    MIN_RETRIEVAL_SCORE = 0.3

    def __init__(self):
        self.extraction_agent = ExtractionAgent()
        self.retrieval_agent = RetrievalAgent()
        self.risk_agent = RiskAnalysisAgent()
        self.report_agent = ReportGenerationAgent()
        self.trend_agent = ArchiveTrendAnalyzer()
        self.orchestrator_agent = OrchestrationAgent(
            extraction_agent=self.extraction_agent,
            retrieval_agent=self.retrieval_agent,
            risk_agent=self.risk_agent,
            report_agent=self.report_agent,
            trend_analyzer=self.trend_agent,
        )

        self.graph = self._build_graph().compile()

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(WorkflowState)

        graph.add_node("extract", self._extract)
        graph.add_node("retrieve", self._retrieve)
        graph.add_node("risk", self._risk)
        graph.add_node("assemble", self._assemble)

        graph.add_edge(START, "extract")
        graph.add_edge("extract", "retrieve")
        graph.add_edge("retrieve", "risk")
        graph.add_edge("risk", "assemble")
        graph.add_edge("assemble", END)
        return graph

    def _extract(self, state: WorkflowState) -> WorkflowState:
        self._check_deadline(state)
        started = monotonic()
        extraction = self.extraction_agent.extract(state["complaint"])
        errors = validate_handoff("extraction", extraction)
        review_reasons: List[str] = []

        gate_retry = extraction.confidence < 0.5 or not extraction.qms_complaint_category or not extraction.key_issues
        if gate_retry:
            extraction = self.extraction_agent.extract(state["complaint"])
            errors = validate_handoff("extraction", extraction)

        if extraction.confidence < 0.5:
            review_reasons.append("Gate1: extraction confidence below 0.5")
        if errors:
            review_reasons.append(f"Gate1: extraction schema issues: {', '.join(errors)}")

        self._trace(
            state,
            agent="extract",
            event="completed",
            gate_result="review" if review_reasons else "pass",
            latency_ms=(monotonic() - started) * 1000.0,
            metadata={"confidence": extraction.confidence, "errors": errors},
        )
        return {"extraction": extraction, "review_needed": bool(review_reasons), "review_reasons": review_reasons}

    def _retrieve(self, state: WorkflowState) -> WorkflowState:
        self._check_deadline(state)
        started = monotonic()
        complaint = state["complaint"]
        subqueries = self.orchestrator_agent.plan_subqueries(
            complaint=complaint,
            extraction=state["extraction"],
        )
        retrieval = self.retrieval_agent.retrieve(
            extracted=state["extraction"],
            complaint_product_code=complaint.product_code,
            events_by_code=state["events_by_code"],
            recalls=state["recalls"],
            vector_collection=state.get("vector_collection"),
            subqueries=subqueries,
        )
        retrieval = [item for item in retrieval if item.score >= self.MIN_RETRIEVAL_SCORE]
        errors = validate_handoff("retrieval", retrieval)

        review_reasons: List[str] = []
        if not retrieval:
            review_reasons.append("Gate2: no evidence above relevance threshold")
        if errors:
            review_reasons.append(f"Gate2: retrieval schema issues: {', '.join(errors)}")

        self._trace(
            state,
            agent="retrieve",
            event="completed",
            gate_result="review" if review_reasons else "pass",
            latency_ms=(monotonic() - started) * 1000.0,
            metadata={"kept_items": len(retrieval), "errors": errors},
        )
        return {
            "retrieval": retrieval,
            "subqueries": subqueries,
            "review_needed": bool(review_reasons),
            "review_reasons": review_reasons,
        }

    def _risk(self, state: WorkflowState) -> WorkflowState:
        self._check_deadline(state)
        started = monotonic()
        risk = self.risk_agent.assess(complaint=state["complaint"], evidence=state["retrieval"])
        errors = validate_handoff("risk", risk)
        review_reasons: List[str] = []

        if risk.risk_bucket == "UNACCEPTABLE" and len(state.get("retrieval", [])) == 0:
            review_reasons.append("Gate3: UNACCEPTABLE risk without evidence citations")
        if state["complaint"].event_type.lower() == "death" and risk.risk_bucket == "ACCEPTABLE":
            review_reasons.append("Gate3: death event with ACCEPTABLE risk requires human escalation")
        if errors:
            review_reasons.append(f"Gate3: risk schema issues: {', '.join(errors)}")

        self._trace(
            state,
            agent="risk",
            event="completed",
            gate_result="review" if review_reasons else "pass",
            latency_ms=(monotonic() - started) * 1000.0,
            metadata={"risk_bucket": risk.risk_bucket, "errors": errors},
        )
        return {"risk": risk, "review_needed": bool(review_reasons), "review_reasons": review_reasons}

    def _assemble(self, state: WorkflowState) -> WorkflowState:
        self._check_deadline(state)
        started = monotonic()
        risk = state["risk"]
        retrieval = state["retrieval"]
        tracer = state.get("tracer")
        template_sections = state.get("template_sections")
        base_review_needed = bool(state.get("review_needed", False))
        base_review_reasons = list(state.get("review_reasons", []))

        # When a skeleton template is supplied, honor it and produce a single
        # template-driven report of the primary type. Otherwise the orchestrator
        # decides the full set of reports the complaint warrants.
        if template_sections:
            report_types = [risk.report_type]
        else:
            report_types = self.orchestrator_agent.decide_report_types(
                complaint=state["complaint"],
                extraction=state["extraction"],
                risk=risk,
                evidence=retrieval,
                tracer=tracer,
            )

        reports = []
        extra_review_reasons: List[str] = []
        for report_type in report_types:
            context = ReportContext(
                complaint=state["complaint"],
                extraction=state["extraction"],
                retrieval=retrieval,
                risk=risk,
                report_type=report_type,
                events_by_code=state["events_by_code"],
                subqueries=state.get("subqueries"),
                review_needed=base_review_needed,
                review_reasons=list(base_review_reasons),
            )
            # Report agent drives the orchestrator, which drives sub-agents per section.
            report = self.report_agent.create_report(
                trace_id=state["trace_id"],
                context=context,
                orchestrator=self.orchestrator_agent,
                tracer=tracer,
                review_needed=context.review_needed,
                review_reasons=context.review_reasons,
                section_specs=template_sections,
            )
            reports.append(report)
            if report.review_needed:
                for reason in report.review_reasons:
                    if reason not in base_review_reasons and reason not in extra_review_reasons:
                        extra_review_reasons.append(reason)
            self._trace(
                state,
                agent="assemble",
                event="report_built",
                gate_result="review" if report.review_needed else "pass",
                latency_ms=(monotonic() - started) * 1000.0,
                metadata={"report_id": report.report_id, "report_type": report.report_type},
            )

        primary = reports[0]
        return {
            "signal_report": primary,
            "signal_reports": reports,
            "trend": primary.trend,
            "report_questions": primary.orchestrator_questions,
            "review_needed": any(r.review_needed for r in reports),
            "review_reasons": extra_review_reasons,
        }

    def run_for_complaint(
        self,
        trace_id: str,
        tracer: TraceLogger,
        complaint: Complaint,
        events_by_code: Dict[str, List[dict]],
        recalls: List[dict],
        vector_collection=None,
        max_runtime_seconds: int = 120,
        template_sections=None,
    ):
        result = self.graph.invoke(
            {
                "trace_id": trace_id,
                "tracer": tracer,
                "deadline_ts": monotonic() + max_runtime_seconds,
                "complaint": complaint,
                "events_by_code": events_by_code,
                "recalls": recalls,
                "vector_collection": vector_collection,
                "template_sections": template_sections,
                "review_needed": False,
                "review_reasons": [],
            }
        )
        return result["signal_reports"]

    @staticmethod
    def _trace(
        state: WorkflowState,
        agent: str,
        event: str,
        gate_result: str,
        latency_ms: float,
        metadata: dict,
    ) -> None:
        tracer = state.get("tracer")
        if tracer is None:
            return
        tracer.log(
            agent=agent,
            event=event,
            gate_result=gate_result,
            latency_ms=round(latency_ms, 2),
            metadata=metadata,
        )

    @staticmethod
    def _check_deadline(state: WorkflowState) -> None:
        deadline_ts = state.get("deadline_ts")
        if deadline_ts is None:
            return
        if monotonic() > deadline_ts:
            raise TimeoutError("Workflow timed out before completing all nodes")
