"""
Guardrail Agent — LLM-based input and output guardrails.

Both guardrails run entirely through the project's Anthropic LLM client
(``AnthropicClient`` → Claude CLI / Anthropic API). There is **no regex or
heuristic fallback**: when the LLM client is not enabled the guardrail reports
itself as *not available* so callers surface an explicit "Agent not available"
state instead of silently passing or pattern-matching.

    * ``check_input(narrative)``  → is this a legitimate complaint, or a
      prompt-injection / instruction-override / non-complaint that must be
      rejected before any downstream agent runs?
    * ``check_output(report_markdown, evidence_ids)`` → is a generated report
      safe to release, or must it be held for human review (uncited high-risk /
      regulatory claims, unsupported certainty)?
"""

from dataclasses import dataclass, field
from typing import List, Optional

from src.utils.llm_client import AnthropicClient
from src.utils.prompt_store import load_prompt


@dataclass
class GuardrailResult:
    """Outcome of a single guardrail check.

    available — False when the LLM client is disabled or returned no decision.
    passed    — True when the input is safe / the output is compliant.
    reasons   — human-readable reasons (empty when passed and available).
    """

    available: bool
    passed: bool
    reasons: List[str] = field(default_factory=list)


class GuardrailAgent:
    """LLM-only input/output guardrails (no heuristic fallback)."""

    def __init__(self, llm: Optional[AnthropicClient] = None):
        self.llm = llm or AnthropicClient()

    @property
    def enabled(self) -> bool:
        return self.llm.enabled

    # ── Input guardrail ──────────────────────────────────────────────────
    def check_input(self, narrative: str) -> GuardrailResult:
        if not self.llm.enabled:
            return GuardrailResult(
                available=False,
                passed=False,
                reasons=["Guardrail agent not available — LLM client is disabled."],
            )

        sentinel: dict = {}
        data = self.llm.complete_json(
            system_prompt=load_prompt("guardrail_input_system"),
            user_prompt=(narrative or "").strip(),
            fallback=sentinel,
        )
        if not isinstance(data, dict) or "safe" not in data:
            # Model returned nothing usable → treat as undecided, not a pass.
            return GuardrailResult(
                available=False,
                passed=False,
                reasons=["Guardrail agent did not return a decision."],
            )

        safe = bool(data.get("safe"))
        reasons = [str(r) for r in (data.get("reasons") or []) if str(r).strip()]
        if not safe and not reasons:
            reasons = [
                f"Input rejected by guardrail ({data.get('category') or 'unsafe input'})."
            ]
        return GuardrailResult(available=True, passed=safe, reasons=reasons)

    # ── Output guardrail ─────────────────────────────────────────────────
    def check_output(self, report_markdown: str, evidence_ids: List[str]) -> GuardrailResult:
        if not self.llm.enabled:
            return GuardrailResult(
                available=False,
                passed=False,
                reasons=["Guardrail agent not available — LLM client is disabled."],
            )

        ids = ", ".join(str(e) for e in (evidence_ids or [])) or "(none)"
        user_prompt = (
            "EVIDENCE IDENTIFIERS AVAILABLE FOR CITATION:\n"
            f"{ids}\n\n"
            "GENERATED REPORT:\n"
            f"{report_markdown or ''}"
        )
        data = self.llm.complete_json(
            system_prompt=load_prompt("guardrail_output_system"),
            user_prompt=user_prompt,
            fallback={},
        )
        if not isinstance(data, dict) or "compliant" not in data:
            return GuardrailResult(
                available=False,
                passed=False,
                reasons=["Guardrail agent did not return a decision."],
            )

        compliant = bool(data.get("compliant"))
        issues = [str(i) for i in (data.get("issues") or []) if str(i).strip()]
        if not compliant and not issues:
            issues = ["Report flagged for human review by the output guardrail."]
        return GuardrailResult(available=True, passed=compliant, reasons=issues)
