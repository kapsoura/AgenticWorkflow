"""Unit tests for the LLM-driven section-narrative agent and the de-hardcoded
narrative section builders.

These tests use stub sub-agents and a fake LLM so no claude CLI or downloaded
archive is required. They verify that:
  * the deterministic regulatory verdicts are still rendered,
  * the interpretive prose now comes from the model (not hardcoded templates),
  * citation grounding is enforced (uncited narrative -> QM review flag),
  * the result is cached, and degrades to "Not available" with no backend.
"""

from __future__ import annotations

from src.agents import report_sections as rs
from src.agents.orchestration import OrchestrationAgent
from src.agents.report_sections import (
    NARRATIVE_SECTIONS,
    ReportContext,
    SECTION_BUILDERS,
    _benefit_risk,
    _executive_summary,
    _incident_reportability,
    _monitoring_recommendation,
    _regulatory_notification,
)
from src.pipeline.schemas import (
    Complaint,
    ExtractedSignal,
    RetrievalEvidence,
    RiskAssessment,
    TrendSummary,
)


# --------------------------------------------------------------------------- #
# Builders / fixtures
# --------------------------------------------------------------------------- #
def _complaint(event_type="Malfunction"):
    return Complaint(
        complaint_id="SIM-LNH-001",
        product_code="LNH",
        manufacturer="Philips",
        event_type=event_type,
        date_received="20200101",
        narrative="MRI reconstruction software froze mid-scan.",
        source_report_number="MW123",
    )


def _extraction(category="SW-FUNC", confidence=0.9):
    return ExtractedSignal(
        complaint_id="SIM-LNH-001",
        qms_complaint_category=category,
        key_issues=["software freeze", "reconstruction"],
        confidence=confidence,
        safety_flags={},
    )


def _risk(bucket="ALARP"):
    return RiskAssessment(
        complaint_id="SIM-LNH-001",
        severity_level="S3",
        probability_level="P2",
        risk_bucket=bucket,
        escalation_required=bucket in {"ALARP", "UNACCEPTABLE"},
        prrc_notification_required=bucket == "UNACCEPTABLE",
        capa_recommendation="Investigate firmware.",
        report_type="PSUR",
        iso_14971_rationale="S3xP2 maps to ALARP.",
        hazardous_situation="Scan interrupted.",
        harm="Repeat exposure.",
    )


def _trend(direction="upward"):
    return TrendSummary(
        product_code="LNH",
        total_events=120,
        software_problem_events=44,
        latest_year_events=30,
        previous_year_events=18,
        trend_direction=direction,
        trend_rationale="Rising YoY.",
    )


def _evidence():
    return [
        RetrievalEvidence(
            evidence_id="EV-1",
            source_type="MAUDE_EVENT",
            product_code="LNH",
            snippet="software froze during reconstruction",
            score=0.8,
        )
    ]


def _ctx(report_type="PSUR", event_type="Malfunction", category="SW-FUNC", confidence=0.9, bucket="ALARP"):
    return ReportContext(
        complaint=_complaint(event_type),
        extraction=_extraction(category, confidence),
        retrieval=_evidence(),
        risk=_risk(bucket),
        report_type=report_type,
        events_by_code={"LNH": []},
        trend=_trend(),
    )


class _FakeLLM:
    def __init__(self, payload, enabled=True):
        self.payload = payload
        self.enabled = enabled
        self.calls = 0

    def complete_json(self, system_prompt, user_prompt, fallback):
        self.calls += 1
        return dict(self.payload)


class _StubAgent:
    def __init__(self, llm=None):
        self.llm = llm


class _StubToolClient:
    enabled = False


def _orch(llm):
    return OrchestrationAgent(
        extraction_agent=_StubAgent(llm),
        retrieval_agent=None,
        risk_agent=None,
        report_agent=None,
        trend_analyzer=None,
        tool_client=_StubToolClient(),
    )


# --------------------------------------------------------------------------- #
# Map / metadata
# --------------------------------------------------------------------------- #
def test_narrative_sections_are_real_builders():
    assert set(NARRATIVE_SECTIONS).issubset(set(SECTION_BUILDERS))


# --------------------------------------------------------------------------- #
# ensure_section_narratives
# --------------------------------------------------------------------------- #
def test_cited_narratives_pass_through_without_review_flag():
    llm = _FakeLLM(
        {
            "executive_summary": "Per EV-1 the freeze pattern persists.",
            "benefit_risk": "Given EV-1, residual risk stays acceptable under controls.",
            "monitoring_recommendation": "Schedule review; EV-1 shows recurrence.",
        }
    )
    ctx = _ctx()
    orch = _orch(llm)

    out = orch.ensure_section_narratives(ctx)

    assert set(out) == {"executive_summary", "benefit_risk", "monitoring_recommendation"}
    assert all("uncited" not in v for v in out.values())
    assert ctx.review_needed is False


def test_uncited_narratives_are_flagged_for_review():
    llm = _FakeLLM(
        {
            "executive_summary": "The device remains broadly acceptable.",
            "benefit_risk": "Benefits outweigh risks.",
            "monitoring_recommendation": "Keep monitoring quarterly.",
        }
    )
    ctx = _ctx()
    orch = _orch(llm)

    out = orch.ensure_section_narratives(ctx)

    assert all(v.endswith("(uncited — flagged for QM review)") for v in out.values())
    assert ctx.review_needed is True
    assert any("cites no retrieved FDA record" in r for r in ctx.review_reasons)


def test_result_is_cached():
    llm = _FakeLLM({"executive_summary": "EV-1 supports.", "benefit_risk": "EV-1.", "monitoring_recommendation": "EV-1."})
    ctx = _ctx()
    orch = _orch(llm)

    orch.ensure_section_narratives(ctx)
    orch.ensure_section_narratives(ctx)

    assert llm.calls == 1  # second call served from ctx cache


def test_no_extraction_returns_not_available():
    llm = _FakeLLM({"executive_summary": "should not be used"})
    ctx = _ctx(category="NOT_AVAILABLE", confidence=0.0)
    orch = _orch(llm)

    out = orch.ensure_section_narratives(ctx)

    assert out == {k: "Not available" for k in out}
    assert llm.calls == 0


def test_no_backend_degrades_to_not_available():
    llm = _FakeLLM({}, enabled=False)
    ctx = _ctx()
    orch = _orch(llm)

    out = orch.ensure_section_narratives(ctx)

    assert all(v == "Not available" for v in out.values())


# --------------------------------------------------------------------------- #
# Builders render deterministic verdict + LLM prose, no canned templates
# --------------------------------------------------------------------------- #
class _FakeOrch:
    def __init__(self, narratives, trend):
        self._narratives = narratives
        self._trend = trend

    def ensure_section_narratives(self, ctx):
        return self._narratives

    def ensure_trend(self, ctx):
        return self._trend


_OLD_CANNED = [
    "Based on the data reviewed, the benefit-risk ratio is",
    "continuous acceptability of the benefit-risk determination",
    "risks are not outweighed by",
    "Prepare regulatory vigilance notification per MDR/regulation timelines",
    "Trend rising; schedule a focused review",
    "Trend flat; maintain monthly management-review monitoring",
]


def test_builders_emit_verdict_plus_llm_prose_without_canned_text():
    narratives = {
        "executive_summary": "Per EV-1, posture holds.",
        "benefit_risk": "Per EV-1, acceptable under controls.",
        "incident_reportability": "Per EV-1, criteria justified.",
        "regulatory_notification": "Per EV-1, notify per timelines.",
        "monitoring_recommendation": "Per EV-1, schedule review.",
    }
    ctx = _ctx(report_type="INCIDENT_ASSESSMENT", event_type="Injury", bucket="UNACCEPTABLE")
    orch = _FakeOrch(narratives, _trend())

    exec_md = _executive_summary(ctx, orch)
    br_md = _benefit_risk(ctx, orch)
    inc_md = _incident_reportability(ctx, orch)
    reg_md = _regulatory_notification(ctx, orch)
    mon_md = _monitoring_recommendation(ctx, orch)
    blob = "\n".join([exec_md, br_md, inc_md, reg_md, mon_md])

    # Deterministic verdicts still present.
    assert "Risk Bucket: UNACCEPTABLE" in exec_md
    assert "Risk Bucket: UNACCEPTABLE" in br_md
    assert "Reportable Serious Incident: **YES**" in inc_md
    assert "Escalation Required: True" in reg_md
    assert "Current Trend Direction:" in mon_md

    # LLM prose present.
    assert "Per EV-1" in exec_md and "Per EV-1" in br_md and "Per EV-1" in mon_md

    # None of the removed hardcoded templates leak through.
    for canned in _OLD_CANNED:
        assert canned not in blob
