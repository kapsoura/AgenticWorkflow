import operator
import sqlite3
from time import monotonic
from typing import Annotated, Dict, List, TypedDict

from langgraph.graph import END, START, StateGraph

from src.agents.archive_trend import ArchiveTrendAnalyzer
from src.agents.extraction import ExtractionAgent
from src.agents.guardrail import GuardrailAgent
from src.agents.orchestration import OrchestrationAgent
from src.agents.report_generation import ReportGenerationAgent
from src.agents.retrieval import RetrievalAgent
from src.agents.risk_analysis import RiskAnalysisAgent
from src.agents.report_sections import ReportContext
from src.config import SQLITE_DB_PATH
from src.observability.tracer import TraceLogger
from src.pipeline.schemas import (
    Complaint,
    RetrievalEvidence,
    validate_signal_handoff as validate_handoff,
)
from src.utils.storage import embed_text


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
    input_guardrail_pass: bool
    input_guardrail_reasons: List[str]
    memory_summary: str
    memory_hits: List[str]
    retrieval_done: bool
    trend_done: bool
    output_guardrail_pass: bool
    output_guardrail_reasons: List[str]


class LangGraphSignalWorkflow:
    MIN_RETRIEVAL_SCORE = 0.3

    def __init__(self):
        self.extraction_agent = ExtractionAgent()
        self.retrieval_agent = RetrievalAgent()
        self.risk_agent = RiskAnalysisAgent()
        self.report_agent = ReportGenerationAgent()
        self.trend_agent = ArchiveTrendAnalyzer()
        self.guardrail_agent = GuardrailAgent()
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

        graph.add_node("input_guardrail", self._input_guardrail)
        graph.add_node("extract", self._extract)
        graph.add_node("memory", self._memory)
        graph.add_node("retrieve", self._retrieve)
        graph.add_node("trend", self._trend)
        graph.add_node("merge", self._merge)
        graph.add_node("risk", self._risk)
        graph.add_node("assemble", self._assemble)
        graph.add_node("output_guardrail", self._output_guardrail)
        graph.add_node("end_rejected", self._end_rejected)
        graph.add_node("end_guarded", self._end_guarded)
        graph.add_node("end_ok", self._end_ok)

        graph.add_edge(START, "input_guardrail")
        graph.add_conditional_edges(
            "input_guardrail",
            self._route_after_input_guardrail,
            {
                "extract": "extract",
                "end_rejected": "end_rejected",
            },
        )
        graph.add_edge("extract", "memory")
        graph.add_edge("memory", "retrieve")
        graph.add_edge("memory", "trend")
        graph.add_edge("retrieve", "merge")
        graph.add_edge("trend", "merge")
        graph.add_edge("merge", "risk")
        graph.add_edge("risk", "assemble")
        graph.add_edge("assemble", "output_guardrail")
        graph.add_conditional_edges(
            "output_guardrail",
            self._route_after_output_guardrail,
            {
                "end_ok": "end_ok",
                "end_guarded": "end_guarded",
            },
        )
        graph.add_edge("end_rejected", END)
        graph.add_edge("end_guarded", END)
        graph.add_edge("end_ok", END)
        return graph

    def _input_guardrail(self, state: WorkflowState) -> WorkflowState:
        self._check_deadline(state)
        started = monotonic()
        verdict = self.guardrail_agent.check_input(state["complaint"].narrative)
        passed = verdict.passed
        reasons = list(verdict.reasons)

        self._trace(
            state,
            agent="input_guardrail",
            event="completed",
            gate_result="pass" if passed else "review",
            latency_ms=(monotonic() - started) * 1000.0,
            metadata={"reasons": reasons, "available": verdict.available},
        )
        return {
            "input_guardrail_pass": passed,
            "input_guardrail_reasons": reasons,
            "review_needed": not passed,
            "review_reasons": reasons,
        }

    def _memory(self, state: WorkflowState) -> WorkflowState:
        self._check_deadline(state)
        started = monotonic()
        complaint = state["complaint"]
        memory_hits: List[str] = []
        memory_lines: List[str] = []

        if SQLITE_DB_PATH.exists():
            try:
                conn = sqlite3.connect(SQLITE_DB_PATH)
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT report_id, risk_bucket, report_type
                    FROM signal_reports
                    WHERE complaint_id IN (
                        SELECT complaint_id FROM complaint_archive WHERE product_code = ?
                    )
                    ORDER BY created_at DESC
                    LIMIT 3
                    """,
                    (complaint.product_code,),
                )
                rows = cur.fetchall()
                for report_id, risk_bucket, report_type in rows:
                    memory_hits.append(str(report_id))
                    memory_lines.append(
                        f"prior report {report_id}: bucket={risk_bucket}, type={report_type}"
                    )
                conn.close()
            except Exception:
                memory_lines.append("sqlite memory unavailable")

        vector_collection = state.get("vector_collection")
        if vector_collection is not None:
            try:
                result = vector_collection.query(
                    query_embeddings=[embed_text(complaint.narrative)],
                    n_results=3,
                )
                ids = result.get("ids", [[]])[0]
                if ids:
                    for value in ids:
                        memory_hits.append(f"vector:{value}")
                    memory_lines.append(f"vector neighbors: {', '.join(str(v) for v in ids)}")
            except Exception:
                memory_lines.append("vector memory unavailable")

        if not memory_lines:
            memory_lines.append("no prior similar complaints or reports found")

        summary = " ; ".join(memory_lines)[:600]
        self._trace(
            state,
            agent="memory",
            event="completed",
            gate_result="pass",
            latency_ms=(monotonic() - started) * 1000.0,
            metadata={"memory_hits": len(memory_hits)},
        )
        return {"memory_summary": summary, "memory_hits": memory_hits}

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
            metadata={
                "confidence": extraction.confidence,
                "errors": errors,
                "backend": getattr(self.extraction_agent, "last_backend", "integrated_unavailable"),
                "fallback_reason": getattr(self.extraction_agent, "last_fallback_reason", None),
            },
        )
        return {"extraction": extraction, "review_needed": bool(review_reasons), "review_reasons": review_reasons}

    def _retrieve(self, state: WorkflowState) -> WorkflowState:
        self._check_deadline(state)
        started = monotonic()
        complaint = state["complaint"]
        extraction = state["extraction"]
        if str(extraction.qms_complaint_category).strip().upper() == "NOT_AVAILABLE" or extraction.confidence <= 0.0:
            self._trace(
                state,
                agent="retrieve",
                event="completed",
                gate_result="pass",
                latency_ms=(monotonic() - started) * 1000.0,
                metadata={"kept_items": 0, "errors": [], "reason": "extraction_not_available"},
            )
            return {
                "retrieval": [],
                "subqueries": [],
                "retrieval_done": True,
                "review_needed": False,
                "review_reasons": [],
            }

        subqueries = self.orchestrator_agent.plan_subqueries(
            complaint=complaint,
            extraction=extraction,
        )
        retrieval = self.retrieval_agent.retrieve(
            extracted=extraction,
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
            "retrieval_done": True,
            "review_needed": bool(review_reasons),
            "review_reasons": review_reasons,
        }

    def _trend(self, state: WorkflowState) -> WorkflowState:
        self._check_deadline(state)
        started = monotonic()
        complaint = state["complaint"]
        trend = self.trend_agent.summarize(
            product_code=complaint.product_code,
            events=state["events_by_code"].get(complaint.product_code, []),
        )
        self._trace(
            state,
            agent="trend",
            event="completed",
            gate_result="pass",
            latency_ms=(monotonic() - started) * 1000.0,
            metadata={
                "trend_direction": trend.trend_direction,
                "backend": getattr(self.trend_agent, "last_backend", "integrated_unavailable"),
                "fallback_reason": getattr(self.trend_agent, "last_fallback_reason", None),
            },
        )
        return {"trend": trend, "trend_done": True}

    def _merge(self, state: WorkflowState) -> WorkflowState:
        self._check_deadline(state)
        started = monotonic()
        reasons: List[str] = []
        if not state.get("retrieval_done"):
            reasons.append("Merge: retrieval branch did not complete")
        if not state.get("trend_done"):
            reasons.append("Merge: trend branch did not complete")

        self._trace(
            state,
            agent="merge",
            event="completed",
            gate_result="review" if reasons else "pass",
            latency_ms=(monotonic() - started) * 1000.0,
            metadata={"retrieval_done": bool(state.get("retrieval_done")), "trend_done": bool(state.get("trend_done"))},
        )
        return {
            "retrieval": state.get("retrieval", []),
            "review_needed": bool(reasons),
            "review_reasons": reasons,
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
                trend=state.get("trend"),
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

    def _output_guardrail(self, state: WorkflowState) -> WorkflowState:
        self._check_deadline(state)
        started = monotonic()
        reports = list(state.get("signal_reports", []))
        review_reasons: List[str] = []

        for report in reports:
            evidence_ids = [item.evidence_id for item in report.retrieval]
            verdict = self.guardrail_agent.check_output(report.report_markdown, evidence_ids)
            report_reasons = list(verdict.reasons)

            if report_reasons:
                report.review_needed = True
                report.review_reasons.extend(r for r in report_reasons if r not in report.review_reasons)
                review_reasons.extend(report_reasons)

        passed = len(review_reasons) == 0
        self._trace(
            state,
            agent="output_guardrail",
            event="completed",
            gate_result="pass" if passed else "review",
            latency_ms=(monotonic() - started) * 1000.0,
            metadata={"reasons": review_reasons},
        )
        return {
            "signal_reports": reports,
            "signal_report": reports[0] if reports else state.get("signal_report"),
            "output_guardrail_pass": passed,
            "output_guardrail_reasons": review_reasons,
            "review_needed": bool(review_reasons),
            "review_reasons": review_reasons,
        }

    def _end_rejected(self, state: WorkflowState) -> WorkflowState:
        reasons = state.get("input_guardrail_reasons", ["InputGuardrail: rejected"]) or [
            "InputGuardrail: rejected"
        ]
        self._trace(
            state,
            agent="end_rejected",
            event="completed",
            gate_result="review",
            latency_ms=0.0,
            metadata={"reasons": reasons},
        )
        return {"signal_reports": [], "review_needed": True, "review_reasons": reasons}

    def _end_guarded(self, state: WorkflowState) -> WorkflowState:
        reasons = state.get("output_guardrail_reasons", [])
        self._trace(
            state,
            agent="end_guarded",
            event="completed",
            gate_result="review",
            latency_ms=0.0,
            metadata={"reasons": reasons},
        )
        return {}

    def _end_ok(self, state: WorkflowState) -> WorkflowState:
        self._trace(
            state,
            agent="end_ok",
            event="completed",
            gate_result="pass",
            latency_ms=0.0,
            metadata={},
        )
        return {}

    @staticmethod
    def _route_after_input_guardrail(state: WorkflowState) -> str:
        return "extract" if state.get("input_guardrail_pass", False) else "end_rejected"

    @staticmethod
    def _route_after_output_guardrail(state: WorkflowState) -> str:
        return "end_ok" if state.get("output_guardrail_pass", True) else "end_guarded"

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
                "input_guardrail_pass": True,
                "input_guardrail_reasons": [],
                "output_guardrail_pass": True,
                "output_guardrail_reasons": [],
            }
        )
        return result.get("signal_reports", [])

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
