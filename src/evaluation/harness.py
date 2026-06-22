"""Evaluation harness: run the gold benchmark through the pipeline and score it.

``run_evaluation`` constructs a :class:`SignalService`, runs each gold case,
scores the resulting report against the labels, and aggregates an
:class:`EvaluationReport`. Semantic metrics that depend on an LLM backend are
recorded as ``None`` (not scored) when the run is in deterministic fallback mode.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import PROJECT_ROOT
from src.evaluation import metrics
from src.evaluation.gold import GoldCase, load_gold_cases
from src.pipeline.schemas import SignalReport, validate_signal_handoff as validate_handoff


DEFAULT_K = 5
EVAL_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "evaluation"

# Acceptance thresholds (from the project design / CLAUDE.md success criteria).
THRESHOLDS: Dict[str, float] = {
    "extraction_key_issue_recall": 0.80,
    "retrieval_precision_at_k": 0.65,
    "risk_bucket_accuracy": 0.70,
    "rejection_accuracy": 1.00,
    "hallucination_rate": 0.15,  # upper bound (lower is better)
}


@dataclass
class CaseResult:
    """Per-case scoring outcome. ``None`` fields were not applicable/scored."""

    case_id: str
    product_code: str
    llm_backed: bool
    produced: bool
    rejection_correct: bool
    schema_errors: List[str] = field(default_factory=list)
    category_hit: Optional[bool] = None
    key_issue_recall: Optional[float] = None
    software_match: Optional[bool] = None
    risk_bucket_hit: Optional[bool] = None
    escalation_hit: Optional[bool] = None
    retrieval_precision_at_k: Optional[float] = None
    hallucination_rate: Optional[float] = None
    review_consistency: Optional[bool] = None
    predicted_category: str = ""
    predicted_risk_bucket: str = ""
    notes: str = ""


def _score_rejected(case: GoldCase, reports: List[SignalReport]) -> CaseResult:
    """Score a case whose input guardrail should refuse the complaint."""
    produced = bool(reports)
    return CaseResult(
        case_id=case.case_id,
        product_code=case.product_code,
        llm_backed=False,
        produced=produced,
        rejection_correct=(not produced),
        notes="prompt-injection / rejection case" if not produced else "FAIL: report produced for a complaint that should be rejected",
    )


def score_case(case: GoldCase, reports: List[SignalReport], k: int = DEFAULT_K) -> CaseResult:
    """Score one gold case against the pipeline output."""
    if case.expect_rejected:
        return _score_rejected(case, reports)

    produced = bool(reports)
    if not produced:
        return CaseResult(
            case_id=case.case_id,
            product_code=case.product_code,
            llm_backed=False,
            produced=False,
            rejection_correct=False,
            notes="FAIL: no report produced (timeout or unexpected rejection)",
        )

    report = reports[0]
    extraction = report.extraction
    risk = report.risk
    llm_backed = bool(getattr(risk, "llm_backed", False)) or extraction.confidence > 0.0

    # ---- structural: schema validity (always) ----
    schema_errors: List[str] = []
    schema_errors += [f"extraction: {e}" for e in validate_handoff("extraction", extraction)]
    schema_errors += [f"risk: {e}" for e in validate_handoff("risk", risk)]
    schema_errors += [f"retrieval: {e}" for e in validate_handoff("retrieval", report.retrieval)]

    # ---- structural: retrieval grounding (precision@k) ----
    flags = [
        any(metrics.normalize(kw) in metrics.normalize(ev.snippet) for kw in case.relevant_keywords)
        for ev in report.retrieval
    ]
    retrieval_p = metrics.precision_at_k(flags, k) if case.relevant_keywords and report.retrieval else None

    # ---- structural: citation hallucination ----
    quality = report.quality or {}
    hall = None
    if quality:
        hall = metrics.hallucination_rate(
            quality.get("unsupported_claims", 0),
            quality.get("citation_count", 0),
        )

    # ---- structural: review-flag consistency ----
    # Low-confidence extraction must raise the review flag (Gate 1 contract).
    review_consistency: Optional[bool] = None
    if extraction.confidence < 0.5:
        review_consistency = bool(report.review_needed)

    # ---- semantic metrics (only when an LLM produced the analysis) ----
    category_hit: Optional[bool] = None
    key_issue_recall: Optional[float] = None
    software_match: Optional[bool] = None
    risk_bucket_hit: Optional[bool] = None
    escalation_hit: Optional[bool] = None

    if llm_backed:
        if case.gold_categories:
            gold_up = {c.strip().upper() for c in case.gold_categories}
            category_hit = extraction.qms_complaint_category.strip().upper() in gold_up
        key_issue_recall = metrics.keyword_recall(
            case.key_issue_keywords, " ".join(extraction.key_issues)
        )
        if case.software_related is not None:
            predicted_sw = metrics.is_software_category(extraction.qms_complaint_category)
            software_match = predicted_sw == case.software_related
        if case.expected_risk_buckets:
            risk_bucket_hit = risk.risk_bucket.strip().upper() in {
                b.strip().upper() for b in case.expected_risk_buckets
            }
        if case.expect_escalation is not None:
            escalation_hit = bool(risk.escalation_required) == case.expect_escalation

    return CaseResult(
        case_id=case.case_id,
        product_code=case.product_code,
        llm_backed=llm_backed,
        produced=True,
        rejection_correct=True,
        schema_errors=schema_errors,
        category_hit=category_hit,
        key_issue_recall=key_issue_recall,
        software_match=software_match,
        risk_bucket_hit=risk_bucket_hit,
        escalation_hit=escalation_hit,
        retrieval_precision_at_k=retrieval_p,
        hallucination_rate=hall,
        review_consistency=review_consistency,
        predicted_category=extraction.qms_complaint_category,
        predicted_risk_bucket=risk.risk_bucket,
        notes="" if not schema_errors else "schema issues detected",
    )


@dataclass
class EvaluationReport:
    generated_at: str
    gold_path: str
    k: int
    total_cases: int
    llm_backed_cases: int
    aggregate: Dict[str, Any]
    threshold_results: Dict[str, Any]
    passed: bool
    cases: List[CaseResult]


def _aggregate(results: List[CaseResult]) -> Dict[str, Any]:
    non_rejected = [r for r in results if r.notes != "prompt-injection / rejection case"]
    return {
        "rejection_accuracy": metrics.accuracy(r.rejection_correct for r in results),
        "report_produced_rate": metrics.accuracy(
            r.produced for r in results if not _is_rejection_case(r)
        ),
        "schema_valid_rate": metrics.accuracy(
            not r.schema_errors for r in results if r.produced
        ),
        "extraction_category_accuracy": metrics.accuracy(
            r.category_hit for r in results if r.category_hit is not None
        ),
        "extraction_key_issue_recall": metrics.mean(
            r.key_issue_recall for r in results if r.key_issue_recall is not None
        ),
        "software_relevance_accuracy": metrics.accuracy(
            r.software_match for r in results if r.software_match is not None
        ),
        "risk_bucket_accuracy": metrics.accuracy(
            r.risk_bucket_hit for r in results if r.risk_bucket_hit is not None
        ),
        "escalation_accuracy": metrics.accuracy(
            r.escalation_hit for r in results if r.escalation_hit is not None
        ),
        "retrieval_precision_at_k": metrics.mean(
            r.retrieval_precision_at_k for r in results if r.retrieval_precision_at_k is not None
        ),
        "hallucination_rate": metrics.mean(
            r.hallucination_rate for r in results if r.hallucination_rate is not None
        ),
        "review_flag_consistency": metrics.accuracy(
            r.review_consistency for r in results if r.review_consistency is not None
        ),
    }


def _is_rejection_case(result: CaseResult) -> bool:
    return result.notes == "prompt-injection / rejection case" or (
        not result.produced and result.rejection_correct
    )


def _evaluate_thresholds(aggregate: Dict[str, Any]) -> Dict[str, Any]:
    """Compare aggregate metrics to thresholds; skip metrics not scored (None)."""
    out: Dict[str, Any] = {}
    for name, bound in THRESHOLDS.items():
        value = aggregate.get(name)
        if value is None:
            out[name] = {"value": None, "threshold": bound, "status": "skipped"}
            continue
        if name == "hallucination_rate":
            ok = value <= bound
        else:
            ok = value >= bound
        out[name] = {"value": value, "threshold": bound, "status": "pass" if ok else "fail"}
    return out


def run_evaluation(
    gold_path: Optional[Path] = None,
    k: int = DEFAULT_K,
    max_events_per_code: Optional[int] = None,
) -> EvaluationReport:
    """Run the full gold benchmark through the pipeline and score it."""
    # Imported here so unit tests of the scoring functions don't pull in the
    # whole pipeline / data archive.
    from src.config import DEFAULT_MAX_EVENTS_PER_CODE
    from src.pipeline.service import SignalService

    cases = load_gold_cases(gold_path)
    service = SignalService(
        max_events_per_code=max_events_per_code or DEFAULT_MAX_EVENTS_PER_CODE
    )

    results: List[CaseResult] = []
    for case in cases:
        try:
            reports = service.run_complaint(
                narrative=case.narrative,
                product_code=case.product_code,
                event_type=case.event_type,
                manufacturer=case.manufacturer,
            )
        except Exception as exc:  # noqa: BLE001 - benchmark must not abort on one case
            results.append(
                CaseResult(
                    case_id=case.case_id,
                    product_code=case.product_code,
                    llm_backed=False,
                    produced=False,
                    rejection_correct=case.expect_rejected,
                    notes=f"ERROR: {type(exc).__name__}: {exc}",
                )
            )
            continue
        results.append(score_case(case, reports, k=k))

    aggregate = _aggregate(results)
    threshold_results = _evaluate_thresholds(aggregate)
    passed = all(t["status"] != "fail" for t in threshold_results.values())

    return EvaluationReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        gold_path=str(gold_path) if gold_path else "data/evaluation/gold_complaints.json",
        k=k,
        total_cases=len(cases),
        llm_backed_cases=sum(1 for r in results if r.llm_backed),
        aggregate=aggregate,
        threshold_results=threshold_results,
        passed=passed,
        cases=results,
    )


def _fmt(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def format_markdown(report: EvaluationReport) -> str:
    lines: List[str] = []
    lines.append("# Pipeline Evaluation Report")
    lines.append("")
    lines.append(f"- Generated: {report.generated_at}")
    lines.append(f"- Gold benchmark: `{report.gold_path}`")
    lines.append(f"- Cases: {report.total_cases} (LLM-backed: {report.llm_backed_cases})")
    lines.append(f"- Precision@k: k={report.k}")
    mode = "LLM-backed" if report.llm_backed_cases else "deterministic fallback (no LLM) — semantic metrics not scored"
    lines.append(f"- Mode: {mode}")
    lines.append("")
    lines.append("## Aggregate metrics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    for name, value in report.aggregate.items():
        lines.append(f"| {name} | {_fmt(value)} |")
    lines.append("")
    lines.append("## Thresholds")
    lines.append("")
    lines.append("| Metric | Value | Threshold | Status |")
    lines.append("| --- | --- | --- | --- |")
    for name, res in report.threshold_results.items():
        lines.append(
            f"| {name} | {_fmt(res['value'])} | {res['threshold']} | {res['status']} |"
        )
    lines.append("")
    lines.append(f"**Overall: {'PASS' if report.passed else 'FAIL'}**")
    lines.append("")
    lines.append("## Per-case")
    lines.append("")
    lines.append("| Case | Code | LLM | Produced | Category | KeyIssue | SW | Risk | Esc | P@k | Notes |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in report.cases:
        def b(x: Optional[bool]) -> str:
            return "n/a" if x is None else ("ok" if x else "X")
        lines.append(
            f"| {r.case_id} | {r.product_code} | {'Y' if r.llm_backed else 'n'} "
            f"| {'Y' if r.produced else 'n'} | {b(r.category_hit)} | {_fmt(r.key_issue_recall)} "
            f"| {b(r.software_match)} | {b(r.risk_bucket_hit)} | {b(r.escalation_hit)} "
            f"| {_fmt(r.retrieval_precision_at_k)} | {r.notes} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_report(report: EvaluationReport, out_dir: Optional[Path] = None) -> Dict[str, Path]:
    """Persist the report as JSON + Markdown; returns the written paths."""
    target = Path(out_dir) if out_dir else EVAL_OUTPUT_DIR
    target.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = target / f"eval-{stamp}.json"
    md_path = target / f"eval-{stamp}.md"

    payload = asdict(report)
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(format_markdown(report), encoding="utf-8")
    # Stable "latest" aliases for tooling.
    (target / "latest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (target / "latest.md").write_text(format_markdown(report), encoding="utf-8")
    return {"json": json_path, "markdown": md_path}
