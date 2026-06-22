"""Anthropic SDK tool-use loop
================================
A small, reusable agentic loop built on the official ``anthropic`` SDK so agents
can expose plain Python functions as **model-callable tools**.

This is the real-tool-use path, driven entirely through the ``claude`` CLI bridge
in ``custom_anthropic_client.py`` (no ``ANTHROPIC_API_KEY`` required). The CLI
client emulates the Messages tool-use contract, returning the same duck-typed
response (``stop_reason`` + ``tool_use``/``text`` blocks) this loop consumes. When
the CLI is unavailable (``CLAUDE_CLI_PATH`` unset) the client reports
``enabled == False`` and every caller falls back to its deterministic/heuristic
behaviour, so the rest of the system keeps running offline exactly as before.

Usage:

    client = AnthropicToolClient()
    if client.enabled:
        result = client.run(system_prompt, user_prompt, tools=[ToolSpec(...), ...])
        verdict = result.json_object()        # final JSON the model produced
        ran = result.invocations              # the tools it actually called

The caller still owns tool *implementations* — a ``ToolSpec`` binds a JSON input
schema to a Python handler; the loop dispatches the model's ``tool_use`` requests
to that handler, feeds the result back, and repeats until the model stops calling
tools (or ``max_iterations`` is hit).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Callable, Dict, List

from dotenv import load_dotenv

from src.utils.custom_anthropic_client import CustomAnthropicClient

load_dotenv()

# Default model for tool calls. Overridable via .env so the model can be swapped
# without code changes. Matches the existing AnthropicClient default string.
_DEFAULT_MODEL = "claude-3-5-sonnet-latest"


@dataclass
class ToolSpec:
    """One model-callable tool: a JSON schema bound to a Python handler.

    ``handler`` is called with the model-supplied arguments as keyword args and
    must return a JSON-serialisable value (or any object — it is stringified for
    the model). Context the model should *not* supply (event archives, the active
    complaint, etc.) is bound by closing over it when the spec is built, so the
    visible ``input_schema`` stays small and the model only chooses the decision
    arguments.
    """

    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[..., Any]

    def to_api(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


@dataclass
class ToolInvocation:
    """A single tool call the model made, plus what the handler returned."""

    name: str
    arguments: Dict[str, Any]
    result: Any
    is_error: bool = False


@dataclass
class ToolLoopResult:
    final_text: str
    invocations: List[ToolInvocation] = field(default_factory=list)
    stop_reason: str = ""
    iterations: int = 0

    def json_object(self) -> Dict[str, Any]:
        """Parse the model's final answer as a JSON object (tolerant of fences)."""
        text = self.final_text.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {}
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {}


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return str(value)


class AnthropicToolClient:
    """Runs an Anthropic tool-use loop over the ``claude`` CLI, or stays disabled
    when the CLI is not configured (``CLAUDE_CLI_PATH`` unset)."""

    def __init__(self, model: str | None = None, max_iterations: int = 8, time_budget_s: float = 45.0):
        self.model = model or os.environ.get("ANTHROPIC_TOOL_MODEL", _DEFAULT_MODEL)
        self.max_iterations = max_iterations
        # Wall-clock cap for the whole loop. Stopping is deterministic (time +
        # iteration count), never the model's self-assessment — mirrors the
        # architecture's loop-safety rule. Whatever tools ran before the cap is
        # still returned, so callers degrade gracefully to partial/empty results.
        self.time_budget_s = time_budget_s
        self._client = None
        try:
            self._client = CustomAnthropicClient()
        except Exception:
            self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def run(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: List[ToolSpec],
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> ToolLoopResult:
        """Drive the model→tool→model loop until it stops requesting tools.

        Raises ``RuntimeError`` if the client is disabled so callers can catch it
        and use their deterministic fallback (mirrors ``complete_json``'s contract).
        """
        if self._client is None:
            raise RuntimeError("AnthropicToolClient is disabled (CLAUDE_CLI_PATH not set)")

        registry = {spec.name: spec for spec in tools}
        tool_defs = [spec.to_api() for spec in tools]
        messages: List[Dict[str, Any]] = [{"role": "user", "content": user_prompt}]
        invocations: List[ToolInvocation] = []
        stop_reason = ""
        deadline = monotonic() + self.time_budget_s

        for iteration in range(1, self.max_iterations + 1):
            # Deterministic stop: out of time budget. Return what ran so far so
            # the caller falls back / uses partial evidence instead of hanging.
            if monotonic() >= deadline:
                return ToolLoopResult("", invocations, stop_reason or "time_budget", iteration - 1)
            response = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                tools=tool_defs,
                messages=messages,
            )
            stop_reason = response.stop_reason or ""

            if stop_reason != "tool_use":
                text = "".join(
                    getattr(block, "text", "")
                    for block in response.content
                    if getattr(block, "type", None) == "text"
                )
                return ToolLoopResult(text, invocations, stop_reason, iteration)

            # Re-add the assistant turn (as plain dicts, robust across SDK versions)
            # then dispatch every tool_use block it contains.
            assistant_content: List[Dict[str, Any]] = []
            tool_results: List[Dict[str, Any]] = []
            for block in response.content:
                btype = getattr(block, "type", None)
                if btype == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                elif btype == "tool_use":
                    assistant_content.append(
                        {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
                    )
                    arguments = dict(block.input or {})
                    spec = registry.get(block.name)
                    if spec is None:
                        result, is_error = f"Unknown tool: {block.name}", True
                    else:
                        try:
                            result, is_error = spec.handler(**arguments), False
                        except Exception as exc:  # noqa: BLE001 — report back to the model
                            result, is_error = f"Tool '{block.name}' failed: {exc}", True
                    invocations.append(ToolInvocation(block.name, arguments, result, is_error))
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": _stringify(result),
                            "is_error": is_error,
                        }
                    )

            messages.append({"role": "assistant", "content": assistant_content})
            messages.append({"role": "user", "content": tool_results})

        # Ran out of iterations while still calling tools.
        return ToolLoopResult("", invocations, stop_reason or "max_iterations", self.max_iterations)
