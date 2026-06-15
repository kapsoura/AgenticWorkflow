from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from src.config import (
    CHROMA_DIR,
    DEFAULT_COMPLAINT_BATCH,
    DEFAULT_MAX_EVENTS_PER_CODE,
    DEFAULT_RANDOM_SEED,
    IMAGING_EVENTS_DIR,
    LOGS_DIR,
    PRODUCT_CODES,
    RECALLS_FILE,
    REPORTS_DIR,
    SQLITE_DB_PATH,
)
from src.observability.tracer import TraceLogger
from src.pipeline.langgraph_flow import LangGraphSignalWorkflow
from src.pipeline.schemas import PipelineRunResult
from src.utils.data_loader import load_events_for_codes, load_recalls, simulate_complaints
from src.utils.storage import (
    archive_complaints,
    init_chroma,
    init_sqlite,
    persist_signal_report,
    upsert_event_vectors,
)


@dataclass
class WorkflowConfig:
    complaints_per_code: int = DEFAULT_COMPLAINT_BATCH
    max_events_per_code: int = DEFAULT_MAX_EVENTS_PER_CODE
    random_seed: int = DEFAULT_RANDOM_SEED


class SignalWorkflowOrchestrator:
    def __init__(self, config: WorkflowConfig | None = None):
        self.config = config or WorkflowConfig()
        self.workflow = LangGraphSignalWorkflow()

    def run(self) -> PipelineRunResult:
        run_id = f"run-{uuid4().hex[:8]}"
        started = datetime.utcnow()

        events_by_code = load_events_for_codes(
            imaging_events_dir=IMAGING_EVENTS_DIR,
            product_codes=PRODUCT_CODES,
            max_events_per_code=self.config.max_events_per_code,
        )
        recalls = load_recalls(recalls_file=RECALLS_FILE, product_codes=PRODUCT_CODES)
        complaints = simulate_complaints(
            events_by_code=events_by_code,
            complaints_per_code=self.config.complaints_per_code,
            seed=self.config.random_seed,
        )

        init_sqlite(SQLITE_DB_PATH)
        archive_complaints(SQLITE_DB_PATH, complaints)
        vector_collection = init_chroma(CHROMA_DIR)
        for code in PRODUCT_CODES:
            upsert_event_vectors(vector_collection, events_by_code.get(code, []))

        generated_paths: list[str] = []
        trace_paths: list[str] = []
        for complaint in complaints:
            trace_id = f"{run_id}-{complaint.complaint_id}"
            tracer = TraceLogger(trace_id=trace_id, logs_dir=LOGS_DIR)
            try:
                reports = self.workflow.run_for_complaint(
                    trace_id=trace_id,
                    tracer=tracer,
                    complaint=complaint,
                    events_by_code=events_by_code,
                    recalls=recalls,
                    vector_collection=vector_collection,
                    max_runtime_seconds=120,
                )
            except TimeoutError as exc:
                tracer.log(
                    agent="workflow",
                    event="timeout",
                    gate_result="review",
                    error=str(exc),
                    metadata={"complaint_id": complaint.complaint_id},
                )
                continue

            for report in reports:
                path = self.workflow.report_agent.persist_report(signal_report=report, reports_dir=REPORTS_DIR)
                persist_signal_report(SQLITE_DB_PATH, report)
                generated_paths.append(str(path))
            trace_paths.append(str(tracer.path))

        completed = datetime.utcnow()
        return PipelineRunResult(
            run_id=run_id,
            started_at=started,
            completed_at=completed,
            selected_product_codes=list(PRODUCT_CODES),
            processed_complaints=len(complaints),
            generated_report_paths=generated_paths,
            generated_trace_paths=trace_paths,
        )
