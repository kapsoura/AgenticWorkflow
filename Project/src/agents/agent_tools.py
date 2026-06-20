"""Tool registries for the model-callable agents.

Each builder turns existing deterministic Python functions into ``ToolSpec``
objects the model can call through ``AnthropicToolClient`` (see
``utils/tool_loop.py``). Runtime context the model must NOT choose (the event
archive, the active product code, recall records) is bound by closure, so the
schema the model sees only exposes the genuine decision arguments.

Builders that produce report content (quality analytics, evidence) also return a
``captured`` list that fills as the model invokes tools — the orchestrator uses
those captured domain objects to render the report, so the model decides *which*
analyses/searches run while the rendering stays deterministic.
"""

from __future__ import annotations

from typing import List, Tuple

from src.agents.quality_tools import QualityAnalyticsToolbox, ToolResult
from src.pipeline.schemas import ExtractedSignal, RetrievalEvidence
from src.utils.tool_loop import ToolSpec

# Tools whose only inputs are bound by closure expose an empty argument schema.
_NO_ARGS = {"type": "object", "properties": {}, "additionalProperties": False}


# ── Scope 1: report quality-analytics selection ────────────────────────────────
def quality_tool_specs(
    toolbox: QualityAnalyticsToolbox,
    events: List[dict],
    key_issues: List[str],
    retrieved_count: int,
) -> Tuple[List[ToolSpec], List[ToolResult]]:
    """Expose each QualityAnalyticsToolbox analysis as a tool the model may run.

    Returns ``(specs, captured)``. ``captured`` collects the real ``ToolResult``
    objects for every analysis the model actually invoked (deduped by tool name),
    ready to render via the existing quality-intelligence section builder.
    """
    captured: List[ToolResult] = []
    seen: set = set()

    def _wrap(run):
        def handler(**_ignored):
            result = run()
            if result.tool not in seen:
                seen.add(result.tool)
                captured.append(result)
            return {
                "tool": result.tool,
                "theme": result.theme,
                "headline": result.headline,
                "metrics": result.metrics,
                "answers": result.answers,
            }

        return handler

    catalog = {
        "recurrence_scan": (
            lambda: toolbox.recurrence_scan(events, key_issues),
            "Pattern recognition: related deviations recurring >12 months after a first matching event.",
        ),
        "cross_dimension_trend": (
            lambda: toolbox.cross_dimension_trend(events),
            "Pattern recognition: activity trends across years and event types.",
        ),
        "recurrence_rate_12m": (
            lambda: toolbox.recurrence_rate_12m(events, key_issues),
            "Root-cause effectiveness: share of matching deviations recurring within 12 months.",
        ),
        "systemic_vs_immediate": (
            lambda: toolbox.systemic_vs_immediate(events, key_issues),
            "Root-cause effectiveness: systemic vs one-off problem signatures.",
        ),
        "analysis_readiness": (
            lambda: toolbox.analysis_readiness(events, retrieved_count),
            "Resource allocation (proxy): relevant precedent pre-indexed vs manual search effort.",
        ),
        "factor_cooccurrence": (
            lambda: toolbox.factor_cooccurrence(events),
            "Predictive capability: factor combinations historically tied to serious outcomes.",
        ),
        "leading_indicators": (
            lambda: toolbox.leading_indicators(events, key_issues),
            "Predictive capability: problem categories rising year-over-year (early warning).",
        ),
    }

    specs = [
        ToolSpec(name=name, description=desc, input_schema=_NO_ARGS, handler=_wrap(run))
        for name, (run, desc) in catalog.items()
    ]
    return specs, captured


# ── Scope 2: trend grounding tools ─────────────────────────────────────────────
def trend_tool_specs(analyzer, events: List[dict]) -> List[ToolSpec]:
    """Read-only tools that let the trend agent pull the aggregates it cites.

    ``analyzer`` is any object exposing ``yearly_breakdown`` / ``problem_breakdown``
    (the ArchiveTrendAnalyzer), duck-typed to avoid an import cycle.
    """
    return [
        ToolSpec(
            name="yearly_event_counts",
            description="Return adverse-event counts per year (ascending) for this product code.",
            input_schema=_NO_ARGS,
            handler=lambda **_ignored: analyzer.yearly_breakdown(events),
        ),
        ToolSpec(
            name="top_reported_problems",
            description="Return the most frequently reported product problems with counts.",
            input_schema=_NO_ARGS,
            handler=lambda **_ignored: analyzer.problem_breakdown(events),
        ),
    ]


# ── Scope 3: retrieval / evidence lookup tools ─────────────────────────────────
def retrieval_tool_specs(
    retrieval_agent,
    product_code: str,
    events_by_code,
    recalls: List[dict],
    vector_collection=None,
) -> Tuple[List[ToolSpec], List[RetrievalEvidence]]:
    """Let the model gather evidence on demand by query.

    Reuses ``RetrievalAgent.retrieve`` for MAUDE/vector scoring (via a synthetic
    single-issue ``ExtractedSignal``) and a direct recall filter for FDA recalls.
    ``captured`` collects deduped ``RetrievalEvidence`` for the orchestrator.
    """
    captured: List[RetrievalEvidence] = []
    seen: set = set()

    def _capture(items: List[RetrievalEvidence]) -> None:
        for item in items:
            if item.evidence_id not in seen:
                seen.add(item.evidence_id)
                captured.append(item)

    def search_maude_events(query: str = "", **_ignored):
        q = str(query).strip()
        if not q:
            return {"matches": [], "note": "empty query"}
        probe = ExtractedSignal(
            complaint_id="tool-search",
            qms_complaint_category="",
            key_issues=[q],
            confidence=1.0,
            safety_flags={},
        )
        hits = retrieval_agent.retrieve(
            extracted=probe,
            complaint_product_code=product_code,
            events_by_code=events_by_code,
            recalls=[],
            vector_collection=vector_collection,
            subqueries=[q],
        )
        _capture(hits)
        return {
            "matches": [
                {"evidence_id": h.evidence_id, "source": h.source_type, "score": h.score, "snippet": h.snippet}
                for h in hits
            ]
        }

    def lookup_recalls(**_ignored):
        items: List[RetrievalEvidence] = []
        for recall in recalls:
            if recall.get("product_code") != product_code:
                continue
            items.append(
                RetrievalEvidence(
                    evidence_id=f"RC-{recall.get('res_event_number', 'unknown')}",
                    source_type="FDA_RECALL",
                    product_code=product_code,
                    snippet=(recall.get("reason_for_recall") or "")[:220],
                    score=0.5,
                    metadata={
                        "classification": recall.get("classification", "Unknown"),
                        "root_cause": recall.get("root_cause_description", "Unknown"),
                    },
                )
            )
        _capture(items)
        return {
            "recalls": [
                {
                    "evidence_id": e.evidence_id,
                    "classification": e.metadata.get("classification"),
                    "root_cause": e.metadata.get("root_cause"),
                    "snippet": e.snippet,
                }
                for e in items
            ]
        }

    specs = [
        ToolSpec(
            name="search_maude_events",
            description=(
                "Search the MAUDE adverse-event archive for this product code by free-text query. "
                "Returns matching events with a relevance score and snippet."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Failure-mode / symptom keywords to search for.",
                    }
                },
                "required": ["query"],
            },
            handler=search_maude_events,
        ),
        ToolSpec(
            name="lookup_recalls",
            description="Return FDA recall records on file for this product code (reason, classification, root cause).",
            input_schema=_NO_ARGS,
            handler=lookup_recalls,
        ),
    ]
    return specs, captured
