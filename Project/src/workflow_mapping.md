# Architecture Mapping

## Fixed product scope

- LNH
- JAK
- LLZ

## 6-part breakdown to modules

- Complaint simulation: `src/utils/data_loader.py::simulate_complaints`
- Extract + archive + trend: `src/agents/extraction.py`, `src/agents/archive_trend.py`, `src/utils/storage.py`
- Orchestration agent: `src/agents/orchestration.py`, `src/pipeline/langgraph_flow.py`
- Report generation agent: `src/agents/report_generation.py`
- Risk analysis agent: `src/agents/risk_analysis.py`
- Retrieval agent from OpenFDA: `src/agents/retrieval.py`

## Top-level runner

- `src/pipeline/orchestrator.py`
- `src/run_workflow.py`

## Reliability and observability additions

- Node handoff validation and gate checks: `src/pipeline/schemas.py::validate_handoff`, `src/pipeline/langgraph_flow.py`
- Trace logging and propagation: `src/observability/tracer.py`, trace ids generated in `src/pipeline/orchestrator.py`
- Runtime persistence of trace and review metadata: `src/utils/storage.py`

## Orchestrator pattern

- Route-first state graph (LangGraph): extract -> retrieve -> trend -> risk -> route questions -> report
- Report types: VIGILANCE_ESCALATION, CAPA_INVESTIGATION, TREND_MONITORING
- Gate checkpoints: extraction confidence/schema, retrieval relevance/schema, risk evidence consistency
