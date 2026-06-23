"""
Risk Analysis Agent — ISO 14971:2019 (two-pass) integrated into the LangGraph flow.

Two-pass design:
    Pass 1  →  generate complete risk assessment + CAPA from complaint context
    Pass 2  →  self-critique against a checklist; return revised assessment

The LLM runs through the project's ``claude`` CLI client (``AnthropicClient`` →
``CustomAnthropicClient``); **no Anthropic API key is required**. When the CLI is
unavailable the agent falls back to a deterministic ISO 14971 estimate so the flow
still runs fully offline (same contract, lower fidelity).

Constitutional guardrail (enforced in Python after Pass 2):
    ALARP or UNACCEPTABLE with zero evidence citations → forced downgrade to ACCEPTABLE.
Escalation flags are computed deterministically in Python, never by the LLM.

Episodic memory:
    load_past_reports() reads prior similar cases from a small SQLite table.
    remember_report() persists a completed report (called by the flow after assembly).

Integration surface:
    * ``RiskAnalysisAgent.assess(complaint, evidence, extraction, trend) -> RiskAssessment``
      is what the LangGraph ``_risk`` node calls; it adapts our dataclasses to/from
      the rich assessment below.
    * ``risk_analysis_agent(state: dict) -> dict`` keeps the standalone state-dict
      interface for direct/experimental use.
"""

import json
import logging
import re
import sqlite3
from pathlib import Path

from src.config import RUNTIME_DIR
from src.pipeline.schemas import Complaint, ExtractedSignal, RetrievalEvidence, RiskAssessment, TrendSummary
from src.utils.llm_client import AnthropicClient

logger = logging.getLogger(__name__)

# Product code → imaging modality (used for episodic-memory matching + context).
MODALITY_BY_CODE = {
    "LNH": "MRI",
    "JAK": "CT",
    "LLZ": "Ultrasound",
    "IYE": "CT X-ray",
    "IZL": "Digital X-ray",
}

_ELEVATED = {"ALARP", "UNACCEPTABLE"}

# ── SQLite episodic memory ──────────────────────────────────────────────────────

_DB_PATH = RUNTIME_DIR / "risk_episodic_memory.db"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS signal_reports (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id           TEXT NOT NULL,
    trace_id              TEXT NOT NULL,
    generated_at          TEXT NOT NULL,
    failure_mode          TEXT,
    modality              TEXT,
    qms_complaint_category TEXT,
    risk_level            TEXT,
    severity_level        TEXT,
    probability_level     TEXT,
    evidence_count        INTEGER DEFAULT 0,
    capa_precedent        TEXT,
    approval_status       TEXT DEFAULT 'DRAFT',
    report_json           TEXT
);
"""

_db_initialized = False


def init_db(db_path: Path = _DB_PATH) -> None:
    """Create the signal_reports table if absent. Safe to call repeatedly."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(_CREATE_TABLE_SQL)
        conn.commit()


def _ensure_db() -> None:
    global _db_initialized
    if not _db_initialized:
        init_db()
        _db_initialized = True


def load_past_reports(
    failure_mode: str,
    modality: str,
    limit: int = 5,
    db_path: Path = _DB_PATH,
) -> list[dict]:
    """Return up to `limit` past reports matching this failure_mode/modality ([] if none)."""
    _ensure_db()
    query = """
        SELECT document_id, generated_at, failure_mode, modality,
               qms_complaint_category, risk_level, severity_level,
               probability_level, evidence_count, capa_precedent
        FROM signal_reports
        WHERE modality = ? OR failure_mode LIKE ?
        ORDER BY generated_at DESC
        LIMIT ?
    """
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, (modality, f"%{(failure_mode or '')[:30]}%", limit)).fetchall()
            return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        logger.warning("load_past_reports failed: %s", exc)
        return []


def save_report(
    document_id: str,
    trace_id: str,
    generated_at: str,
    failure_mode: str,
    modality: str,
    qms_complaint_category: str,
    risk_level: str,
    severity_level: str,
    probability_level: str,
    evidence_count: int,
    capa_precedent: str,
    report_json: str,
    db_path: Path = _DB_PATH,
) -> None:
    """Persist a completed report to episodic memory."""
    _ensure_db()
    sql = """
        INSERT INTO signal_reports
            (document_id, trace_id, generated_at, failure_mode, modality,
             qms_complaint_category, risk_level, severity_level,
             probability_level, evidence_count, capa_precedent, report_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """
    with sqlite3.connect(db_path) as conn:
        conn.execute(sql, (
            document_id, trace_id, generated_at, failure_mode, modality,
            qms_complaint_category, risk_level, severity_level,
            probability_level, evidence_count, capa_precedent, report_json,
        ))
        conn.commit()


# ── Prompts ─────────────────────────────────────────────────────────────────────

_PASS1_SYSTEM = """\
You are a medical device risk analyst applying ISO 14971:2019.

Your task: given a device complaint, prior FDA evidence, trend data, and any past similar
signal reports, produce a complete risk assessment and CAPA recommendation.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ISO 14971 SEVERITY SCALE (Annex D)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
S1 (Negligible)   – No injury; no clinical impact; inconvenience only.
S2 (Minor)        – Minor, reversible injury; minor delay in diagnosis.
S3 (Serious)      – Serious injury; major delay in diagnosis; repeat procedure required.
S4 (Critical)     – Permanent injury; surgical intervention required.
S5 (Catastrophic) – Death.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ISO 14971 PROBABILITY SCALE (calibrated to ~14,000 FDA imaging device events)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
P1 (Improbable) – < 1 per 1,000,000 uses.
P2 (Remote)     – 1 per 100,000 to 1 per 1,000,000.
P3 (Occasional) – 1 per 10,000 to 1 per 100,000.
P4 (Probable)   – 1 per 1,000 to 1 per 10,000.
P5 (Frequent)   – > 1 per 1,000.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RISK ACCEPTABILITY MATRIX (5×5)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ACCEPTABLE:    S1×(P1–P5)  S2×(P1–P3)  S3×(P1–P2)  S4×P1   S5×P1
ALARP:         S2×(P4–P5)  S3×(P3–P4)  S4×(P2–P3)  S5×(P2–P3)
UNACCEPTABLE:  S3×P5  S4×(P4–P5)  S5×(P4–P5)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EVIDENCE CITATION REQUIREMENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NEVER assign ALARP or UNACCEPTABLE unless evidence_basis contains at least one specific
FDA record (MAUDE report number or recall ID) that justifies the probability estimate.
If you cannot cite evidence, assign ACCEPTABLE and document the uncertainty.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REASONING APPROACH
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Identify the hazardous situation (device failure → patient/operator exposure path).
2. Identify the specific harm (what injury or consequence results).
3. Justify severity S1–S5 from the complaint and evidence.
4. Justify probability P1–P5 using event counts, recall history, and trend data.
5. Apply the matrix to determine risk_level.
6. Cite real FDA record IDs in evidence_basis — do not invent IDs.
7. Generate CAPA proportionate to risk_level:
   UNACCEPTABLE → immediate containment within hours is mandatory.
   ALARP         → immediate action and formal investigation.
   ACCEPTABLE    → investigation and preventive action.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Return ONLY a valid JSON object. No markdown fences, no prose outside the JSON.

{
  "chain_of_thought": "Step-by-step reasoning (not shown to QM, used for audit trail)",
  "hazardous_situation": "Specific situation: device failure → operator/patient exposure path",
  "harm": "Specific harm: injury or consequence to patient or operator",
  "severity_level": "S1|S2|S3|S4|S5",
  "severity_rationale": "1–2 sentences citing complaint language and evidence",
  "probability_level": "P1|P2|P3|P4|P5",
  "probability_rationale": "Cite specific FDA record IDs to justify — e.g. '3 MAUDE events (MW3021547, MW2998341, MW3014892) + 1 Class II recall (Z-2024-00423) for the same failure mode'",
  "risk_level": "ACCEPTABLE|ALARP|UNACCEPTABLE",
  "evidence_basis": [
    {"source": "MAUDE|RECALL", "id": "string", "relevance": "one sentence why this record applies"}
  ],
  "uncertainty": "What is unknown or unconfirmed — e.g. patient outcome not reported, root cause not yet verified",
  "capa_immediate": "Immediate containment action and timeline (e.g. 'Within 24h: notify field service to check SW version at all affected sites')",
  "capa_investigation": "Root cause investigation steps and responsible function",
  "capa_corrective": "Corrective action per ISO 13485 §8.5.2 (fix the root cause)",
  "capa_preventive": "Preventive action per ISO 13485 §8.5.3 (prevent recurrence in other products)",
  "capa_verification": "How to verify the CAPA is effective (test, audit, metric)",
  "capa_effectiveness": "Measurable criteria for effectiveness (e.g. '0 recurrence events in 90 days post-fix')",
  "capa_precedent": "Real MAUDE report number or recall ID used as basis for the CAPA recommendation"
}
"""

_PASS2_USER = """\
You have just produced a risk assessment (your draft JSON is provided below). Review it
against this checklist and return a corrected version:

CHECKLIST:
1. MATRIX MATH — Does your S×P combination map correctly to the risk_level per the defined matrix?
   Verify cell by cell. Correct if wrong.

2. CITATION COVERAGE — If risk_level is ALARP or UNACCEPTABLE, does evidence_basis contain at
   least one specific FDA record ID? If not, either add citations from the provided evidence or
   downgrade risk_level to ACCEPTABLE.

3. CAPA PROPORTIONALITY —
   • UNACCEPTABLE: capa_immediate must specify a concrete action within hours.
   • ALARP: capa_immediate must be present and specific.
   • ACCEPTABLE: capa_investigation should still be present.
   Fix any mismatch.

4. PRECEDENT LINKAGE — Does capa_precedent cite a real ID from the evidence provided?
   If you used a fabricated ID, correct it to a real one from the input, or set it to null.

5. UNCERTAINTY — Does the uncertainty field capture what would change this assessment?

Return ONLY a revised JSON object with the same schema as the draft.
If a field needs no change, carry it forward unchanged. No commentary outside the JSON.
"""


# ── Normalisation helpers ───────────────────────────────────────────────────────

def _norm_level(value, prefix: str, default: str) -> str:
    if not value:
        return default
    m = re.search(rf"{prefix}[1-5]", str(value).upper())
    return m.group(0) if m else default


def _norm_bucket(value) -> str:
    v = str(value or "").upper()
    for bucket in ("UNACCEPTABLE", "ALARP", "ACCEPTABLE"):
        if bucket in v:
            return bucket
    return "ACCEPTABLE"


def _report_type(event_type: str, risk_bucket: str) -> str:
    """Primary report type under the PSUR / INCIDENT_ASSESSMENT / CAPA taxonomy."""
    if event_type in {"death", "injury"} or risk_bucket == "UNACCEPTABLE":
        return "INCIDENT_ASSESSMENT"
    if risk_bucket == "ALARP":
        return "CAPA"
    return "PSUR"


# ── Context + LLM passes ────────────────────────────────────────────────────────

def _build_context(state: dict, past_reports: list[dict]) -> str:
    if past_reports:
        past = "\n## Past Similar Signal Reports (episodic memory)\n" + "".join(
            f"- {r['document_id']} ({(r['generated_at'] or '')[:10]}): "
            f"{r['failure_mode']} / {r['modality']} → {r['risk_level']} "
            f"[{r['severity_level']}×{r['probability_level']}] precedent: {r.get('capa_precedent', 'N/A')}\n"
            for r in past_reports
        )
    else:
        past = "\n## Past Similar Signal Reports\nNone found in episodic memory.\n"

    return f"""
## Complaint
{state.get('complaint_text', '')}

## Extracted Fields
- Modality:            {state.get('modality')}
- Device:              {state.get('device_model')} by {state.get('manufacturer')}
- Software Version:    {state.get('software_version')}
- Component:           {state.get('component')}
- Failure Mode:        {state.get('failure_mode')}
- Severity Indicator:  {state.get('severity_indicator')} (initial estimate from extraction)
- QMS Category:        {state.get('qms_complaint_category')}
- Safety Related:      {state.get('is_safety_related')}

## FDA Evidence
{state.get('regulatory_context', 'No regulatory context available.')}

Matching Adverse Events:
{json.dumps(state.get('matching_events', []), indent=2)}

Matching Recalls:
{json.dumps(state.get('matching_recalls', []), indent=2)}

## Trend Data
- Cluster:       {state.get('cluster_label')} (size: {state.get('cluster_size', 'unknown')})
- Trend:         {state.get('trend_flag')} (30-day growth rate: {state.get('growth_rate_30d')})
- Similar IDs:   {state.get('similar_event_ids', [])}
{past}"""


def _two_pass_llm(context: str, llm: AnthropicClient) -> dict | None:
    """Run Pass 1 + Pass 2 through the claude CLI client. Returns None if unusable."""
    p1 = llm.complete_json(
        system_prompt=_PASS1_SYSTEM,
        user_prompt=f"Perform ISO 14971 risk assessment:\n{context}",
        fallback={},
    )
    if not isinstance(p1, dict) or not p1.get("severity_level"):
        return None

    p2 = llm.complete_json(
        system_prompt=_PASS1_SYSTEM,
        user_prompt=_PASS2_USER + "\n\n## Your draft assessment (JSON)\n" + json.dumps(p1),
        fallback=p1,
    )
    return p2 if isinstance(p2, dict) and p2.get("severity_level") else p1


# ── Standalone state-dict agent ─────────────────────────────────────────────────

def risk_analysis_agent(state: dict) -> dict:
    """Full ISO 14971 assessment over a flat state dict (two-pass + guardrail + memory)."""
    _ensure_db()
    llm = AnthropicClient()

    failure_mode = state.get("failure_mode") or ""
    modality = state.get("modality") or ""
    past_reports = load_past_reports(failure_mode, modality)

    if not llm.enabled:
        mode = "NOT AVAILABLE (LLM disabled)"
    elif llm._backend == "api":
        mode = "LIVE (Anthropic API)"
    else:
        mode = "LIVE (claude CLI)"
    print(f"\n{'─' * 64}\n  RISK ANALYSIS AGENT  [{mode}]\n{'─' * 64}")
    print(f"  failure_mode={failure_mode!r} modality={modality!r} "
          f"events={len(state.get('matching_events') or [])} recalls={len(state.get('matching_recalls') or [])} "
          f"past_reports={len(past_reports)}")

    context = _build_context(state, past_reports)

    result = _two_pass_llm(context, llm) if llm.enabled else None
    if result is None:
        # LLM-only: no heuristic/deterministic fallback. Surface an explicit
        # "agent not available" so the API can show it instead of inventing data.
        print("  → RISK AGENT NOT AVAILABLE (LLM disabled or returned no usable assessment)")
        return {
            "hazardous_situation": "",
            "harm": "",
            "severity_level": "",
            "severity_rationale": "",
            "probability_level": "",
            "probability_rationale": "",
            "risk_level": "NOT_AVAILABLE",
            "evidence_basis": [],
            "uncertainty": "Agent not available — risk analysis requires the LLM "
            "(set CLAUDE_CLI_PATH or ANTHROPIC_API_KEY).",
            "capa_immediate": "",
            "capa_investigation": "",
            "capa_corrective": "",
            "capa_preventive": "",
            "capa_verification": "",
            "capa_effectiveness": "",
            "capa_precedent": None,
            "escalation_required": False,
            "prrc_notification_required": False,
            "fsca_required": False,
            "gate3_passed": False,
            "_llm_backed": False,
        }
    llm_backed = True

    severity = _norm_level(result.get("severity_level"), "S", "S2")
    probability = _norm_level(result.get("probability_level"), "P", "P2")
    risk = _norm_bucket(result.get("risk_level"))
    evidence = result.get("evidence_basis") or []

    # Constitutional guardrail — elevated risk needs at least one citation.
    if risk in _ELEVATED and len(evidence) == 0:
        logger.warning("Guardrail: %s with 0 citations → downgrading to ACCEPTABLE", risk)
        result["uncertainty"] = (
            f"[DOWNGRADED from {risk}] Elevated risk assigned with no FDA citations; "
            "requires human review with direct evidence lookup. " + (result.get("uncertainty") or "")
        )
        risk = "ACCEPTABLE"

    escalation_required = risk in _ELEVATED
    prrc_notification = risk == "UNACCEPTABLE"
    fsca_required = False  # needs confirmed root cause + active distribution — human decision
    gate3_passed = not (risk == "UNACCEPTABLE" and len(evidence) == 0)

    print(f"  → risk={risk} severity={severity} probability={probability} "
          f"citations={len(evidence)} escalation={escalation_required} llm_backed={llm_backed}")

    return {
        "hazardous_situation": result.get("hazardous_situation"),
        "harm": result.get("harm"),
        "severity_level": severity,
        "severity_rationale": result.get("severity_rationale"),
        "probability_level": probability,
        "probability_rationale": result.get("probability_rationale"),
        "risk_level": risk,
        "evidence_basis": evidence,
        "uncertainty": result.get("uncertainty"),
        "capa_immediate": result.get("capa_immediate"),
        "capa_investigation": result.get("capa_investigation"),
        "capa_corrective": result.get("capa_corrective"),
        "capa_preventive": result.get("capa_preventive"),
        "capa_verification": result.get("capa_verification"),
        "capa_effectiveness": result.get("capa_effectiveness"),
        "capa_precedent": result.get("capa_precedent"),
        "escalation_required": escalation_required,
        "prrc_notification_required": prrc_notification,
        "fsca_required": fsca_required,
        "gate3_passed": gate3_passed,
        "_llm_backed": llm_backed,
    }


# ── Flow adapter ────────────────────────────────────────────────────────────────

class RiskAnalysisAgent:
    """Adapts the rich ISO 14971 agent to the flow's dataclass contract."""

    def assess(
        self,
        complaint: Complaint,
        evidence: list[RetrievalEvidence],
        extraction: "ExtractedSignal | None" = None,
        trend: "TrendSummary | None" = None,
    ) -> RiskAssessment:
        state = self._build_state(complaint, evidence, extraction, trend)
        result = risk_analysis_agent(state)
        return self._to_assessment(complaint, result)

    @staticmethod
    def _build_state(complaint, evidence, extraction, trend) -> dict:
        events, recalls = [], []
        for e in evidence or []:
            record = {
                "id": e.evidence_id,
                "source_type": e.source_type,
                "snippet": e.snippet,
                "score": e.score,
                **(e.metadata or {}),
            }
            (recalls if e.source_type == "FDA_RECALL" else events).append(record)

        key_issues = list(extraction.key_issues) if extraction else []
        category = extraction.qms_complaint_category if extraction else None
        failure_mode = (key_issues[0] if key_issues else category) or ""
        safety_flags = extraction.safety_flags if extraction else {}
        regulatory = "; ".join(r.get("snippet", "") for r in recalls[:3]) or "No recall precedent retrieved."

        return {
            "complaint_text": complaint.narrative,
            "event_type": complaint.event_type,
            "failure_mode": failure_mode,
            "key_issues": key_issues,
            "modality": MODALITY_BY_CODE.get(complaint.product_code, complaint.product_code),
            "manufacturer": complaint.manufacturer,
            "device_model": None,
            "software_version": None,
            "component": None,
            "severity_indicator": complaint.event_type,
            "qms_complaint_category": category,
            "is_safety_related": any(bool(v) for v in (safety_flags or {}).values()),
            "matching_events": events,
            "matching_recalls": recalls,
            "regulatory_context": regulatory,
            "cluster_label": getattr(trend, "trend_direction", None) if trend else None,
            "cluster_size": getattr(trend, "total_events", None) if trend else None,
            "trend_flag": getattr(trend, "trend_direction", None) if trend else None,
            "growth_rate_30d": None,
            "similar_event_ids": [e["id"] for e in events[:5]],
        }

    @staticmethod
    def _to_assessment(complaint, result: dict) -> RiskAssessment:
        if not result.get("_llm_backed", False):
            # LLM did not produce an assessment — no fabricated/heuristic values.
            return RiskAssessment(
                complaint_id=complaint.complaint_id,
                severity_level="",
                probability_level="",
                risk_bucket="NOT_AVAILABLE",
                escalation_required=False,
                prrc_notification_required=False,
                capa_recommendation="",
                report_type="PSUR",
                iso_14971_rationale=result.get("uncertainty")
                or "Agent not available — risk analysis requires the LLM.",
                hazardous_situation="",
                harm="",
                severity_rationale="",
                probability_rationale="",
                evidence_basis=[],
                uncertainty=result.get("uncertainty") or "",
                fsca_required=False,
                llm_backed=False,
            )

        risk = _norm_bucket(result.get("risk_level"))
        severity = _norm_level(result.get("severity_level"), "S", "S2")
        probability = _norm_level(result.get("probability_level"), "P", "P2")

        capa_recommendation = (
            result.get("capa_immediate")
            or result.get("capa_corrective")
            or result.get("capa_investigation")
            or "Monitor and investigate per QMS."
        )
        haz = result.get("hazardous_situation") or ""
        harm = result.get("harm") or ""
        iso_rationale = " ".join(
            part for part in [
                f"Hazardous situation: {haz}." if haz else "",
                f"Harm: {harm}." if harm else "",
                (f"Severity {severity}: {result.get('severity_rationale', '')}".strip()),
                (f"Probability {probability}: {result.get('probability_rationale', '')}".strip()),
                f"Risk {risk} per ISO 14971 acceptability matrix.",
            ] if part
        ).strip()

        return RiskAssessment(
            complaint_id=complaint.complaint_id,
            severity_level=severity,
            probability_level=probability,
            risk_bucket=risk,
            escalation_required=bool(result.get("escalation_required", risk in _ELEVATED)),
            prrc_notification_required=bool(result.get("prrc_notification_required", risk == "UNACCEPTABLE")),
            capa_recommendation=capa_recommendation,
            report_type=_report_type(complaint.event_type.lower(), risk),
            iso_14971_rationale=iso_rationale,
            hazardous_situation=haz,
            harm=harm,
            severity_rationale=result.get("severity_rationale") or "",
            probability_rationale=result.get("probability_rationale") or "",
            evidence_basis=result.get("evidence_basis") or [],
            uncertainty=result.get("uncertainty") or "",
            capa_immediate=result.get("capa_immediate") or "",
            capa_investigation=result.get("capa_investigation") or "",
            capa_corrective=result.get("capa_corrective") or "",
            capa_preventive=result.get("capa_preventive") or "",
            capa_verification=result.get("capa_verification") or "",
            capa_effectiveness=result.get("capa_effectiveness") or "",
            capa_precedent=result.get("capa_precedent") or "",
            fsca_required=bool(result.get("fsca_required", False)),
            llm_backed=bool(result.get("_llm_backed", False)),
        )


def remember_report(report, extraction, complaint, trace_id: str, evidence_count: int) -> None:
    """Persist a completed report to episodic memory (best-effort; never raises into the flow)."""
    try:
        key_issues = list(extraction.key_issues) if extraction else []
        category = extraction.qms_complaint_category if extraction else ""
        failure_mode = (key_issues[0] if key_issues else category) or ""
        save_report(
            document_id=report.report_id,
            trace_id=trace_id,
            generated_at=report.created_at,
            failure_mode=failure_mode,
            modality=MODALITY_BY_CODE.get(complaint.product_code, complaint.product_code),
            qms_complaint_category=category or "",
            risk_level=report.risk.risk_bucket,
            severity_level=report.risk.severity_level,
            probability_level=report.risk.probability_level,
            evidence_count=evidence_count,
            capa_precedent=report.risk.capa_precedent or "",
            report_json=json.dumps({
                "report_id": report.report_id,
                "report_type": report.report_type,
                "risk_bucket": report.risk.risk_bucket,
            }),
        )
    except Exception as exc:  # noqa: BLE001 — episodic memory must never break the flow
        logger.warning("remember_report failed: %s", exc)
