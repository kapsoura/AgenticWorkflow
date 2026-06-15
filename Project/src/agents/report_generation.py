from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from src.agents.report_sections import ReportContext, abbr_for
from src.pipeline.schemas import SignalReport


class ReportGenerationAgent:
    """Assembles a report by asking the orchestrator for the sections its type needs.

    The agent owns *layout and rendering*; it delegates *what work to do* to the
    orchestrator, which drives the relevant sub-agents per section.
    """

    def create_report(
        self,
        trace_id: str,
        context: ReportContext,
        orchestrator,
        tracer=None,
        review_needed: bool = False,
        review_reasons: Optional[List[str]] = None,
        section_specs=None,
    ) -> SignalReport:
        review_reasons = review_reasons or []
        context.review_needed = review_needed
        context.review_reasons = review_reasons

        created_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        complaint = context.complaint
        report_id = (
            f"SR-{complaint.product_code}-{complaint.complaint_id.split('-')[-1]}-"
            f"{abbr_for(context.report_type)}-{datetime.utcnow().strftime('%Y%m%d')}"
        )

        # Report drives the orchestrator, which drives sub-agents per section.
        sections = orchestrator.build_sections(context, tracer, section_specs=section_specs)
        # Guarantee trend is populated for the report record even if no section
        # in the blueprint required it.
        trend = orchestrator.ensure_trend(context)
        questions = context.report_questions or []

        md = self._render_markdown(report_id, created_at, trace_id, sections)

        return SignalReport(
            report_id=report_id,
            created_at=created_at,
            trace_id=trace_id,
            complaint=complaint,
            extraction=context.extraction,
            retrieval=context.retrieval or [],
            risk=context.risk,
            trend=trend,
            report_type=context.report_type,
            orchestrator_questions=questions,
            report_markdown=md,
            review_needed=context.review_needed,
            review_reasons=context.review_reasons,
        )

    def persist_report(self, signal_report: SignalReport, reports_dir: Path) -> Path:
        reports_dir.mkdir(parents=True, exist_ok=True)
        path = reports_dir / f"{signal_report.report_id}.md"
        path.write_text(signal_report.report_markdown, encoding="utf-8")
        return path

    @staticmethod
    def _render_markdown(
        report_id: str,
        created_at: str,
        trace_id: str,
        sections: List[Tuple[str, str]],
    ) -> str:
        lines: List[str] = [
            f"# Signal Report {report_id}",
            "",
            f"- Created: {created_at}",
            f"- Trace ID: {trace_id}",
            "",
        ]
        for title, body in sections:
            lines.append(f"## {title}")
            lines.append(body)
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

