from typing import List

from src.pipeline.schemas import Complaint, RetrievalEvidence, RiskAssessment


class RiskAnalysisAgent:
    """Risk and CAPA recommendation agent (merged baseline)."""

    def assess(self, complaint: Complaint, evidence: List[RetrievalEvidence]) -> RiskAssessment:
        text = complaint.narrative.lower()
        event_type = complaint.event_type.lower()

        severity = "S2"
        if "death" in text or event_type == "death":
            severity = "S5"
        elif "injury" in text or event_type == "injury":
            severity = "S4"
        elif "malfunction" in text or event_type == "malfunction":
            severity = "S3"

        recall_hits = sum(1 for e in evidence if e.source_type == "FDA_RECALL")
        if recall_hits >= 3:
            probability = "P4"
        elif recall_hits >= 1:
            probability = "P3"
        else:
            probability = "P2"

        risk_bucket = self._risk_bucket(severity, probability)
        escalation_required = risk_bucket in {"ALARP", "UNACCEPTABLE"}
        prrc_required = risk_bucket == "UNACCEPTABLE"
        report_type = self._report_type(event_type=event_type, risk_bucket=risk_bucket)

        if risk_bucket == "UNACCEPTABLE":
            capa = "Immediate containment, CAPA initiation, and PRRC notification within 24h."
        elif risk_bucket == "ALARP":
            capa = "Open CAPA with root-cause investigation and software patch validation plan."
        else:
            capa = "Track in trend log; monitor recurrence before CAPA escalation."

        return RiskAssessment(
            complaint_id=complaint.complaint_id,
            severity_level=severity,
            probability_level=probability,
            risk_bucket=risk_bucket,
            escalation_required=escalation_required,
            prrc_notification_required=prrc_required,
            capa_recommendation=capa,
            report_type=report_type,
            iso_14971_rationale=(
                f"Risk estimated using severity={severity} and probability={probability}; "
                f"bucket={risk_bucket} under ISO 14971 risk acceptability criteria."
            ),
        )

    @staticmethod
    def _risk_bucket(severity: str, probability: str) -> str:
        severity_rank = int(severity[1])
        probability_rank = int(probability[1])
        score = severity_rank * probability_rank

        if score >= 16:
            return "UNACCEPTABLE"
        if score >= 8:
            return "ALARP"
        return "ACCEPTABLE"

    @staticmethod
    def _report_type(event_type: str, risk_bucket: str) -> str:
        """Primary report type under the PSUR / INCIDENT_ASSESSMENT / CAPA taxonomy."""
        if event_type in {"death", "injury"} or risk_bucket == "UNACCEPTABLE":
            return "INCIDENT_ASSESSMENT"
        if risk_bucket == "ALARP":
            return "CAPA"
        return "PSUR"
