#!/usr/bin/env python3
"""
demo.py -- Single-command demo of the Multi-Agent Quality Intelligence Pipeline.

Runs all four agents in sequence on a sample FDA adverse event complaint and
prints their output to the terminal.

Usage:
    python demo.py
    python demo.py --complaint "CT scanner image noise increased during cardiac scan" --product-code JAK
    python demo.py --product-code LLZ

Agents:
    1  Extraction      Raw narrative → structured QMS complaint record
    3  Retrieval       QMS record → similar FDA events & recall precedents
    2  Risk Analysis   Evidence → ISO 14971 risk bucket + CAPA
    4  Report          All above → regulatory report draft (PSUR / CAPA / Incident)

Requires: pip install -r requirements.txt
Optional: set ANTHROPIC_API_KEY in .env for LLM-backed output (falls back to
          deterministic rules when not configured).
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import textwrap

# Force UTF-8 output on Windows so Unicode chars inside agents don't crash
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

# -- env ------------------------------------------------------------------------
from dotenv import load_dotenv
load_dotenv()

# -- paths ----------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "signal_intelligence.db"

SAMPLE_COMPLAINTS = {
    "LNH": "MRI system showed banding artifacts during cardiac MRI sequence. "
           "Banding artifact visible in reconstructed images, repeat scan required. "
           "Software version 4.2.1, reported by field service engineer.",
    "JAK": "CT scanner image noise increased unexpectedly during a contrast-enhanced "
           "abdominal scan. Reconstruction algorithm produced images with streak "
           "artifacts. Patient received an additional low-dose verification scan.",
    "LLZ": "Ultrasound probe intermittently loses connection during cardiac echo exam. "
           "Image freezes for 2-3 seconds, then recovers. Occurred 4 times in one session.",
    "IZL": "Digital X-ray system produced overexposed images despite automatic exposure "
           "control being active. Three patients received repeat exposures before issue "
           "was identified by radiographer.",
    "QKO": "PCR instrument reported false-negative results for known positive samples. "
           "Occurred after a software update to version 3.1.0. Affected 12 patient samples.",
}

MODALITY_NAMES = {
    "LNH": "MRI System",
    "JAK": "CT Scanner",
    "LLZ": "Ultrasound",
    "IYE": "CT X-ray",
    "IZL": "Digital X-ray",
    "MQB": "Molecular Dx",
    "GKZ": "Hematology Analyzer",
    "QKO": "PCR System",
}

SEP = "-" * 68


def _hdr(title: str, agent_num: str = "") -> None:
    label = f"  AGENT {agent_num} -- {title}  " if agent_num else f"  {title}  "
    print(f"\n{SEP}")
    print(label)
    print(SEP)


def _load_events(product_code: str, limit: int = 200) -> list[dict]:
    """Load events from the pre-ingested SQLite DB for the retrieval agent."""
    if not DB_PATH.exists():
        print(f"  [warn] DB not found at {DB_PATH} -- retrieval will use empty archive")
        return []
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT e.report_number, e.event_type, e.narrative,
                   GROUP_CONCAT(ep.problem_code, '; ') AS product_problems
            FROM events e
            LEFT JOIN event_problems ep ON ep.event_id = e.id
            WHERE e.product_code = ?
            GROUP BY e.id
            LIMIT ?
            """,
            (product_code, limit),
        ).fetchall()
        conn.close()
        return [
            {
                "report_number": r["report_number"],
                "event_type": r["event_type"] or "Unknown",
                "product_problems": [p.strip() for p in (r["product_problems"] or "").split(";") if p.strip()],
                "narrative": (r["narrative"] or "")[:300],
            }
            for r in rows
        ]
    except sqlite3.Error as exc:
        print(f"  [warn] DB query failed: {exc}")
        return []


def _db_stats() -> dict:
    if not DB_PATH.exists():
        return {}
    try:
        conn = sqlite3.connect(str(DB_PATH))
        total = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        by_code = conn.execute(
            "SELECT product_code, COUNT(*) as n FROM events GROUP BY product_code ORDER BY n DESC"
        ).fetchall()
        conn.close()
        return {"total": total, "by_code": by_code}
    except sqlite3.Error:
        return {}


def _run_live_retrieval(complaint, extraction, product_code: str) -> list:
    """Call Sai's RetrievalAgent (MCP -> live OpenFDA) and convert to RetrievalEvidence."""
    try:
        # Sai's agent lives at the repo root and uses Mohammad's ExtractionOutput schema
        from retrieval_agent import RetrievalAgent as LiveRetrievalAgent
        from schemas import (
            ExtractionOutput as Ext, Modality, EventType as ET,
            SeverityLevel, QMSCategory,
        )
        from src.pipeline.schemas import RetrievalEvidence
    except ImportError as e:
        print(f"  [warn] Live retrieval import failed: {e}")
        print("  [warn] Falling back to offline archive.")
        return []

    # Map qms_complaint_category string -> QMSCategory enum
    _cat = {
        "SW-FUNC": QMSCategory.SW_FUNC, "SW-ALGO": QMSCategory.SW_ALGO,
        "SW-DATA": QMSCategory.SW_DATA,  "IMG-QUAL": QMSCategory.IMG_QUAL,
        "HW-FAIL": QMSCategory.HW_MECH,  "HW-MECH": QMSCategory.HW_MECH,
    }
    # Map product_code -> Modality enum
    _mod = {
        "LNH": Modality.MRI, "JAK": Modality.CT, "IYE": Modality.CT,
        "LLZ": Modality.ULTRASOUND, "IZL": Modality.XRAY,
        "MQB": Modality.MOLECULAR,  "GKZ": Modality.UNKNOWN,
        "QKO": Modality.MOLECULAR,
    }
    key_issues = list(extraction.key_issues or [])
    failure_mode = key_issues[0] if key_issues else "device malfunction"

    ext_output = Ext(
        report_id=complaint.complaint_id,
        modality=_mod.get(product_code, Modality.UNKNOWN),
        manufacturer=complaint.manufacturer or "Unknown",
        device_model=MODALITY_NAMES.get(product_code, product_code),
        component="device subsystem",
        failure_mode=failure_mode,
        symptom=key_issues[1] if len(key_issues) > 1 else failure_mode,
        event_type=ET.MALFUNCTION,
        severity_indicator=SeverityLevel.S3,
        software_related="SW" in (extraction.qms_complaint_category or ""),
        is_safety_related=bool((extraction.safety_flags or {}).get("mentions_patient_harm")),
        usability_concern=False,
        security_concern=False,
        qms_complaint_category=_cat.get(extraction.qms_complaint_category, QMSCategory.UNKNOWN),
        patient_impact=complaint.narrative[:100],
        confidence=extraction.confidence,
    )

    try:
        agent = LiveRetrievalAgent()
        output = agent.run(ext_output)
    except Exception as e:
        print(f"  [warn] Live retrieval failed: {e}")
        return []

    # Convert RetrievalOutput -> List[RetrievalEvidence]
    evidence = []
    for ev in output.similar_events:
        evidence.append(RetrievalEvidence(
            evidence_id=ev.report_id,
            source_type="MAUDE_EVENT",
            snippet=ev.narrative_snippet,
            score=ev.similarity_score,
        ))
    for rec in output.matched_recalls:
        evidence.append(RetrievalEvidence(
            evidence_id=rec.recall_id or rec.firm,
            source_type="FDA_RECALL",
            snippet=(rec.reason_for_recall or "")[:200],
            score=0.9,
            metadata={"root_cause": rec.root_cause, "firm": rec.firm},
        ))
    return evidence


def run_demo(complaint_text: str, product_code: str, live: bool = False) -> None:
    product_code = product_code.upper()
    device_name = MODALITY_NAMES.get(product_code, product_code)

    # -- Banner ----------------------------------------------------------------
    print(f"\n{'=' * 68}")
    print("  MULTI-AGENT QUALITY INTELLIGENCE PIPELINE -- DEMO")
    print(f"  IISc Bangalore | Deep Learning (DA225o) | {datetime.now().strftime('%Y-%m-%d')}")
    print(f"{'=' * 68}")

    stats = _db_stats()
    if stats:
        print(f"\n  Archive: {stats['total']:,} FDA adverse events loaded")
        codes = ", ".join(f"{row[0]}={row[1]:,}" for row in (stats.get("by_code") or []))
        print(f"  By code: {codes}")

    print(f"\n  Complaint  : {complaint_text[:90]}{'...' if len(complaint_text) > 90 else ''}")
    print(f"  Device     : {device_name} ({product_code})")

    # -- Import agents (done here so import errors surface clearly) ------------
    try:
        from src.pipeline.schemas import (
            Complaint, ExtractedSignal, RetrievalEvidence, RiskAssessment, TrendSummary,
        )
        from src.agents.extraction import ExtractionAgent
        from src.agents.retrieval import RetrievalAgent
        from src.agents.risk_analysis import RiskAnalysisAgent
        from src.agents.report_generation import ReportGenerationAgent
        from src.agents.archive_trend import ArchiveTrendAnalyzer
        from src.agents.orchestration import OrchestrationAgent
        from src.agents.report_sections import ReportContext
    except ImportError as exc:
        print(f"\n  [error] Import failed: {exc}")
        print("  Run: pip install -r requirements.txt")
        sys.exit(1)

    # -- Build complaint object ------------------------------------------------
    complaint = Complaint(
        complaint_id=f"DEMO-{product_code}-{uuid4().hex[:6].upper()}",
        product_code=product_code,
        manufacturer="Demo Manufacturer",
        event_type="Malfunction",
        date_received=datetime.now(timezone.utc).strftime("%Y%m%d"),
        narrative=complaint_text,
        source_report_number="DEMO-SUBMISSION",
    )

    # -- Agent 1: Extraction ---------------------------------------------------
    _hdr("EXTRACTION", "1")
    print("  Input : raw complaint narrative")
    print("  LLM   : Anthropic API (ANTHROPIC_API_KEY) or CLI (CLAUDE_CLI_PATH) -- falls back to keyword rules\n")

    extraction_agent = ExtractionAgent()
    extraction: ExtractedSignal = extraction_agent.extract(complaint)

    backend = getattr(extraction_agent, "last_backend", "unknown")
    print(f"  Backend            : {backend}")
    print(f"  QMS Category       : {extraction.qms_complaint_category}")
    print(f"  Key Issues         : {', '.join(extraction.key_issues) or 'none'}")
    print(f"  Confidence         : {extraction.confidence:.2f}")
    print(f"  ISO 13485 Clauses  : {', '.join(extraction.iso_13485_clauses) or 'none'}")
    print(f"  ISO 14971 Hazards  : {', '.join(extraction.iso_14971_hazard_tags) or 'none'}")
    safety = ", ".join(k for k, v in (extraction.safety_flags or {}).items() if v) or "none"
    print(f"  Safety Flags       : {safety}")

    # -- Agent 3: Retrieval ----------------------------------------------------
    _hdr("RETRIEVAL", "3")

    evidence: list[RetrievalEvidence] = []

    retrieval_agent = RetrievalAgent()  # always needed for orchestrator
    events = _load_events(product_code)  # always loaded (used by ReportContext + trend)
    if live:
        # Live path: Sai's RetrievalAgent → MCP → live OpenFDA API
        print("  Input : ExtractionOutput + live OpenFDA API via MCP server")
        print("  Tools : LLM tool planner -> search_adverse_events, search_recalls, ...\n")
        evidence = _run_live_retrieval(complaint, extraction, product_code)
    else:
        # Offline path: fuzzy-match against pre-ingested SQLite archive
        print("  Input : ExtractedSignal + local SQLite archive")
        print("  Tools : fuzzy-match against MAUDE events & FDA recalls\n")
        print(f"  Archive events loaded for {product_code}: {len(events):,}")
        evidence = retrieval_agent.retrieve(
            extracted=extraction,
            complaint_product_code=product_code,
            events_by_code={product_code: events},
            recalls=[],
            top_k=5,
        )

    print(f"  Evidence retrieved : {len(evidence)} items")
    for i, ev in enumerate(evidence, 1):
        snippet = textwrap.shorten(ev.snippet or "", width=70, placeholder="...")
        print(f"  [{i}] {ev.evidence_id}  score={ev.score:.3f}  type={ev.source_type}")
        print(f"       {snippet}")

    if not evidence:
        print("  (no matching events found -- risk agent will use heuristic fallback)")

    # -- Agent 2: Risk Analysis ------------------------------------------------
    _hdr("RISK ANALYSIS", "2")
    print("  Input : ExtractedSignal + RetrievalEvidence")
    print("  LLM   : two-pass ISO 14971:2019 assessment -- falls back to rule-based matrix\n")

    risk_agent = RiskAnalysisAgent()
    risk: RiskAssessment = risk_agent.assess(
        complaint=complaint,
        evidence=evidence,
        extraction=extraction,
    )

    print(f"\n  Risk Bucket        : {risk.risk_bucket}")
    print(f"  Severity           : {risk.severity_level}")
    print(f"  Probability        : {risk.probability_level}")
    print(f"  Escalation         : {'YES' if risk.escalation_required else 'NO'}")
    print(f"  PRRC Notification  : {'YES' if risk.prrc_notification_required else 'NO'}")
    if risk.hazardous_situation:
        print(f"  Hazardous Situation: {textwrap.shorten(risk.hazardous_situation, 70)}")
    if risk.capa_immediate:
        print(f"  CAPA (Immediate)   : {textwrap.shorten(risk.capa_immediate, 70)}")

    # -- Agent 4: Report Generation --------------------------------------------
    _hdr("REPORT GENERATION", "4")
    print("  Input : all above (complaint + extraction + retrieval + risk)")
    print("  LLM   : demand-driven section builder + self-critique loop (max 2 rounds)\n")

    trend_analyzer = ArchiveTrendAnalyzer()
    orchestrator = OrchestrationAgent(
        extraction_agent=extraction_agent,
        retrieval_agent=retrieval_agent,
        risk_agent=risk_agent,
        report_agent=ReportGenerationAgent(),
        trend_analyzer=trend_analyzer,
    )

    report_types = orchestrator.decide_report_types(
        complaint=complaint,
        extraction=extraction,
        risk=risk,
        evidence=evidence,
    )
    primary_report_type = report_types[0]
    print(f"  Report type(s) selected: {', '.join(report_types)}")
    print(f"  Generating primary report: {primary_report_type}\n")

    ctx = ReportContext(
        complaint=complaint,
        extraction=extraction,
        retrieval=evidence,
        risk=risk,
        report_type=primary_report_type,
        events_by_code={product_code: events},
    )

    report_agent = ReportGenerationAgent()
    from uuid import uuid4 as _uuid4
    trace_id = f"demo-{_uuid4().hex[:8]}"
    report = report_agent.create_report(
        trace_id=trace_id,
        context=ctx,
        orchestrator=orchestrator,
    )

    # -- Summary ---------------------------------------------------------------
    _hdr("PIPELINE COMPLETE")
    print(f"  Report ID          : {report.report_id}")
    print(f"  Report Type        : {report.report_type}")
    print(f"  Risk Decision      : {report.risk.risk_bucket}")
    print(f"  Review Needed      : {'YES -- ' + '; '.join(report.review_reasons) if report.review_needed else 'NO'}")
    if report.quality:
        print(f"  Self-critique      : {report.quality}")

    print(f"\n  --- Report Preview (first 1500 chars) ---\n")
    preview = (report.report_markdown or "").strip()
    print(textwrap.indent(preview[:1500] + ("..." if len(preview) > 1500 else ""), "  "))
    print(f"\n{'=' * 68}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Demo: run the full 4-agent pipeline on a single complaint",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--complaint",
        type=str,
        default=None,
        help="Complaint narrative text (uses a built-in sample if omitted)",
    )
    parser.add_argument(
        "--product-code",
        type=str,
        default="LNH",
        choices=list(MODALITY_NAMES.keys()),
        help="FDA product code (default: LNH = MRI System)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        default=False,
        help="Use live OpenFDA API via MCP server (Agent 3 real-time path). "
             "Requires openfda-mcp-server/ built next to this file.",
    )
    args = parser.parse_args()

    product_code = args.product_code.upper()
    complaint_text = args.complaint or SAMPLE_COMPLAINTS.get(
        product_code,
        SAMPLE_COMPLAINTS["LNH"],
    )

    run_demo(complaint_text, product_code, live=args.live)


if __name__ == "__main__":
    main()
