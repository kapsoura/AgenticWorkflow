"""
FastAPI backend — exposes the complaint processing pipeline as REST API.
"""

import sys
import time
from pathlib import Path

# Add parent to path so we can import src modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.pipeline.orchestrator import Pipeline
from src.pipeline.database import get_connection, get_db_stats
from src.embeddings.generator import EmbeddingGenerator

app = FastAPI(title="Signal Intelligence API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global pipeline instance (lazy init)
_pipeline: Pipeline | None = None


def get_pipeline() -> Pipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = Pipeline(model="mistral-small", base_url="http://localhost:11434")
        # Pre-load clusters
        embeddings, report_numbers = EmbeddingGenerator.load_embeddings()
        _pipeline.trend_analyzer.fit_clusters(embeddings, report_numbers)
    return _pipeline


class ComplaintRequest(BaseModel):
    narrative: str
    report_id: str = "UI-001"
    skip_extraction: bool = True


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
