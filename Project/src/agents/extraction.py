import json
import os
from typing import Dict, List, Optional

from src.pipeline.schemas import Complaint, ExtractedSignal
from src.utils.llm_client import AnthropicClient
from src.utils.prompt_store import render_prompt


class ExtractionAgent:
    """Extraction agent with integrated backend only.

    If integrated extraction is unavailable, return an explicit
    not-available payload instead of heuristic extraction.
    """

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

    _ALIAS_TO_CANONICAL = {
        "device_component": "component",
        "affected_component": "component",
        "failure_description": "failure_mode",
        "failure": "failure_mode",
        "observed_symptom": "symptom",
        "symptoms": "symptom",
        "severity": "severity_indicator",
        "severity_level": "severity_indicator",
        "severity_code": "severity_indicator",
        "device_modality": "modality",
        "is_software_related": "software_related",
        "safety_related": "is_safety_related",
        "usability_issue": "usability_concern",
        "security_issue": "security_concern",
        "qms_category": "qms_complaint_category",
        "complaint_category": "qms_complaint_category",
        "category": "qms_complaint_category",
        "countries": "affected_countries",
        "source": "complaint_source",
        "device_manufacturer": "manufacturer",
        "model": "device_model",
        "device_name": "device_model",
        "impact": "patient_impact",
        "reasoning_trace": "reasoning",
        "chain_of_thought": "reasoning",
    }

    _QMS_COMPAT_MAP = {
        "SW-UI": "SW-FUNC",
        "SW-CYBER": "SW-DATA",
        "IMG-PROC": "IMG-QUAL",
        "PERF-ACC": "SW-ALGO",
        "SAFE-PAT": "SW-FUNC",
        "SAFE-USR": "SW-FUNC",
        "HW-MECH": "HW-FAIL",
        "HW-ELEC": "HW-FAIL",
        "DOC-LABEL": "SW-DATA",
    }

    def __init__(self):
        self.backend = os.getenv("EXTRACTION_BACKEND", "integrated").strip().lower()
        self.llm = AnthropicClient()
        self._integrated_extractor = None
        self.last_backend = "integrated"
        self.last_fallback_reason: Optional[str] = None

        try:
            from src.agents.structured_extraction import StructuredExtractionAgent

            self._integrated_extractor = StructuredExtractionAgent(
                model=os.getenv("EXTRACTION_MODEL", "mistral-small"),
                temperature=0.1,
                base_url=os.getenv("EXTRACTION_BASE_URL", "http://localhost:11434"),
            )
            self.backend = "integrated"
        except Exception as exc:
            self.last_fallback_reason = f"Integrated backend unavailable: {exc}"
            self.backend = "integrated_unavailable"

    def extract(self, complaint: Complaint) -> ExtractedSignal:
        if self.backend == "integrated" and self._integrated_extractor is not None:
            try:
                result = self._extract_integrated(complaint)
                self.last_backend = "integrated"
                self.last_fallback_reason = None
                return result
            except Exception as exc:
                self.last_backend = "integrated_unavailable"
                self.last_fallback_reason = f"Integrated extraction unavailable: {exc}"
                return self._not_available_extraction(complaint)

        self.last_backend = "integrated_unavailable"
        if not self.last_fallback_reason:
            self.last_fallback_reason = "Integrated extraction backend not configured"
        return self._not_available_extraction(complaint)

    @staticmethod
    def _not_available_extraction(complaint: Complaint) -> ExtractedSignal:
        return ExtractedSignal(
            complaint_id=complaint.complaint_id,
            qms_complaint_category="NOT_AVAILABLE",
            key_issues=["Not available"],
            confidence=0.0,
            safety_flags={
                "mentions_death": False,
                "mentions_injury": False,
                "mentions_patient_harm": False,
                "needs_manual_review": True,
            },
            iso_13485_clauses=["Not available"],
            iso_14971_hazard_tags=["Not available"],
        )

    def _extract_internal(self, complaint: Complaint) -> ExtractedSignal:
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
            system_prompt=render_prompt("extraction_system"),
            user_prompt=render_prompt(
                "extraction_user",
                report_id=complaint.complaint_id,
                product_hint_line=(f"Product hint: {complaint.product_code}" if complaint.product_code else ""),
                narrative=complaint.narrative,
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

    def _extract_integrated(self, complaint: Complaint) -> ExtractedSignal:
        extracted = self._integrated_extractor.extract(
            narrative=complaint.narrative,
            report_id=complaint.complaint_id,
            product_hint=complaint.product_code,
            reflect=False,
        )

        data = extracted.model_dump()
        qms_raw = str(data.get("qms_complaint_category") or "SW-FUNC").strip()
        qms_norm = self._normalize_qms_category(qms_raw)

        key_issues = self._build_key_issues(data)
        conf = self._to_float(data.get("confidence"), default=0.5)

        text = complaint.narrative.lower()
        safety_flags = {
            "mentions_death": "death" in text,
            "mentions_injury": "injury" in text,
            "mentions_patient_harm": "harm" in text or "burn" in text,
            "needs_manual_review": conf < 0.55,
        }
        if bool(data.get("is_safety_related", False)):
            safety_flags["needs_manual_review"] = safety_flags["needs_manual_review"] or conf < 0.65

        return ExtractedSignal(
            complaint_id=complaint.complaint_id,
            qms_complaint_category=qms_norm,
            key_issues=key_issues[:8],
            confidence=round(min(max(conf, 0.0), 1.0), 2),
            safety_flags=safety_flags,
            iso_13485_clauses=["8.2.1", "8.3", "8.5.2"],
            iso_14971_hazard_tags=self._CATEGORY_TO_ISO_14971.get(qms_norm, ["general safety concern"]),
        )

    def _coerce_integrated_fields(self, data: Dict[str, object]) -> Dict[str, object]:
        coerced = dict(data)
        for alias, canonical in self._ALIAS_TO_CANONICAL.items():
            if alias in coerced and canonical not in coerced:
                coerced[canonical] = coerced.pop(alias)

        if not coerced.get("qms_complaint_category"):
            coerced["qms_complaint_category"] = "SW-FUNC"
        if not coerced.get("severity_indicator"):
            coerced["severity_indicator"] = "S2_minor"

        for field in ("software_related", "is_safety_related", "usability_concern", "security_concern"):
            if field not in coerced or coerced[field] is None:
                coerced[field] = False

        if "confidence" not in coerced or coerced["confidence"] is None:
            coerced["confidence"] = 0.5
        return coerced

    @staticmethod
    def _parse_json(raw: str) -> Dict[str, object]:
        text = raw.strip()
        if text.startswith("```"):
            lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
            text = "\n".join(lines).strip()
        if not text:
            return {}
        return json.loads(text)

    def _normalize_qms_category(self, value: str) -> str:
        category = value.split(",")[0].strip().upper()
        category = self._QMS_COMPAT_MAP.get(category, category)
        if category in self._CATEGORY_KEYWORDS:
            return category
        return "SW-FUNC"

    @staticmethod
    def _build_key_issues(data: Dict[str, object]) -> List[str]:
        candidates = [
            data.get("failure_mode"),
            data.get("symptom"),
            data.get("component"),
            data.get("qms_complaint_category"),
        ]
        values: List[str] = []
        for candidate in candidates:
            text = str(candidate or "").strip()
            if text and text.lower() not in {"unknown", "none", "null"}:
                values.append(text)
        if not values:
            values.append("unclassified")
        return values

    @staticmethod
    def _to_float(value: object, default: float) -> float:
        try:
            return float(value)
        except Exception:
            return default
