"""Interactive single-complaint service.

Loads the working archive once (events, recalls, vector index) and runs the
LangGraph workflow for one user-supplied complaint. Optionally accepts a list of
template headings (from an uploaded .docx skeleton) to drive the report structure.
"""

from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

from dataclasses import asdict

from src.agents.report_sections import sections_from_headings
from src.config import (
    CHROMA_DIR,
    DEFAULT_MAX_EVENTS_PER_CODE,
    IMAGING_EVENTS_DIR,
    LOGS_DIR,
    PRODUCT_CODES,
    RECALLS_FILE,
    REPORTS_DIR,
    SQLITE_DB_PATH,
)
from src.observability.tracer import TraceLogger
from src.pipeline.langgraph_flow import LangGraphSignalWorkflow
from src.pipeline.schemas import Complaint, SignalReport
from src.utils.data_loader import load_events_for_codes, load_recalls
from src.utils.docx_io import render_report_docx
from src.utils.storage import init_chroma, init_sqlite, persist_signal_report, upsert_event_vectors


class SignalService:
    """Caches loaded data and runs the workflow for individual complaints."""

    def __init__(self, max_events_per_code: int = DEFAULT_MAX_EVENTS_PER_CODE):
        self.product_codes = list(PRODUCT_CODES)
        self.events_by_code = load_events_for_codes(
            imaging_events_dir=IMAGING_EVENTS_DIR,
            product_codes=self.product_codes,
            max_events_per_code=max_events_per_code,
        )
        try:
            self.recalls = load_recalls(recalls_file=RECALLS_FILE, product_codes=self.product_codes)
        except FileNotFoundError:
            self.recalls = []

        init_sqlite(SQLITE_DB_PATH)
        self.vector_collection = init_chroma(CHROMA_DIR)
        for code in self.product_codes:
            upsert_event_vectors(self.vector_collection, self.events_by_code.get(code, []))

        self.workflow = LangGraphSignalWorkflow()

    def run_complaint(
        self,
        narrative: str,
        product_code: str,
        event_type: str = "Malfunction",
        manufacturer: str = "Unknown",
        template_headings: Optional[List[str]] = None,
    ) -> List[SignalReport]:
        code = product_code.upper()
        complaint = Complaint(
            complaint_id=f"WEB-{code}-{uuid4().hex[:6]}",
            product_code=code,
            manufacturer=manufacturer or "Unknown",
            event_type=event_type or "Malfunction",
            date_received=datetime.utcnow().strftime("%Y%m%d"),
            narrative=narrative.strip(),
            source_report_number="USER-SUBMITTED",
            ground_truth_problems=[],
        )

        template_sections = sections_from_headings(template_headings) if template_headings else None

        trace_id = f"web-{uuid4().hex[:8]}-{complaint.complaint_id}"
        tracer = TraceLogger(trace_id=trace_id, logs_dir=LOGS_DIR)
        reports = self.workflow.run_for_complaint(
            trace_id=trace_id,
            tracer=tracer,
            complaint=complaint,
            events_by_code=self.events_by_code,
            recalls=self.recalls,
            vector_collection=self.vector_collection,
            template_sections=template_sections,
        )
        for report in reports:
            persist_signal_report(SQLITE_DB_PATH, report)
        return reports

    def analyze_complaint(
        self,
        narrative: str,
        product_code: str,
        event_type: str = "Malfunction",
        manufacturer: str = "Unknown",
        template_headings: Optional[List[str]] = None,
    ) -> Dict:
        """Run a complaint and return a structured payload for the validation UI.

        Includes the decided reports, the full LangGraph activity timeline (so the
        user can validate the sequence of agent/LLM responses) and trend-plot data
        for the complaint's product code.
        """
        code = product_code.upper()
        complaint = Complaint(
            complaint_id=f"WEB-{code}-{uuid4().hex[:6]}",
            product_code=code,
            manufacturer=manufacturer or "Unknown",
            event_type=event_type or "Malfunction",
            date_received=datetime.utcnow().strftime("%Y%m%d"),
            narrative=narrative.strip(),
            source_report_number="USER-SUBMITTED",
            ground_truth_problems=[],
        )

        template_sections = sections_from_headings(template_headings) if template_headings else None
        used_template = bool(template_sections)

        trace_id = f"web-{uuid4().hex[:8]}-{complaint.complaint_id}"
        tracer = TraceLogger(trace_id=trace_id, logs_dir=LOGS_DIR)
        reports = self.workflow.run_for_complaint(
            trace_id=trace_id,
            tracer=tracer,
            complaint=complaint,
            events_by_code=self.events_by_code,
            recalls=self.recalls,
            vector_collection=self.vector_collection,
            template_sections=template_sections,
        )
        for report in reports:
            persist_signal_report(SQLITE_DB_PATH, report)

        events = self.events_by_code.get(code, [])
        analyzer = self.workflow.trend_agent
        primary = reports[0]

        report_payloads = [
            {
                "report_id": r.report_id,
                "report_type": r.report_type,
                "review_needed": r.review_needed,
                "review_reasons": list(r.review_reasons),
                "markdown": r.report_markdown,
                "questions": list(r.orchestrator_questions),
                "docx_name": render_report_docx(r, REPORTS_DIR / f"{r.report_id}.docx").name,
            }
            for r in reports
        ]

        return {
            "trace_id": trace_id,
            "complaint": asdict(complaint),
            "used_template": used_template,
            "template_sections": [
                {"name": s.name, "title": s.title} for s in (template_sections or [])
            ],
            "report_types": [r.report_type for r in reports],
            "reports": report_payloads,
            "risk": asdict(primary.risk),
            "extraction": asdict(primary.extraction),
            "evidence_count": len(primary.retrieval),
            "subqueries": [
                e.metadata.get("subquery")
                for e in primary.retrieval
                if e.metadata.get("subquery")
            ],
            "timeline": tracer.events,
            "trend": {
                "summary": asdict(primary.trend),
                "yearly": analyzer.yearly_breakdown(events),
                "problems": analyzer.problem_breakdown(events),
            },
        }
