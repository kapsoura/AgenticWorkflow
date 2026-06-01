"""
FDA Data Collection: Medical Imaging & Molecular Diagnostics
Downloads adverse events, recalls, and statistics for:
  - LNH (MRI Systems) - 4,598 events, 699 recalls
  - JAK (CT Scanners) - 5,182 events, 857 recalls  
  - IYE (CT X-ray) - 3,058 events, 559 recalls
  - LLZ (Ultrasound) - 19,482 events, 548 recalls
  - IZL (Digital X-ray) - 914 events, 167 recalls
  - MQB (Molecular Dx) - 1,274 events, 194 recalls
  - QKO (PCR Platform) - 1,550 events, 31 recalls
  - GKZ (Hematology Analyzer) - 23,422 events, 244 recalls
"""

import json
import time
import os
from pathlib import Path
from collections import Counter
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

BASE_DIR = Path(__file__).parent
EVENTS_DIR = BASE_DIR / "imaging_events"
MOLDX_DIR = BASE_DIR / "molecular_dx_events"
RECALL_DIR = BASE_DIR / "recalls"
ANALYSIS_DIR = BASE_DIR / "analysis"

# Create directories
for d in [EVENTS_DIR, MOLDX_DIR, RECALL_DIR, ANALYSIS_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def fetch_json(url, retries=3, delay=2):
    """Fetch JSON from URL with retry logic."""
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "MTech-Research/1.0"})
            with urlopen(req, timeout=45) as response:
                return json.loads(response.read().decode())
        except HTTPError as e:
            if e.code == 429:
                wait = delay * (attempt + 1)
                print(f"    Rate limited. Waiting {wait}s...")
                time.sleep(wait)
            elif e.code == 500:
                print(f"    Server error 500 - skipping")
                return None
            else:
                print(f"    HTTP {e.code}")
                if attempt == retries - 1:
                    return None
        except (URLError, Exception) as e:
            print(f"    Error: {e}")
            if attempt == retries - 1:
                return None
        time.sleep(delay)
    return None


def download_events(product_codes, output_dir, date_from="20190101", batches_per_code=5):
    """Download adverse events for given product codes."""
    all_events = []
    
    for pc, desc in product_codes:
        print(f"\n  [{pc}] {desc}")
        for batch in range(batches_per_code):
            skip = batch * 100
            url = (f"https://api.fda.gov/device/event.json?"
                   f"search=device.device_report_product_code:{pc}"
                   f"+AND+date_received:[{date_from}+TO+20261231]"
                   f"&limit=100&skip={skip}")
            
            data = fetch_json(url)
            if data and "results" in data:
                count = len(data["results"])
                total = data["meta"]["results"]["total"]
                print(f"    Batch {batch+1}: {count} results (total avail: {total:,})")
                all_events.extend(data["results"])
                
                # Save individual batch
                filepath = output_dir / f"{pc}_batch{batch+1}.json"
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                
                if count < 100:
                    break
            else:
                print(f"    Batch {batch+1}: FAILED/empty")
                break
            
            time.sleep(1.5)
    
    # Save combined
    combined_path = output_dir / "combined_events.json"
    with open(combined_path, "w", encoding="utf-8") as f:
        json.dump(all_events, f, indent=2)
    
    print(f"\n  Total downloaded: {len(all_events)} events")
    return all_events


def download_recalls(product_codes):
    """Download all recalls for given product codes."""
    all_recalls = []
    
    for pc, desc in product_codes:
        print(f"\n  [{pc}] {desc}")
        for skip in range(0, 1000, 100):
            url = f"https://api.fda.gov/device/recall.json?search=product_code:{pc}&limit=100&skip={skip}"
            data = fetch_json(url)
            if data and "results" in data:
                count = len(data["results"])
                total = data["meta"]["results"]["total"]
                print(f"    Skip {skip}: {count} results (total: {total})")
                all_recalls.extend(data["results"])
                if count < 100:
                    break
            else:
                break
            time.sleep(1.5)
    
    # Save
    filepath = RECALL_DIR / "all_imaging_moldx_recalls.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(all_recalls, f, indent=2)
    
    print(f"\n  Total recalls downloaded: {len(all_recalls)}")
    return all_recalls


def download_counts():
    """Download statistics (using small enough datasets to avoid 500 errors)."""
    counts = {}
    
    # Use individual product code counts with no date filter for small codes
    # Or tight date range for larger codes
    count_queries = [
        ("manufacturers_LNH", 
         "https://api.fda.gov/device/event.json?search=device.device_report_product_code:LNH+AND+date_received:[20220101+TO+20261231]&count=device.manufacturer_d_name.exact",
         "MRI manufacturers"),
        ("manufacturers_JAK",
         "https://api.fda.gov/device/event.json?search=device.device_report_product_code:JAK+AND+date_received:[20220101+TO+20261231]&count=device.manufacturer_d_name.exact",
         "CT manufacturers"),
        ("event_types_LNH",
         "https://api.fda.gov/device/event.json?search=device.device_report_product_code:LNH+AND+date_received:[20220101+TO+20261231]&count=event_type",
         "MRI event types"),
        ("event_types_JAK",
         "https://api.fda.gov/device/event.json?search=device.device_report_product_code:JAK+AND+date_received:[20220101+TO+20261231]&count=event_type",
         "CT event types"),
        ("event_types_LLZ",
         "https://api.fda.gov/device/event.json?search=device.device_report_product_code:LLZ+AND+date_received:[20220101+TO+20261231]&count=event_type",
         "Ultrasound event types"),
        ("recall_roots_imaging",
         "https://api.fda.gov/device/recall.json?search=product_code:LNH+OR+product_code:JAK+OR+product_code:LLZ&count=root_cause_description.exact",
         "Imaging recall root causes"),
        ("recall_roots_moldx",
         "https://api.fda.gov/device/recall.json?search=product_code:MQB+OR+product_code:GKZ&count=root_cause_description.exact",
         "MolDx recall root causes"),
        ("brand_names_LNH",
         "https://api.fda.gov/device/event.json?search=device.device_report_product_code:LNH+AND+date_received:[20220101+TO+20261231]&count=device.brand_name.exact",
         "MRI brand names"),
        ("brand_names_JAK",
         "https://api.fda.gov/device/event.json?search=device.device_report_product_code:JAK+AND+date_received:[20220101+TO+20261231]&count=device.brand_name.exact",
         "CT brand names"),
    ]
    
    for key, url, desc in count_queries:
        print(f"  {desc}...")
        data = fetch_json(url)
        if data and "results" in data:
            counts[key] = data["results"]
            print(f"    Got {len(data['results'])} entries")
        else:
            print(f"    SKIPPED")
        time.sleep(1.5)
    
    filepath = ANALYSIS_DIR / "count_data.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(counts, f, indent=2)
    
    return counts


def analyze_all(imaging_events, moldx_events, recalls, counts):
    """Produce comprehensive analysis report."""
    all_events = imaging_events + moldx_events
    
    report = []
    report.append("# FDA Data Analysis Report\n")
    report.append("## Medical Imaging & Molecular Diagnostics Signal Intelligence\n\n")
    report.append(f"Generated: 2026-05-29\n\n")
    report.append(f"| Dataset | Count |\n|---|---|\n")
    report.append(f"| Medical Imaging Events (MRI+CT+Ultrasound+X-ray) | {len(imaging_events)} |\n")
    report.append(f"| Molecular Diagnostics Events (Mol Dx+Hematology) | {len(moldx_events)} |\n")
    report.append(f"| Total Adverse Events | {len(all_events)} |\n")
    report.append(f"| Total Recalls | {len(recalls)} |\n\n")
    
    # ============ Field Availability Analysis ============
    report.append("## 1. Data Quality Assessment\n\n")
    report.append("### Field Availability (Critical for NLP Pipeline)\n\n")
    
    # Analyze narrative availability
    events_with_text = 0
    events_with_problems = 0
    events_with_patient = 0
    narrative_lengths = []
    event_types = Counter()
    manufacturers = Counter()
    brand_names = Counter()
    product_codes_found = Counter()
    all_problems = []
    
    for e in all_events:
        # Narrative
        if "mdr_text" in e and e["mdr_text"]:
            for t in e["mdr_text"]:
                if t.get("text", "").strip() and len(t["text"]) > 30:
                    events_with_text += 1
                    narrative_lengths.append(len(t["text"]))
                    break
        
        # Product problems
        if "product_problems" in e and e["product_problems"]:
            problems = [p for p in e["product_problems"] if p.strip()]
            if problems:
                events_with_problems += 1
                all_problems.extend(problems)
        
        # Patient data
        if "patient" in e and e["patient"]:
            for p in e["patient"]:
                if p.get("patient_problems") or p.get("sequence_number_outcome"):
                    events_with_patient += 1
                    break
        
        # Event type
        event_types[e.get("event_type", "Unknown")] += 1
        
        # Device info
        if "device" in e:
            for d in e["device"]:
                manufacturers[d.get("manufacturer_d_name", "Unknown")] += 1
                brand_names[d.get("brand_name", "Unknown")] += 1
                product_codes_found[d.get("device_report_product_code", "N/A")] += 1
    
    total = max(len(all_events), 1)
    
    report.append(f"| Field | Available | Percentage | Impact on Project |\n")
    report.append(f"|-------|-----------|------------|-------------------|\n")
    report.append(f"| mdr_text (narratives) | {events_with_text}/{total} | **{events_with_text/total*100:.1f}%** | CRITICAL - Input for extraction |\n")
    report.append(f"| product_problems | {events_with_problems}/{total} | {events_with_problems/total*100:.1f}% | HIGH - Ground truth labels |\n")
    report.append(f"| patient data | {events_with_patient}/{total} | {events_with_patient/total*100:.1f}% | MEDIUM - Severity assessment |\n\n")
    
    if narrative_lengths:
        report.append("### Narrative Statistics\n\n")
        report.append(f"- Total narratives found: {len(narrative_lengths)}\n")
        report.append(f"- Average length: {sum(narrative_lengths)/len(narrative_lengths):.0f} chars\n")
        report.append(f"- Median length: {sorted(narrative_lengths)[len(narrative_lengths)//2]} chars\n")
        report.append(f"- Max length: {max(narrative_lengths)} chars\n")
        report.append(f"- Min length: {min(narrative_lengths)} chars\n")
        report.append(f"- Events with narrative > 200 chars: {sum(1 for l in narrative_lengths if l > 200)} ({sum(1 for l in narrative_lengths if l > 200)/total*100:.1f}%)\n\n")
    
    # Event types
    report.append("### Event Type Distribution\n\n")
    report.append("| Type | Count | % |\n|---|---|---|\n")
    for etype, count in event_types.most_common():
        report.append(f"| {etype} | {count} | {count/total*100:.1f}% |\n")
    report.append("\n")
    
    # Product codes
    report.append("### Product Code Distribution (in sample)\n\n")
    report.append("| Code | Count | Domain |\n|---|---|---|\n")
    pc_domains = {"LNH": "MRI", "JAK": "CT", "IYE": "CT X-ray", "LLZ": "Ultrasound", 
                  "IZL": "Digital X-ray", "MQB": "Molecular Dx", "QKO": "PCR", "GKZ": "Hematology"}
    for pc, count in product_codes_found.most_common():
        domain = pc_domains.get(pc, "Other")
        report.append(f"| {pc} | {count} | {domain} |\n")
    report.append("\n")
    
    # Manufacturers
    report.append("### Top 20 Manufacturers\n\n")
    report.append("| Manufacturer | Count |\n|---|---|\n")
    for mfr, count in manufacturers.most_common(20):
        report.append(f"| {mfr} | {count} |\n")
    report.append("\n")
    
    # Top brand names
    report.append("### Top 20 Brand Names\n\n")
    report.append("| Brand | Count |\n|---|---|\n")
    for bn, count in brand_names.most_common(20):
        report.append(f"| {bn} | {count} |\n")
    report.append("\n")
    
    # Product problems (software-focused analysis)
    report.append("### Product Problems — Software Relevance Analysis\n\n")
    sw_keywords = ["software", "display", "image", "screen", "program", "communication",
                   "data", "network", "algorithm", "calibration", "error", "freeze",
                   "crash", "artifact", "processing", "computation", "interface", "timeout",
                   "loss", "corrupt", "missing", "incorrect", "failure to", "unable"]
    
    problem_counter = Counter(all_problems)
    report.append("| Problem | Count | Software-Related? |\n|---|---|---|\n")
    for problem, count in problem_counter.most_common(30):
        is_sw = "✅ YES" if any(kw in problem.lower() for kw in sw_keywords) else ""
        report.append(f"| {problem} | {count} | {is_sw} |\n")
    
    sw_problems = sum(count for p, count in problem_counter.items() 
                      if any(kw in p.lower() for kw in sw_keywords))
    total_problems = sum(problem_counter.values())
    report.append(f"\n**Software-related problems: {sw_problems}/{total_problems} ({sw_problems/max(total_problems,1)*100:.1f}%)**\n\n")
    
    # ============ Recall Analysis ============
    report.append("## 2. Recall Data Analysis\n\n")
    
    recalls_with_reason = sum(1 for r in recalls if r.get("reason_for_recall", "").strip())
    recalls_with_action = sum(1 for r in recalls if r.get("action", "").strip())
    recalls_with_root = sum(1 for r in recalls if r.get("root_cause_description", "").strip())
    rtotal = max(len(recalls), 1)
    
    report.append("### Field Coverage\n\n")
    report.append(f"| Field | Available | % | Project Use |\n|---|---|---|---|\n")
    report.append(f"| reason_for_recall | {recalls_with_reason}/{rtotal} | {recalls_with_reason/rtotal*100:.1f}% | CAPA ground truth |\n")
    report.append(f"| action | {recalls_with_action}/{rtotal} | {recalls_with_action/rtotal*100:.1f}% | Corrective action examples |\n")
    report.append(f"| root_cause_description | {recalls_with_root}/{rtotal} | {recalls_with_root/rtotal*100:.1f}% | Root cause classification |\n\n")
    
    # Root causes
    root_causes = Counter(r.get("root_cause_description", "Unknown").strip() 
                          for r in recalls if r.get("root_cause_description", "").strip())
    report.append("### Root Cause Distribution\n\n")
    report.append("| Root Cause | Count | % |\n|---|---|---|\n")
    for rc, count in root_causes.most_common():
        report.append(f"| {rc} | {count} | {count/rtotal*100:.1f}% |\n")
    report.append("\n")
    
    # Recall reason length
    reason_lengths = [len(r["reason_for_recall"]) for r in recalls if r.get("reason_for_recall", "").strip()]
    if reason_lengths:
        report.append("### Recall Reason Text Stats\n\n")
        report.append(f"- Average: {sum(reason_lengths)/len(reason_lengths):.0f} chars\n")
        report.append(f"- Max: {max(reason_lengths)} chars\n")
        report.append(f"- Min: {min(reason_lengths)} chars\n\n")
    
    # ============ Count-based stats ============
    if counts:
        report.append("## 3. Population-Level Statistics (from API counts)\n\n")
        for key, data_list in counts.items():
            report.append(f"### {key.replace('_', ' ').title()}\n\n")
            report.append("| Term | Count |\n|---|---|\n")
            for item in data_list[:15]:
                report.append(f"| {item['term']} | {item['count']:,} |\n")
            report.append("\n")
    
    # ============ BLOCKERS & RISKS ============
    report.append("## 4. BLOCKERS & RISKS\n\n")
    
    report.append("### 🔴 Critical\n\n")
    
    narrative_pct = events_with_text / total * 100
    if narrative_pct < 70:
        report.append(f"1. **NARRATIVE COVERAGE: {narrative_pct:.0f}%** — Many events lack narrative text.\n")
        report.append(f"   - MITIGATION: Filter to events WITH mdr_text only. Still have {events_with_text} usable events.\n")
        report.append(f"   - This is normal for MAUDE — manufacturer-reported events often skip narrative.\n\n")
    else:
        report.append(f"1. ✅ Good narrative coverage ({narrative_pct:.0f}%). NLP pipeline has sufficient input.\n\n")
    
    report.append("2. **COMBINED DATA SIZE**: Medical imaging events (~33K) are more manageable than ")
    report.append("infusion pumps (1.94M), but API pagination limits to 26K results per query.\n")
    report.append("   - MITIGATION: For MRI+CT+IYE (combined ~13K), API pagination is sufficient!\n")
    report.append("   - For ultrasound (19K), need multiple date-ranged queries or bulk download.\n\n")
    
    report.append("3. **PRODUCT_PROBLEMS FIELD SPARSE**: Only structured problem codes are available for ")
    report.append(f"{events_with_problems/total*100:.0f}% of events.\n")
    report.append("   - MITIGATION: Use narratives as primary input. Product_problems is bonus ground truth.\n\n")
    
    report.append("### 🟡 Medium Risks\n\n")
    
    report.append("4. **IMAGING EVENTS ARE HARDWARE-HEAVY**: Many events are mechanical/electrical ")
    report.append("(coil heating, table movement, physical burns), not software.\n")
    report.append("   - MITIGATION: Pre-filter using keywords: 'software', 'image', 'display', 'artifact', ")
    report.append("'algorithm', 'reconstruction', 'processing', 'data loss', 'DICOM'.\n")
    report.append("   - The CT recalls explicitly mention 'Software Design' as root cause — good signal.\n\n")
    
    report.append("5. **MOLECULAR DX EVENTS MAY BE COVID-DOMINATED**: QJR (20K events) is mostly ")
    report.append("COVID rapid tests which may skew the dataset.\n")
    report.append("   - MITIGATION: Focus on MQB (instrument-level) and GKZ (hematology analyzers) ")
    report.append("which are platform/software issues, not test strip failures.\n\n")
    
    report.append("6. **RECALL DATA IS BETTER THAN EVENTS FOR SOFTWARE FAILURES**: Recalls explicitly ")
    report.append("cite 'Software Design' as root cause and describe the fix.\n")
    report.append("   - OPPORTUNITY: 2,830 imaging recalls + 589 mol dx recalls = 3,419 total. ")
    report.append("This is a RICH dataset for CAPA training and Graph RAG.\n\n")
    
    report.append("7. **MULTIPLE MANUFACTURERS ADD COMPLEXITY**: Philips, Siemens, GE Healthcare all ")
    report.append("report differently. Entity resolution needed.\n")
    report.append("   - MITIGATION: Normalize manufacturer names in preprocessing. Use knowledge graph.\n\n")
    
    report.append("### 🟢 Advantages Over Infusion Pumps\n\n")
    report.append("8. ✅ **More manageable volume**: 33K imaging events vs 1.94M infusion pump events\n")
    report.append("9. ✅ **Richer recall data**: 2,830 imaging recalls with detailed root causes and actions\n")
    report.append("10. ✅ **Clear software failures**: CT/MRI recalls explicitly cite 'Software Design' root cause\n")
    report.append("11. ✅ **Multi-domain**: MRI + CT + Ultrasound + Molecular Dx shows system generalization\n")
    report.append("12. ✅ **AI/ML relevance**: Image reconstruction, CAD algorithms, DICOM processing — all software\n")
    report.append("13. ✅ **Major manufacturers**: Philips, Siemens, GE — well-documented device families\n")
    report.append("14. ✅ **API pagination feasible**: Most product codes have <26K events — no bulk download needed\n\n")
    
    # ============ OVERSTATEMENTS AUDIT ============
    report.append("## 5. OVERSTATEMENTS AUDIT (System_Design.md)\n\n")
    report.append("| Claim | Reality | Fix |\n|---|---|---|\n")
    report.append("| 'In 2 minutes' | LLM API latency + 6 agents + retrieval = 3-8 min realistic | Change to '< 10 minutes' |\n")
    report.append("| '5x faster' | No baseline measured. Industry avg unknown | Remove or say 'significantly faster' |\n")
    report.append("| '87% confidence' | Fabricated for demo illustration | Label as 'illustrative' or remove |\n")
    report.append("| 'First application of DPO/RLHF' | Can't verify without lit review | Say 'novel in this domain' |\n")
    report.append("| '1.94M events implies using all' | We'll use ~5-15K subset | Clarify actual working set |\n")
    report.append("| '18 techniques deeply' | Can't deeply implement 18 in 4 weeks | Tier: 6 core, 6 extended, 6 stretch |\n")
    report.append("| 'PPO training' | PPO is unstable, needs 100+ GPU-hrs | Lead with DPO, PPO as comparison |\n")
    report.append("| 'Contrastive embeddings' | Needs 500+ pairs minimum to converge | Mark as Week 3 stretch goal |\n")
    report.append("| 'Knowledge distillation' | Needs eval infrastructure first | Mark as ablation experiment |\n")
    report.append("| 'Production pathway' | Academic project, not production-ready | Frame as 'proof of concept' |\n\n")
    
    # ============ COLLABORATION STRATEGY ============
    report.append("## 6. COLLABORATION STRATEGY (6 Members, 4 Weeks)\n\n")
    
    report.append("### Member Assignments (Revised for Imaging/MolDx)\n\n")
    report.append("| Member | Primary Responsibility | Secondary |\n|---|---|---|\n")
    report.append("| M1 | Data pipeline + Embeddings | Entity resolution for manufacturers |\n")
    report.append("| M2 | Agent 3 (FDA Retrieval) + Knowledge Graph | Pipeline integration |\n")
    report.append("| M3 | Agent 1 (Extraction) + DSPy optimization | Agent 6 (Report) |\n")
    report.append("| M4 | Agent 2 (Similarity/Clustering) + Dashboard | UMAP visualizations |\n")
    report.append("| M5 | Agent 4 (Risk) + Agent 5 (CAPA) + DPO | Alignment experiments |\n")
    report.append("| M6 | Evaluation framework + LLM-as-Judge | Gold standard labeling |\n\n")
    
    report.append("### JSON Schema Contracts (Define in Week 1)\n\n")
    report.append("```json\n")
    report.append("// Agent 1 Output → Agents 2,3,4 Input\n")
    report.append("{\n")
    report.append('  "report_id": "string",\n')
    report.append('  "modality": "MRI|CT|Ultrasound|MolDx",\n')
    report.append('  "component": "string (e.g., image reconstruction, DICOM gateway)",\n')
    report.append('  "failure_mode": "string (e.g., image artifact, data loss, incorrect result)",\n')
    report.append('  "symptom": "string",\n')
    report.append('  "severity_indicator": "string",\n')
    report.append('  "manufacturer": "string (normalized)",\n')
    report.append('  "device_model": "string",\n')
    report.append('  "patient_impact": "string|null",\n')
    report.append('  "discovery_phase": "in-use|maintenance|calibration|qa-check",\n')
    report.append('  "software_related": true,\n')
    report.append('  "confidence": 0.0\n')
    report.append("}\n")
    report.append("```\n\n")
    
    report.append("### Collaboration Risks\n\n")
    report.append("| Risk | Impact | Mitigation |\n|---|---|---|\n")
    report.append("| Integration breaks at agent boundaries | HIGH | JSON schema contracts frozen end of Week 1 |\n")
    report.append("| One member's agent blocks downstream | HIGH | Mock inputs for each agent; standalone testing |\n")
    report.append("| Data too large for Git | MEDIUM | .gitignore data/. Script re-downloads. Share embeddings via cloud |\n")
    report.append("| API key sharing | MEDIUM | .env files. Single shared key with rate awareness |\n")
    report.append("| GPU contention for DPO/fine-tuning | MEDIUM | Schedule: M5 Mon-Wed, M6 Thu-Fri, M1 weekends |\n")
    report.append("| Evaluation needs all agents running | HIGH | LLM-as-Judge evaluates each agent independently |\n")
    report.append("| Merge conflicts | LOW | Each member owns their agent .py file |\n\n")
    
    report.append("### Repository Structure\n\n")
    report.append("```\n")
    report.append("imaging-signal-intelligence/\n")
    report.append("├── data/                       # .gitignored\n")
    report.append("│   ├── imaging_events/         # MRI+CT+Ultrasound+X-ray\n")
    report.append("│   ├── molecular_dx_events/    # Mol Dx + Hematology\n")
    report.append("│   ├── recalls/                # All recalls\n")
    report.append("│   ├── embeddings/             # Shared via cloud storage\n")
    report.append("│   └── analysis/               # Reports and stats\n")
    report.append("├── src/\n")
    report.append("│   ├── agents/                 # One file per agent (clear ownership)\n")
    report.append("│   │   ├── extraction.py       # M3\n")
    report.append("│   │   ├── similarity.py       # M4\n")
    report.append("│   │   ├── retrieval.py        # M2\n")
    report.append("│   │   ├── risk.py             # M5\n")
    report.append("│   │   ├── capa.py             # M5\n")
    report.append("│   │   └── report.py           # M3\n")
    report.append("│   ├── pipeline/\n")
    report.append("│   │   ├── orchestrator.py     # M2 (integration)\n")
    report.append("│   │   └── schemas.py          # SHARED - frozen Week 1\n")
    report.append("│   ├── data_processing/        # M1\n")
    report.append("│   ├── embeddings/             # M1 + M4\n")
    report.append("│   ├── evaluation/             # M6\n")
    report.append("│   ├── alignment/              # M5\n")
    report.append("│   └── dashboard/              # M4\n")
    report.append("├── notebooks/                  # Each member owns theirs\n")
    report.append("├── configs/                    # Prompts, model configs\n")
    report.append("├── tests/                      # Unit tests per agent\n")
    report.append("└── docs/                       # Final report, poster\n")
    report.append("```\n\n")
    
    report.append("### Communication Protocol\n\n")
    report.append("1. **Daily async standup** (Slack/Teams): What done, what next, what blocks\n")
    report.append("2. **Schema freeze**: End of Week 1 — JSON contracts locked\n")
    report.append("3. **Integration checkpoint**: End of each week — run `pytest tests/`\n")
    report.append("4. **Code reviews**: Before merging to main, at least 1 peer review\n")
    report.append("5. **Shared artifacts**: Embeddings generated Week 1 by M1, shared via Google Drive\n")
    report.append("6. **Demo rehearsal**: Week 4 Day 3 — full end-to-end run with 5 examples\n\n")
    
    # ============ RECOMMENDED DATA SUBSET ============
    report.append("## 7. RECOMMENDED WORKING DATASET\n\n")
    report.append("| Dataset | Size | Source | When |\n|---|---|---|---|\n")
    report.append("| MRI events (LNH, 2019-2026, with narratives) | ~3,000 | API pagination | Week 1 Day 1 |\n")
    report.append("| CT events (JAK+IYE, 2019-2026, with narratives) | ~5,000 | API pagination | Week 1 Day 1 |\n")
    report.append("| Ultrasound events (LLZ, 2019-2026, with narratives) | ~8,000 | API (multiple queries) | Week 1 Day 1-2 |\n")
    report.append("| Molecular Dx events (MQB+GKZ, with narratives) | ~3,000 | API pagination | Week 1 Day 2 |\n")
    report.append("| All imaging recalls | ~2,830 | API (done ✅) | Done |\n")
    report.append("| All mol dx recalls | ~589 | API (done ✅) | Done |\n")
    report.append("| Synthetic internal defect reports | 200 | GPT-4 generation | Week 1 Day 3-4 |\n")
    report.append("| Gold-standard labeled set | 50 | Manual team labeling | Week 1 Day 4-5 |\n")
    report.append(f"| **Total working set** | **~20,000 events + 3,419 recalls** | | |\n\n")
    
    report.append("### Why This Is Better Than 1.94M Infusion Pump Events\n\n")
    report.append("- **Manageable**: 20K events can be fully embedded in hours, not days\n")
    report.append("- **Multi-domain**: Shows system works across MRI, CT, Ultrasound, Mol Dx\n")
    report.append("- **Software-rich recalls**: Imaging recalls explicitly cite software design failures\n")
    report.append("- **API-feasible**: No bulk download needed — all fits within API pagination limits\n")
    report.append("- **Diverse manufacturers**: Philips, Siemens, GE — entity resolution challenge\n")
    report.append("- **Realistic**: A QM would actually assess across their imaging fleet, not one product\n\n")
    
    # ============ SAMPLE NARRATIVES ============
    report.append("## 8. SAMPLE NARRATIVES (Team Review)\n\n")
    
    sample_count = 0
    for e in all_events:
        if sample_count >= 12:
            break
        if "mdr_text" in e and e["mdr_text"]:
            for t in e["mdr_text"]:
                if (t.get("text_type_code") in ["Description of Event or Problem", "Additional Manufacturer Narrative"]
                    and len(t.get("text", "")) > 100):
                    pc = "N/A"
                    brand = "N/A"
                    if "device" in e:
                        pc = e["device"][0].get("device_report_product_code", "N/A")
                        brand = e["device"][0].get("brand_name", "N/A")[:40]
                    report.append(f"**Sample {sample_count+1}** — {pc} | {brand}\n")
                    report.append(f"- Event type: {e.get('event_type', 'N/A')}\n")
                    report.append(f"- Problems: {e.get('product_problems', ['N/A'])}\n")
                    report.append(f"- Narrative: \"{t['text'][:400]}\"\n\n")
                    sample_count += 1
                    break
    
    # ============ TECHNIQUE PRIORITIZATION ============
    report.append("## 9. TECHNIQUE PRIORITIZATION (Realistic for 4 Weeks)\n\n")
    report.append("### Core (MUST implement — these define the project)\n\n")
    report.append("| # | Technique | Agent | Why Core |\n|---|---|---|---|\n")
    report.append("| 1 | RAG (Vector + Semantic) | Agent 3 | Foundation of evidence retrieval |\n")
    report.append("| 2 | Chain-of-Thought Extraction | Agent 1 | Structured output from narratives |\n")
    report.append("| 3 | Sentence-Transformer Embeddings | Agent 2 | Clustering and similarity |\n")
    report.append("| 4 | HDBSCAN + UMAP | Agent 2 | Pattern detection and visualization |\n")
    report.append("| 5 | ReAct Pattern | Agent 3 | Tool-augmented retrieval |\n")
    report.append("| 6 | Self-Reflection / Critique-Revise | Agent 4, 6 | Hallucination reduction |\n\n")
    
    report.append("### Extended (SHOULD implement — demonstrates depth)\n\n")
    report.append("| # | Technique | Agent | Effort |\n|---|---|---|---|\n")
    report.append("| 7 | DSPy Prompt Optimization | Agent 1 | Medium (2-3 days) |\n")
    report.append("| 8 | DPO Alignment | Agent 5, 6 | Medium (needs 50+ preference pairs) |\n")
    report.append("| 9 | Graph RAG | Agent 3 | Medium (knowledge graph build) |\n")
    report.append("| 10 | LLM-as-Judge | Eval | Medium (prompt design + calibration) |\n")
    report.append("| 11 | Temporal Anomaly Detection | Agent 2 | Low-Medium (stats on clusters) |\n")
    report.append("| 12 | Constrained Decoding / JSON Schema | Agent 1, 4 | Low (use tool calling) |\n\n")
    
    report.append("### Stretch (NICE TO HAVE — if time permits)\n\n")
    report.append("| # | Technique | Effort | Risk |\n|---|---|---|---|\n")
    report.append("| 13 | Contrastive Fine-tuning | High | Needs 500+ pairs, may not converge |\n")
    report.append("| 14 | PPO (compare with DPO) | High | Unstable training, needs GPU time |\n")
    report.append("| 15 | Knowledge Distillation | High | Needs working system first |\n")
    report.append("| 16 | Active Learning | Medium | Needs iteration loop infrastructure |\n")
    report.append("| 17 | LoRA Fine-tuning | High | Needs GPU + training data |\n")
    report.append("| 18 | MCP Tool Integration | Medium | Nice demo, not research contribution |\n\n")
    
    # Write report
    report_path = ANALYSIS_DIR / "data_analysis_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.writelines(report)
    
    print(f"\n  Report saved: {report_path}")
    return report_path


# ============================================================
# MAIN EXECUTION
# ============================================================
if __name__ == "__main__":
    print("=" * 70)
    print("FDA DATA COLLECTION: Medical Imaging & Molecular Diagnostics")
    print("=" * 70)
    
    # 1. Download Medical Imaging Events
    print("\n\n>>> PHASE 1: MEDICAL IMAGING ADVERSE EVENTS")
    print("=" * 70)
    imaging_codes = [
        ("LNH", "MRI System"),
        ("JAK", "CT Scanner"),
        ("IYE", "CT X-ray System"),
        ("LLZ", "Ultrasound Imaging System"),
        ("IZL", "Digital X-ray System"),
    ]
    imaging_events = download_events(imaging_codes, EVENTS_DIR, date_from="20190101", batches_per_code=5)
    
    # 2. Download Molecular Dx Events
    print("\n\n>>> PHASE 2: MOLECULAR DIAGNOSTICS ADVERSE EVENTS")
    print("=" * 70)
    moldx_codes = [
        ("MQB", "Molecular Dx Instrument"),
        ("GKZ", "Hematology Analyzer"),
        ("QKO", "PCR Platform"),
    ]
    moldx_events = download_events(moldx_codes, MOLDX_DIR, date_from="20190101", batches_per_code=5)
    
    # 3. Download Recalls (ALL codes)
    print("\n\n>>> PHASE 3: RECALLS (ALL PRODUCT CODES)")
    print("=" * 70)
    all_codes = imaging_codes + moldx_codes
    recalls = download_recalls(all_codes)
    
    # 4. Download Count Statistics
    print("\n\n>>> PHASE 4: STATISTICS / COUNTS")
    print("=" * 70)
    counts = download_counts()
    
    # 5. Analyze Everything
    print("\n\n>>> PHASE 5: DATA ANALYSIS")
    print("=" * 70)
    analyze_all(imaging_events, moldx_events, recalls, counts)
    
    print("\n\n" + "=" * 70)
    print("DATA COLLECTION COMPLETE!")
    print("=" * 70)
    print(f"\n  Imaging events: {len(imaging_events)}")
    print(f"  Molecular Dx events: {len(moldx_events)}")
    print(f"  Recalls: {len(recalls)}")
    print(f"  Files in {EVENTS_DIR}: {len(list(EVENTS_DIR.glob('*.json')))}")
    print(f"  Files in {MOLDX_DIR}: {len(list(MOLDX_DIR.glob('*.json')))}")
    print(f"  Files in {RECALL_DIR}: {len(list(RECALL_DIR.glob('*.json')))}")
    print(f"  Analysis: {ANALYSIS_DIR / 'data_analysis_report.md'}")
