from __future__ import annotations

import json
from typing import Optional

from src.pipeline.signal_intelligence_schemas import (
    ComplaintSource,
    ExtractionOutput,
)
from src.utils.prompt_store import render_prompt


class StructuredExtractionAgent:
    """Structured extraction using local chat model with strict JSON output."""

    def __init__(
        self,
        model: str = "mistral-small",
        temperature: float = 0.1,
        base_url: str = "http://localhost:11434",
    ):
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_ollama import ChatOllama

        self._SystemMessage = SystemMessage
        self._HumanMessage = HumanMessage
        self.llm = ChatOllama(
            model=model,
            temperature=temperature,
            base_url=base_url,
            format="json",
            num_ctx=2048,
            num_predict=512,
        )

    def _call_llm(self, system_prompt: str, user_message: str) -> str:
        messages = [
            self._SystemMessage(content=system_prompt),
            self._HumanMessage(content=user_message),
        ]
        response = self.llm.invoke(messages)
        return response.content

    @staticmethod
    def _build_user_message(narrative: str, report_id: str, product_hint: Optional[str] = None) -> str:
        return render_prompt(
            "extraction_user",
            report_id=report_id,
            product_hint_line=(f"Product hint: {product_hint}" if product_hint else ""),
            narrative=narrative,
        )

    def extract(
        self,
        narrative: str,
        report_id: str,
        product_hint: Optional[str] = None,
        reflect: bool = False,
    ) -> ExtractionOutput:
        user_msg = self._build_user_message(narrative, report_id, product_hint)
        raw_output = self._call_llm(render_prompt("extraction_system"), user_msg)
        extraction_data = self._parse_json(raw_output)

        if reflect:
            reflection_input = render_prompt(
                "extraction_reflection",
                narrative=narrative,
                extraction_json=json.dumps(extraction_data, indent=2),
            )
            reflected_output = self._call_llm(reflection_input, "")
            extraction_data = self._parse_json(reflected_output)

        extraction_data["report_id"] = report_id
        return self._validate(extraction_data)

    @staticmethod
    def _parse_json(raw: str) -> dict:
        text = raw.strip()
        if text.startswith("```"):
            lines = [line for line in text.split("\n") if not line.strip().startswith("```")]
            text = "\n".join(lines)
        return json.loads(text)

    def _validate(self, data: dict) -> ExtractionOutput:
        field_aliases = {
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
        for alias, canonical in field_aliases.items():
            if alias in data and canonical not in data:
                data[canonical] = data.pop(alias)

        if "affected_countries" not in data or not data["affected_countries"]:
            data["affected_countries"] = ["unknown"]
        if "complaint_source" not in data or not data["complaint_source"]:
            data["complaint_source"] = ComplaintSource.UNKNOWN.value

        if not data.get("component"):
            data["component"] = "unknown"
        if not data.get("failure_mode"):
            data["failure_mode"] = "unknown"
        if not data.get("symptom"):
            data["symptom"] = "unknown"

        severity = data.get("severity_indicator", "")
        if severity and "_" not in str(severity):
            sev_map = {
                "S1": "S1_negligible",
                "S2": "S2_minor",
                "S3": "S3_serious",
                "S4": "S4_critical",
                "S5": "S5_catastrophic",
                "negligible": "S1_negligible",
                "minor": "S2_minor",
                "serious": "S3_serious",
                "critical": "S4_critical",
                "catastrophic": "S5_catastrophic",
            }
            data["severity_indicator"] = sev_map.get(str(severity), "S2_minor")

        if not data.get("modality"):
            data["modality"] = "Unknown"

        for bool_field in ["software_related", "is_safety_related", "usability_concern", "security_concern"]:
            if bool_field not in data or data[bool_field] is None:
                data[bool_field] = False

        if "confidence" not in data or data["confidence"] is None:
            data["confidence"] = 0.5

        qms = data.get("qms_complaint_category", "")
        if not qms:
            data["qms_complaint_category"] = "SW-FUNC"
        elif "," in str(qms):
            data["qms_complaint_category"] = str(qms).split(",")[0].strip()

        return ExtractionOutput.model_validate(data)