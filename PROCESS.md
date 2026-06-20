# Signal Intelligence Pipeline — Full Process Documentation

## Overview

The **Signal Intelligence Pipeline** is a medical device adverse event processing system that implements an L2-autonomy agentic workflow. It ingests FDA complaint data, extracts structured QMS (Quality Management System) fields via LLM, generates semantic embeddings, clusters events to detect emerging safety signals, and serves results through a REST API with a React dashboard.

---

## Architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         Signal Intelligence Pipeline                        │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│   ┌──────────┐    ┌──────────────┐    ┌───────────┐    ┌──────────────┐  │
│   │  Ingest  │───▶│  Extraction  │───▶│ Embedding │───▶│    Trend     │  │
│   │ (openFDA)│    │  (LLM Agent) │    │ (BGE-1024)│    │  (HDBSCAN)  │  │
│   └──────────┘    └──────────────┘    └───────────┘    └──────────────┘  │
│        │                  │                  │                  │          │
│        ▼                  ▼                  ▼                  ▼          │
│   ┌──────────────────────────────────────────────────────────────────┐    │
│   │                    SQLite Database                                │    │
│   │   events │ event_problems │ recalls │ clusters                   │    │
│   └──────────────────────────────────────────────────────────────────┘    │
│                                                                            │
├────────────────────────────────────────────────────────────────────────────┤
│   ┌────────────────┐              ┌──────────────────────┐                │
│   │  FastAPI (8000)│◀────────────▶│  React UI (5173)     │                │
│   └────────────────┘              └──────────────────────┘                │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

### System Requirements

| Component | Requirement |
|-----------|-------------|
| Python | 3.11+ |
| Ollama | Running locally at `http://localhost:11434` |
| LLM Model | `mistral-small` (pulled in Ollama) |
| Node.js | 18+ (for UI) |
| Disk | ~500 MB (embeddings + model cache) |
| RAM | 8 GB minimum (sentence-transformers + HDBSCAN) |

### Install Dependencies

```powershell
# From the part2/ directory
pip install -r requirements.txt
```

**Key packages:**
- `pydantic>=2.0` — Data validation & schema contracts
- `langchain>=0.3.0` + `langchain-ollama>=0.3.0` — LLM orchestration
- `sentence-transformers>=3.0.0` — BGE embedding model
- `torch>=2.0.0` — PyTorch backend
- `hdbscan>=0.8.33` — Density-based clustering
- `umap-learn>=0.5.5` — Dimensionality reduction
- `scikit-learn>=1.4.0` — Cosine similarity, silhouette score
- `fastapi` + `uvicorn` — REST API
- `requests>=2.31.0` — openFDA API calls

### Ollama Setup

```powershell
# Install Ollama and pull the model
ollama pull mistral-small
```

Ensure Ollama is running before starting extraction.

---

## Pipeline Stages

### Stage 1: Data Ingestion

**Module:** `src/pipeline/ingest.py`  
**Command:** `py main.py --ingest`

Downloads adverse event reports and recalls from the openFDA API for 8 medical device product codes:

| Code | Device |
|------|--------|
| LNH | MRI Systems |
| JAK | CT Scanners |
| IYE | CT (alternate) |
| LLZ | Ultrasound |
| IZL | Digital X-ray |
| MQB | Molecular Dx Instruments |
| GKZ | Hematology Analyzers |
| QKO | PCR Systems |

**Process:**
1. For each product code, paginate through `https://api.fda.gov/device/event.json` (100 per batch, max 5000 per code)
2. Parse raw JSON into flat event rows via `parse_event()`
3. Extract narratives from `mdr_text` arrays via `parse_narrative()`
4. Insert events + associated problems into SQLite
5. Download recalls from `https://api.fda.gov/device/recall.json`
6. Insert recalls with software-related flag (keyword heuristic)

**Error handling:** Exponential backoff on 429 rate limits, 3 retries per request.

**Output:** Populated `data/signal_intelligence.db` with `events`, `event_problems`, and `recalls` tables.

---

### Stage 2: LLM Extraction (Agent 1)

**Module:** `src/extraction/agent.py`  
**Command:** `py main.py --extract-only [--reflect] [--batch-size 10]`

Converts unstructured complaint narratives into 20 structured QMS fields using a local LLM.

**Autonomy Level:** L1 (Augmented LLM — single pass + optional self-reflection)

**Process:**
1. Query unextracted events from DB (`get_unextracted_events()`)
2. For each narrative:
   - **Pass 1 — Chain-of-Thought Extraction:**
     - Load system prompt from `configs/prompts/extraction.md`
     - Wrap narrative in `<user_narrative>…</user_narrative>` safety delimiters
     - Call LLM (temperature=0.1, format=json)
     - Parse JSON response
   - **Pass 2 — Self-Reflection (optional, `--reflect` flag):**
     - Load reflection prompt from `configs/prompts/reflection.md`
     - LLM reviews extraction for schema validity, consistency, completeness
     - Outputs corrected JSON if errors found
3. Validate output via Pydantic (`ExtractionOutput` model)
4. **Gate 1:** If `confidence < 0.5`, flag for human review
5. Write structured fields back to DB via `update_extraction_fields()`

**Extracted Fields (20):**
- `modality`, `component`, `failure_mode`, `symptom`
- `severity_indicator` (ISO 14971: S1–S5)
- `manufacturer`, `device_model`, `patient_impact`
- `discovery_phase`, `software_related`, `is_safety_related`
- `usability_concern`, `security_concern`
- `affected_countries`, `complaint_source`
- `qms_complaint_category` (13 ISO 13485 categories)
- `confidence`, `reasoning`

**QMS Categories:**
`SW-FUNC`, `SW-ALGO`, `HW-MECH`, `HW-ELEC`, `IMG-QUAL`, `PERF-ACC`, `SAFE-PAT`, `SAFE-OP`, `USAB`, `CONN`, `CYBER`, `ENV`, `MAINT`

---

### Stage 3: Embedding Generation

**Module:** `src/embeddings/generator.py`  
**Command:** `py main.py --embed-only`

Generates dense vector representations of complaint narratives for similarity search and clustering.

**Model:** `BAAI/bge-large-en-v1.5` (1024 dimensions, L2-normalized)

**Process:**
1. Load all narratives from DB via `get_narratives()`
2. Lazy-load SentenceTransformer model (auto GPU/CPU)
3. Batch encode narratives (batch_size=32)
4. Normalize embeddings to unit length
5. Save to `data/embeddings.npz` (compressed NumPy archive)

**Output:**
- `embeddings.npz` containing:
  - `embeddings`: (N, 1024) float32 matrix
  - `report_numbers`: (N,) string array mapping rows to events

**Single complaint (API):**
- `embed_single(text)` → returns 1024-dim normalized vector

---

### Stage 4: Trend Analysis & Clustering

**Module:** `src/trend/analyzer.py`  
**Command:** `py main.py --trend-only`

Applies unsupervised ML to detect emerging safety signals. **No LLM calls** — fully deterministic.

**Process:**

#### 4a. HDBSCAN Clustering
- Input: (N, 1024) embeddings matrix
- Parameters: `min_cluster_size=15`, `min_samples=5`, `metric="euclidean"`, `cluster_selection_method="eom"`
- Output: Cluster labels per event (-1 = noise)
- Quality metric: Silhouette score

#### 4b. UMAP 2D Projection
- Input: (N, 1024) embeddings
- Parameters: `n_neighbors=15`, `min_dist=0.1`, `metric="cosine"`
- Output: (N, 2) coordinates for dashboard visualization
- Saved to `data/umap_projection.npy`

#### 4c. Cluster Metadata
- **Label:** Dominant modality + dominant problem code
- **Size:** Event count per cluster
- **Growth rate:** `(events_last_30d − events_prior_30d) / events_prior_30d × 100%`
- **Trend flag:**
  - `emerging` → growth > 20%
  - `stable` → growth between -20% and +20%
  - `declining` → growth < -20%

#### 4d. New Complaint Assignment
- Compute cosine similarity to all cluster centroids
- Assign to nearest cluster
- Find top-K most similar historical events by cosine similarity
- Return `SimilarityOutput` with cluster ID, similar events, trend flag

**Output:** `clusters` table populated in DB with metadata.

---

## Running the Pipeline

### Full Pipeline (Batch)

```powershell
cd part2

# 1. Ingest data from openFDA
py main.py --ingest

# 2. Run full pipeline (extract + embed + cluster)
py main.py --full --batch-size 10 --reflect

# Or run stages individually:
py main.py --extract-only --batch-size 10
py main.py --embed-only
py main.py --trend-only
```

### Single Complaint (CLI)

```powershell
py main.py --complaint "The MRI system unexpectedly shut down during a patient scan. The gradient coil overheated causing thermal protection to activate."
```

### Check Stats

```powershell
py main.py --stats
```

---

## Running the API Server

### Start Backend

```powershell
cd part2
py api/server.py
```

Server starts at `http://0.0.0.0:8000`.

**Startup sequence:**
1. TensorFlow/oneDNN initialization (info messages — safe to ignore)
2. SentenceTransformer model loading
3. Embeddings + cluster centroids loaded into memory
4. Uvicorn serving on port 8000

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/process` | POST | Process complaint through pipeline |
| `/api/stats` | GET | Database statistics |
| `/api/clusters` | GET | All cluster metadata |
| `/docs` | GET | Swagger/OpenAPI docs |

### Example Request

```powershell
Invoke-RestMethod -Uri http://localhost:8000/api/process -Method POST -ContentType "application/json" -Body '{"narrative": "MRI showed banding artifacts during cardiac imaging sequence", "report_id": "TEST-001", "skip_extraction": true}'
```

**Response structure:**
```json
{
  "report_id": "TEST-001",
  "total_duration_ms": 1234.5,
  "steps": [
    {
      "step": "extraction",
      "status": "skipped",
      "duration_ms": 0,
      "data": {"message": "Skipped"}
    },
    {
      "step": "embedding",
      "status": "success",
      "duration_ms": 45.2,
      "data": {"dimensions": 1024, "vector_preview": [...], "norm": 1.0}
    },
    {
      "step": "cluster_assignment",
      "status": "success",
      "duration_ms": 12.1,
      "data": {
        "cluster_id": 3,
        "trend_flag": "emerging",
        "growth_rate": 35.2,
        "similar_events": [...]
      }
    }
  ]
}
```

---

## Running the UI

### Start Frontend

```powershell
cd part2/ui
npm install
npm run dev
```

Dashboard available at `http://localhost:5173`.

### UI Features

1. **Complaint Input** — Paste narrative or use sample complaints (MRI Shutdown, CT Artifact, Pump Overdose)
2. **Pipeline Visualization** — 3 stages with real-time status: 🧠 Extraction → 📐 Embedding → 🎯 Cluster
3. **Results Display:**
   - Extraction: QMS category, severity, confidence, reasoning
   - Embedding: Dimensions, vector preview, norm
   - Cluster: Label, size, growth rate, trend flag, top-5 similar events
4. **Stats Panel** — Total events, clusters, recalls from DB

---

## Running the Full Stack

```powershell
# Terminal 1: Start the API server
cd part2
py api/server.py

# Terminal 2: Start the UI dev server
cd part2/ui
npm run dev
```

Then open `http://localhost:5173` in your browser.

---

## Running Tests

```powershell
cd part2
py -m pytest tests/ -v
```

**Test coverage:**
- Schema validation (Pydantic models, enums, bounds)
- Extraction output validation
- Similarity output validation
- Pipeline handoff validation
- Prompt injection defense
- Database CRUD operations

---

## Project Structure

```
part2/
├── main.py                          # CLI entry point
├── requirements.txt                 # Python dependencies
├── api/
│   └── server.py                    # FastAPI REST API (port 8000)
├── configs/
│   └── prompts/
│       ├── extraction.md            # CoT extraction system prompt
│       └── reflection.md            # Self-reflection system prompt
├── data/
│   ├── signal_intelligence.db       # SQLite database (runtime)
│   ├── embeddings.npz               # Cached embeddings (N × 1024)
│   └── umap_projection.npy          # 2D projection for UI
├── src/
│   ├── __init__.py
│   ├── pipeline/
│   │   ├── orchestrator.py          # L2 pipeline coordinator
│   │   ├── database.py              # Schema, queries, parsing
│   │   ├── ingest.py                # openFDA data download
│   │   └── schemas.py               # Pydantic models & enums
│   ├── extraction/
│   │   └── agent.py                 # LLM extraction agent (L1)
│   ├── embeddings/
│   │   └── generator.py             # BGE-large embedding generator
│   └── trend/
│       └── analyzer.py              # HDBSCAN clustering + trends
├── tests/
│   └── test_pipeline.py             # Unit tests
└── ui/
    ├── package.json                 # React + Vite config
    ├── vite.config.js               # Vite dev server config
    └── src/
        ├── App.jsx                  # Main dashboard component
        └── main.jsx                 # React entry point
```

---

## Configuration

### Environment Variables

Create a `.env` file in `part2/`:

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=mistral-small
```

### Key Thresholds

| Parameter | Value | Purpose |
|-----------|-------|---------|
| Confidence Gate | < 0.5 | Flag extraction for human review |
| HDBSCAN min_cluster_size | 15 | Minimum events to form a cluster |
| HDBSCAN min_samples | 5 | Core point density threshold |
| Trend emerging threshold | > 20% | Growth rate to flag as emerging |
| Trend declining threshold | < -20% | Growth rate to flag as declining |
| Embedding dimensions | 1024 | BGE-large-en-v1.5 fixed |
| LLM temperature | 0.1 | Near-deterministic extraction |
| Similar events top-K | 10 | Events returned per query |

---

## Security Measures

- **Prompt injection defense:** Narratives wrapped in `<user_narrative>…</user_narrative>` XML tags
- **Input validation:** Pydantic models enforce type safety on all boundaries
- **CORS:** Restricted to `localhost:5173` and `localhost:3000`
- **No secrets in code:** LLM runs locally via Ollama (no API keys)
- **SQL parameterization:** All DB queries use parameterized statements
