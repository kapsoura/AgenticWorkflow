# Project Viability Assessment

> **Date**: 2026-06-01  
> **Project**: Multi-Agent Regulatory Signal Intelligence System for Medical Imaging & Molecular Diagnostics  
> **Purpose**: Systematic assessment of ISO standards knowledge, data availability, and project feasibility

---

## 1. ISO Standards Understanding — Gap Analysis

### Standards Coverage Status

| Standard | Clauses Referenced | Understanding Level | Source of Knowledge | Gap |
|----------|-------------------|--------------------|--------------------|-----|
| **ISO 13485:2016** | §4.2.4, §4.2.5, §5.6, §7.1, §8.2.1, §8.2.2, §8.5.2, §8.5.3 | Sufficient for implementation | OpenRegulatory templates, public guidance, OneQMS familiarity | Full standard text paywalled (~$180 CHF) |
| **ISO 14971:2019** | §5.4, §5.5, §6, §7.1–§7.6, §8, §9, §10, Annex C, Annex D | Strong — full risk process mapped | Public summaries, MEDDEV guidance, OpenRegulatory risk templates | Annex D examples are illustrative only |
| **IEC 62304:2006+A1:2015** | §4.3, §5–§9 | Strong — §9 mapped step-by-step | AAMI summaries, OpenRegulatory templates, FDA guidance on software lifecycle | Full standard text paywalled |
| **IEC 82304-1:2016** | §6, §7, §8 | Partial — referenced for completeness | Public summaries only | Not critical for our implementation |
| **FDA 21 CFR Part 820** | §820.90, §820.198 | Strong — full text freely available | eCFR.gov (free, full text) | None |
| **EU MDR 2017/745** | Art. 83, 86, 87, 88, 89 | Strong — full text freely available | EUR-Lex (free, full text) | None |
| **MDCG 2019-16 Rev. 1** | — | Moderate | EC website (free guidance) | None |
| **MDCG 2020-7** | — | Moderate | EC website (free guidance) | None |
| **ISO/IEC 42001:2023** | §6.1, §8.4, §9.1, Annex B | Partial — newest standard, less public material | Published summaries, conference presentations | Full text paywalled; limited public implementation guides |

### What We Actually Need vs What's Available

For an MTech research prototype demonstrating *how AI can support QMS processes*, we do NOT need to own every standard. We need to demonstrate:

1. **Understanding of requirements** each clause imposes → Available from public guidance
2. **Correct implementation pattern** → Available from OpenRegulatory templates + Innolitics RDM
3. **Accurate terminology** → Available from standard titles, clause headings, and guidance documents
4. **Defensible justification** → Our ISO 14971 risk matrix and IEC 62304 §9 mapping are structurally correct

### Free Public Sources That Provide Sufficient Knowledge

| Source | URL | What It Provides |
|--------|-----|-----------------|
| OpenRegulatory Templates | https://github.com/openregulatory/templates | Audit-ready document templates implementing ISO 13485, IEC 62304, ISO 14971 |
| Innolitics RDM | https://github.com/innolitics/rdm | Traceability matrices, risk tables, YAML-based requirements |
| EUR-Lex | https://eur-lex.europa.eu/ | Full EU MDR 2017/745 text |
| eCFR.gov | https://www.ecfr.gov/ | Full 21 CFR 820 text |
| MDCG Guidance | https://health.ec.europa.eu/medical-devices-sector/new-regulations/guidance-mdcg-endorsed-documents_en | Free implementation guidance for EU MDR |
| FDA Software Guidance | https://www.fda.gov/medical-devices/digital-health-center-excellence/ | Free guidance on software validation, AI/ML, cybersecurity |
| IMDRF Documents | http://www.imdrf.org/documents/documents.asp | SaMD classification, risk categorization (N12, N41) |
| FDA CDRH Learn | https://www.fda.gov/training-and-continuing-education/cdrh-learn | Free educational modules on device regulation |

### Recommendation for ISO Standard Access

- **Check IISc Bengaluru library**: Many university libraries have ISO/BSI digital subscriptions. Check if IISc provides access through SAI Global, Techstreet, or ISO Online Browsing Platform (OBP).
- **If unavailable**: The combination of OpenRegulatory templates + FDA guidance + MDCG guidance + EUR-Lex provides sufficient implementation knowledge for a research project.
- **In the report**: Frame as "System designed to comply with ISO 14971:2019 risk management methodology as documented in publicly available guidance and organizational QMS procedures."

---

## 2. Data Availability — Complete Inventory

### Data We Have (Downloaded and Verified)

| Dataset | Records | Format | Access | Status |
|---------|---------|--------|--------|--------|
| FDA MAUDE Adverse Events (8 product codes) | 3,701 | JSON via API | openFDA API (free) | ✅ Downloaded |
| FDA Device Recalls (8 product codes) | 3,299 | JSON via API | openFDA API (free) | ✅ Downloaded |
| — Software-related recalls subset | 1,076 (32.6%) | Filtered from above | — | ✅ Identified |
| Narrative text coverage | 98.4% of events | Text field in JSON | — | ✅ Verified |

### Data Available But Not Yet Downloaded

| Dataset | Estimated Volume | Access Method | Cost | Priority |
|---------|-----------------|---------------|------|----------|
| Full MAUDE (2019+ all 8 codes) | ~14,000–20,000 events | openFDA API pagination | Free | Week 1 — M1 task |
| FDA Device Classification | ~6,000 product codes | openFDA API | Free | Week 1 — context enrichment |
| FDA 510(k) Clearances (imaging/MolDx) | ~500–1,000 relevant | openFDA API | Free | Week 1 — predicate device context |
| FDA UDI/GUDID | Device-level metadata | openFDA API | Free | Week 1 — entity resolution |
| FDA Problem Codes codebook | ~2,000 codes | FDA website download (CSV) | Free | Week 1 — ontology |
| MAUDE Bulk Download (full history) | 355 ZIP files (~50GB) | open.fda.gov/download | Free | Optional — API sufficient for scope |

### Data We Must Create

| Dataset | Quantity Needed | Method | Effort | Owner |
|---------|----------------|--------|--------|-------|
| Synthetic internal complaints | 200 | GPT-4 generation using MAUDE narrative templates | ~4 hours | M1 |
| Gold-standard labeled examples | 50 | Manual annotation by team (extraction fields, relevance, quality) | ~10 person-hours | M6 + all |
| DPO preference pairs | 50+ | Team compares good vs bad report drafts | ~8 person-hours (Week 2-3) | M6 |
| LLM-as-Judge calibration set | 20 | Subset of gold-standard with human scores | ~3 person-hours | M6 |

### Data We Cannot Get

| Dataset | Why Unavailable | Impact | Mitigation |
|---------|-----------------|--------|------------|
| Real internal complaints from a medical device company | Confidential, NDA-protected | Cannot validate on actual QMS data | Synthetic generation from MAUDE templates — explicitly documented as limitation |
| Expert QM reviewer feedback | Would need industry partnership | DPO limited to team-generated preferences | Frame as methodology demonstration, not production alignment |
| ISO standard full texts | Paywalled ($180-300 each) | Cannot quote verbatim in report | Use public guidance + templates; check university library |
| Patient-identifiable data | Not in MAUDE (FDA redacts) | None — this is by design | N/A — we process no PII |

### API Constraints

| Constraint | Value | Impact | Mitigation |
|-----------|-------|--------|------------|
| openFDA rate limit | 240 requests/minute (with API key) | Minimal — we batch download | Implement backoff, use API key |
| Skip + limit ceiling | ≤ 26,000 | Cannot paginate beyond 26K for a single query | All our product codes have < 26K events — no issue |
| Results per query | 1,000 max | Need pagination for full download | Implemented in download script |
| MAUDE data latency | ~2 weeks from event to database | Recent events may be missing | Acceptable for research — not real-time surveillance |

---

## 3. Technical Viability Assessment

### Component-Level Risk Analysis

| Component | Technical Risk | Confidence | Evidence |
|-----------|---------------|-----------|----------|
| Agent 1: LLM Extraction | **LOW** | 90% | GPT-4.1 structured output is proven; CoT + DSPy well-documented |
| Similarity Module: Clustering | **LOW** | 90% | sentence-transformers + HDBSCAN is standard ML; 98.4% narrative coverage |
| Agent 3: RAG Retrieval | **MEDIUM** | 75% | Medical narratives can be noisy; Graph RAG adds complexity |
| Agent 4: Risk Scoring | **MEDIUM** | 70% | LLM must consistently use our 5×5 matrix; constitutional guardrails needed |
| Agent 5: Report Assembly | **LOW** | 85% | Template filling + self-critique is well-established |
| DPO Alignment | **MEDIUM** | 65% | 50 pairs is small; may show trend but not statistical significance |
| End-to-End Integration | **MEDIUM-HIGH** | 60% | 6 components must work together; integration always harder than expected |
| Evaluation Pipeline | **LOW** | 85% | LLM-as-Judge methodology is established; Cohen's kappa is standard |

### Technology Stack Readiness

| Technology | Maturity | Documentation | Team Familiarity |
|-----------|----------|---------------|-----------------|
| GPT-4.1 / OpenAI API | Production | Excellent | High |
| LangGraph | Mature | Good | Medium — requires Week 1 learning |
| ChromaDB | Stable | Good | Medium |
| HDBSCAN + UMAP | Established ML | Excellent (scikit-learn ecosystem) | High |
| DSPy | Emerging | Moderate | Low — requires experimentation |
| TRL (DPO) | Stable | Good | Low — M5/M6 must learn |
| Streamlit | Production | Excellent | High |
| LangSmith | Stable | Good | Low — M5 to set up |

### Key Technical Risks and Mitigations

| # | Risk | Probability | Impact | Mitigation |
|---|------|------------|--------|------------|
| 1 | Agent 4 inconsistently applies risk matrix | Medium | High | Constitutional guardrails + validation gate + explicit CoT steps through matrix |
| 2 | RAG retrieval returns irrelevant events | Medium | Medium | Semantic re-ranking + relevance threshold (0.3) + Graph RAG structure |
| 3 | DPO training doesn't converge with 50 pairs | Medium | Low | Frame as methodology demonstration; report learning curve |
| 4 | Integration breaks at JSON contract boundaries | Medium | High | Contracts frozen Week 1; mock I/O testing; schema validation |
| 5 | LangGraph complexity slows development | Low | Medium | Start with simple linear orchestration; add ReAct/loops only when baseline measured |
| 6 | Token budget exceeded for complex cases | Low | Medium | Summarization at checkpoints; retrieval result pruning |
| 7 | Cluster quality poor for short narratives | Low | Low | Filter events with < 100 chars; augment with metadata |

---

## 4. Scope Viability — Can 6 People Build This in 4 Weeks?

### Effort Estimation

| Week | Total Person-Days (6 people × 5 days) | Critical Path | Slack |
|------|---------------------------------------|---------------|-------|
| Week 1 | 30 person-days | Data pipeline + baseline + contracts | Medium — parallel work |
| Week 2 | 30 person-days | Individual agents (all parallel) | High — independent streams |
| Week 3 | 30 person-days | Integration + DPO + evaluation | **Low — highest risk week** |
| Week 4 | 30 person-days | Ablation + demo + report | Medium — depends on Week 3 |

### Week 3 Integration Risk (Highest Risk)

**Why Week 3 is the bottleneck**:
- All 6 components must connect for the first time
- Real data flows through the full pipeline (not mocks)
- DPO training happens concurrently with integration debugging
- Evaluation requires stable pipeline to produce meaningful results

**Mitigation strategies**:
1. JSON schema contracts frozen end of Week 1 — no interface changes after this
2. Each agent tested with real data individually in Week 2 (not just mocks)
3. M2 dedicated to integration (not building new features) in Week 3
4. Daily 15-min sync in Week 3 to surface blockers immediately
5. "Ship what works" fallback: if Agent 3 Graph RAG isn't ready, use flat RAG

### Minimum Viable Deliverable (If Things Go Wrong)

Even if we hit significant blockers, the following is achievable with reduced scope:

| Component | Full Plan | Minimum Viable | Still Publishable? |
|-----------|-----------|----------------|-------------------|
| Agent 1 | CoT + DSPy + self-reflection | CoT extraction only | Yes |
| Similarity Module | HDBSCAN + UMAP + temporal | HDBSCAN + UMAP (no temporal) | Yes |
| Agent 3 | ReAct + Graph RAG | Simple vector RAG | Yes |
| Agent 4 | ISO 14971 matrix + CoT + guardrails | CoT risk scoring (no formal matrix) | Partial |
| Agent 5 | Self-critique + DPO-aligned | Template filling only | Partial |
| Evaluation | Full ablation + trajectory | Outcome metrics only | Yes |
| DPO | 50 pairs + before/after | Report methodology, show 10-pair pilot | Yes (as future work) |

---

## 5. Academic Viability — Is This MTech-Worthy?

### Novelty Claim

**No published work combines ALL of the following in a single system**:
- Multi-agent LLM pipeline for post-market surveillance
- ISO 14971 risk methodology encoded in LLM reasoning
- RAG over real FDA adverse event + recall databases
- DPO alignment for regulatory report generation
- Ablation study with trajectory + outcome evaluation

**Closest related work**:
- General medical NLP (NER on clinical notes) — doesn't address regulatory QMS
- FDA signal detection (traditional statistical methods) — no LLM/agent architecture
- Multi-agent systems (general) — not applied to medical device quality

### Research Contributions (Ranked by Strength)

| # | Contribution | Type | Strength |
|---|-------------|------|----------|
| 1 | DPO alignment for regulated-domain report generation | Novel application | Strong — publishable |
| 2 | ISO 14971 risk methodology encoded in LLM Chain-of-Thought | Novel method | Strong — practical + novel |
| 3 | Multi-agent ablation study (component removal analysis) | Rigorous methodology | Strong — demonstrates understanding |
| 4 | Graph RAG for device→event→recall knowledge traversal | Applied technique | Medium — technique exists, domain is new |
| 5 | Temporal anomaly detection on NLP-derived clusters | Applied technique | Medium — combines known methods |
| 6 | LLM-as-Judge calibration for regulatory text quality | Applied evaluation | Medium — methodology contribution |

### Grading Criteria Alignment (Typical MTech Project)

| Criterion | Our Coverage |
|-----------|-------------|
| Literature awareness | 15 advanced techniques documented with implementation plan |
| Technical depth | RAG + DPO + Graph RAG + ReAct + temporal ML + evaluation methodology |
| Implementation quality | 6-component pipeline with real data, not toy examples |
| Evaluation rigor | Ablation study, trajectory metrics, LLM-Judge correlation, outcome metrics |
| Practical relevance | Directly applicable to medical device quality management |
| Standards awareness | ISO 14971, IEC 62304, ISO 13485 mapped to system architecture |
| Presentation quality | Dashboard with UMAP visualization, demo scenario, formatted reports |

---

## 6. Summary Verdict

| Dimension | Verdict | Confidence |
|-----------|---------|-----------|
| **ISO Standards Knowledge** | Sufficient for research prototype | 80% — public guidance covers implementation needs |
| **Data Availability** | Strong — all primary data freely available | 95% — FDA ecosystem is well-designed for research |
| **Technical Feasibility** | Achievable with baseline-first approach | 75% — Week 3 integration is the real test |
| **Scope for 4 Weeks / 6 People** | Tight but realistic | 70% — requires discipline on contracts + scope |
| **Academic Merit** | Strong MTech-level project | 90% — novel domain + rigorous methodology + real data |

### Top 3 Actions to De-Risk

1. **Check IISc library for ISO standard access** — If digital subscriptions exist, download ISO 14971 and IEC 62304 to verify our clause interpretations are correct.
2. **Build single-LLM baseline on Day 1-2 of Week 1** — This proves the gap that justifies multi-agent complexity AND gives us Ablation Study #1 for free.
3. **Freeze JSON contracts by end of Week 1** — No interface changes after this. All Week 2 work must conform to frozen schemas. This is the #1 mitigation for Week 3 integration risk.

---

## 7. QMS Process Review Feedback (2026-06-01)

> External review of project alignment with Quality Management System processes.

### Verdict: Well-positioned for QMS integration

### Key Requirements from Review

#### 1. Standards and Regulatory Alignment

| Standard | Requirement | Current Coverage | Action Needed |
|----------|------------|-----------------|---------------|
| EN 62304/A1:2015 | Medical device software lifecycle | §9 mapped to pipeline | None — already covered |
| EN ISO 15223-1:2021 | Labelling symbols | Not referenced | Low priority — labelling is not in scope for signal detection |
| EN 62366-1:2015 | Usability engineering | Not referenced | Consider adding usability of the QM dashboard as a requirement |
| ISO 14971 | Risk management methodology | Full 5×5 matrix encoded in Agent 4 | None — already covered |

#### 2. Complaint Management and Reporting — Gaps Identified

The review flags that our pipeline should also support:

| Requirement | Current Status | Priority | How to Address |
|-------------|---------------|----------|----------------|
| Determine affected countries for adverse event reporting | ❌ Not in scope | Medium | Add `affected_countries` field to extraction schema — derivable from manufacturer + distribution data |
| Reporting to regulatory bodies (FDA, BfArM, Notified Body) | ❌ Not automated | Low | Out of scope for prototype — note as "future work: automated MDR/MIR form pre-fill" |
| Field Safety Corrective Actions (FSCA) | Partially covered by CAPA output | Medium | Add `fsca_required: boolean` flag to risk output when risk = UNACCEPTABLE |
| Customer Safety Advisory Notices (CSAN) | ❌ Not in scope | Low | Future work — downstream of CAPA approval |
| Traceability per complaint and corrective action | ✅ Covered | — | Traceability JSON already includes full audit trail |

#### 3. Post-Market Surveillance Integration

| Requirement | Current Status | Action |
|-------------|---------------|--------|
| PMCF (Post-Market Clinical Follow-up) | Not directly addressed | Add note: our signal reports feed into PMCF activities as evidence source |
| PSUR (Periodic Safety Update Report) | Partially covered by trend data | Similarity Module trend output maps to PSUR trend section |
| Public database screening | ✅ Core function | Agent 3 retrieval from MAUDE + recalls satisfies this |

#### 4. Evaluation and Documentation

Review confirms our evaluation strategy is QMS-compatible:
- Extraction F1 → scientific evaluation evidence
- Retrieval Precision@5 → evidence of component validation
- Expert rubric → qualification evidence
- Ablation studies → continuous improvement documentation

#### 5. Output and Traceability

Review confirms:
- Signal report format must meet QMS documentation standards → ✅ Agent 5 produces controlled document format
- All outputs must be traceable and auditable → ✅ Traceability JSON with full audit trail
- Must support management review → ✅ Aggregated metrics planned for dashboard

### Actions to Incorporate from Review

| # | Action | Owner | When | Impact on Design |
|---|--------|-------|------|-----------------|
| 1 | Add `affected_countries` to extraction output schema | M3 | Week 1 | Minor schema addition |
| 2 | Add `fsca_required` boolean to risk output | M5 | Week 2 | Add logic: if risk = UNACCEPTABLE → flag FSCA |
| 3 | Add note in report that signal outputs feed PMCF/PSUR | M3 | Week 3 | Report template addition |
| 4 | Reference EN 62304/A1:2015 explicitly (not just IEC 62304) | All | Week 1 | Terminology update in docs |
| 5 | Document that regulatory body reporting (MDR/MIR form pre-fill) is future work | M6 | Week 4 | Report "future work" section |

### Standards Not Yet Referenced (from review)

- **EN ISO 15223-1:2021** — Medical device labelling symbols. Not directly relevant to our signal detection pipeline, but good to acknowledge awareness in the report.
- **EN 62366-1:2015** — Usability engineering. Relevant if we discuss the QM dashboard UX, but not core to the AI pipeline.

---

## 7B. Extended QMS Review Feedback (2026-06-01, Round 2)

> Second round of review feedback, expanding standards coverage and clarifying functional expectations per agent.

### 1. Additional Standards to Acknowledge

| Standard | Scope | Current Coverage | Action |
|----------|-------|-----------------|--------|
| ISO 13485:2016 | Quality Management Systems | ✅ Already covered (§§4.2.4, 5.6, 7.1, 8.2.1, 8.2.2, 8.5.2, 8.5.3) | None |
| ISO 14971:2019 | Risk Management | ✅ Full 5×5 matrix in Agent 4 | None |
| IEC 62304 | Software Life Cycle | ✅ §9 mapped to pipeline | None |
| IEC 82304-1 | Health Software Safety | ✅ Already referenced | None |
| **IEC 80001-1** | IT Network Risk Management | ❌ Not referenced | Add as "out of scope for prototype — networked deployment is future work" |
| **ISO/IEC 27001** | Information Security | ❌ Not referenced | Add data handling section: openFDA data is public, no PII; production deployment would require ISO 27001 controls |
| **IEC 62366-1** | Usability Engineering | ❌ Not referenced | Add note: dashboard UX follows usability engineering principles; formal IEC 62366-1 file is future work |
| **GDPR** | Data Privacy (EU) | ❌ Not referenced | Add note: no PII processed (FDA pre-redacts MAUDE narratives); GDPR not triggered for our data |

### 2. Functional Design Expectations per Agent

Review specifies what each agent should do. Mapping against our current design:

| Reviewer Expectation | Our Current Agent | Coverage | Gap / Action |
|---------------------|-------------------|----------|--------------|
| **Complaint intake from multiple sources** (customer, service, PMS, publications) | Agent 1 (Extraction) | Partial — we accept text input | Document that the input format is source-agnostic; multi-source ingestion connectors are future work |
| **Classify as safety vs non-safety** | Agent 1 + Agent 4 | Partial — we have `severity_indicator` but no explicit safety/non-safety flag | Add `is_safety_related: boolean` field to extraction output |
| **Structured extraction (failure, component, severity, usability, security)** | Agent 1 | Partial — we have failure mode and component | Add `usability_concern` and `security_concern` boolean flags to extraction schema |
| **Risk assessment per ISO 14971** | Agent 4 | ✅ Full S×P matrix with acceptability zones | None |
| **Escalate critical cases to Safety Council / PRRC** | Validation gate after Agent 4 | Partial — we have escalation for HIGH risk + no citations | Add explicit `escalation_required` field with PRRC notification flag for UNACCEPTABLE risk |
| **Regulatory database screening (FDA, EU, etc.)** | Agent 3 (Retrieval) | Partial — FDA only | Document: EU EUDAMED is not yet publicly queryable; FDA MAUDE is our proxy. Add note in report. |
| **CAPA recommendation referencing previous outcomes** | Agent 4 (merged) | ✅ Precedent basis field already in output | None |
| **Report assembly with traceability and citations** | Agent 5 | ✅ Already in design | None |
| **Human expert review and approval before implementation** | QM Review gate in workflow | ✅ Explicitly designed as decision support | None |

### 3. Security, Privacy, Usability — Where We Stand

| Concern | Reviewer Requirement | Our Position |
|---------|--------------------|--------------|
| Information security (ISO/IEC 27001) | All data handling compliant | Data is public FDA records, no PII. Production deployment would require ISO/IEC 27001 controls — out of scope for prototype. |
| Data privacy (GDPR) | EU privacy requirements | No personal data processed. FDA pre-redacts MAUDE narratives. GDPR not triggered. |
| Usability engineering (IEC 62366-1) | Maximize safe and effective use | Dashboard design will follow basic usability principles (clear labels, error states, confirmation prompts). Formal IEC 62366-1 usability file is future work. |

### 4. Continuous Improvement and Feedback Loop

| Reviewer Requirement | Current Coverage | Gap |
|---------------------|-----------------|-----|
| Feed complaint trends into QMS improvement cycle | ✅ Aggregated dashboard for management review | None |
| Feedback loops for reviewers to refine extraction | Partial — DPO captures preference feedback for reports | Extend to extraction quality: add "reviewer correction" tracking to extraction outputs |
| CAPA outcomes feedback | ❌ Not in scope | Future work — would require integration with CAPA tracking system |

### 5. Documentation and Auditability — Confirmed

All agent actions, decisions, and outputs are documented per our Observability section:
- LangSmith traces for every LLM call
- JSON logs with full trace IDs
- Signal reports stored with version, timestamp, model info
- Audit trail satisfies ISO 13485 §4.2.5 and IEC 62304 §9.5

### Schema Additions Required (Consolidated)

Based on both rounds of review, the extraction output schema needs these additional fields:

```json
{
  "extraction_output": {
    // ... existing fields ...
    "is_safety_related": "boolean",
    "usability_concern": "boolean",
    "security_concern": "boolean",
    "affected_countries": ["string"] | "unknown",
    "complaint_source": "customer|service|PMS|publication|internal|unknown"
  },
  "risk_output": {
    // ... existing fields ...
    "escalation_required": "boolean",
    "prrc_notification_required": "boolean",
    "fsca_required": "boolean"
  }
}
```

### Updated Action List (Consolidating Both Reviews)

| # | Action | Owner | When | Priority |
|---|--------|-------|------|----------|
| 1 | Add `affected_countries` to extraction schema | M3 | Week 1 | Medium |
| 2 | Add `is_safety_related`, `usability_concern`, `security_concern` flags | M3 | Week 1 | Medium |
| 3 | Add `complaint_source` field with default value for synthetic data | M3 | Week 1 | Low |
| 4 | Add `fsca_required`, `escalation_required`, `prrc_notification_required` to risk output | M5 | Week 2 | High |
| 5 | Document EUDAMED limitation; FDA MAUDE is our regulatory database proxy | M2 | Week 1 | Low |
| 6 | Add data privacy section: no PII, GDPR not triggered | M6 | Week 4 | Low |
| 7 | Add security section: ISO/IEC 27001 out of scope; production note in future work | M6 | Week 4 | Low |
| 8 | Add usability note: basic principles followed; formal IEC 62366-1 file is future work | M6 | Week 4 | Low |
| 9 | Add note that multi-source ingestion connectors are future work | M6 | Week 4 | Low |
| 10 | Add reviewer correction tracking for extraction (extends DPO feedback) | M6 | Week 3 | Low |

### What's Explicitly Out of Scope (Document in Report)

To avoid scope creep from review feedback, the following are explicitly future work:

- **IEC 80001-1 networked deployment** — prototype runs locally, not on a hospital IT network
- **ISO/IEC 27001 information security controls** — production deployment requirement, not prototype
- **GDPR compliance** — not triggered (no PII), but production deployment would need privacy impact assessment
- **Formal IEC 62366-1 usability engineering file** — basic UX principles only
- **EUDAMED integration** — not publicly queryable; FDA MAUDE is the working proxy
- **Multi-source ingestion connectors** (customer portal, service desk, PMS feeds) — input is text-based for prototype
- **CAPA outcome tracking integration** — would need access to QMS CAPA system
- **Automated regulatory body reporting** (MDR/MIR form pre-fill) — downstream of CAPA approval

---

## 8. Open Questions for Team Discussion

1. Does anyone have access to ISO 14971:2019 or IEC 62304 through employer/university?
2. Should we scope down to 4 product codes (MRI + CT only) if Week 2 progress is slow?
3. Who will generate the 200 synthetic complaints — M1 alone or paired with M3?
4. Do we target a conference paper (AMIA, EMBC, or AAAI health track) or just the MTech report?
5. Can we get 30 minutes of QM expert time (even informal) to validate our complaint categories?
6. Should we add FSCA/CSAN logic to Agent 4, or document it as future work?
7. Do we reference EN-prefixed standards (European harmonized) or ISO/IEC-prefixed (international)? Both refer to the same content.
