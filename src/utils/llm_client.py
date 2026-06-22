import json
import os
from dataclasses import dataclass
from typing import Any, Dict

from dotenv import load_dotenv

from src.observability.langsmith_tracing import traceable_llm
from src.utils.custom_anthropic_client import CustomAnthropicClient

load_dotenv()


@dataclass
class LLMResult:
    content: str
    model: str


class AnthropicClient:
    """Wrapper that routes LLM calls through whichever backend is available.

    Priority:
      1. Direct Anthropic API  — when ANTHROPIC_API_KEY is set (fastest, no subprocess)
      2. Claude Code CLI       — when CLAUDE_CLI_PATH is set (no API key needed)
      3. Disabled              — every agent falls back to its offline heuristic
    """

    def __init__(self, model: str = "claude-3-5-sonnet-latest"):
        self.model = model
        self._client = None
        self._backend = "disabled"

        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if api_key:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=api_key).messages
                self._backend = "api"
            except Exception:
                pass

        if self._client is None:
            try:
                self._client = CustomAnthropicClient()
                self._backend = "cli"
            except Exception:
                self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    @traceable_llm(name="claude.complete_json")
    def complete_json(self, system_prompt: str, user_prompt: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
        if not self._client:
            return fallback

        try:
            kwargs = dict(
                max_tokens=800,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            if self._backend == "api":
                kwargs["model"] = self.model
            response = self._client.create(**kwargs)
            text = ""
            for block in response.content:
                block_text = getattr(block, "text", "")
                if block_text:
                    text += block_text

            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1:
                return fallback
            return json.loads(text[start : end + 1])
        except Exception:
            return fallback

    def complete_text(self, system_prompt: str, user_prompt: str, fallback: str = "") -> str:
        """Return a plain-text completion (no JSON parsing).

        Used by the report agent's optimizer step, where the model returns a full
        revised markdown document rather than a JSON envelope.
        """
        if not self._client:
            return fallback
        return self._complete_text(system_prompt, user_prompt, fallback)

    @traceable_llm(name="claude.complete_text")
    def _complete_text(self, system_prompt: str, user_prompt: str, fallback: str = "") -> str:
        try:
            kwargs = dict(
                max_tokens=4000,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            if self._backend == "api":
                kwargs["model"] = self.model
            response = self._client.create(**kwargs)
            text = ""
            for block in response.content:
                block_text = getattr(block, "text", "")
                if block_text:
                    text += block_text
            return text.strip() or fallback
        except Exception:
            return fallback
