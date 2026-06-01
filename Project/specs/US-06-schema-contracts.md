# US-06: Shared JSON Schema Contracts

| Field | Value |
|---|---|
| Epic | A. Foundation |
| Owner | M2 (final decision authority) |
| Sprint | Week 1 (FROZEN end of Week 1) |
| Priority | P0 |
| Estimate | 1–2 days |
| Status | Not started |

## User Story
As **any component owner**, I want the inter-component JSON contracts defined and frozen in one place, so that all six components can be built and tested independently against stable interfaces without integration surprises.

## Context
The pipeline communicates via **message passing** with typed JSON (`System_Design.md` §Collaboration). Freezing these end of Week 1 is the single most important integration risk control. Schemas mirror the component outputs in `System_Design.md` (extraction, similarity, retrieval, risk+capa merged, report).

## Scope
- **In**: `src/pipeline/schemas.py` with Pydantic models + `validate()` helpers + mock-output factories for each component.
- **Out**: business logic (lives in each component).

## Inputs / Outputs
- **Output**: `schemas.py` exposing `ExtractionOutput`, `SimilarityOutput`, `RetrievalOutput`, `RiskCapaOutput`, `ReportOutput`, plus `mock_<x>()` factories. Field definitions per `System_Design.md` (note: `severity_indicator` uses S-codes e.g. `S3_serious`; risk output is the merged `iso14971_assessment` + `evidence_basis` + `capa_recommendation` + `escalation_flags`).

## Acceptance Criteria
- [ ] Given each component output, when validated, then required fields are enforced and bad payloads raise a clear error. Specifically `ExtractionOutput` requires: `modality`, `component`, `failure_mode`, `severity_indicator` (S1–S5 code), `software_related`, `is_safety_related`, `usability_concern`, `security_concern`, `affected_countries`, `complaint_source`, `qms_complaint_category` (13-code ISO 13485 §8.2.2 enum), `confidence`.
- [ ] Given `RiskCapaOutput`, when validated, then `risk_level ∈ {ACCEPTABLE, ALARP, UNACCEPTABLE}` (ISO 14971 5×5 matrix) is enforced — "HIGH"/"MEDIUM"/"LOW" are NOT valid values.
- [ ] Given a downstream component under test, when it imports `mock_extraction()` etc., then it can run standalone without upstream components.
- [ ] Given the schema is frozen (end Week 1), then any later change requires team sign-off and a version bump comment.
- [ ] Given `escalation_flags`, then the model encodes the rule constraints: `escalation_required` true iff `risk_level ∈ {ALARP, UNACCEPTABLE}`; `prrc_notification_required` true iff `risk_level == UNACCEPTABLE`; `fsca_required` true iff (confirmed_root_cause AND UNACCEPTABLE AND active_distribution).

## Technical Approach
1. Pydantic v2 models; enums for modality, severity S1–S5, risk level, trend flag.
2. `mock_*()` factories returning schema-valid example instances (reuse the JSON examples from `System_Design.md`).
3. A `validate_handoff(stage_name, payload)` used by the orchestrator gates (US-14).

## Dependencies
Blocked by: none (needs the field designs already in System_Design.md). Blocks: US-07, US-09, US-11, US-12, US-13, US-14.

## Test Plan
- Unit: valid mock passes; missing required field fails; out-of-enum value fails; escalation cross-field rule enforced.

## Definition of Done
- [ ] `schemas.py` + mocks committed, reviewed by all owners, tagged "FROZEN v1".
- [ ] Each downstream spec references the exact model it consumes/produces.
