"""Unit tests for the evaluation harness (US-16).

Pure-function and scoring-logic tests only — no LLM backend or data archive is
required. The end-to-end ``run_evaluation`` path is exercised separately by the
``python -m src.evaluation.run_eval`` smoke run.
"""

from __future__ import annotations

from src.evaluation import metrics
from src.evaluation.gold import GoldCase, load_gold_cases
from src.evaluation.harness import score_case
from src.pipeline.schemas import (
    Complaint,
    ExtractedSignal,
    RetrievalEvidence,
    RiskAssessment,
    SignalReport,
    TrendSummary,
)


# --------------------------------------------------------------------------- #
# Pure metric functions
# --------------------------------------------------------------------------- #
def test_set_prf_perfect_overlap():
    res = metrics.set_prf(["a", "b"], ["a", "b"])
    assert res == {"precision": 1.0, "recall": 1.0, "f1": 1.0}


def test_set_prf_partial_overlap():
    res = metrics.set_prf(["a", "b", "c"], ["a", "b"])
    assert res["recall"] == 1.0
    assert abs(res["precision"] - 2 / 3) < 1e-9


def test_set_prf_both_empty_is_perfect():
    assert metrics.set_prf([], [])["f1"] == 1.0


def test_keyword_recall():
    assert metrics.keyword_recall(["artifact", "missing"], "an Artifact appeared") == 0.5
    assert metrics.keyword_recall([], "anything") == 1.0


def test_precision_at_k():
    assert metrics.precision_at_k([True, False, True, True], 3) == 2 / 3
    assert metrics.precision_at_k([], 5) == 0.0


def test_is_software_category():
    assert metrics.is_software_category("SW-FUNC")
    assert metrics.is_software_category("IMG-QUAL")
    assert not metrics.is_software_category("HW-MECH")


def test_hallucination_rate():
    assert metrics.hallucination_rate(0, 4) == 0.0
    assert metrics.hallucination_rate(1, 3) == 0.25
    assert metrics.hallucination_rate(0, 0) == 0.0


def test_mean_and_accuracy_empty():
    assert metrics.mean([]) is None
    assert metrics.accuracy([]) is None


# --------------------------------------------------------------------------- #
# Gold loader
# --------------------------------------------------------------------------- #
def test_load_gold_cases_ships_with_injection_case():
    cases = load_gold_cases()
    assert len(cases) >= 10
    by_id = {c.case_id: c for c in cases}
    assert "GOLD-INJ-001" in by_id
    assert by_id["GOLD-INJ-001"].expect_rejected is True
    # A normal case must not be flagged for rejection.
    assert by_id["GOLD-LNH-001"].expect_rejected is False


# --------------------------------------------------------------------------- #
# Scoring helpers / fixtures
# --------------------------------------------------------------------------- #
def _build_report(
    *,
    category: str,
    key_issues,
    confidence: float,
    risk_bucket: str,
    escalation: bool,
    llm_backed: bool,
    snippets,
    review_needed: bool = False,
    quality=None,
) -> SignalReport:
    complaint = Complaint(
        complaint_id="T-1",
        product_code="LNH",
        manufacturer="Test",
        event_type="Malfunction",
        date_received="20260101",
        narrative="n",
        source_report_number="r",
    )
    extraction = ExtractedSignal(
        complaint_id="T-1",
        qms_complaint_category=category,
        key_issues=list(key_issues),
        confidence=confidence,
        safety_flags={"mentions_death": False, "mentions_injury": False,
                      "mentions_patient_harm": False, "needs_manual_review": False},
    )
    retrieval = [
        RetrievalEvidence(
            evidence_id=f"E{i}",
            source_type="event",
            product_code="LNH",
            snippet=s,
            score=0.5,
        )
        for i, s in enumerate(snippets)
    ]
    risk = RiskAssessment(
        complaint_id="T-1",
        severity_level="S4",
        probability_level="P3",
        risk_bucket=risk_bucket,
        escalation_required=escalation,
        prrc_notification_required=False,
        capa_recommendation="do x",
        report_type="INCIDENT_ASSESSMENT",
        iso_14971_rationale="because",
        llm_backed=llm_backed,
    )
    trend = TrendSummary(
        product_code="LNH",
        total_events=10,
        software_problem_events=3,
        latest_year_events=2,
        previous_year_events=1,
        trend_direction="stable",
    )
    return SignalReport(
        report_id="SR-T-1",
        created_at="2026-01-01T00:00:00Z",
        trace_id="trace-1",
        complaint=complaint,
        extraction=extraction,
        retrieval=retrieval,
        risk=risk,
        trend=trend,
        report_type="INCIDENT_ASSESSMENT",
        orchestrator_questions=[],
        report_markdown="# Report\nbody",
        review_needed=review_needed,
        review_reasons=[],
        quality=quality or {},
    )


# --------------------------------------------------------------------------- #
# score_case
# --------------------------------------------------------------------------- #
def test_score_rejected_case_with_no_report():
    case = GoldCase(case_id="GOLD-INJ-001", product_code="LNH", narrative="x", expect_rejected=True)
    res = score_case(case, [])
    assert res.rejection_correct is True
    assert res.produced is False


def test_score_rejected_case_but_report_produced_fails():
    case = GoldCase(case_id="GOLD-INJ-001", product_code="LNH", narrative="x", expect_rejected=True)
    report = _build_report(
        category="SW-FUNC", key_issues=["x"], confidence=0.9, risk_bucket="ACCEPTABLE",
        escalation=False, llm_backed=True, snippets=["x"],
    )
    res = score_case(case, [report])
    assert res.rejection_correct is False
    assert res.produced is True


def test_score_llm_backed_case_all_hits():
    case = GoldCase(
        case_id="GOLD-LNH-001",
        product_code="LNH",
        narrative="x",
        software_related=True,
        gold_categories=["IMG-QUAL", "SW-ALGO"],
        key_issue_keywords=["artifact", "reconstruction"],
        expected_risk_buckets=["ALARP", "UNACCEPTABLE"],
        expect_escalation=True,
        relevant_keywords=["artifact", "image"],
    )
    report = _build_report(
        category="IMG-QUAL",
        key_issues=["reconstruction artifact on diffusion images"],
        confidence=0.9,
        risk_bucket="UNACCEPTABLE",
        escalation=True,
        llm_backed=True,
        snippets=["image shows an artifact", "unrelated text"],
        quality={"unsupported_claims": 0, "citation_count": 3},
    )
    res = score_case(case, [report], k=5)
    assert res.category_hit is True
    assert res.key_issue_recall == 1.0
    assert res.software_match is True
    assert res.risk_bucket_hit is True
    assert res.escalation_hit is True
    assert res.retrieval_precision_at_k == 0.5  # 1 of 2 snippets relevant
    assert res.hallucination_rate == 0.0
    assert res.schema_errors == []


def test_score_deterministic_fallback_skips_semantics():
    case = GoldCase(
        case_id="GOLD-LNH-001",
        product_code="LNH",
        narrative="x",
        software_related=True,
        gold_categories=["IMG-QUAL"],
        key_issue_keywords=["artifact"],
        expected_risk_buckets=["UNACCEPTABLE"],
        expect_escalation=True,
        relevant_keywords=["artifact"],
    )
    # NOT_AVAILABLE deterministic fallback: confidence 0.0, llm_backed False.
    report = _build_report(
        category="NOT_AVAILABLE",
        key_issues=["Not available"],
        confidence=0.0,
        risk_bucket="ALARP",
        escalation=False,
        llm_backed=False,
        snippets=["artifact present"],
        review_needed=True,
    )
    res = score_case(case, [report])
    assert res.llm_backed is False
    assert res.category_hit is None
    assert res.key_issue_recall is None
    assert res.software_match is None
    assert res.risk_bucket_hit is None
    assert res.escalation_hit is None
    # Low confidence must keep the review flag raised.
    assert res.review_consistency is True
    # Structural retrieval grounding still runs.
    assert res.retrieval_precision_at_k == 1.0
