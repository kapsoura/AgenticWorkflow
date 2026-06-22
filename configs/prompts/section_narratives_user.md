Active complaint and deterministic FACTS (do not change the verdicts):
- Product code: $product_code
- Event type: $event_type
- ISO 13485 complaint category: $category
- Key issues: $key_issues
- ISO 14971 risk bucket (FACT): $risk_bucket
- Severity (FACT): $severity
- Probability (FACT): $probability
- Escalation required (FACT): $escalation_required
- PRRC notification required (FACT): $prrc_required
- FSCA required (FACT): $fsca_required
- MDR reportable serious incident (FACT): $reportable
- Hazardous situation: $hazardous_situation
- Harm: $harm
- ISO 14971 rationale: $iso_14971_rationale
- Trend direction (FACT): $trend_direction
- Total events in working archive: $total_events
- Software-like problem events: $software_events
- Latest-year event count: $latest_year
- Previous-year event count: $previous_year

Complaint narrative:
$narrative

Retrieved FDA evidence you may cite (evidence_id [source] snippet):
$evidence_block

Write the narrative for EACH of these report sections (key: what it must cover):
$sections_block

Return ONLY the JSON object mapping each section key above to its narrative string.
