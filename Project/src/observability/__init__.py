"""Tracing and observability helpers.

- ``tracer`` -- local JSONL trace log written per ``trace_id`` (always on).
- ``langsmith_tracing`` -- optional LangSmith export for LangGraph runs and
  LLM-call spans, enabled via ``.env`` (``LANGCHAIN_TRACING_V2`` + key).
"""

from src.observability.langsmith_tracing import (
    configure_langsmith,
    run_metadata,
    traceable_llm,
    tracing_active,
)
from src.observability.tracer import TraceLogger

__all__ = [
    "TraceLogger",
    "configure_langsmith",
    "run_metadata",
    "traceable_llm",
    "tracing_active",
]
