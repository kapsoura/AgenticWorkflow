
Title: Multi-Agent Regulatory Signal Intelligence System for Medical Software and SaMD Quality Teams

> **🎯 FOCUSED SYSTEM DESIGN**: See [System_Design.md](System_Design.md) for the concrete workflow automation, target product (Infusion Pumps), demo scenario, 4-week build plan, and per-agent technical details. This Ideation document provides background research and technique catalog.

---

Description:
Medical software and Software as a Medical Device (SaMD) teams generate defect reports, complaints, incident narratives, CAPA notes, and test escapes in large volumes. Most of this data is unstructured text, reviewed manually, and stored across disconnected tools. Quality and regulatory teams must then answer difficult questions under time pressure:

- Are multiple teams seeing the same hidden failure pattern?
- Is a local defect actually an early post-market safety signal?
- Has a similar issue already appeared in FDA adverse event or recall data?
- What corrective action is justified, and how should the risk be documented?

This project proposes a research-grade GenAI system that transforms raw defect narratives into evidence-backed regulatory intelligence. Instead of building six generic agents with vague roles, the system will use a scoped multi-agent architecture, grounded in public FDA/openFDA data and human-in-the-loop review, to detect, explain, and prioritize quality signals for medical software and connected medical devices.

Why The Current Idea Needs Improvement:

- The current concept is strong directionally, but too broad for a 4-week build.
- It does not define the input data model, evaluation method, or what public regulatory data is actually available.
- It assumes fully automated risk scoring, which is not defensible without clear guardrails.
- It does not yet demonstrate enough MTech-level depth in retrieval, reasoning, orchestration, evaluation, and systems design.

Improved Project Thesis:
Build a multi-agent regulatory intelligence copilot that combines internal defect data with public FDA/openFDA device safety datasets to identify recurring defect themes, retrieve comparable real-world regulatory evidence, generate structured CAPA and risk recommendations, and produce an auditable signal report for expert review.

This should be positioned as decision support, not decision automation.

Refined Research Contribution:

The MTech-level contribution is not merely "using multiple agents." The contribution is a full agentic intelligence pipeline with:

- domain-specific information extraction from defect narratives
- semantic clustering and trend detection over incidents
- tool-augmented retrieval from FDA/openFDA datasets
- retrieval-augmented regulatory reasoning
- explainable risk scoring with traceable evidence
- human-in-the-loop validation and report generation
- evaluation of agent quality, retrieval quality, and end-to-end signal usefulness

GenAI Topics Covered:

Core Topics:
- Multi-agent orchestration and routing
- Retrieval-Augmented Generation (RAG) and Graph RAG
- Tool-using agents via MCP (Model Context Protocol)
- LLM-based information extraction and normalization
- Embeddings, semantic clustering, and contrastive learning
- Knowledge-grounded summarization
- Guardrails, hallucination reduction, and Constitutional AI
- Human-in-the-loop review workflows
- Agent evaluation and ablation studies
- Structured output generation and constrained decoding

Advanced GenAI/ML Engineering Topics:
- Reinforcement Learning from Human Feedback (RLHF) with PPO
- Direct Preference Optimization (DPO) for reviewer alignment
- Reward modeling from expert QA/RA feedback
- Dimensionality reduction and projection (UMAP, t-SNE, PCA) for cluster visualization
- Active learning for iterative label-efficient model improvement
- DSPy-style prompt optimization and compilation
- Self-reflection and self-correction in agents (critique-revise loops)
- Knowledge distillation from large LLM to smaller task-specific models
- LoRA/QLoRA fine-tuning for domain-adapted extraction
- LLM-as-Judge evaluation methodology
- Mixture of Experts (MoE) routing for multi-domain reasoning
- Chain-of-Thought (CoT) and Tree-of-Thought (ToT) reasoning
- ReAct (Reasoning + Acting) agent pattern
- Temporal signal detection and anomaly scoring

Recommended Final Scope:

Focus the project on medical device software / SaMD quality intelligence, not all healthcare regulation.

Inputs:

- Internal synthetic or anonymized defect reports
- Customer complaints
- Test escape summaries
- Service incident notes

External evidence sources:

- FDA MAUDE / openFDA device adverse events
- FDA device recalls
- FDA 510(k) clearances
- FDA device classification database
- FDA UDI / GUDID metadata

Outputs:

- defect taxonomy labels
- related-incident clusters
- comparable FDA signal evidence
- draft CAPA recommendations
- draft risk class and rationale
- auditable signal report for QA/RA review

Proposed Multi-Agent Architecture:

1. Ingestion and Normalization Agent
- Cleans raw defect text.
- Extracts structured fields such as component, failure mode, symptom, likely cause, discovery phase, and affected workflow.
- Maps free text into a controlled defect ontology.

2. Similarity and Pattern Mining Agent
- Embeds incidents and groups semantically related defects.
- Detects repeated or emerging themes across teams, versions, and modules.
- Flags clusters whose growth rate or severity trend is increasing.

3. FDA Evidence Retrieval Agent
- Resolves device names, product codes, manufacturers, and regulatory categories.
- Queries openFDA device event, recall, 510(k), classification, and UDI datasets.
- Retrieves comparable device failures, recall reasons, and predicate-device context.

4. Regulatory Reasoning and Risk Agent
- Combines internal defect clusters with retrieved FDA evidence.
- Produces a draft risk rationale aligned to a simplified ISO 14971-inspired rubric.
- Explicitly separates evidence, assumptions, and uncertainty.

5. CAPA Recommendation Agent
- Suggests corrective and preventive actions based on failure patterns and retrieved precedents.
- Distinguishes immediate containment, root-cause investigation, verification action, and systemic prevention.

6. Report Assembly and Reviewer Copilot Agent
- Builds a structured signal report.
- Includes traceable citations to internal incidents and external FDA evidence.
- Prepares the final output for human approval rather than autonomous submission.

Why This Version Is Stronger:

- It is realistic for 4 weeks.
- It uses public regulatory data that is actually accessible.
- It demonstrates multiple GenAI methods, not just prompt chaining.
- It has clear evaluation surfaces.
- It is aligned with real QA/RA workflows in regulated software environments.

FDA/openFDA Research: What You Can Use

1. openFDA Device Adverse Event API
- Source: MAUDE.
- Public device adverse event reports, including malfunctions, injuries, and deaths.
- API coverage: 2009 to 2026-05-12, updated weekly.
- Useful for: finding comparable failure narratives, product problems, remedial actions, manufacturers, and event types.
- Important limitation: MDR/MAUDE data is passive surveillance data and should not be treated as proof of causality.

2. FDA MAUDE / MDR Context
- FDA states MDR is a post-market surveillance source, not a causal proof system.
- Reports may be incomplete, biased, under-reported, or unverified.
- This is actually good research material because your system can explicitly model uncertainty and evidence quality.

3. openFDA Device Recall API
- Coverage: 2002 to 2026-05-23, updated weekly.
- Useful for: recall reasons, classification, recalling firm, affected products, and corrective actions.
- Strong source for evidence-backed CAPA suggestions and regulatory precedent.

4. openFDA Device 510(k) API
- Coverage: 1976 to 2026-05-18, updated monthly.
- Useful for: predicate devices, sponsor/applicant, device names, and regulatory context.
- Helpful for benchmarking your internal product area against previously cleared comparable devices.

5. openFDA Device Classification API
- Coverage: 1976 to 2026-05-18, updated monthly.
- Useful for: product code, device class, regulation number, and medical specialty.
- Important for normalizing device category and resolving entity names.

6. openFDA UDI API
- Source: GUDID.
- Coverage: 2013 to 2026-05-01, updated weekly.
- Useful for: device metadata, device identifiers, manufacturer-submitted device details, and entity resolution.

7. openFDA Searchable Fields
- The device event endpoint exposes fields such as `event_type`, `product_problems`, `manufacturer_name`, `mdr_text`, `report_number`, and event/report dates.
- These are directly useful for retrieval, cluster labeling, and structured report generation.

8. FDA MAUDE Bulk Data Download
- URL: https://open.fda.gov/apis/device/event/download/
- 355 zipped JSON files (as of May 2026), updated weekly.
- Contains the full historical MAUDE dataset in machine-readable format.
- Each file is a JSON array of device adverse event reports with all MAUDE fields.
- Use for: offline analysis, embedding generation, training data for extraction models, batch processing.
- Alternative: FDA MDR Data Files page provides CSV-format downloads going back to 1991.

Additional Public Data Sources — Medical Software Requirements, Risk, and Quality Files:

Beyond the openFDA API data, the following publicly available sources provide real-world medical software documentation including requirements specifications, risk management files, and quality system artifacts:

1. OpenRegulatory Templates (GitHub: openregulatory/templates)
- URL: https://github.com/openregulatory/templates
- What it contains: Complete, audit-ready document templates for ISO 13485, IEC 62304, ISO 14971, and IEC 62366 compliance.
- Specific files available:
  - Software Requirements Specification (SRS) templates
  - Risk Management Plan and Risk Management File templates (ISO 14971)
  - Software Development Plan (IEC 62304)
  - SOUP (Software of Unknown Provenance) list template
  - CAPA (Corrective and Preventive Action) procedure templates
  - Design and Development Planning templates
  - Usability Engineering File (IEC 62366)
  - Clinical Evaluation Plan templates
  - Post-Market Surveillance Plan templates
- Format: Markdown files (also available as .docx/.pdf on their website).
- Use for: Schema reference for what the system should extract and generate. Training data for CAPA and risk document generation. Grounding the report assembly agent output format.
- License: Open source.

2. Innolitics RDM (GitHub: innolitics/rdm)
- URL: https://github.com/innolitics/rdm
- What it contains: Regulatory Documentation Manager that streamlines IEC 62304, ISO 14971, and 510(k) documentation for real software projects.
- Includes: document generation from YAML-based requirement specifications, traceability matrices, risk tables, and regulatory submission helpers.
- Use for: Understanding how software requirements map to risk controls, how traceability works in practice, and what structured requirement + risk data looks like.
- License: MIT.

3. FDA 510(k) Summary Documents (Publicly Available)
- URL: https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm
- What it contains: Every 510(k) clearance includes a publicly available summary document.
- These summaries contain:
  - Intended use / indications for use
  - Device description and software description
  - Substantial equivalence comparison to predicate devices
  - Performance data summaries
  - Biocompatibility, electrical safety, and software documentation summaries
  - Cybersecurity information (for newer submissions)
- Use for: Understanding real SaMD/medical software device descriptions, intended use statements, predicate device relationships, and what FDA reviewers expect.
- Quantity: Over 200,000 cleared 510(k) devices with publicly available summaries.

4. FDA De Novo Decision Summaries
- URL: https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/denovo.cfm
- What it contains: De Novo classification decisions for novel devices (including AI/ML-based SaMD).
- These are particularly relevant because many AI/ML SaMD devices go through De Novo pathway.
- Contains: special controls, performance requirements, intended use, and risk/benefit analysis.
- Use for: Understanding risk classification rationale for software devices, what safety controls FDA requires.

5. FDA AI/ML-Based SaMD List
- URL: https://www.fda.gov/medical-devices/software-medical-device-samd/artificial-intelligence-and-machine-learning-aiml-enabled-medical-devices
- What it contains: Official FDA list of all authorized AI/ML-enabled medical devices (700+ devices as of 2025).
- Fields: device name, company, clearance date, panel, and product code.
- Use for: Building a reference database of real AI/ML SaMD products, cross-referencing with MAUDE events and recalls for those specific devices.

6. FDA Total Product Life Cycle (TPLC) Database
- URL: https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfTPLC/tplc.cfm
- What it contains: Links all FDA product lifecycle data: 510(k), PMA, adverse events, recalls, and classification for a given product.
- Use for: Building complete device profiles that connect premarket (clearance) data with postmarket (adverse events, recalls) data.

7. FDA Recall Database (Full Text)
- URL: https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRES/res.cfm
- What it contains: Full recall notices with:
  - Reason for recall (free-text narrative)
  - Root cause category
  - Corrective action taken
  - Distribution pattern
  - Product quantity affected
- Use for: Ground truth CAPA examples. The "reason for recall" field often reads like a well-structured defect report. The "corrective action" field is real-world CAPA data.
- Quantity: Thousands of device recalls with detailed narratives.

8. Open-Source Medical Device Software Projects with Regulatory Documentation
- OpenSaMD (GitHub: OpenSaMD/OpenSaMD)
  - Open source medical software (radiation therapy) with IEC 62304 compliance documentation.
  - Includes: software lifecycle records, risk management artifacts, verification records.
- OpenAPS (openaps.org)
  - Open-source artificial pancreas system.
  - Extensive documentation on safety requirements, hazard analysis, and risk controls.
  - Community-maintained safety documentation with real incident reports.
- LibreHealth (librehealth.io)
  - Open-source health IT platform.
  - Publicly available requirements and design documentation.

9. IMDRF (International Medical Device Regulators Forum) Documents
- URL: http://www.imdrf.org/documents/documents.asp
- What it contains: International guidance documents on:
  - SaMD classification and risk categorization (IMDRF N12)
  - Clinical evaluation of SaMD (IMDRF N41)
  - Software lifecycle processes
  - Adverse event terminology and coding
- Use for: Grounding the risk classification logic and taxonomy definitions.

10. FDA Product Problem Codes and Patient Problem Codes
- URL: https://www.fda.gov/medical-devices/mdr-adverse-event-codes
- What it contains: Complete codebook of standardized device problem codes (2000+) and patient problem codes.
- Use for: Building the controlled ontology/taxonomy for defect classification. These are the standard codes used in MAUDE reports.
- Format: Downloadable, structured code lists with definitions.

11. ClinicalTrials.gov (Medical Device Studies)
- URL: https://clinicaltrials.gov/
- Filter by: device studies, SaMD studies, software interventions.
- Contains: protocol documents, outcome measures, adverse event summaries.
- Use for: Understanding what safety endpoints are monitored for SaMD devices.

12. FDA Guidance Documents for Medical Device Software
- Key documents:
  - "Content of Premarket Submissions for Device Software Functions" (2023)
  - "Cybersecurity in Medical Devices" (2023)
  - "Clinical Decision Support Software" (2022)
  - "Predetermined Change Control Plans for AI/ML-Enabled Devices" (2024)
  - "Computer Software Assurance for Production and Quality System Software" (2022)
- URL: https://www.fda.gov/medical-devices/digital-health-center-excellence/device-software-functions-including-mobile-medical-applications
- Use for: Understanding what documentation FDA expects, what risk factors they prioritize, what CAPA patterns they accept.

Data Strategy for the Project:

Primary training/retrieval data:
- FDA MAUDE bulk download (355 JSON files = millions of adverse event reports with narratives)
- FDA Recall database (thousands of recall notices with root cause and corrective action)
- openFDA APIs for real-time queries during agent operation

Schema and template references:
- OpenRegulatory templates for document structure (SRS, risk files, CAPA)
- FDA product/patient problem codes for ontology/taxonomy

Benchmark and grounding:
- 510(k) summaries for device descriptions and intended use
- FDA AI/ML SaMD list for scoping to relevant devices
- TPLC database for connecting premarket and postmarket data

Synthetic data generation guidance:
- Use real MAUDE narratives as stylistic templates to generate synthetic internal defect reports
- Use real recall "reason for recall" text as templates for synthetic CAPA scenarios
- Use OpenRegulatory risk file templates to generate synthetic risk management records

Recommended Research Framing:

Do not say: "the system determines regulatory truth".

Say instead: "the system assists quality and regulatory professionals by surfacing evidence-backed signals, comparable FDA events, and structured risk narratives for human review."

Advanced GenAI/ML Techniques — Detailed Integration Plan:

This section maps each advanced technique to a concrete role in the system architecture. As AI engineers, these are the techniques you should demonstrate hands-on competence with.

1. RLHF with PPO (Proximal Policy Optimization)
- Where it fits: Report Generation Agent and CAPA Recommendation Agent.
- How: Collect binary accept/reject feedback from human reviewers on generated reports. Train a reward model that predicts reviewer satisfaction. Use PPO to fine-tune the report-generation policy so it maximizes the learned reward.
- Implementation: Use TRL (Transformer Reinforcement Learning) library with a small LoRA-adapted model. Even 50-100 preference pairs from simulated reviewer feedback can show measurable improvement.
- What you demonstrate: Understanding of reward modeling, policy gradient optimization, KL-divergence penalty, and training stability.

2. Direct Preference Optimization (DPO)
- Where it fits: Alternative to PPO for aligning extraction and report agents.
- How: Instead of training a separate reward model, directly optimize the LLM policy from preference pairs (preferred vs rejected report drafts).
- Advantage over PPO: Simpler pipeline (no separate reward model training), more stable for small datasets.
- Implementation: Collect pairs of (good report, bad report) for the same defect input. Fine-tune with DPO loss. Compare DPO vs PPO vs baseline on report quality metrics.
- What you demonstrate: Modern alignment techniques beyond basic RLHF.

3. Reward Modeling from Expert Feedback
- Where it fits: Evaluation pipeline for all agents.
- How: Ask domain experts (QA/RA professionals or simulated) to rate outputs on axes: accuracy, completeness, actionability, citation quality. Train a reward model (small classifier on top of embeddings) that predicts these ratings.
- Use: As automatic evaluation proxy during development. Also as the reward signal for PPO/DPO.
- What you demonstrate: How to build evaluation infrastructure that scales beyond manual review.

4. Dimensionality Reduction and Projection (UMAP, t-SNE, PCA)
- Where it fits: Similarity and Pattern Mining Agent, Dashboard visualization.
- How: After embedding defect narratives into high-dimensional space (768-d or 1536-d), project them into 2D/3D for:
  - Interactive cluster visualization on the dashboard
  - Outlier/anomaly detection (points far from any cluster centroid)
  - Temporal drift visualization (plot embeddings over time, color by month)
  - Cluster boundary analysis for emerging signal identification
- Implementation: Use UMAP (better preservation of global structure) for the primary visualization. Use PCA for fast linear projection. Use t-SNE for publication-quality cluster plots.
- Advanced: Parametric UMAP that can project new incoming defects without recomputing the entire projection.
- What you demonstrate: Understanding of manifold learning, curse of dimensionality, and how to make high-dimensional patterns interpretable.

5. Contrastive Learning for Domain-Specific Embeddings
- Where it fits: Embedding layer used by the Similarity Agent.
- How: Fine-tune sentence-transformers using contrastive loss on pairs of (defect_narrative, related_FDA_event). This creates an embedding space where internal defects and their corresponding FDA parallels are close together.
- Data source: Use the openFDA MAUDE narratives + recall descriptions. Create positive pairs (defect text, matching FDA event) and negative pairs (defect text, unrelated FDA event).
- What you demonstrate: Transfer learning, metric learning, and domain adaptation of pretrained embeddings.

6. Active Learning for Label-Efficient Improvement
- Where it fits: Extraction Agent ontology labeling and evaluation benchmark creation.
- How: Instead of labeling 500 defects upfront, use uncertainty sampling. The extraction agent processes defects, flags ones where confidence is lowest, and a human labels only those. Retrain/update the system iteratively.
- Implementation: Measure extraction confidence via logprob analysis or ensemble disagreement. Present top-k uncertain samples to the reviewer interface.
- What you demonstrate: Practical understanding of how to build ML systems with minimal labeled data.

7. DSPy-Style Prompt Optimization
- Where it fits: All agents (extraction, reasoning, CAPA, report).
- How: Instead of manually iterating on prompts, use DSPy to define agent signatures (input/output schemas) and automatically optimize prompts using a small labeled validation set.
- Implementation: Define metrics (extraction F1, retrieval precision, report rubric score). Let DSPy compile optimal few-shot examples and instructions for each agent.
- What you demonstrate: Programmatic prompt engineering, moving beyond manual trial-and-error.

8. Self-Reflection and Critique-Revise Loops
- Where it fits: Risk Reasoning Agent and Report Assembly Agent.
- How: After generating a draft risk rationale or report, the agent critiques its own output for: unsupported claims, missing citations, logical gaps, regulatory language errors. It then revises and produces a final version.
- Implementation: Two-pass generation. Pass 1: draft. Pass 2: critique prompt that identifies weaknesses. Pass 3: revision incorporating critique.
- Measurement: Compare single-pass vs critique-revise on hallucination rate and completeness.
- What you demonstrate: Agentic self-improvement patterns, meta-cognitive capabilities.

9. Knowledge Distillation
- Where it fits: Deploy smaller, faster models for production extraction.
- How: Use GPT-4.1 / Claude as teacher to generate high-quality extraction outputs. Distill into a smaller fine-tuned model (e.g., Llama-3-8B or Phi-3) that can run locally/cheaply.
- Why: Production regulatory systems need predictable latency and cost. Distillation enables GPT-4-quality extraction at 10x lower cost.
- What you demonstrate: Model compression, student-teacher paradigm, cost-performance tradeoffs.

10. LoRA/QLoRA Fine-Tuning
- Where it fits: Extraction Agent, Report Generation Agent.
- How: Fine-tune a base model (Llama-3, Mistral, Phi-3) with LoRA adapters on domain-specific tasks: defect field extraction, CAPA generation, regulatory language compliance.
- Data: Use the synthetic defect dataset + FDA MAUDE narratives as training data.
- What you demonstrate: Parameter-efficient fine-tuning, adapter merging, domain specialization without catastrophic forgetting.

11. Graph RAG
- Where it fits: FDA Evidence Retrieval Agent.
- How: Instead of flat vector retrieval, build a knowledge graph connecting: devices → manufacturers → product codes → adverse events → recalls → 510(k) predicates. Traverse the graph during retrieval to find non-obvious connections.
- Implementation: Use NetworkX or Neo4j. Populate from openFDA data. Retrieve by graph traversal + embedding similarity hybrid.
- What you demonstrate: Going beyond naive RAG to structured knowledge retrieval.

12. LLM-as-Judge Evaluation
- Where it fits: Automated evaluation pipeline.
- How: Use a strong LLM (GPT-4.1) as an evaluator/judge to score outputs from your agents on rubrics: factual accuracy, completeness, regulatory alignment, actionability.
- Implementation: Design judge prompts with explicit rubrics. Calibrate by comparing LLM-judge scores with human scores on a shared subset. Report inter-annotator agreement (Cohen's kappa).
- What you demonstrate: Scalable evaluation methodology for generative systems.

13. Chain-of-Thought (CoT) and Tree-of-Thought (ToT)
- Where it fits: Risk Reasoning Agent.
- How: Force the risk agent to show its reasoning chain: evidence → inference → risk level → justification. Use ToT for complex cases where multiple reasoning paths should be explored and the best selected.
- Implementation: Structured CoT with explicit steps. For ToT: generate 3 parallel reasoning branches, score each, select most evidence-supported.
- What you demonstrate: Interpretable AI reasoning, structured problem decomposition.

14. ReAct (Reasoning + Acting) Agent Pattern
- Where it fits: FDA Evidence Retrieval Agent.
- How: The agent alternates between reasoning about what evidence is needed and acting by querying FDA APIs. It reasons about query results, decides if more evidence is needed, and iterates.
- Implementation: Implement with LangGraph or custom state machine. Log the full Thought-Action-Observation trace for auditability.
- What you demonstrate: Tool-augmented reasoning, dynamic planning, and audit-trail generation.

15. Temporal Signal Detection and Anomaly Scoring
- Where it fits: Similarity and Pattern Mining Agent.
- How: Track cluster growth rates over time windows. Apply statistical anomaly detection (z-score, IQR, or isolation forest) to flag clusters whose growth rate exceeds baseline. Combine with severity weighting.
- Advanced: Use changepoint detection algorithms (PELT, BOCPD) to identify when a defect pattern shifts from background noise to emerging signal.
- What you demonstrate: Time-series analysis, statistical process control applied to NLP-derived features.

MTech-Level Novelty Options:

Choose at least three to four of these and make them explicit in the report. These combine classic research contributions with demonstrable AI engineering skills.

1. Retrieval + reasoning benchmark
- Compare plain LLM vs RAG vs Graph RAG vs multi-agent RAG for signal quality.
- Ablate retrieval methods: vector search vs graph traversal vs hybrid.

2. Evidence-grounded risk scoring
- Force the risk agent to output risk rationale only when enough evidence is retrieved.
- Measure unsupported claims vs supported claims.
- Use Chain-of-Thought structured reasoning with explicit evidence linking.

3. RLHF/DPO alignment study
- Collect reviewer preferences on generated reports.
- Compare: baseline (no alignment) vs DPO-aligned vs PPO-aligned models.
- Measure: report acceptance rate, hallucination reduction, citation density improvement.
- This is the strongest MTech-level contribution — novel application of alignment to regulated-domain report generation.

4. Projection-based signal emergence detection
- Embed all defects, project via UMAP into 2D.
- Track cluster centroid drift over time windows.
- Apply changepoint detection to identify when a new failure pattern emerges.
- Visualize temporal progression of defect clusters.

5. Contrastive embedding fine-tuning for cross-domain retrieval
- Fine-tune embeddings so that internal defect descriptions land near semantically equivalent FDA MAUDE events.
- Evaluate: retrieval precision before vs after contrastive fine-tuning.
- This shows understanding of metric learning and domain adaptation.

6. Structured ontology extraction with active learning
- Build a controlled taxonomy for failure mode, root cause, and escape reason.
- Use active learning to minimize labeling effort while maximizing extraction F1.
- Show the learning curve: how many labels are needed to reach 90% accuracy.

7. Human-in-the-loop with reward modeling
- Add reviewer feedback, train a reward model, and show it correlates with human judgment.
- Use the reward model for automatic evaluation at scale.
- Show inter-annotator agreement between LLM-as-judge and human judge.

8. Multi-agent ablation study with component analysis
- Remove one agent at a time and show how performance degrades.
- Also ablate techniques: remove CoT, remove self-reflection, remove graph RAG, and measure impact.
- This demonstrates rigorous experimental methodology.

9. Knowledge distillation for production readiness
- Show that a small distilled model (8B params) can match GPT-4 quality on extraction tasks after distillation.
- Report cost, latency, and accuracy tradeoffs.
- This demonstrates practical engineering thinking beyond research.

Suggested System Stack:

- LLM: GPT-4.1 / GPT-4o / Claude / equivalent strong instruction model
- Fine-tuning base: Llama-3-8B or Phi-3-mini (for LoRA/distillation experiments)
- Alignment: TRL library (for PPO, DPO, reward modeling)
- Prompt optimization: DSPy framework
- Embeddings: sentence-transformers or OpenAI embeddings (+ contrastive fine-tuning)
- Vector store: FAISS, Chroma, or Qdrant
- Knowledge graph: NetworkX or Neo4j (for Graph RAG)
- Backend: Python FastAPI
- Data analysis: Pandas + scikit-learn
- Clustering: HDBSCAN or BERTopic-style topic grouping
- Projection/visualization: UMAP, t-SNE (via umap-learn, scikit-learn)
- Anomaly detection: PyOD or scikit-learn IsolationForest
- Agent framework: LangGraph or custom state machine (for ReAct, self-reflection)
- UI: Streamlit or lightweight React dashboard (with Plotly for interactive projections)
- Evaluation: labeled sample set + reviewer rubric + LLM-as-Judge

Suggested MCP Strategy:

Do not spend week 1 building custom protocol plumbing unless required. Reuse or adapt existing MCP servers where possible.

Most Relevant Existing MCP Servers Found:

1. Augmented-Nature/OpenFDA-MCP-Server
- Covers openFDA drug and device data.
- Device support includes 510(k), classifications, adverse events, and recalls.
- Best fit if you want a focused FDA/openFDA device data MCP starting point.

2. SuyashEkhande/OpenFDA-Semantic-MCP
- Broader, AI-native openFDA MCP server.
- Includes intent-driven tools and better handling for large result sets and pagination.
- Good inspiration if you want semantic tool design rather than raw endpoint wrappers.

3. lzinga/us-gov-open-data-mcp
- Very broad U.S. government open-data MCP with FDA, CDC, ClinicalTrials.gov, and many other agencies.
- Good if your project expands into cross-agency correlation.
- Probably too large to make it your primary dependency for a 4-week student project, but useful as a reference.

4. JamesANZ/medical-mcp
- Strong general medical information MCP with FDA, PubMed, WHO, RxNorm, and literature retrieval.
- More useful for literature and clinical context than for device-quality intelligence specifically.

5. Cicatriiz/healthcare-mcp-public
- General healthcare MCP with FDA, PubMed, ClinicalTrials.gov, ICD-10, and DICOM metadata.
- Useful as a general medical data integration example.

Recommended MCP Decision:

- For the main project: adapt or mirror the device-focused parts of Augmented-Nature/OpenFDA-MCP-Server.
- For inspiration on agent-friendly tool design: study SuyashEkhande/OpenFDA-Semantic-MCP.
- For supporting utilities: use official MCP reference ideas such as Fetch, Memory, and Sequential Thinking from the modelcontextprotocol/servers repository.

Evaluation Plan:

Define a small benchmark set of defect cases with faculty-reviewed expected outputs.

Evaluate:

- Extraction accuracy: did the system correctly identify defect type, module, cause hints, and escape stage?
- Retrieval quality: are the retrieved FDA records relevant to the defect cluster?
- Cluster quality: do related incidents group together meaningfully?
- Report usefulness: does the final report help a reviewer act faster and with more confidence?
- Hallucination control: does the system cite evidence and avoid unsupported claims?

Possible metrics:

- Precision@k for retrieved FDA evidence
- cluster coherence score
- ontology extraction F1 on a labeled subset
- expert rubric scoring for final reports
- time saved in manual review simulation

Deliverables:

- Working multi-agent prototype with 6 agents and full pipeline
- Public-data ingestion pipeline (MAUDE bulk, recalls, 510(k), classification)
- Graph RAG knowledge graph populated with FDA device data
- Contrastive-tuned embedding model for cross-domain retrieval
- UMAP projection dashboard with temporal cluster visualization
- DPO/PPO alignment experiment with before/after comparison
- Structured signal report generator with self-reflection and citation tracing
- Small evaluation benchmark with LLM-as-Judge + human judge correlation
- Ablation study results (per-agent and per-technique)
- Knowledge distillation experiment showing small-model viability
- Architecture diagram and pipeline visualization
- Final dissertation/report with limitations, ablations, and future work

4-Week Execution Plan for a 6-Member Team:

Week 1: Data, embeddings, and baselines
- Member 1: MAUDE bulk data download + FDA recall data ingestion. Parse JSON files, build local database. Create synthetic defect narratives using real MAUDE style.
- Member 2: OpenRegulatory templates study + defect schema design. Define extraction ontology using FDA product/patient problem codes.
- Member 3: Baseline extraction prompts with structured output. Implement CoT reasoning for extraction. Set up DSPy signatures.
- Member 4: Embedding pipeline + UMAP/t-SNE projection experiments. Contrastive learning data preparation (defect-FDA event pairs).
- Member 5: MCP server integration spike + Graph RAG knowledge graph schema design (device → manufacturer → product code → events → recalls).
- Member 6: Literature review on RLHF/DPO in domain-specific applications. Evaluation rubric design. LLM-as-Judge prompt development.

Week 2: Core agents + advanced ML pipeline
- Build ingestion agent with CoT extraction and self-reflection loop
- Build similarity/pattern agent with HDBSCAN + UMAP visualization
- Build FDA retrieval agent with ReAct pattern and Graph RAG
- Begin contrastive embedding fine-tuning on defect-FDA pairs
- Set up reward model data collection (reviewer feedback interface)
- Start active learning loop for extraction labeling

Week 3: Reasoning, alignment, and integration
- Build risk reasoning agent with Tree-of-Thought for complex cases
- Build CAPA agent with evidence-grounded generation
- Integrate report assembly with critique-revise loop
- Implement DPO alignment on collected preference data (or PPO if enough data)
- Run first end-to-end pipeline tests
- Implement temporal anomaly detection on cluster growth rates
- Build UMAP dashboard with temporal slider

Week 4: Evaluation, distillation, and polishing
- Multi-agent ablation study (remove each agent, remove each technique)
- RLHF/DPO vs baseline comparison on report quality
- Knowledge distillation experiment (GPT-4 → smaller model for extraction)
- Projection analysis and signal emergence case studies
- LLM-as-Judge evaluation at scale + correlation with human scores
- Dashboard polish, poster, presentation, and report finalization

Suggested Member Role Split:

- Member 1: Data engineering + bulk FDA data pipeline + synthetic data generation
- Member 2: FDA/openFDA retrieval + MCP + Graph RAG knowledge graph
- Member 3: Extraction agent + ontology + DSPy optimization + active learning
- Member 4: Embeddings + clustering + projections + contrastive learning + anomaly detection
- Member 5: Reasoning + CAPA + report generation + RLHF/DPO alignment + self-reflection
- Member 6: Evaluation + LLM-as-Judge + reward modeling + distillation + documentation + demo

Risks And Mitigations:

- Risk: internal data unavailable
- Mitigation: create high-quality synthetic defect narratives based on real regulatory categories

- Risk: too much agent complexity
- Mitigation: keep each agent narrow and observable, and use structured JSON handoffs

- Risk: hallucinated regulatory statements
- Mitigation: citation-first prompting, evidence thresholding, and explicit uncertainty sections

- Risk: scope explosion into all healthcare data
- Mitigation: keep the main domain to SaMD and device-quality surveillance

Recommended Final Project Positioning:

This project should be presented as:

"An evidence-grounded multi-agent GenAI system for post-market quality signal detection and regulatory decision support in medical software and SaMD environments, integrating internal defect data with FDA/openFDA public safety intelligence, enhanced by RLHF-based alignment, contrastive retrieval, projection-based signal emergence detection, and knowledge-distilled production deployment."

That framing demonstrates:
- Systems engineering (multi-agent architecture, MCP integration, knowledge graphs)
- Modern ML research (RLHF, DPO, contrastive learning, active learning)
- Practical AI engineering (distillation, prompt optimization, evaluation at scale)
- Domain expertise (FDA regulatory data, ISO 14971 risk management, IEC 62304 lifecycle)
- Responsible AI (guardrails, human-in-the-loop, citation-first design, uncertainty modeling)

This positions the team as AI engineers who can not only build agentic systems but also apply the full spectrum of modern GenAI techniques to a real regulated-domain problem.
