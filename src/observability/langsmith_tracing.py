"""LangSmith observability wiring.

LangGraph is LangSmith-native: once the LangChain tracing environment variables
are set, every ``graph.invoke(...)`` run is exported to LangSmith as a trace tree
(one span per node: input_guardrail -> extract -> retrieve/trend -> risk ->
assemble -> output_guardrail). This module:

1. ``configure_langsmith()`` -- reads the key/project from ``src.config`` (which
   loads ``.env``) and exports the canonical ``LANGCHAIN_*`` variables so the
   LangChain SDK picks them up. Idempotent and safe to call on every run.
2. ``traceable_llm(name)`` -- a decorator that turns the Claude-CLI calls (which
   bypass LangChain and would otherwise be invisible) into nested ``llm`` spans.

Everything degrades to a no-op when ``langsmith`` is not installed or tracing is
disabled, so the pipeline never depends on the network or an API key. The local
JSONL ``TraceLogger`` keeps working regardless -- LangSmith is additive.
"""

import os
from typing import Any, Callable, Dict, Optional

from src import config

# Resolve the optional dependency once. ``langsmith`` ships with langchain, but
# guard the import so the pipeline still runs in minimal environments.
try:  # pragma: no cover - import guard
    from langsmith import traceable as _ls_traceable
except Exception:  # pragma: no cover - langsmith absent
    _ls_traceable = None

_CONFIGURED = False
_ACTIVE = False


def configure_langsmith() -> bool:
    """Export LangChain tracing env vars from config; return whether it is active.

    Tracing is active only when (a) ``LANGSMITH_TRACING`` / ``LANGCHAIN_TRACING_V2``
    is truthy, (b) an API key is present, and (c) the ``langsmith`` package is
    importable. The status line is printed once per process.
    """
    global _CONFIGURED, _ACTIVE
    if _CONFIGURED:
        return _ACTIVE
    _CONFIGURED = True

    if not config.LANGSMITH_TRACING:
        _ACTIVE = False
        return _ACTIVE

    if _ls_traceable is None:
        print("[langsmith] tracing requested but `langsmith` is not installed; skipping.")
        _ACTIVE = False
        return _ACTIVE

    if not config.LANGSMITH_API_KEY:
        print("[langsmith] tracing requested but no API key set (LANGCHAIN_API_KEY); skipping.")
        _ACTIVE = False
        return _ACTIVE

    # Export the canonical names the LangChain SDK reads at run time.
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = config.LANGSMITH_API_KEY
    os.environ["LANGCHAIN_PROJECT"] = config.LANGSMITH_PROJECT
    os.environ["LANGCHAIN_ENDPOINT"] = config.LANGSMITH_ENDPOINT

    _ACTIVE = True
    print(f"[langsmith] tracing enabled -> project '{config.LANGSMITH_PROJECT}'")
    return _ACTIVE


def tracing_active() -> bool:
    """Return True when LangSmith export is configured for this process."""
    return _ACTIVE


def _strip_self(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Drop the bound ``self`` and truncate long prompts for readable spans."""
    cleaned: Dict[str, Any] = {}
    for key, value in inputs.items():
        if key == "self":
            continue
        if isinstance(value, str) and len(value) > 2000:
            cleaned[key] = value[:2000] + "...[truncated]"
        else:
            cleaned[key] = value
    return cleaned


def traceable_llm(name: str, run_type: str = "llm") -> Callable:
    """Decorate an LLM-call method so it appears as a span in LangSmith.

    When ``langsmith`` is unavailable the decorator returns the function
    unchanged. When present, ``langsmith.traceable`` only emits a span if tracing
    is enabled at call time, so this is safe to apply at import time.
    """
    def decorator(func: Callable) -> Callable:
        if _ls_traceable is None:
            return func
        return _ls_traceable(run_type=run_type, name=name, process_inputs=_strip_self)(func)

    return decorator


def run_metadata(trace_id: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build LangChain run config so each pipeline run is named by its trace_id.

    Pass the result as ``graph.invoke(state, config=run_metadata(trace_id))`` so
    the LangSmith trace shares the same id as the local JSONL log for easy
    cross-referencing.
    """
    metadata = {"trace_id": trace_id}
    if extra:
        metadata.update(extra)
    return {"run_name": trace_id, "metadata": metadata}
