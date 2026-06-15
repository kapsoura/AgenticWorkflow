from typing import List

from src.pipeline.schemas import Complaint, ExtractedSignal
from src.utils.llm_client import AnthropicClient


class ExtractionAgent:
    """Heuristic baseline for structured complaint extraction."""

    _CATEGORY_KEYWORDS = {
        "SW-FUNC": ["software", "application", "freeze", "crash", "bug"],
        "SW-ALGO": ["algorithm", "reconstruction", "analysis", "false"],
        "SW-DATA": ["dicom", "data", "transfer", "archive", "storage"],
        "IMG-QUAL": ["artifact", "image", "quality", "blurry", "distortion"],
        "HW-FAIL": ["break", "failure", "overheat", "coil", "probe"],
    }

    _CATEGORY_TO_ISO_14971 = {
        "SW-FUNC": ["software functional failure"],
        "SW-ALGO": ["algorithmic performance"],
        "SW-DATA": ["data integrity"],
        "IMG-QUAL": ["diagnostic image quality"],
        "HW-FAIL": ["hardware component failure"],
    }

    def __init__(self):
        self.llm = AnthropicClient()

    def extract(self, complaint: Complaint) -> ExtractedSignal:
        text = complaint.narrative.lower()
        scores = {category: 0 for category in self._CATEGORY_KEYWORDS}
        key_issues: List[str] = []

        for category, keywords in self._CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    scores[category] += 1
                    if kw not in key_issues:
                        key_issues.append(kw)

        best_category = max(scores, key=scores.get)
        score_total = sum(scores.values())
        confidence = min(0.95, 0.35 + (0.08 * score_total))
        if score_total == 0:
            best_category = "SW-FUNC"
            confidence = 0.4
            key_issues = ["unclassified"]

        baseline = {
            "qms_complaint_category": best_category,
            "key_issues": key_issues[:8],
            "confidence": round(confidence, 2),
        }

        llm_payload = self.llm.complete_json(
            system_prompt=(
                "You are a medical-device quality engineer. "
                "Extract ISO 13485 compatible complaint fields and return strict JSON."
            ),
            user_prompt=(
                "Narrative:\n"
                f"{complaint.narrative}\n\n"
                "Return JSON with keys: qms_complaint_category, key_issues, confidence."
            ),
            fallback=baseline,
        )

        category = str(llm_payload.get("qms_complaint_category", best_category))
        issues = llm_payload.get("key_issues", key_issues[:8])
        if not isinstance(issues, list):
            issues = key_issues[:8]
        conf = llm_payload.get("confidence", round(confidence, 2))
        try:
            conf = float(conf)
        except Exception:
            conf = round(confidence, 2)

        return ExtractedSignal(
            complaint_id=complaint.complaint_id,
            qms_complaint_category=category,
            key_issues=[str(x) for x in issues[:8]],
            confidence=round(min(max(conf, 0.0), 1.0), 2),
            safety_flags={
                "mentions_death": "death" in text,
                "mentions_injury": "injury" in text,
                "mentions_patient_harm": "harm" in text or "burn" in text,
                "needs_manual_review": conf < 0.55,
            },
            iso_13485_clauses=["8.2.1", "8.3", "8.5.2"],
            iso_14971_hazard_tags=self._CATEGORY_TO_ISO_14971.get(category, ["general safety concern"]),
        )
