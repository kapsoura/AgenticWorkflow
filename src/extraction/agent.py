"""
Extraction Agent (US-07) - Agent 1.
Chain-of-Thought extraction + 1-pass self-reflection.
Uses LangChain + ChatOllama for local LLM inference.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage

from src.pipeline.schemas import (
    ComplaintSource,
    ExtractionOutput,
    Modality,
    QMSCategory,
    SeverityCode,
)

# Load prompts
PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "configs" / "prompts"


def _load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    return path.read_text(encoding="utf-8")


class ExtractionAgent:
    """
    Agent 1: Complaint Narrative -> Structured ExtractionOutput.

    Architecture: CoT extraction pass -> 1 self-reflection pass -> validated output.
    Autonomy Level: L1 (Augmented LLM - single-pass + 1 reflection round).
    """

    def __init__(
        self,
        model: str = "mistral-small",
        temperature: float = 0.1,
        base_url: str = "http://localhost:11434",
    ):
        """
        Args:
            model: Ollama model name (e.g., "mistral-small", "qwen3:32b", "phi4").
                   Ignored when ANTHROPIC_API_KEY is set (Anthropic backend used instead).
            temperature: Low temperature for deterministic extraction.
            base_url: Ollama server URL. Ignored when ANTHROPIC_API_KEY is set.
        """
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if anthropic_key:
            # Cloud deployments have no local Ollama server to reach — use the
            # Anthropic API instead. The extraction prompt already requires a
            # raw JSON response, so no provider-specific JSON mode is needed.
            from langchain_anthropic import ChatAnthropic

            self.llm = ChatAnthropic(
                model=os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
                temperature=temperature,
                api_key=anthropic_key,
                max_tokens=512,
            )
        else:
            self.llm = ChatOllama(
                model=model,
                temperature=temperature,
                base_url=base_url,
                format="json",
                num_ctx=2048,
                num_predict=512,
            )
        self._system_prompt = _load_prompt("extraction")
        self._reflection_prompt = _load_prompt("reflection")

    def _call_llm(self, system_prompt: str, user_message: str) -> str:
        """Make an LLM call via LangChain ChatOllama."""
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ]
        response = self.llm.invoke(messages)
        return response.content

    def _build_user_message(self, narrative: str, report_id: str, product_hint: Optional[str] = None) -> str:
        """Build the user message with the narrative wrapped in safety delimiters."""
        parts = [f"Report ID: {report_id}"]
        if product_hint:
            parts.append(f"Product hint: {product_hint}")
        parts.append(f"\n<user_narrative>\n{narrative}\n</user_narrative>")
        parts.append("\nExtract structured fields as JSON:")
        return "\n".join(parts)

    def extract(
        self,
        narrative: str,
        report_id: str,
        product_hint: Optional[str] = None,
        reflect: bool = False,
    ) -> ExtractionOutput:
        """
        Run the full extraction pipeline:
        1. CoT extraction pass
        2. Self-reflection pass (if enabled)
        3. Pydantic validation

        Args:
            narrative: Raw complaint text.
            report_id: Unique complaint/event identifier.
            product_hint: Optional device type hint (e.g., "MRI", "CT Scanner").
            reflect: Whether to run the self-reflection pass.

        Returns:
            Validated ExtractionOutput.
        """
        # Pass 1: CoT Extraction
        user_msg = self._build_user_message(narrative, report_id, product_hint)
        raw_output = self._call_llm(self._system_prompt, user_msg)
        extraction_data = self._parse_json(raw_output)

        # Pass 2: Self-Reflection (optional, 1 round)
        if reflect:
            reflection_input = (
                f"Original narrative:\n<user_narrative>\n{narrative}\n</user_narrative>\n\n"
                f"Extraction output to review:\n```json\n{json.dumps(extraction_data, indent=2)}\n```"
            )
            reflected_output = self._call_llm(self._reflection_prompt, reflection_input)
            extraction_data = self._parse_json(reflected_output)

        # Validate with Pydantic
        extraction_data["report_id"] = report_id
        return self._validate(extraction_data)

    def _parse_json(self, raw: str) -> dict:
        """Parse JSON from LLM output, handling markdown code fences."""
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)
        return json.loads(text)

    def _validate(self, data: dict) -> ExtractionOutput:
        """Validate and coerce the extraction data into the Pydantic model.
        Handles common field name variations from the LLM.
        """
        # Map common LLM field name variations to our schema names
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

        # Handle missing/default fields
        if "affected_countries" not in data or not data["affected_countries"]:
            data["affected_countries"] = ["unknown"]
        if "complaint_source" not in data or not data["complaint_source"]:
            data["complaint_source"] = "unknown"

        # Default None string fields
        if not data.get("component"):
            data["component"] = "unknown"
        if not data.get("failure_mode"):
            data["failure_mode"] = "unknown"
        if not data.get("symptom"):
            data["symptom"] = "unknown"

        # Handle severity mapping ("S3" or "serious" -> "S3_serious")
        sev = data.get("severity_indicator", "")
        if sev and "_" not in str(sev):
            sev_map = {
                "S1": "S1_negligible", "S2": "S2_minor", "S3": "S3_serious",
                "S4": "S4_critical", "S5": "S5_catastrophic",
                "negligible": "S1_negligible", "minor": "S2_minor",
                "serious": "S3_serious", "critical": "S4_critical",
                "catastrophic": "S5_catastrophic",
            }
            data["severity_indicator"] = sev_map.get(str(sev), "S2_minor")

        # Default modality if missing
        if not data.get("modality"):
            data["modality"] = "Unknown"

        # Ensure boolean fields default to False
        for bool_field in ["software_related", "is_safety_related", "usability_concern", "security_concern"]:
            if bool_field not in data or data[bool_field] is None:
                data[bool_field] = False

        # Default confidence
        if "confidence" not in data or data["confidence"] is None:
            data["confidence"] = 0.5

        # Default qms_complaint_category — handle LLM returning multiple values
        qms = data.get("qms_complaint_category", "")
        if not qms:
            data["qms_complaint_category"] = "SW-FUNC"
        elif "," in str(qms):
            # LLM returned multiple categories, take the first valid one
            data["qms_complaint_category"] = str(qms).split(",")[0].strip()

        return ExtractionOutput.model_validate(data)

    def extract_batch(
        self,
        events: list[dict],
        reflect: bool = False,
    ) -> list[ExtractionOutput]:
        """Extract from a batch of events."""
        results = []
        for event in events:
            narrative = event.get("narrative", "")
            if not narrative:
                continue
            report_id = event.get("report_number", "UNKNOWN")
            product_hint = event.get("modality") or event.get("product_code")

            try:
                result = self.extract(
                    narrative=narrative,
                    report_id=report_id,
                    product_hint=product_hint,
                    reflect=reflect,
                )
                results.append(result)
            except Exception as e:
                print(f"  [WARN] Extraction failed for {report_id}: {e}")
                continue

        return results
