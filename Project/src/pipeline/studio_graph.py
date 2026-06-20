"""LangGraph UI / Studio entrypoint.

Exposes the *same* production agentic flow

    prepare -> extract -> retrieve -> risk -> assemble

so it can be run and watched node-by-node in the LangGraph UI (``langgraph dev``)
with nothing but a narrative + product code as input. ``langgraph.json`` points
at ``make_graph`` below.

Design note — why a thin wrapper instead of reusing ``LangGraphSignalWorkflow``
directly: the production graph carries heavy, non-serializable objects in its
state channels (the loaded FDA archive, the Chroma collection, the trace logger).
The LangGraph dev server persists every written channel, so we keep those objects
in this module's closure and inject them into each node at call time. Only
JSON/dataclass-friendly values (the complaint and the agent outputs) ever cross a
channel, which keeps Studio's checkpointing happy. The agent objects, gate logic,
and ordering are identical to production.
"""

from datetime import datetime
from time import monotonic
from typing import Dict, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from src.config import (
    CHROMA_DIR,
    DEFAULT_MAX_EVENTS_PER_CODE,
    IMAGING_EVENTS_DIR,
    PRODUCT_CODES,
    RECALLS_FILE,
    SQLITE_DB_PATH,
)
from src.pipeline.langgraph_flow import LangGraphSignalWorkflow, WorkflowState
from src.pipeline.schemas import Complaint
from src.utils.data_loader import load_events_for_codes, load_recalls
from src.utils.storage import init_chroma, init_sqlite, upsert_event_vectors


class StudioInput(TypedDict, total=False):
    """The minimal form shown in the LangGraph UI."""

    narrative: str
    product_code: str
    event_type: str
    manufacturer: str


class StudioState(WorkflowState, StudioInput, total=False):
    """Production channels + the raw UI input fields."""


def make_graph():
    """Build the monitorable agentic graph referenced by ``langgraph.json``."""
    workflow = LangGraphSignalWorkflow()

    # Load the working archive once when the graph is built (cached in closure).
    # Heavy/unserializable objects live here, never in a persisted channel.
    events_by_code = load_events_for_codes(
        imaging_events_dir=IMAGING_EVENTS_DIR,
        product_codes=PRODUCT_CODES,
        max_events_per_code=DEFAULT_MAX_EVENTS_PER_CODE,
    )
    try:
        recalls = load_recalls(recalls_file=RECALLS_FILE, product_codes=PRODUCT_CODES)
    except FileNotFoundError:
        recalls = []
    init_sqlite(SQLITE_DB_PATH)
    vector_collection = init_chroma(CHROMA_DIR)
    for code in PRODUCT_CODES:
        upsert_event_vectors(vector_collection, events_by_code.get(code, []))

    def _inject(state: StudioState) -> Dict:
        # Supply the closure-held resources the production nodes read from state,
        # without ever writing them back into a persisted channel.
        return {
            **state,
            "events_by_code": events_by_code,
            "recalls": recalls,
            "vector_collection": vector_collection,
            "tracer": None,
        }

    def prepare(state: StudioState) -> Dict:
        product_code = (state.get("product_code") or PRODUCT_CODES[0]).upper()
        narrative = (state.get("narrative") or "").strip() or "No narrative provided."
        complaint = Complaint(
            complaint_id=f"STUDIO-{product_code}-{uuid4().hex[:6]}",
            product_code=product_code,
            manufacturer=state.get("manufacturer") or "Unknown",
            event_type=state.get("event_type") or "Malfunction",
            date_received=datetime.utcnow().strftime("%Y%m%d"),
            narrative=narrative,
            source_report_number="STUDIO",
            ground_truth_problems=[],
        )
        return {
            "trace_id": f"studio-{uuid4().hex[:8]}",
            "deadline_ts": monotonic() + 120,
            "complaint": complaint,
            "review_needed": False,
            "review_reasons": [],
        }

    graph = StateGraph(StudioState, input_schema=StudioInput)
    graph.add_node("prepare", prepare)
    graph.add_node("extract", lambda s: workflow._extract(_inject(s)))
    graph.add_node("retrieve", lambda s: workflow._retrieve(_inject(s)))
    graph.add_node("risk", lambda s: workflow._risk(_inject(s)))
    graph.add_node("assemble", lambda s: workflow._assemble(_inject(s)))

    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "extract")
    graph.add_edge("extract", "retrieve")
    graph.add_edge("retrieve", "risk")
    graph.add_edge("risk", "assemble")
    graph.add_edge("assemble", END)
    return graph.compile()
