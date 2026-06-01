# US-15: Observability & Tracing

| Field | Value |
|---|---|
| Epic | C. Integration |
| Owner | M6 (cross-cutting) |
| Sprint | Week 1 (skeleton) → Week 4 |
| Priority | P1 |
| Estimate | 2–3 days |
| Status | Not started |

## User Story
As a **developer / evaluator**, I want every LLM and tool call logged under one trace id per report, so that I can replay any failed run step-by-step, compute cost/latency, and supply trajectory-evaluation data.

## Context
`System_Design.md` §Observability. Lecture rule: "if a failed run cannot be replayed step by step, logging is insufficient." Underpins US-14 debugging, US-16 trajectory metrics, US-10 stats page.

## Scope
- **In**: logging wrapper for all LLM/tool calls; `trace_id` propagation; per-call JSON log schema; aggregation helpers (cost/latency/completion-rate).
- **Out**: production APM, alerting.

## Inputs / Outputs
- **Output**: `src/observability/tracer.py`; per-call records to `logs/<trace_id>.jsonl` (and/or LangSmith) using the schema in `System_Design.md` (`trace_id, agent, timestamp, input/output_tokens, model, latency_ms, tool_calls[], gate_result, error`).

## Acceptance Criteria
- [ ] Given any LLM/tool call in any component, when it runs, then a log record with the full schema is written under the report's `trace_id`.
- [ ] Given a completed report, when its trace is queried, then the full ordered step sequence (every call, gate result, tokens, latency) can be replayed.
- [ ] Given a day of runs, when aggregated, then cost/report, mean latency, per-component latency breakdown, and completion rate are computable.
- [ ] Given a failure, then the `error` field and the gate that caught it are captured.

## Technical Approach
1. Decorator/context-manager wrapping model + tool calls; pull `trace_id` from pipeline state.
2. Append JSONL per trace; optional LangSmith integration (LangGraph-native).
3. Aggregation script feeding the US-10 stats page and US-16 trajectory metrics.

## Dependencies
Blocked by: none (skeleton early). Integrates with: US-14, US-16, US-10.

## Test Plan
- Unit: wrapped dummy call emits a schema-valid record.
- Integration: a full pipeline run produces a replayable trace; aggregation yields cost/latency.

## Definition of Done
- [ ] Tracer wired into all components; replayable traces verified; aggregation feeds dashboard + eval.
