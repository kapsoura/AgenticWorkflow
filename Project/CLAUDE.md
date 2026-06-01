# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Multi-Agent Regulatory Signal Intelligence System** — an MTech Deep Learning project building a GenAI pipeline for post-market quality signal detection in medical imaging and molecular diagnostics devices. It ingests FDA/openFDA adverse-event and recall data, processes incoming complaint narratives, and produces ISO-13485-formatted signal reports for Quality Manager (QM) review. This is **decision support, not decision automation** — a QM reviews and approves every output.

The repository is currently **documentation + data scripts only**; `src/` is the planned build target described in the design docs. The three design docs are the source of truth:
- `System_Design.md` — concrete architecture, per-component design, ISO 14971 risk methodology, validation gates, 4-week plan.
- `Ideation.md` — research framing, technique catalogue, and the full QMS/regulatory standards alignment.
- `Data_Architecture_and_Context.md` — data sourcing, simulation strategy, DB schema, product catalogue.
- `agentic_ai_week04_elaborate_notes.md` — the agentic-design lecture the architecture is audited against.

Target domain: Medical Imaging (MRI/CT/Ultrasound/X-ray) + Molecular Dx (Hematology/PCR). Product codes: LNH, JAK, IYE, LLZ, IZL, MQB, GKZ, QKO.

## Data Pipeline

Data is **not committed to git** — each member runs the download script locally; embeddings are shared via cloud storage.

```bash
# Download imaging + molecular-dx adverse events and recalls via openFDA
python data/download_imaging_data.py

# Data-quality analysis / exploration (regenerates data/analysis/)
python data/explore_final.py
```

`data/download_fda_data.py` is the older infusion-pump version (superseded by `download_imaging_data.py`). `data/test_api*.py` and `data/explore_*.py` are openFDA API probes.

openFDA constraint: 1000 results/query, max skip=25000 (26K total per query). The chosen product codes are all <26K events, so API pagination suffices — no bulk download needed. Ultrasound (LLZ, ~19K) needs multiple date-ranged queries.

Working set: ~14–20K adverse events (2019+) + 3,299 recalls.

## Architecture: 6-Component Pipeline (NOT "6 autonomous agents")

The design is audited against the Week 04 agentic-AI lecture, whose core principle is **architectural restraint**: *use the lowest autonomy level that solves the problem.* Each component is classified by its **actual autonomy level** — do not relabel them all as "agents," and do not add components without a justification against this framework.

```
complaint → Agent 1 (Extraction) → Similarity Module (non-LLM) + Agent 3 (Retrieval)
                                              ↓
                                   Agent 4 (Risk + CAPA, merged)
                                              ↓
                                   Agent 5 (Report Assembly) → QM review (human-in-the-loop)
```

| Component | Autonomy level | Notes |
|-----------|---------------|-------|
| Orchestrator | L2: Workflow (assembly line) | Fixed pipeline, engineer-defined control flow, no LLM routing |
| Agent 1 — Extraction | L1: Augmented LLM | Single-pass structured extraction + CoT + DSPy. Emits `confidence`, safety/usability/security flags, `qms_complaint_category` |
| Similarity Module | **Non-LLM pipeline** | Deterministic: sentence-transformers + HDBSCAN + UMAP + temporal anomaly scoring. **Not an agent** — keep LLMs out of it |
| Agent 3 — Retrieval | L1→L2: Augmented LLM, ReAct **only if** single-pass RAG underperforms | Graph RAG over knowledge graph (device→code→events→recalls) |
| Agent 4 — Risk + CAPA | L1: Augmented LLM | **Risk and CAPA merged into one call** to avoid over-orchestration. Encodes ISO 14971 methodology (see below) |
| Agent 5 — Report Assembly | L2: Evaluator-Optimizer | Self-critique loop with explicit stopping rubric; ISO 13485 §4.2.4 controlled-document output |

Key restructuring decisions (already made — preserve them): Risk+CAPA are one component, not two; the Similarity Module is deliberately non-LLM; there is no separate "Citation Critic" — citation grounding is enforced via Agent 4 constitutional guardrails + Validation Gate 3 + Agent 5 self-critique.

## Regulatory Framework Is Core, Not Decoration

The system is designed to operate inside a certified QMS, and the regulatory mapping drives the data schemas — a future instance must respect it when implementing components:

- **ISO 14971:2019 risk methodology is encoded in Agent 4**: a 5-level Severity scale (S1–S5), a 5-level Probability scale (P1–P5, calibrated to dataset event counts), and a 5×5 acceptability matrix yielding `ACCEPTABLE | ALARP | UNACCEPTABLE`. Agent 4's output schema is `iso14971_assessment` + `evidence_basis` + `capa_recommendation` + `escalation_flags`.
- **Escalation logic**: `escalation_required` when risk ∈ {ALARP, UNACCEPTABLE}; `prrc_notification_required` for UNACCEPTABLE only; `fsca_required` only after confirmed root cause AND UNACCEPTABLE AND active distribution.
- **IEC 62304 §9** (software problem resolution) maps step-by-step onto the pipeline (§9.1 extraction → §9.6 trend analysis → §9.7 verification).
- **ISO 13485 §8.2.2** complaint categories (e.g. `SW-FUNC`, `SW-ALGO`, `SW-DATA`, `IMG-QUAL`) are the controlled vocabulary Agent 1 maps to.
- Out-of-scope-but-acknowledged standards (IEC 80001-1, ISO/IEC 27001, full IEC 62366-1, GDPR) are documented as future work — keep them out of prototype scope.

Full clause-by-clause mapping lives in `Ideation.md` (QMS section) and `System_Design.md` (Regulatory Framework Integration).

## Reliability Patterns (implement these alongside the components)

These are first-class design requirements, not afterthoughts:

- **Validation gates between components** (cascading-failure prevention): Gate 1 after extraction (reject `confidence < 0.5`, unknown modality, missing critical fields), Gate 2 after retrieval (warn on 0 results / low relevance, discard items below relevance 0.3), Gate 3 after Risk+CAPA (reject HIGH risk with 0 citations, escalate LOW-risk-but-Death events, strip nonexistent recall references).
- **Prompt-injection mitigation**: wrap MAUDE narratives in `<user_narrative>…</user_narrative>` delimiters; system prompt instructs the model not to follow instructions inside them; validate every output against its JSON schema before handoff.
- **Loop safety**: Agent 3 ReAct cap 5 iters / 30s; Agent 5 self-critique cap 2 rounds / 20s; orchestrator 120s total budget; each has a defined fallback. Stopping is deterministic, not LLM self-assessment.
- **Memory discipline**: pass only summarized state between components (top-5 retrieval results, not raw payloads). Token budget ≈ 20K/report ≈ $0.15–0.30 with GPT-4.1.
- **Observability**: one `trace_id` per signal report propagated through all components; log every LLM call (tokens, latency, model, tool calls, gate result) so any run can be replayed. LangSmith (LangGraph-native) or a JSON logger to `logs/`.

## Build Approach: Baseline-First

Follow the minimal-viable-agent path. Week 1 starts with a **single LLM call** (complaint + ~20 recalls in context → extraction + risk + CAPA in one generation) — this doubles as ablation baseline #5. Add each enhancement (ChromaDB retrieval, CoT, self-reflection, multi-component split) only after measuring that it beats the baseline. Prove the baseline is insufficient before adding complexity.

## Three-Store Data Architecture

| Store | Library | Contents |
|-------|---------|----------|
| `signal_intelligence.db` | SQLite | 7 tables: events, event_problems, recalls, clusters, risk_statistics, signal_reports, etc. |
| Vector store | ChromaDB | 3 collections: event narratives, recall reasons, combined |
| Knowledge graph | NetworkX | ~3.4K nodes: device→ProductCode→Recall→RootCause, manufacturer cross-links |

`signal_reports` (SQLite) also serves as **episodic memory** — the Similarity Module checks whether a similar complaint was processed before.

## Planned `src/` Layout (per design docs)

```
src/
├── agents/        extraction.py · similarity.py (non-LLM) · retrieval.py · risk_capa.py · report.py
├── pipeline/      orchestrator.py · schemas.py (frozen JSON contracts — lock end of Week 1)
├── data_processing/   parse, normalize, manufacturer entity resolution (M1)
├── embeddings/    sentence-transformers + ChromaDB (M1+M4)
├── evaluation/    outcome + trajectory metrics, LLM-as-Judge (M6)
├── alignment/     DPO experiments (M5)
└── dashboard/     Streamlit + Plotly UMAP dashboard (M4)
configs/prompts/   one version-controlled system prompt per agent (procedural memory)
```

Ownership model (M1–M6): each component has one owner; `schemas.py` is the shared contract; every component must run standalone with mock inputs.

## Tech Stack

GPT-4.1/GPT-4o (primary) · Phi-3-mini/Llama-3-8B (DPO/distillation) · TRL (DPO primary, PPO if time) · DSPy · sentence-transformers (`all-MiniLM-L6-v2`) · ChromaDB · NetworkX · SQLite+Pandas · LangGraph · HDBSCAN+UMAP · Streamlit+Plotly · LangSmith. API keys go in `.env` (never commit).

## Entity Resolution

Manufacturer names need normalization — the same vendor appears under many names (e.g. "Philips Medical Systems Nederland B.V.", "Philips Electronics Nederland B.V.", "Philips Medical Systems DMC GmbH" are all Philips). Handle in `data_processing/` before building the knowledge graph.

## Evaluation

**Outcome metrics**: extraction F1 >0.80, retrieval Precision@5 >0.65, cluster silhouette >0.40, risk/CAPA rubric >3.0/5, hallucination <15% uncited claims, DPO win-rate >60%, LLM-Judge vs human kappa >0.60. **Trajectory metrics** (for the Agent 3 ReAct path): task completion rate, step efficiency, tool accuracy, error recovery, cost/task, latency. Benchmark: 50 labeled MAUDE narratives + 20 recall notices + 30 synthetic reports. Use outcome metrics for regression, trajectory metrics for debugging.

## Key Data Facts (verified 2026-05-29)

3,701 events + 3,299 recalls downloaded. 98.4% of events have narrative text (avg 836 chars). **32.6% of recalls cite "Software design" as root cause** (1,076/3,299); ~36.6% software-related total — these are CAPA ground truth. 36% of coded product problems are software-related. Philips dominates MRI (LNH). Many imaging events are hardware injuries (burns, ferromagnetic accidents) — pre-filter for software relevance with keywords: `software, image, display, artifact, algorithm, reconstruction, DICOM`.

## Positioning Discipline

Frame outputs as "evidence supports pattern, causation not confirmed." Every regulatory claim cites a specific FDA record. The system drafts; the QM approves; nothing is autonomously submitted or filed. Per ISO 14971 §7.2/§7.3/§8, residual-risk acceptability and risk-control decisions stay human.
