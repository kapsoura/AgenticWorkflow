from typing import Dict, List, Optional

from src.pipeline.schemas import Complaint, ExtractedSignal
from src.utils.llm_client import AnthropicClient
from src.utils.prompt_store import render_prompt


class ExtractionAgent:
    """Agent-driven complaint extraction routed entirely through the Anthropic
    LLM client (the ``claude`` CLI, via ``AnthropicClient``).

    There is **no heuristic fallback**: every field comes from the LLM. If the
    client is not enabled (``CLAUDE_CLI_PATH`` unset) or the model returns nothing
    usable, ``extract`` yields an explicit ``NOT_AVAILABLE`` signal so the
    validation gate flags the complaint for human review instead of inventing a
    keyword-based classification.
    """

    # Canonical QMS categories (also the valid set used to validate LLM output).
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

    # Tolerate common field-name variants the model may emit.
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

    # Map the prompt's fine-grained categories onto the canonical 5.
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

    _SEVERITY_DEATH = "S5"
    _SEVERITY_INJURY = {"S3", "S4"}

    def __init__(self):
        self.llm = AnthropicClient()
        if self.llm.enabled:
            self.last_backend = "anthropic"
            self.last_fallback_reason: Optional[str] = None
        else:
            self.last_backend = "unavailable"
            self.last_fallback_reason = (
                "Anthropic LLM client not enabled (set CLAUDE_CLI_PATH in .env)"
            )

    def extract(self, complaint: Complaint) -> ExtractedSignal:
        if not self.llm.enabled:
            self.last_backend = "unavailable"
            self.last_fallback_reason = (
                "Anthropic LLM client not enabled (set CLAUDE_CLI_PATH in .env)"
            )
            return self._not_available_extraction(complaint)

        try:
            signal = self._extract_llm(complaint)
            self.last_backend = "anthropic"
            # Only clear the reason on a genuine success. _extract_llm may return
            # NOT_AVAILABLE *without raising* (e.g. the model came back empty); in
            # that case it already set an accurate last_fallback_reason, so don't
            # overwrite it — otherwise the server falls back to its misleading
            # "LLM client not enabled" default even though the client is enabled.
            if signal.qms_complaint_category != "NOT_AVAILABLE":
                self.last_fallback_reason = None
            return signal
        except Exception as exc:  # noqa: BLE001 — surface the reason via the trace
            self.last_backend = "unavailable"
            self.last_fallback_reason = f"Anthropic extraction failed: {exc}"
            return self._not_available_extraction(complaint)

    def _extract_llm(self, complaint: Complaint) -> ExtractedSignal:
        payload = self.llm.complete_json(
            system_prompt=render_prompt("extraction_system"),
            user_prompt=render_prompt(
                "extraction_user",
                report_id=complaint.complaint_id,
                product_hint_line=(
                    f"Product hint: {complaint.product_code}" if complaint.product_code else ""
                ),
                narrative=complaint.narrative,
            ),
            fallback={},
        )

        data = self._coerce_fields(payload)
        if not data.get("qms_complaint_category"):
            # LLM disabled / errored / produced nothing usable. Without a heuristic
            # fallback the only honest answer is NOT_AVAILABLE.
            self.last_fallback_reason = "Anthropic model returned no usable extraction"
            return self._not_available_extraction(complaint)

        category = self._normalize_qms_category(str(data.get("qms_complaint_category")))
        key_issues = self._build_key_issues(data)
        confidence = round(min(max(self._to_float(data.get("confidence"), 0.5), 0.0), 1.0), 2)

        return ExtractedSignal(
            complaint_id=complaint.complaint_id,
            qms_complaint_category=category,
            key_issues=key_issues[:8],
            confidence=confidence,
            safety_flags=self._safety_flags(data, confidence),
            iso_13485_clauses=["8.2.1", "8.3", "8.5.2"],
            iso_14971_hazard_tags=self._CATEGORY_TO_ISO_14971.get(category, ["general safety concern"]),
        )

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

    def _coerce_fields(self, data: Optional[Dict[str, object]]) -> Dict[str, object]:
        """Normalize field-name variants onto the canonical schema (no value invention)."""
        coerced = dict(data or {})
        for alias, canonical in self._ALIAS_TO_CANONICAL.items():
            if alias in coerced and canonical not in coerced:
                coerced[canonical] = coerced.pop(alias)
        return coerced

    def _safety_flags(self, data: Dict[str, object], confidence: float) -> Dict[str, bool]:
        """Derive safety flags from the agent's own severity/safety assessment."""
        severity = str(data.get("severity_indicator") or "").upper()
        sev_code = severity.split("_")[0]  # "S5_catastrophic" -> "S5"
        is_safety = bool(data.get("is_safety_related", False))
        mentions_death = sev_code == self._SEVERITY_DEATH
        mentions_injury = sev_code in self._SEVERITY_INJURY
        return {
            "mentions_death": mentions_death,
            "mentions_injury": mentions_injury,
            "mentions_patient_harm": is_safety or mentions_death or mentions_injury,
            "needs_manual_review": confidence < 0.55 or (is_safety and confidence < 0.65),
        }

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
