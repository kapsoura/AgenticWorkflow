from datetime import datetime
from pathlib import Path
from time import monotonic
from typing import Any, Dict, List, Optional, Tuple

from src.agents.report_sections import ReportContext, abbr_for
from src.pipeline.schemas import SignalReport
from src.utils.llm_client import AnthropicClient
from src.utils.prompt_store import render_prompt


class ReportGenerationAgent:
    """Assembles a report by asking the orchestrator for the sections its type needs.

    The agent owns *layout and rendering*; it delegates *what work to do* to the
    orchestrator, which drives the relevant sub-agents per section.

    Autonomy level L2 (Evaluator-Optimizer): after the draft is rendered the agent
    runs a bounded self-critique loop (max 2 rounds / 20 s) that grades the draft
    against a fixed rubric and revises it. Stopping is deterministic (round/time
    caps), never the model's own "I'm done" — per the architecture's loop-safety
    rule. When the CLI backend is unavailable the loop is skipped gracefully and the
    draft is returned unchanged.
    """

    #: Hard cap on revision rounds (deterministic stop).
    MAX_ROUNDS = 2
    #: Wall-clock budget for the whole self-critique loop, in seconds.
    TIME_BUDGET_S = 20.0

    def __init__(self) -> None:
        self.llm = AnthropicClient()

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

        # L2 Evaluator-Optimizer: grade the draft and revise it (bounded loop).
        final_md, quality = self._self_critique(context, md, tracer)

        # Propagate any unresolved critique findings into the review flags so the
        # Quality Manager sees them; the report stays usable either way.
        if quality.get("review_needed"):
            context.review_needed = True
            for issue in quality.get("issues", []):
                reason = f"SelfCritique: {issue}"
                if reason not in context.review_reasons:
                    context.review_reasons.append(reason)

        # Append the controlled-document quality footer (Reviewed by stays blank).
        final_md = final_md.rstrip() + "\n\n" + self._quality_section(quality) + "\n"

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
            report_markdown=final_md,
            review_needed=context.review_needed,
            review_reasons=context.review_reasons,
            quality=quality,
        )

    # --- Evaluator-Optimizer self-critique loop ----------------------------
    def _self_critique(
        self,
        context: ReportContext,
        report_markdown: str,
        tracer=None,
    ) -> Tuple[str, Dict[str, Any]]:
        """Grade-and-revise the draft within deterministic round/time caps.

        Returns ``(final_markdown, quality_block)``. The loop:
          * runs at most :pyattr:`MAX_ROUNDS` critic passes,
          * stops as soon as the critic approves, the optimizer offers no usable
            revision, or :pyattr:`TIME_BUDGET_S` is exhausted,
          * is skipped entirely (draft unchanged) when the CLI backend is off.
        Stopping is controlled by the round/time counters, never by trusting the
        model's self-assessment alone.
        """
        evidence_ids = [
            e.evidence_id for e in (context.retrieval or []) if getattr(e, "evidence_id", "")
        ]
        risk_bucket = getattr(context.risk, "risk_bucket", "UNKNOWN")
        report_type = context.report_type

        if not self.llm.enabled:
            return report_markdown, self._quality_block(
                report_markdown,
                evidence_ids,
                self_score=None,
                unsupported_claims=None,
                rounds=0,
                approved=None,
                issues=[],
                llm_backed=False,
            )

        current = report_markdown
        deadline = monotonic() + self.TIME_BUDGET_S
        rounds = 0
        verdict: Dict[str, Any] = {}

        for round_idx in range(1, self.MAX_ROUNDS + 1):
            if monotonic() >= deadline:
                break
            rounds = round_idx

            verdict = self.llm.complete_json(
                system_prompt=render_prompt("report_critique_system"),
                user_prompt=render_prompt(
                    "report_critique_user",
                    report_type=report_type,
                    risk_bucket=risk_bucket,
                    evidence_ids=", ".join(evidence_ids) or "None",
                    report_markdown=current,
                ),
                fallback={},
            )
            approved = bool(verdict.get("approved"))
            issues = [str(i) for i in (verdict.get("issues") or [])]
            score = verdict.get("self_score")

            if tracer is not None:
                tracer.log(
                    agent="report_self_critique",
                    event="critique_round",
                    gate_result="pass" if approved else "revise",
                    metadata={
                        "round": round_idx,
                        "approved": approved,
                        "self_score": score,
                        "issues": issues,
                    },
                )

            if approved or not issues:
                break

            # Last round reached: don't optimize again, accept with review flag.
            if round_idx >= self.MAX_ROUNDS or monotonic() >= deadline:
                break

            revised = self.llm.complete_text(
                system_prompt=render_prompt("report_optimize_system"),
                user_prompt=render_prompt(
                    "report_optimize_user",
                    issues="\n".join(f"- {i}" for i in issues),
                    evidence_ids=", ".join(evidence_ids) or "None",
                    report_markdown=current,
                ),
                fallback="",
            )
            revised = revised.strip()
            # Guard against truncated/garbage revisions: a valid report keeps its
            # headings and roughly its length.
            if (
                revised
                and "#" in revised
                and len(revised) >= 0.5 * len(current)
                and revised != current
            ):
                current = revised
            else:
                if tracer is not None:
                    tracer.log(
                        agent="report_self_critique",
                        event="optimize_skipped",
                        gate_result="revise",
                        metadata={"round": round_idx, "reason": "no_usable_revision"},
                    )
                break

        approved_final = bool(verdict.get("approved"))
        quality = self._quality_block(
            current,
            evidence_ids,
            self_score=verdict.get("self_score"),
            unsupported_claims=verdict.get("unsupported_claims"),
            rounds=rounds,
            approved=approved_final,
            issues=[str(i) for i in (verdict.get("issues") or [])] if not approved_final else [],
            llm_backed=True,
        )
        return current, quality

    @staticmethod
    def _quality_block(
        report_markdown: str,
        evidence_ids: List[str],
        *,
        self_score,
        unsupported_claims,
        rounds: int,
        approved,
        issues: List[str],
        llm_backed: bool,
    ) -> Dict[str, Any]:
        text = report_markdown.lower()
        citation_count = sum(1 for eid in evidence_ids if eid and eid.lower() in text)
        review_needed = bool(issues) or approved is False
        return {
            "citation_count": citation_count,
            "unsupported_claims": unsupported_claims,
            "self_score": self_score,
            "rounds": rounds,
            "approved": approved,
            "review_needed": review_needed,
            "llm_backed": llm_backed,
            "issues": issues,
        }

    def _quality_section(self, quality: Dict[str, Any]) -> str:
        unsupported = quality.get("unsupported_claims")
        score = quality.get("self_score")
        lines = [
            "## Report Quality (Self-Critique)",
            f"- Citations referenced: {quality.get('citation_count', 0)}",
            f"- Unsupported claims (no FDA citation): {unsupported if unsupported is not None else 'n/a'}",
            f"- Self-critique score: {score if score is not None else 'n/a'} / 5",
            f"- Critique rounds: {quality.get('rounds', 0)} (cap {self.MAX_ROUNDS})",
            f"- Self-critique backend: {'claude CLI' if quality.get('llm_backed') else 'unavailable (skipped)'}",
            f"- Review Needed: {quality.get('review_needed', False)}",
            "- Reviewed by: _____________________ (Quality Manager)",
        ]
        issues = quality.get("issues") or []
        if issues:
            lines.append("- Outstanding reviewer issues:")
            lines.extend(f"  - {issue}" for issue in issues)
        return "\n".join(lines)

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

