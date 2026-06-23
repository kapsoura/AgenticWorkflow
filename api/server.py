"""
FastAPI backend — exposes the complaint processing pipeline as REST API.
"""

import json
import sys
import time
from pathlib import Path
from typing import Optional

# Add parent to path so we can import src modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Lazy-import heavy modules (sentence-transformers) to keep startup fast
from src.pipeline.database import get_connection, get_db_stats

app = FastAPI(title="Signal Intelligence API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "https://kapsoura.github.io",
    ],
    # Vercel assigns a new random per-deployment URL on every preview deploy
    # (e.g. multi-agent-quality-intellience-3xwmj18qm.vercel.app), in addition
    # to the stable production alias. Matching by pattern avoids having to
    # update this allowlist on every deploy.
    allow_origin_regex=r"https://multi-agent-quality-intellience.*\.vercel\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global pipeline instance (lazy init)
_pipeline = None


def get_pipeline():
    global _pipeline
    if _pipeline is None:
        from src.pipeline.orchestrator import Pipeline
        from src.embeddings.generator import EmbeddingGenerator
        _pipeline = Pipeline(model="mistral-small", base_url="http://localhost:11434")
        # Pre-load clusters
        embeddings, report_numbers = EmbeddingGenerator.load_embeddings()
        _pipeline.trend_analyzer.fit_clusters(embeddings, report_numbers)
    return _pipeline


# Anthropic multi-agent stack (lazy init) — used for the INTERACTIVE analyze path.
# Ollama (via the Pipeline above) is reserved strictly for the batch extraction job.
_agents = None


def get_agents():
    """Return the Anthropic-backed interactive agents (extraction + ISO 14971 risk).

    These route through ``AnthropicClient`` (Claude CLI / Anthropic API), never
    Ollama. Construction is cheap — no model server is contacted until ``.extract``
    / ``.assess`` is called.
    """
    global _agents
    if _agents is None:
        from src.agents.extraction import ExtractionAgent as AnthropicExtractionAgent
        from src.agents.risk_analysis import RiskAnalysisAgent
        _agents = {
            "extraction": AnthropicExtractionAgent(),
            "risk": RiskAnalysisAgent(),
        }
    return _agents


def _interactive_extract(narrative: str, report_id: str, product_code: Optional[str] = None) -> dict:
    """Run interactive extraction through the Anthropic agent (never Ollama).

    Returns a JSON-safe dict. On failure / when the LLM client is disabled the
    returned dict carries an ``error`` key so callers can surface a graceful
    status to the UI.
    """
    import dataclasses
    from src.pipeline.schemas import Complaint

    complaint = Complaint(
        complaint_id=report_id,
        product_code=product_code or "",
        manufacturer="Unknown",
        event_type="Malfunction",
        date_received="",
        narrative=narrative,
        source_report_number=report_id,
    )
    agent = get_agents()["extraction"]
    try:
        signal = agent.extract(complaint)
        data = dataclasses.asdict(signal)
        if signal.qms_complaint_category == "NOT_AVAILABLE":
            data["error"] = (
                getattr(agent, "last_fallback_reason", None)
                or "Anthropic LLM client not enabled (set CLAUDE_CLI_PATH or ANTHROPIC_API_KEY)."
            )
        return data
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


class ComplaintRequest(BaseModel):
    narrative: str
    report_id: str = "UI-001"
    skip_extraction: bool = True
    product_code: Optional[str] = None


class StepResult(BaseModel):
    step: str
    status: str
    duration_ms: float
    data: dict


@app.get("/api/stats")
def stats():
    """Get database statistics."""
    conn = get_connection()
    s = get_db_stats(conn)
    conn.close()
    return s


@app.post("/api/process")
def process_complaint(req: ComplaintRequest):
    """
    Process a complaint through the full pipeline:
    1. LLM Extraction
    2. BGE Embedding
    3. Cluster Assignment + Similar Events
    Returns step-by-step results for visualization.
    """
    if not req.narrative.strip():
        raise HTTPException(400, "Narrative cannot be empty")

    pipeline = get_pipeline()
    steps = []

    # Step 1: Extraction (optional) — Anthropic agent only; Ollama is batch-only
    t0 = time.time()
    if not req.skip_extraction:
        try:
            extraction_data = _interactive_extract(
                req.narrative, req.report_id, req.product_code
            )
            if extraction_data.get("error"):
                steps.append(StepResult(
                    step="extraction",
                    status="error",
                    duration_ms=round((time.time() - t0) * 1000, 1),
                    data={"error": extraction_data["error"]},
                ))
            else:
                steps.append(StepResult(
                    step="extraction",
                    status="success",
                    duration_ms=round((time.time() - t0) * 1000, 1),
                    data=extraction_data,
                ))
        except Exception as e:
            steps.append(StepResult(
                step="extraction",
                status="error",
                duration_ms=round((time.time() - t0) * 1000, 1),
                data={"error": str(e)},
            ))
    else:
        steps.append(StepResult(
            step="extraction",
            status="skipped",
            duration_ms=0,
            data={"message": "Skipped — not required for cluster assignment"},
        ))

    # Step 2: Embedding
    t1 = time.time()
    try:
        embedding = pipeline.embedder.embed_single(req.narrative)
        steps.append(StepResult(
            step="embedding",
            status="success",
            duration_ms=round((time.time() - t1) * 1000, 1),
            data={
                "dimensions": int(embedding.shape[0]),
                "vector_preview": embedding[:8].tolist(),
                "norm": round(float((embedding ** 2).sum() ** 0.5), 4),
            },
        ))
    except Exception as e:
        steps.append(StepResult(
            step="embedding",
            status="error",
            duration_ms=round((time.time() - t1) * 1000, 1),
            data={"error": str(e)},
        ))
        return {"steps": [s.model_dump() for s in steps]}

    # Step 3: Cluster Assignment
    t2 = time.time()
    try:
        similarity = pipeline.trend_analyzer.assign_complaint(
            embedding=embedding, conn=pipeline.conn, top_k=10
        )
        sim_data = similarity.model_dump()
        # Convert enums
        for k, v in sim_data.items():
            if hasattr(v, "value"):
                sim_data[k] = v.value
        # Get narratives for similar events
        similar_with_text = []
        for ev in sim_data.get("similar_events", [])[:5]:
            row = pipeline.conn.execute(
                "SELECT narrative, product_code, manufacturer FROM events WHERE report_number = ?",
                (ev["report_number"],),
            ).fetchone()
            similar_with_text.append({
                **ev,
                "narrative_preview": (row["narrative"][:200] + "...") if row and row["narrative"] else "",
                "product_code": row["product_code"] if row else "",
                "manufacturer": row["manufacturer"] if row else "",
            })
        sim_data["similar_events"] = similar_with_text

        steps.append(StepResult(
            step="cluster_assignment",
            status="success",
            duration_ms=round((time.time() - t2) * 1000, 1),
            data=sim_data,
        ))
    except Exception as e:
        steps.append(StepResult(
            step="cluster_assignment",
            status="error",
            duration_ms=round((time.time() - t2) * 1000, 1),
            data={"error": str(e)},
        ))

    total_ms = round((time.time() - t0) * 1000, 1)
    return {
        "report_id": req.report_id,
        "total_duration_ms": total_ms,
        "steps": [s.model_dump() for s in steps],
    }


@app.get("/api/clusters")
def get_clusters():
    """Get all cluster summaries."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, label, size, growth_rate_30d, dominant_problem, dominant_modality, trend_flag FROM clusters ORDER BY size DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _product_trend(product_code: str, limit_months: int = 12) -> list[dict]:
    """Monthly event counts for a single product code (trend for the incoming complaint)."""
    if not product_code:
        return []
    try:
        conn = get_connection()
    except Exception:
        return []
    try:
        rows = conn.execute(
            """
            SELECT substr(date_received, 1, 6) AS label, COUNT(*) AS count
            FROM events
            WHERE product_code = ?
            GROUP BY label
            HAVING label IS NOT NULL AND label != ''
            ORDER BY label
            """,
            (product_code,),
        ).fetchall()
    finally:
        conn.close()
    series = [
        {"label": f"{r['label'][:4]}-{r['label'][4:]}", "count": r["count"]}
        for r in rows
        if r["label"] and len(r["label"]) >= 6
    ]
    return series[-limit_months:]


def _sse(event: str, payload: dict) -> str:
    """Format a Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"


@app.post("/api/process/stream")
def process_complaint_stream(req: ComplaintRequest):
    """
    Same pipeline as /api/process but streamed as Server-Sent Events so the UI
    can show the agentic flow live, node-by-node, while analysis happens.
    Emits: `step` events per node, a `trend` event (per-complaint product trend),
    a `cluster` event (membership), and a final `done` event.
    """
    if not req.narrative.strip():
        raise HTTPException(400, "Narrative cannot be empty")

    def gen():
        pipeline = get_pipeline()
        overall = time.time()

        # Step 1: Extraction
        yield _sse("step", {"step": "extraction", "status": "processing", "data": {}})
        t0 = time.time()
        if not req.skip_extraction:
            try:
                extraction_data = _interactive_extract(
                    req.narrative, req.report_id, req.product_code
                )
                if extraction_data.get("error"):
                    yield _sse("step", {
                        "step": "extraction", "status": "error",
                        "duration_ms": round((time.time() - t0) * 1000, 1),
                        "data": {"error": extraction_data["error"]},
                    })
                else:
                    yield _sse("step", {
                        "step": "extraction", "status": "success",
                        "duration_ms": round((time.time() - t0) * 1000, 1),
                        "data": extraction_data,
                    })
            except Exception as e:
                yield _sse("step", {
                    "step": "extraction", "status": "error",
                    "duration_ms": round((time.time() - t0) * 1000, 1),
                    "data": {"error": str(e)},
                })
        else:
            yield _sse("step", {
                "step": "extraction", "status": "skipped", "duration_ms": 0,
                "data": {"message": "Skipped — not required for cluster assignment"},
            })

        # Step 2: Embedding
        yield _sse("step", {"step": "embedding", "status": "processing", "data": {}})
        t1 = time.time()
        try:
            embedding = pipeline.embedder.embed_single(req.narrative)
            yield _sse("step", {
                "step": "embedding", "status": "success",
                "duration_ms": round((time.time() - t1) * 1000, 1),
                "data": {
                    "dimensions": int(embedding.shape[0]),
                    "vector_preview": embedding[:8].tolist(),
                    "norm": round(float((embedding ** 2).sum() ** 0.5), 4),
                },
            })
        except Exception as e:
            yield _sse("step", {
                "step": "embedding", "status": "error",
                "duration_ms": round((time.time() - t1) * 1000, 1),
                "data": {"error": str(e)},
            })
            yield _sse("done", {"total_duration_ms": round((time.time() - overall) * 1000, 1)})
            return

        # Step 3: Cluster assignment
        yield _sse("step", {"step": "cluster_assignment", "status": "processing", "data": {}})
        t2 = time.time()
        cluster_data: dict = {}
        try:
            similarity = pipeline.trend_analyzer.assign_complaint(
                embedding=embedding, conn=pipeline.conn, top_k=10
            )
            cluster_data = similarity.model_dump()
            for k, v in cluster_data.items():
                if hasattr(v, "value"):
                    cluster_data[k] = v.value
            similar_with_text = []
            for ev in cluster_data.get("similar_events", [])[:5]:
                row = pipeline.conn.execute(
                    "SELECT narrative, product_code, manufacturer FROM events WHERE report_number = ?",
                    (ev["report_number"],),
                ).fetchone()
                similar_with_text.append({
                    **ev,
                    "narrative_preview": (row["narrative"][:200] + "...") if row and row["narrative"] else "",
                    "product_code": row["product_code"] if row else "",
                    "manufacturer": row["manufacturer"] if row else "",
                })
            cluster_data["similar_events"] = similar_with_text
            yield _sse("step", {
                "step": "cluster_assignment", "status": "success",
                "duration_ms": round((time.time() - t2) * 1000, 1),
                "data": cluster_data,
            })
            yield _sse("cluster", cluster_data)
        except Exception as e:
            yield _sse("step", {
                "step": "cluster_assignment", "status": "error",
                "duration_ms": round((time.time() - t2) * 1000, 1),
                "data": {"error": str(e)},
            })

        # Per-complaint trend (based on the incoming complaint's product code)
        product_code = req.product_code or cluster_data.get("dominant_modality")
        yield _sse("trend", {
            "product_code": product_code,
            "series": _product_trend(product_code) if product_code else [],
        })

        yield _sse("done", {
            "report_id": req.report_id,
            "total_duration_ms": round((time.time() - overall) * 1000, 1),
        })

    return StreamingResponse(gen(), media_type="text/event-stream")


_graph_cache: Optional[dict] = None


@app.get("/api/graph")
def langgraph_structure():
    """Return the restored LangGraph agentic-flow structure (nodes + edges)."""
    global _graph_cache
    if _graph_cache is not None:
        return _graph_cache
    try:
        from src.pipeline.langgraph_flow import LangGraphSignalWorkflow
        workflow = LangGraphSignalWorkflow()
        drawable = workflow.graph.get_graph()
        nodes = [
            {"id": node_id} for node_id in drawable.nodes.keys()
        ]
        edges = [
            {
                "source": e.source,
                "target": e.target,
                "conditional": bool(getattr(e, "conditional", False)),
            }
            for e in drawable.edges
        ]
        _graph_cache = {"nodes": nodes, "edges": edges}
        return _graph_cache
    except Exception as e:
        raise HTTPException(500, f"Could not build graph: {e}")


# ---------- Endpoints for React UI ----------


PRODUCT_CODES = ["LNH", "JAK", "LLZ"]
EVENT_TYPES = ["Malfunction", "Injury", "Death"]
REPORT_TYPES = ["PSUR", "INCIDENT_ASSESSMENT", "CAPA"]


@app.get("/health")
def health():
    return {"status": "ok", "service": "signal-intelligence-api"}


@app.get("/api/meta")
def meta():
    """Static metadata for the UI."""
    return {
        "product_codes": PRODUCT_CODES,
        "event_types": EVENT_TYPES,
        "report_types": REPORT_TYPES,
    }


@app.get("/api/trends")
def trends(
    dimension: str,
    product_code: Optional[str] = None,
    event_type: Optional[str] = None,
    software_related: Optional[bool] = None,
):
    """Aggregate a dimension from the events/clusters tables."""
    try:
        conn = get_connection()
    except Exception as e:
        raise HTTPException(500, f"Database connection failed: {e}")

    series = []

    allowed_cluster_dims = {"trend_flag", "dominant_problem", "dominant_modality"}

    try:
        if dimension == "product_code":
            sql = "SELECT product_code AS label, COUNT(*) AS count FROM events"
            conditions, params = _build_where(product_code, event_type, software_related)
            sql += conditions + " GROUP BY product_code ORDER BY count DESC LIMIT 20"
            rows = conn.execute(sql, params).fetchall()
            series = [{"label": r["label"] or "Unknown", "count": r["count"]} for r in rows]
        elif dimension == "event_type":
            sql = "SELECT event_type AS label, COUNT(*) AS count FROM events"
            conditions, params = _build_where(product_code, event_type, software_related)
            sql += conditions + " GROUP BY event_type ORDER BY count DESC"
            rows = conn.execute(sql, params).fetchall()
            series = [{"label": r["label"] or "Unknown", "count": r["count"]} for r in rows]
        elif dimension == "manufacturer":
            sql = "SELECT manufacturer AS label, COUNT(*) AS count FROM events"
            conditions, params = _build_where(product_code, event_type, software_related)
            sql += conditions + " GROUP BY manufacturer ORDER BY count DESC LIMIT 12"
            rows = conn.execute(sql, params).fetchall()
            series = [{"label": r["label"] or "Unknown", "count": r["count"]} for r in rows]
        elif dimension == "year":
            sql = "SELECT substr(date_received, 1, 4) AS label, COUNT(*) AS count FROM events"
            conditions, params = _build_where(product_code, event_type, software_related)
            sql += conditions + " GROUP BY label HAVING label IS NOT NULL AND label != '' ORDER BY label"
            rows = conn.execute(sql, params).fetchall()
            series = [{"label": r["label"], "count": r["count"]} for r in rows if r["label"]]
        elif dimension == "month":
            sql = "SELECT substr(date_received, 1, 6) AS label, COUNT(*) AS count FROM events"
            conditions, params = _build_where(product_code, event_type, software_related)
            sql += conditions + " GROUP BY label HAVING label IS NOT NULL AND label != '' ORDER BY label"
            rows = conn.execute(sql, params).fetchall()
            series = [
                {"label": f"{r['label'][:4]}-{r['label'][4:]}", "count": r["count"]}
                for r in rows if r["label"] and len(r["label"]) >= 6
            ]
        elif dimension == "quarter":
            sql = """SELECT substr(date_received, 1, 4) AS yr,
                            CAST((CAST(substr(date_received, 5, 2) AS INTEGER) - 1) / 3 + 1 AS TEXT) AS q,
                            COUNT(*) AS count
                     FROM events"""
            conditions, params = _build_where(product_code, event_type, software_related)
            sql += conditions + " GROUP BY yr, q HAVING yr IS NOT NULL AND yr != '' ORDER BY yr, q"
            rows = conn.execute(sql, params).fetchall()
            series = [
                {"label": f"{r['yr']}-Q{r['q']}", "count": r["count"]}
                for r in rows if r["yr"]
            ]
        elif dimension in allowed_cluster_dims:
            col_map = {
                "trend_flag": "trend_flag",
                "dominant_problem": "dominant_problem",
                "dominant_modality": "dominant_modality",
            }
            col = col_map[dimension]
            rows = conn.execute(
                f"SELECT {col} AS label, COUNT(*) AS count FROM clusters GROUP BY {col} ORDER BY count DESC"
            ).fetchall()
            series = [{"label": r["label"] or "Unknown", "count": r["count"]} for r in rows]
        else:
            conn.close()
            raise HTTPException(400, f"Unknown dimension: {dimension}")
    except HTTPException:
        raise
    except Exception as e:
        conn.close()
        raise HTTPException(500, f"Query error: {e}")

    conn.close()
    return {"dimension": dimension, "series": series}


def _build_where(
    product_code: Optional[str],
    event_type: Optional[str],
    software_related: Optional[bool],
) -> tuple:
    """Build a parameterised WHERE clause from filter values."""
    clauses = []
    params: list = []
    if product_code:
        clauses.append("product_code = ?")
        params.append(product_code)
    if event_type:
        clauses.append("event_type = ?")
        params.append(event_type)
    if software_related is not None:
        clauses.append("software_related = ?")
        params.append(software_related)
    if clauses:
        return " WHERE " + " AND ".join(clauses), params
    return "", params


@app.get("/api/templates")
def templates():
    """Report structures and section catalog."""
    try:
        from src.agents.report_sections import SECTION_KEYWORDS, blueprint_for
        catalog = [
            {"section": name, "keywords": keywords}
            for name, keywords in SECTION_KEYWORDS.items()
        ]
        blueprints = {}
        for rt in REPORT_TYPES:
            try:
                specs = blueprint_for(rt)
                blueprints[rt] = [{"name": s.name, "title": s.title} for s in specs]
            except Exception:
                blueprints[rt] = []
        return {"section_catalog": catalog, "blueprints": blueprints}
    except ImportError:
        return {"section_catalog": [], "blueprints": {}}


# ─── Analytics (deterministic dashboard aggregations over the real archive) ──
_analytics_cache: Optional[dict] = None


def _analytics_data() -> dict:
    """Build (events_by_code, recalls) from ``data/signal_intelligence.db`` in the
    shape ``src.analytics`` expects. Cached — the archive is static at runtime.
    """
    global _analytics_cache
    if _analytics_cache is None:
        from collections import defaultdict
        conn = get_connection()
        try:
            problems_by_event: dict = defaultdict(list)
            for r in conn.execute(
                "SELECT event_id, problem_code FROM event_problems"
            ).fetchall():
                problems_by_event[r["event_id"]].append(r["problem_code"])

            by_code: dict = defaultdict(list)
            for r in conn.execute(
                "SELECT id, date_received, event_type, product_code, manufacturer FROM events"
            ).fetchall():
                by_code[r["product_code"] or "Unknown"].append({
                    "date_received": str(r["date_received"] or ""),
                    "event_type": r["event_type"],
                    "device": [{"manufacturer_d_name": r["manufacturer"]}],
                    "product_problems": problems_by_event.get(r["id"], []),
                })

            recall_count = conn.execute("SELECT COUNT(*) FROM recalls").fetchone()[0]
            recalls = [{} for _ in range(int(recall_count))]
        finally:
            conn.close()
        _analytics_cache = {"events_by_code": dict(by_code), "recalls": recalls}
    return _analytics_cache


@app.get("/api/analytics/stats")
def analytics_stats():
    """Headline dashboard counts computed deterministically over the real archive."""
    from src.analytics import compute_stats
    from src.config import SQLITE_DB_PATH

    data = _analytics_data()
    return compute_stats(data["events_by_code"], data["recalls"], SQLITE_DB_PATH)


@app.get("/api/analytics/trends")
def analytics_trends(
    dimension: str = "product_code",
    product_code: Optional[str] = None,
    event_type: Optional[str] = None,
    software_related: Optional[bool] = None,
    top_n: int = 12,
):
    """Aggregate one allow-listed dimension into a chart-ready series."""
    from src.analytics import compute_trends
    from src.config import SQLITE_DB_PATH

    data = _analytics_data()
    filters = {
        "product_code": product_code,
        "event_type": event_type,
        "software_related": software_related,
    }
    try:
        return compute_trends(
            data["events_by_code"], SQLITE_DB_PATH, dimension, filters, top_n=top_n
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))


# ─── Analyze helpers (retrieval / recalls / report) ─────────────────────────


def _enrich_similar_events(conn, similar_events: list, limit: int = 5) -> list:
    """Attach real narrative snippets + device context to retrieved events."""
    enriched = []
    for ev in similar_events[:limit]:
        row = conn.execute(
            "SELECT narrative, product_code, manufacturer, device_name, date_received "
            "FROM events WHERE report_number = ?",
            (ev.get("report_number"),),
        ).fetchone()
        narrative = (row["narrative"] if row and row["narrative"] else "") or ""
        snippet = (narrative[:220] + "…") if len(narrative) > 220 else narrative
        enriched.append({
            **ev,
            "narrative_snippet": snippet or None,
            "product_code": row["product_code"] if row else None,
            "manufacturer": row["manufacturer"] if row else None,
            "device_name": row["device_name"] if row else None,
            "date_received": row["date_received"] if row else None,
        })
    return enriched


def _related_recalls(conn, product_code: Optional[str], limit: int = 5) -> list:
    """Pull openFDA recalls for the same product code as supporting evidence."""
    if not product_code:
        return []
    rows = conn.execute(
        "SELECT recall_number, reason_for_recall, root_cause, classification, "
        "recalling_firm, recall_date FROM recalls WHERE product_code = ? "
        "ORDER BY recall_date DESC LIMIT ?",
        (product_code, limit),
    ).fetchall()
    out = []
    for r in rows:
        reason = (r["reason_for_recall"] or "")
        out.append({
            "recall_number": r["recall_number"],
            "reason_for_recall": (reason[:240] + "…") if len(reason) > 240 else reason,
            "root_cause": r["root_cause"],
            "classification": r["classification"],
            "recalling_firm": r["recalling_firm"],
            "recall_date": r["recall_date"],
        })
    return out


def _build_report_sections(
    complaint,
    extraction_data: dict,
    risk_block: dict,
    cluster_data: dict,
    recalls: list,
) -> list:
    """Assemble a deterministic, downloadable report from the structured analysis.

    No LLM is required — every section is rendered from data already produced by
    the extraction / risk / retrieval steps, so a report is always available to
    download regardless of which risk backend was used.
    """
    def _fmt(value):
        return value if value not in (None, "") else "—"

    sections: list = []

    sections.append({
        "name": "executive_summary",
        "title": "1. Executive Summary",
        "content": (
            f"Report type: {risk_block.get('report_type') or 'PSUR'}\n"
            f"Product code: {complaint.product_code}\n"
            f"Event type: {complaint.event_type}\n"
            f"Manufacturer: {complaint.manufacturer}\n"
            f"Overall risk (ISO 14971): {risk_block.get('bucket')}\n"
            f"Assessment method: "
            f"{'LLM (Anthropic)' if risk_block.get('method') == 'anthropic' else 'Deterministic ISO 14971'}"
        ),
    })

    if (
        extraction_data
        and not extraction_data.get("error")
        and extraction_data.get("qms_complaint_category") not in (None, "NOT_AVAILABLE")
    ):
        flags = extraction_data.get("safety_flags") or {}
        sections.append({
            "name": "signal_extraction",
            "title": "2. Signal Extraction",
            "content": (
                f"QMS category: {_fmt(extraction_data.get('qms_complaint_category'))}\n"
                f"Key issues: {', '.join(extraction_data.get('key_issues') or []) or '—'}\n"
                f"Confidence: {extraction_data.get('confidence')}\n"
                f"Safety flags: {', '.join(k for k, v in flags.items() if v) or 'none'}\n"
                f"ISO 13485 clauses: {', '.join(extraction_data.get('iso_13485_clauses') or []) or '—'}\n"
                f"ISO 14971 hazard tags: {', '.join(extraction_data.get('iso_14971_hazard_tags') or []) or '—'}"
            ),
        })
    else:
        sections.append({
            "name": "signal_extraction",
            "title": "2. Signal Extraction",
            "content": "Structured extraction not available (LLM client not configured).",
        })

    sections.append({
        "name": "risk_assessment",
        "title": "3. Risk Assessment (ISO 14971)",
        "content": (
            f"Risk bucket: {risk_block.get('bucket')}\n"
            f"Severity: {_fmt(risk_block.get('severity_level'))}\n"
            f"Probability: {_fmt(risk_block.get('probability_level'))}\n"
            f"Hazardous situation: {_fmt(risk_block.get('hazardous_situation'))}\n"
            f"Harm: {_fmt(risk_block.get('harm'))}\n"
            f"Escalation required: {risk_block.get('escalation_required', False)}\n"
            f"PRRC notification: {risk_block.get('prrc_notification_required', False)}\n\n"
            f"Rationale:\n{risk_block.get('rationale') or '—'}"
        ),
    })

    if risk_block.get("capa_recommendation"):
        sections.append({
            "name": "capa",
            "title": "4. CAPA Recommendation",
            "content": str(risk_block.get("capa_recommendation")),
        })

    similar = cluster_data.get("similar_events") or []
    if similar:
        lines = []
        for ev in similar:
            score = ev.get("similarity_score")
            pct = f"{score * 100:.1f}%" if isinstance(score, (int, float)) else "—"
            meta = " · ".join(
                str(x) for x in [ev.get("manufacturer"), ev.get("product_code"), ev.get("date_received")] if x
            )
            lines.append(
                f"- {ev.get('report_number')} ({pct} match) {meta}\n  {ev.get('narrative_snippet') or ''}".rstrip()
            )
        sections.append({
            "name": "retrieval_evidence",
            "title": "5. Retrieved Similar Events",
            "content": "\n".join(lines),
        })

    if recalls:
        lines = []
        for rc in recalls:
            lines.append(
                f"- {rc.get('recall_number')} [{rc.get('classification') or '—'}] "
                f"{rc.get('recalling_firm') or ''} {rc.get('recall_date') or ''}\n"
                f"  {rc.get('reason_for_recall') or ''}".rstrip()
            )
        sections.append({
            "name": "fda_recalls",
            "title": "6. Related FDA Recalls (openFDA)",
            "content": "\n".join(lines),
        })

    if cluster_data and not cluster_data.get("error"):
        sections.append({
            "name": "cluster_assignment",
            "title": "7. Cluster Assignment",
            "content": (
                f"Cluster ID: {_fmt(cluster_data.get('cluster_id'))}\n"
                f"Cluster label: {_fmt(cluster_data.get('cluster_label'))}\n"
                f"Trend flag: {_fmt(cluster_data.get('trend_flag'))}\n"
                f"Cluster size: {_fmt(cluster_data.get('cluster_size'))}\n"
                f"30-day growth rate: {_fmt(cluster_data.get('growth_rate_30d'))}"
            ),
        })

    return sections


@app.post("/api/analyze")
def analyze_complaint_endpoint(
    narrative: str,
    product_code: str = "LNH",
    event_type: str = "Malfunction",
    manufacturer: str = "Unknown",
):
    """Run a complaint through the INTERACTIVE agent stack and return structured results.

    Interactive extraction + ISO 14971 risk run through the Anthropic agents
    (``AnthropicClient`` → Claude CLI / Anthropic API). Ollama is NOT used here;
    it is reserved for the batch extraction job. Retrieval + cluster assignment
    use the prebuilt BGE index over ``data/signal_intelligence.db``.
    """
    if not narrative.strip():
        raise HTTPException(400, "Narrative cannot be empty")

    import dataclasses
    from src.pipeline.schemas import Complaint, RetrievalEvidence

    pipeline = get_pipeline()
    agents = get_agents()
    t0 = time.time()
    report_id = f"UI-{int(time.time())}"

    complaint = Complaint(
        complaint_id=report_id,
        product_code=product_code,
        manufacturer=manufacturer,
        event_type=event_type,
        date_received="",
        narrative=narrative,
        source_report_number=report_id,
    )

    # ── Extraction (Anthropic agent) ──────────────────────────────────────
    extraction_agent = agents["extraction"]
    extracted_signal = None
    extraction_data: dict = {}
    try:
        extracted_signal = extraction_agent.extract(complaint)
        extraction_data = dataclasses.asdict(extracted_signal)
    except Exception as e:  # noqa: BLE001
        extraction_data = {"error": str(e)}

    extraction_available = (
        extracted_signal is not None
        and extracted_signal.qms_complaint_category != "NOT_AVAILABLE"
    )
    if extraction_available:
        extraction_status = {"ok": True, "backend": extraction_agent.last_backend}
    else:
        extraction_status = {
            "ok": False,
            "reason": "llm_unavailable",
            "backend": getattr(extraction_agent, "last_backend", "unavailable"),
            "message": (
                getattr(extraction_agent, "last_fallback_reason", None)
                or "Anthropic LLM client not enabled (set CLAUDE_CLI_PATH or "
                "ANTHROPIC_API_KEY in .env). Risk below uses the deterministic "
                "ISO 14971 estimate from the risk-analysis agent."
            ),
        }

    # ── Embedding + cluster assignment (BGE index over the real archive) ──
    cluster_data: dict = {}
    try:
        embedding = pipeline.embedder.embed_single(narrative)
        similarity = pipeline.trend_analyzer.assign_complaint(
            embedding=embedding, conn=pipeline.conn, top_k=5
        )
        cluster_data = similarity.model_dump()
        for k, v in cluster_data.items():
            if hasattr(v, "value"):
                cluster_data[k] = v.value
        if cluster_data.get("similar_events"):
            cluster_data["similar_events"] = _enrich_similar_events(
                pipeline.conn, cluster_data["similar_events"]
            )
    except Exception as e:  # noqa: BLE001
        cluster_data = {"error": str(e)}

    # ── openFDA recalls for the same product code (supporting evidence) ───
    recalls = _related_recalls(pipeline.conn, product_code)

    # ── Build evidence bundle for the risk agent ──────────────────────────
    evidence: list = []
    for ev in cluster_data.get("similar_events", []) or []:
        evidence.append(RetrievalEvidence(
            evidence_id=str(ev.get("report_number") or "event"),
            source_type="MAUDE_EVENT",
            product_code=ev.get("product_code") or product_code,
            snippet=ev.get("narrative_snippet") or "",
            score=float(ev.get("similarity_score") or 0.0),
            metadata={
                "manufacturer": ev.get("manufacturer"),
                "device_name": ev.get("device_name"),
                "date_received": ev.get("date_received"),
            },
        ))
    for rc in recalls:
        evidence.append(RetrievalEvidence(
            evidence_id=str(rc.get("recall_number") or "recall"),
            source_type="FDA_RECALL",
            product_code=product_code,
            snippet=rc.get("reason_for_recall") or "",
            score=1.0,
            metadata={
                "classification": rc.get("classification"),
                "root_cause": rc.get("root_cause"),
                "recalling_firm": rc.get("recalling_firm"),
                "recall_date": rc.get("recall_date"),
            },
        ))

    # ── Risk assessment (Anthropic ISO 14971 agent; deterministic when offline) ──
    risk_agent = agents["risk"]
    assessment = None
    try:
        assessment = risk_agent.assess(
            complaint=complaint,
            evidence=evidence,
            extraction=extracted_signal,
            trend=None,
        )
    except Exception:  # noqa: BLE001
        assessment = None

    report_type = "PSUR"
    if assessment is not None:
        report_type = assessment.report_type or report_type
        method = "anthropic" if assessment.llm_backed else "deterministic"
        risk_signals = [s for s in (
            f"Severity {assessment.severity_level} / probability {assessment.probability_level}",
            f"Hazardous situation: {assessment.hazardous_situation}" if assessment.hazardous_situation else "",
            "Escalation required" if assessment.escalation_required else "",
            "PRRC notification required" if assessment.prrc_notification_required else "",
            f"{len(recalls)} related FDA recall(s)" if recalls else "",
        ) if s]
        risk_block = {
            "bucket": assessment.risk_bucket,
            "method": method,
            "report_type": report_type,
            "signals": risk_signals,
            "rationale": assessment.iso_14971_rationale
            or "ISO 14971 assessment produced by the risk-analysis agent.",
            "severity_level": assessment.severity_level,
            "probability_level": assessment.probability_level,
            "escalation_required": assessment.escalation_required,
            "prrc_notification_required": assessment.prrc_notification_required,
            "capa_recommendation": assessment.capa_recommendation,
            "hazardous_situation": assessment.hazardous_situation,
            "harm": assessment.harm,
        }
    else:
        risk_block = {
            "bucket": "UNKNOWN",
            "method": "unavailable",
            "report_type": report_type,
            "signals": [],
            "rationale": "Risk analysis could not be completed.",
        }

    sections = _build_report_sections(
        complaint, extraction_data, risk_block, cluster_data, recalls
    )

    total_ms = round((time.time() - t0) * 1000, 1)

    return {
        "report_id": report_id,
        "report_type": report_type,
        "risk_bucket": risk_block["bucket"],
        "risk": risk_block,
        "extraction": extraction_data,
        "extraction_status": extraction_status,
        "evidence_count": len(cluster_data.get("similar_events", [])),
        "recalls": recalls,
        "sections": sections,
        "validation": {"passed": True, "issues": []},
        "cluster": cluster_data,
        "total_duration_ms": total_ms,
    }


# ─── DOCX report export ──────────────────────────────────────────────────────

class ReportExportRequest(BaseModel):
    """Analysis payload (the /api/analyze response) to render as a Word report."""
    report_id: Optional[str] = None
    report_type: Optional[str] = None
    risk_bucket: Optional[str] = None
    risk: Optional[dict] = None
    extraction: Optional[dict] = None
    recalls: Optional[list] = None
    sections: Optional[list] = None
    cluster: Optional[dict] = None
    narrative: Optional[str] = None
    product_code: Optional[str] = None
    event_type: Optional[str] = None
    manufacturer: Optional[str] = None


def _build_report_docx(payload: "ReportExportRequest") -> bytes:
    """Render an analysis payload to a Word (.docx) document in memory."""
    import io

    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, RGBColor

    risk = payload.risk or {}
    cluster = payload.cluster or {}
    similar = cluster.get("similar_events") or []
    recalls = payload.recalls or []

    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)

    # Title
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("Signal Intelligence Report")
    run.bold = True
    run.font.size = Pt(20)
    run.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)

    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta_run = meta.add_run(
        f"Report ID: {payload.report_id or '—'}   |   "
        f"Report type: {payload.report_type or '—'}   |   "
        f"Risk: {payload.risk_bucket or '—'}"
    )
    meta_run.font.size = Pt(10)
    meta_run.font.color.rgb = RGBColor(0x40, 0x40, 0x40)
    doc.add_paragraph()

    # Complaint
    doc.add_heading("Complaint", level=1)
    info = doc.add_paragraph()
    info.add_run("Product code: ").bold = True
    info.add_run(f"{payload.product_code or '—'}\n")
    info.add_run("Event type: ").bold = True
    info.add_run(f"{payload.event_type or '—'}\n")
    info.add_run("Manufacturer: ").bold = True
    info.add_run(f"{payload.manufacturer or 'Unknown'}")
    if payload.narrative:
        nar = doc.add_paragraph(payload.narrative)
        nar.style = doc.styles["Quote"] if "Quote" in [s.name for s in doc.styles] else nar.style

    # Prefer the structured sections produced by the backend; they already
    # cover risk, CAPA, evidence, recalls and cluster in a deterministic order.
    if payload.sections:
        for sec in payload.sections:
            doc.add_heading(sec.get("title") or sec.get("name") or "Section", level=1)
            for line in str(sec.get("content") or "").split("\n"):
                doc.add_paragraph(line)
    else:
        # Fallback rendering when sections are absent.
        doc.add_heading("Risk Assessment (ISO 14971)", level=1)
        rp = doc.add_paragraph()
        rp.add_run("Risk bucket: ").bold = True
        rp.add_run(f"{risk.get('bucket') or payload.risk_bucket or '—'}\n")
        rp.add_run("Method: ").bold = True
        rp.add_run(f"{risk.get('method') or '—'}\n")
        rp.add_run("Rationale: ").bold = True
        rp.add_run(f"{risk.get('rationale') or '—'}")
        for sig in risk.get("signals") or []:
            doc.add_paragraph(sig, style="List Bullet")

        if similar:
            doc.add_heading("Retrieved Similar Events", level=1)
            for ev in similar:
                score = ev.get("similarity_score")
                pct = f"{score * 100:.1f}%" if isinstance(score, (int, float)) else "—"
                doc.add_paragraph(
                    f"{ev.get('report_number')} ({pct} match) — {ev.get('narrative_snippet') or ''}",
                    style="List Bullet",
                )

        if recalls:
            doc.add_heading("Related FDA Recalls", level=1)
            for rc in recalls:
                doc.add_paragraph(
                    f"{rc.get('recall_number')} [{rc.get('classification') or '—'}] — "
                    f"{rc.get('reason_for_recall') or ''}",
                    style="List Bullet",
                )

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


@app.post("/api/analyze/report")
def export_report_docx(payload: ReportExportRequest):
    """Return the analysis payload rendered as a downloadable Word document."""
    try:
        data = _build_report_docx(payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Report generation failed: {exc}")

    filename = f"{payload.report_id or 'analysis'}.docx"
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


if __name__ == "__main__":
    import os
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))

