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

    # Step 1: Extraction (optional)
    t0 = time.time()
    if not req.skip_extraction:
        try:
            extraction = pipeline.extractor.extract(
                narrative=req.narrative,
                report_id=req.report_id,
            )
            extraction_data = extraction.model_dump()
            # Convert enums to strings for JSON
            for k, v in extraction_data.items():
                if hasattr(v, "value"):
                    extraction_data[k] = v.value
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
                extraction = pipeline.extractor.extract(
                    narrative=req.narrative, report_id=req.report_id
                )
                extraction_data = extraction.model_dump()
                for k, v in extraction_data.items():
                    if hasattr(v, "value"):
                        extraction_data[k] = v.value
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


@app.post("/api/analyze")
def analyze_complaint_endpoint(
    narrative: str,
    product_code: str = "LNH",
    event_type: str = "Malfunction",
    manufacturer: str = "Unknown",
):
    """Run complaint through the pipeline and return structured results."""
    if not narrative.strip():
        raise HTTPException(400, "Narrative cannot be empty")

    pipeline = get_pipeline()
    t0 = time.time()
    result: dict = {"report_id": f"UI-{int(time.time())}", "steps": []}

    # Extraction
    extraction_data = {}
    try:
        extraction = pipeline.extractor.extract(
            narrative=narrative, report_id=result["report_id"]
        )
        extraction_data = extraction.model_dump()
        for k, v in extraction_data.items():
            if hasattr(v, "value"):
                extraction_data[k] = v.value
    except Exception as e:
        extraction_data = {"error": str(e)}

    # Embedding + cluster
    cluster_data = {}
    try:
        embedding = pipeline.embedder.embed_single(narrative)
        similarity = pipeline.trend_analyzer.assign_complaint(
            embedding=embedding, conn=pipeline.conn, top_k=5
        )
        cluster_data = similarity.model_dump()
        for k, v in cluster_data.items():
            if hasattr(v, "value"):
                cluster_data[k] = v.value
    except Exception as e:
        cluster_data = {"error": str(e)}

    total_ms = round((time.time() - t0) * 1000, 1)

    return {
        "report_id": result["report_id"],
        "report_type": "PSUR",
        "risk_bucket": extraction_data.get("severity_indicator", "UNKNOWN"),
        "extraction": extraction_data,
        "evidence_count": len(cluster_data.get("similar_events", [])),
        "sections": [],
        "validation": {"passed": True, "issues": []},
        "cluster": cluster_data,
        "total_duration_ms": total_ms,
    }


if __name__ == "__main__":
    import os
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
