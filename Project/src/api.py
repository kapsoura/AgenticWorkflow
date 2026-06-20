from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Optional
from zipfile import ZipFile

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from src.agents.report_sections import SECTION_KEYWORDS, blueprint_for
from src.config import PRODUCT_CODES, REPORTS_DIR
from src.pipeline.orchestrator import SignalWorkflowOrchestrator, WorkflowConfig
from src.pipeline.service import SignalService
from src.utils.docx_io import extract_headings_from_docx, render_report_docx


# Shared service holding the loaded archive (FDA events, recalls, SQLite, Chroma).
_service: Optional[SignalService] = None


def get_service() -> SignalService:
    global _service
    if _service is None:
        _service = SignalService()
    return _service


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the working archive at application startup so the database (SQLite tables
    # + Chroma vectors) is ready before the first request, rather than paying the
    # one-time load cost lazily on the first call.
    get_service()
    yield


app = FastAPI(
    title="Regulatory Signal Intelligence API",
    version="0.4.0",
    lifespan=lifespan,
)

WEB_DIR = Path(__file__).resolve().parent / "web"

# Report types the user can expect from the orchestrator's decision.
ACTIVE_REPORT_TYPES = ["PSUR", "INCIDENT_ASSESSMENT", "CAPA"]


class WorkflowRequest(BaseModel):
    complaints_per_code: int = Field(default=6, ge=1, le=50)
    max_events_per_code: int = Field(default=250, ge=10, le=2000)
    seed: int = 42


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "signal-workflow"}


@app.post("/run")
def run_workflow(request: WorkflowRequest) -> dict:
    orchestrator = SignalWorkflowOrchestrator(
        config=WorkflowConfig(
            complaints_per_code=request.complaints_per_code,
            max_events_per_code=request.max_events_per_code,
            random_seed=request.seed,
        )
    )
    result = orchestrator.run()
    return asdict(result)


@app.get("/api/meta")
def meta() -> dict:
    """Static metadata the UI needs to render its controls."""
    return {
        "product_codes": list(PRODUCT_CODES),
        "event_types": ["Malfunction", "Injury", "Death"],
        "report_types": ACTIVE_REPORT_TYPES,
    }


@app.get("/api/templates")
def templates() -> dict:
    """Describe the supported report templates and the section catalog.

    The section catalog is what an uploaded skeleton's headings are matched
    against; the blueprints are the built-in structures used when no template is
    supplied.
    """
    catalog = [
        {"section": name, "keywords": keywords}
        for name, keywords in SECTION_KEYWORDS.items()
    ]
    blueprints = {
        report_type: [
            {"name": spec.name, "title": spec.title} for spec in blueprint_for(report_type)
        ]
        for report_type in ACTIVE_REPORT_TYPES
    }
    return {"section_catalog": catalog, "blueprints": blueprints}


async def _read_template_headings(template: Optional[UploadFile]):
    if template is None or not template.filename:
        return None
    content = await template.read()
    if not content:
        return None
    try:
        return extract_headings_from_docx(content)
    except Exception:
        return None


@app.post("/api/analyze")
async def analyze(
    narrative: str = Form(...),
    product_code: str = Form(...),
    event_type: str = Form("Malfunction"),
    manufacturer: str = Form("Unknown"),
    template: Optional[UploadFile] = File(None),
) -> dict:
    """Run the workflow and return the full validation payload (no file download)."""
    template_headings = await _read_template_headings(template)
    service = get_service()
    return service.analyze_complaint(
        narrative=narrative,
        product_code=product_code,
        event_type=event_type,
        manufacturer=manufacturer,
        template_headings=template_headings,
    )


@app.get("/download/{name}")
def download(name: str) -> FileResponse:
    """Serve a previously-rendered report file from the reports directory."""
    safe_name = Path(name).name
    target = (REPORTS_DIR / safe_name).resolve()
    reports_root = REPORTS_DIR.resolve()
    if reports_root not in target.parents or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    media = (
        "application/zip"
        if target.suffix == ".zip"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return FileResponse(path=str(target), media_type=media, filename=target.name)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (WEB_DIR / "index.html").read_text(encoding="utf-8")


@app.post("/generate")
async def generate(
    narrative: str = Form(...),
    product_code: str = Form(...),
    event_type: str = Form("Malfunction"),
    manufacturer: str = Form("Unknown"),
    template: Optional[UploadFile] = File(None),
) -> FileResponse:
    template_headings = await _read_template_headings(template)

    service = get_service()
    reports = service.run_complaint(
        narrative=narrative,
        product_code=product_code,
        event_type=event_type,
        manufacturer=manufacturer,
        template_headings=template_headings,
    )

    # Render every decided report to Word. A single report is returned directly;
    # multiple reports are bundled into a zip so the caller receives the whole set.
    docx_paths = []
    for report in reports:
        out_path = REPORTS_DIR / f"{report.report_id}.docx"
        render_report_docx(report, out_path)
        docx_paths.append(out_path)

    if len(docx_paths) == 1:
        out_path = docx_paths[0]
        return FileResponse(
            path=str(out_path),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=out_path.name,
        )

    primary = reports[0]
    zip_path = REPORTS_DIR / f"{primary.report_id}-bundle.zip"
    with ZipFile(zip_path, "w") as bundle:
        for path in docx_paths:
            bundle.write(path, arcname=path.name)
    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=zip_path.name,
    )
