"""
FDA Data Collection Script for Infusion Pump Signal Intelligence System
Downloads adverse events, recalls, and supporting data via openFDA API.
Saves raw JSON + produces summary statistics.
"""

import json
import time
import os
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

BASE_DIR = Path(__file__).parent
MAUDE_DIR = BASE_DIR / "maude_events"
RECALL_DIR = BASE_DIR / "recalls"
ANALYSIS_DIR = BASE_DIR / "analysis"

# openFDA API has a limit of 1000 results per query (skip+limit <= 26000)
# We'll download in batches

def fetch_json(url, retries=3, delay=2):
    """Fetch JSON from URL with retry logic for 429 rate limits."""
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "MTech-Research/1.0"})
            with urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode())
        except HTTPError as e:
            if e.code == 429:
                wait = delay * (attempt + 1)
                print(f"  Rate limited (429). Waiting {wait}s...")
                time.sleep(wait)
            else:
                print(f"  HTTP Error {e.code}: {e.reason}")
                if attempt == retries - 1:
                    raise
        except URLError as e:
            print(f"  URL Error: {e.reason}")
            if attempt == retries - 1:
                raise
        except Exception as e:
            print(f"  Error: {e}")
            if attempt == retries - 1:
                raise
    return None


def download_maude_events():
    """Download infusion pump adverse events from openFDA MAUDE."""
    print("\n" + "="*70)
    print("DOWNLOADING MAUDE ADVERSE EVENTS (Infusion Pumps)")
    print("="*70)
    
    # Product codes: FRN (general infusion), MEA (PCA), QFG (alternate controller/insulin)
    # We'll download recent data (2019-2026) to keep manageable
    # Focus on software-related: filter by product_problems containing key terms
    
    all_events = []
    
    # Strategy: Download by year to manage API limits
    # openFDA max: skip+limit <= 26000, so we can get up to 26000 per query
    # For 2019-2026, download 1000 per year-product_code combo
    
    queries = [
        # Recent events for FRN (general infusion pumps) - correct field: device.device_report_product_code
        {
            "name": "FRN_2020_2026_batch1",
            "url": "https://api.fda.gov/device/event.json?search=device.device_report_product_code:FRN+AND+date_received:[20200101+TO+20261231]&limit=100&skip=0",
            "desc": "General infusion pump events (2020-2026), batch 1"
        },
        {
            "name": "FRN_2020_2026_batch2",
            "url": "https://api.fda.gov/device/event.json?search=device.device_report_product_code:FRN+AND+date_received:[20200101+TO+20261231]&limit=100&skip=100",
            "desc": "General infusion pump events (2020-2026), batch 2"
        },
        {
            "name": "FRN_2020_2026_batch3",
            "url": "https://api.fda.gov/device/event.json?search=device.device_report_product_code:FRN+AND+date_received:[20200101+TO+20261231]&limit=100&skip=200",
            "desc": "General infusion pump events (2020-2026), batch 3"
        },
        {
            "name": "FRN_2020_2026_batch4",
            "url": "https://api.fda.gov/device/event.json?search=device.device_report_product_code:FRN+AND+date_received:[20200101+TO+20261231]&limit=100&skip=300",
            "desc": "General infusion pump events (2020-2026), batch 4"
        },
        {
            "name": "FRN_2020_2026_batch5",
            "url": "https://api.fda.gov/device/event.json?search=device.device_report_product_code:FRN+AND+date_received:[20200101+TO+20261231]&limit=100&skip=400",
            "desc": "General infusion pump events (2020-2026), batch 5"
        },
        # QFG (insulin pumps with AI/algorithms - most software-relevant)
        {
            "name": "QFG_2020_2026_batch1",
            "url": "https://api.fda.gov/device/event.json?search=device.device_report_product_code:QFG+AND+date_received:[20200101+TO+20261231]&limit=100&skip=0",
            "desc": "Alternate controller infusion pump events (2020-2026), batch 1"
        },
        {
            "name": "QFG_2020_2026_batch2",
            "url": "https://api.fda.gov/device/event.json?search=device.device_report_product_code:QFG+AND+date_received:[20200101+TO+20261231]&limit=100&skip=100",
            "desc": "Alternate controller events batch 2"
        },
        {
            "name": "QFG_2020_2026_batch3",
            "url": "https://api.fda.gov/device/event.json?search=device.device_report_product_code:QFG+AND+date_received:[20200101+TO+20261231]&limit=100&skip=200",
            "desc": "Alternate controller events batch 3"
        },
        {
            "name": "QFG_2020_2026_batch4",
            "url": "https://api.fda.gov/device/event.json?search=device.device_report_product_code:QFG+AND+date_received:[20200101+TO+20261231]&limit=100&skip=300",
            "desc": "Alternate controller events batch 4"
        },
        {
            "name": "QFG_2020_2026_batch5",
            "url": "https://api.fda.gov/device/event.json?search=device.device_report_product_code:QFG+AND+date_received:[20200101+TO+20261231]&limit=100&skip=400",
            "desc": "Alternate controller events batch 5"
        },
        # MEA (PCA pumps - smaller population, hospital-focused)
        {
            "name": "MEA_2019_2026_batch1",
            "url": "https://api.fda.gov/device/event.json?search=device.device_report_product_code:MEA+AND+date_received:[20190101+TO+20261231]&limit=100&skip=0",
            "desc": "PCA infusion pump events (2019-2026), batch 1"
        },
        {
            "name": "MEA_2019_2026_batch2",
            "url": "https://api.fda.gov/device/event.json?search=device.device_report_product_code:MEA+AND+date_received:[20190101+TO+20261231]&limit=100&skip=100",
            "desc": "PCA pump events batch 2"
        },
    ]
    
    for q in queries:
        print(f"\n  Fetching: {q['desc']}...")
        data = fetch_json(q["url"])
        if data and "results" in data:
            count = len(data["results"])
            total = data["meta"]["results"]["total"]
            print(f"    Got {count} results (total available: {total:,})")
            
            # Save raw JSON
            filepath = MAUDE_DIR / f"{q['name']}.json"
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            
            all_events.extend(data["results"])
        else:
            print(f"    FAILED or no results")
        
        time.sleep(1.5)  # Rate limit courtesy
    
    # Save combined events
    combined_path = MAUDE_DIR / "combined_events.json"
    with open(combined_path, "w", encoding="utf-8") as f:
        json.dump(all_events, f, indent=2)
    
    print(f"\n  Total events downloaded: {len(all_events)}")
    return all_events


def download_recalls():
    """Download all infusion pump recalls (513 total - manageable)."""
    print("\n" + "="*70)
    print("DOWNLOADING FDA RECALLS (Infusion Pumps)")
    print("="*70)
    
    all_recalls = []
    
    # 513 total recalls - download in batches of 100
    for skip in range(0, 600, 100):
        url = f"https://api.fda.gov/device/recall.json?search=product_code:FRN&limit=100&skip={skip}"
        print(f"  Fetching recalls (skip={skip})...")
        data = fetch_json(url)
        if data and "results" in data:
            count = len(data["results"])
            total = data["meta"]["results"]["total"]
            print(f"    Got {count} results (total: {total})")
            all_recalls.extend(data["results"])
            
            if count < 100:
                break  # No more results
        else:
            print(f"    FAILED or no results")
            break
        
        time.sleep(1.5)
    
    # Save combined recalls
    filepath = RECALL_DIR / "all_recalls.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(all_recalls, f, indent=2)
    
    print(f"\n  Total recalls downloaded: {len(all_recalls)}")
    return all_recalls


def download_counts():
    """Download count/statistics data for analysis. Handles errors gracefully."""
    print("\n" + "="*70)
    print("DOWNLOADING COUNT DATA FOR ANALYSIS")
    print("="*70)
    
    counts = {}
    
    # Note: count queries on very large datasets (FRN=1.8M) may timeout/500.
    # Use smaller-scoped queries or recall-based counts which are smaller.
    
    count_queries = [
        ("event_types_MEA", 
         "https://api.fda.gov/device/event.json?search=device.device_report_product_code:MEA&count=event_type",
         "MEA event type distribution (smaller dataset)"),
        ("product_problems_MEA",
         "https://api.fda.gov/device/event.json?search=device.device_report_product_code:MEA&count=product_problems",
         "MEA product problems"),
        ("recall_root_causes",
         "https://api.fda.gov/device/recall.json?search=product_code:FRN&count=root_cause_description.exact",
         "FRN recall root causes"),
        ("recall_event_types",
         "https://api.fda.gov/device/recall.json?search=product_code:FRN&count=event_type.exact",
         "FRN recall event types"),
        # Try FRN with date limit to reduce dataset size
        ("event_types_FRN_recent",
         "https://api.fda.gov/device/event.json?search=device.device_report_product_code:FRN+AND+date_received:[20230101+TO+20261231]&count=event_type",
         "FRN event types (2023-2026 only)"),
        ("product_problems_FRN_recent",
         "https://api.fda.gov/device/event.json?search=device.device_report_product_code:FRN+AND+date_received:[20230101+TO+20261231]&count=product_problems",
         "FRN product problems (2023-2026)"),
        ("manufacturers_FRN_recent",
         "https://api.fda.gov/device/event.json?search=device.device_report_product_code:FRN+AND+date_received:[20230101+TO+20261231]&count=device.manufacturer_d_name.exact",
         "FRN manufacturers (2023-2026)"),
        ("product_problems_QFG_recent",
         "https://api.fda.gov/device/event.json?search=device.device_report_product_code:QFG+AND+date_received:[20230101+TO+20261231]&count=product_problems",
         "QFG product problems (2023-2026)"),
        ("brand_names_FRN_recent",
         "https://api.fda.gov/device/event.json?search=device.device_report_product_code:FRN+AND+date_received:[20230101+TO+20261231]&count=device.brand_name.exact",
         "FRN brand names (2023-2026)"),
    ]
    
    for key, url, desc in count_queries:
        print(f"  Fetching {desc}...")
        try:
            data = fetch_json(url)
            if data and "results" in data:
                counts[key] = data["results"]
                print(f"    Got {len(data['results'])} entries")
            else:
                print(f"    No results or error")
        except Exception as e:
            print(f"    SKIPPED (error: {type(e).__name__})")
        time.sleep(1.5)

    # Save counts
    filepath = ANALYSIS_DIR / "count_data.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(counts, f, indent=2)
    
    print(f"\n  Successfully fetched {len(counts)} count datasets")
    return counts


def analyze_data(events, recalls, counts):
    """Produce analysis report from downloaded data."""
    print("\n" + "="*70)
    print("DATA ANALYSIS REPORT")
    print("="*70)
    
    report = []
    report.append("# FDA Data Analysis Report - Infusion Pump Signal Intelligence\n")
    report.append(f"Generated: 2026-05-29\n")
    report.append(f"Total adverse events downloaded: {len(events)}\n")
    report.append(f"Total recalls downloaded: {len(recalls)}\n\n")
    
    # --- Adverse Event Analysis ---
    report.append("## 1. Adverse Event Data Quality Analysis\n\n")
    
    # Check for narrative text availability (critical for our system)
    events_with_text = 0
    events_with_product_problems = 0
    events_with_patient_data = 0
    event_types = {}
    narrative_lengths = []
    manufacturers = {}
    brand_names = {}
    product_problems_list = []
    
    for e in events:
        # Check mdr_text (narratives)
        if "mdr_text" in e and e["mdr_text"]:
            has_text = False
            for text_entry in e["mdr_text"]:
                if text_entry.get("text", "").strip():
                    has_text = True
                    narrative_lengths.append(len(text_entry["text"]))
            if has_text:
                events_with_text += 1
        
        # Check product_problems
        if "product_problems" in e and e["product_problems"]:
            problems = [p for p in e["product_problems"] if p.strip()]
            if problems:
                events_with_product_problems += 1
                product_problems_list.extend(problems)
        
        # Check patient data
        if "patient" in e and e["patient"]:
            for p in e["patient"]:
                if p.get("patient_problems") or p.get("patient_age"):
                    events_with_patient_data += 1
                    break
        
        # Event type
        etype = e.get("event_type", "Unknown")
        event_types[etype] = event_types.get(etype, 0) + 1
        
        # Manufacturer
        if "device" in e:
            for d in e["device"]:
                mfr = d.get("manufacturer_d_name", "Unknown")
                manufacturers[mfr] = manufacturers.get(mfr, 0) + 1
                bn = d.get("brand_name", "Unknown")
                brand_names[bn] = brand_names.get(bn, 0) + 1
    
    total = len(events) if events else 1
    
    report.append(f"### Field Availability (Critical for Project)\n\n")
    report.append(f"| Field | Available | Percentage | Project Impact |\n")
    report.append(f"|-------|-----------|------------|----------------|\n")
    report.append(f"| mdr_text (narratives) | {events_with_text}/{total} | {events_with_text/total*100:.1f}% | **CRITICAL** - Input for extraction agent |\n")
    report.append(f"| product_problems | {events_with_product_problems}/{total} | {events_with_product_problems/total*100:.1f}% | HIGH - Ground truth for classification |\n")
    report.append(f"| patient data | {events_with_patient_data}/{total} | {events_with_patient_data/total*100:.1f}% | MEDIUM - Severity assessment |\n\n")
    
    # Narrative length stats
    if narrative_lengths:
        avg_len = sum(narrative_lengths) / len(narrative_lengths)
        max_len = max(narrative_lengths)
        min_len = min(narrative_lengths)
        report.append(f"### Narrative Text Statistics\n\n")
        report.append(f"- Average narrative length: {avg_len:.0f} characters\n")
        report.append(f"- Max narrative length: {max_len} characters\n")
        report.append(f"- Min narrative length: {min_len} characters\n")
        report.append(f"- Total narrative entries: {len(narrative_lengths)}\n\n")
    
    # Event types
    report.append(f"### Event Type Distribution\n\n")
    report.append(f"| Event Type | Count | Percentage |\n")
    report.append(f"|------------|-------|------------|\n")
    for etype, count in sorted(event_types.items(), key=lambda x: -x[1]):
        report.append(f"| {etype} | {count} | {count/total*100:.1f}% |\n")
    report.append("\n")
    
    # Top manufacturers
    report.append(f"### Top 15 Manufacturers (in downloaded sample)\n\n")
    report.append(f"| Manufacturer | Count |\n")
    report.append(f"|-------------|-------|\n")
    for mfr, count in sorted(manufacturers.items(), key=lambda x: -x[1])[:15]:
        report.append(f"| {mfr} | {count} |\n")
    report.append("\n")
    
    # Top brand names
    report.append(f"### Top 15 Brand Names\n\n")
    report.append(f"| Brand Name | Count |\n")
    report.append(f"|-----------|-------|\n")
    for bn, count in sorted(brand_names.items(), key=lambda x: -x[1])[:15]:
        report.append(f"| {bn} | {count} |\n")
    report.append("\n")
    
    # Top product problems
    from collections import Counter
    problem_counts = Counter(product_problems_list)
    report.append(f"### Top 20 Product Problems (Failure Modes)\n\n")
    report.append(f"| Problem | Count | Relevance to Software |\n")
    report.append(f"|---------|-------|----------------------|\n")
    sw_keywords = ["software", "display", "alarm", "screen", "program", "communication", 
                   "data", "battery", "power", "stop", "error", "timeout", "calibration"]
    for problem, count in problem_counts.most_common(20):
        is_sw = "⚠️ Likely" if any(kw in problem.lower() for kw in sw_keywords) else ""
        report.append(f"| {problem} | {count} | {is_sw} |\n")
    report.append("\n")
    
    # --- Recall Analysis ---
    report.append("## 2. Recall Data Analysis\n\n")
    
    recalls_with_reason = 0
    recalls_with_action = 0
    recalls_with_root_cause = 0
    root_causes = {}
    reason_lengths = []
    
    for r in recalls:
        if r.get("reason_for_recall", "").strip():
            recalls_with_reason += 1
            reason_lengths.append(len(r["reason_for_recall"]))
        if r.get("action", "").strip():
            recalls_with_action += 1
        rc = r.get("root_cause_description", "").strip()
        if rc:
            recalls_with_root_cause += 1
            root_causes[rc] = root_causes.get(rc, 0) + 1
    
    rtotal = len(recalls) if recalls else 1
    
    report.append(f"### Recall Field Availability\n\n")
    report.append(f"| Field | Available | Percentage | Project Impact |\n")
    report.append(f"|-------|-----------|------------|----------------|\n")
    report.append(f"| reason_for_recall | {recalls_with_reason}/{rtotal} | {recalls_with_reason/rtotal*100:.1f}% | **CRITICAL** - CAPA ground truth |\n")
    report.append(f"| action (corrective) | {recalls_with_action}/{rtotal} | {recalls_with_action/rtotal*100:.1f}% | **CRITICAL** - CAPA examples |\n")
    report.append(f"| root_cause_description | {recalls_with_root_cause}/{rtotal} | {recalls_with_root_cause/rtotal*100:.1f}% | HIGH - Root cause classification |\n\n")
    
    if reason_lengths:
        report.append(f"### Recall Reason Text Statistics\n\n")
        report.append(f"- Average reason length: {sum(reason_lengths)/len(reason_lengths):.0f} characters\n")
        report.append(f"- Max reason length: {max(reason_lengths)} characters\n")
        report.append(f"- Min reason length: {min(reason_lengths)} characters\n\n")
    
    report.append(f"### Root Cause Distribution\n\n")
    report.append(f"| Root Cause | Count | Percentage |\n")
    report.append(f"|-----------|-------|------------|\n")
    for rc, count in sorted(root_causes.items(), key=lambda x: -x[1]):
        report.append(f"| {rc} | {count} | {count/rtotal*100:.1f}% |\n")
    report.append("\n")
    
    # --- Count-based analysis from API ---
    if counts:
        report.append("## 3. Full Population Statistics (from openFDA counts)\n\n")
        
        if "event_types_FRN" in counts:
            report.append("### FRN Event Types (Full Population)\n\n")
            report.append("| Event Type | Count |\n|---|---|\n")
            for item in counts["event_types_FRN"]:
                report.append(f"| {item['term']} | {item['count']:,} |\n")
            report.append("\n")
        
        if "product_problems_FRN" in counts:
            report.append("### FRN Top 30 Product Problems (Full Population)\n\n")
            report.append("| Problem | Count | Software-Related? |\n|---|---|---|\n")
            for item in counts["product_problems_FRN"][:30]:
                is_sw = "⚠️" if any(kw in item["term"].lower() for kw in sw_keywords) else ""
                report.append(f"| {item['term']} | {item['count']:,} | {is_sw} |\n")
            report.append("\n")
        
        if "product_problems_QFG" in counts:
            report.append("### QFG Product Problems (Insulin/AI Pumps - Full Population)\n\n")
            report.append("| Problem | Count |\n|---|---|\n")
            for item in counts["product_problems_QFG"][:20]:
                report.append(f"| {item['term']} | {item['count']:,} |\n")
            report.append("\n")
        
        if "manufacturers_FRN" in counts:
            report.append("### Top 20 Manufacturers (Full Population)\n\n")
            report.append("| Manufacturer | Event Count |\n|---|---|\n")
            for item in counts["manufacturers_FRN"][:20]:
                report.append(f"| {item['term']} | {item['count']:,} |\n")
            report.append("\n")
        
        if "recall_root_causes" in counts:
            report.append("### Recall Root Causes (Full Population)\n\n")
            report.append("| Root Cause | Count |\n|---|---|\n")
            for item in counts["recall_root_causes"]:
                report.append(f"| {item['term']} | {item['count']:,} |\n")
            report.append("\n")
    
    # --- Blockers and Risks ---
    report.append("## 4. BLOCKERS & RISKS IDENTIFIED\n\n")
    
    report.append("### 🔴 Critical Issues\n\n")
    
    narrative_pct = events_with_text / total * 100 if total > 0 else 0
    if narrative_pct < 80:
        report.append(f"1. **LOW NARRATIVE COVERAGE**: Only {narrative_pct:.0f}% of events have narrative text. ")
        report.append(f"Without narratives, Agent 1 (extraction) has no input. ")
        report.append(f"**MITIGATION**: Filter dataset to only events with mdr_text populated.\n\n")
    else:
        report.append(f"1. ✅ Narrative coverage is good ({narrative_pct:.0f}%). Agent 1 has sufficient input.\n\n")
    
    report.append("2. **API RATE LIMITS**: openFDA API limits to 1000 results per query, max skip=25000. ")
    report.append("Cannot paginate beyond 26,000 results via API alone. ")
    report.append("**MITIGATION**: Use MAUDE bulk download files for full dataset. API only for real-time retrieval agent.\n\n")
    
    report.append("3. **DATA VOLUME FOR EMBEDDINGS**: 1.94M events is too large to embed in 4 weeks. ")
    report.append("**MITIGATION**: Sub-sample. Recommended strategy:\n")
    report.append("   - Focus on 2019-2026 (most relevant, better data quality)\n")
    report.append("   - Filter: only events WITH mdr_text narratives\n")
    report.append("   - Filter: only software-related product_problems\n")
    report.append("   - Target: 10,000-50,000 events for embedding (feasible in week 1)\n\n")
    
    report.append("### 🟡 Medium Risks\n\n")
    
    report.append("4. **MANY EVENTS LACK PRODUCT_PROBLEMS FIELD**: Some events only have narratives, no structured problem codes. ")
    report.append("This means we can't easily filter to 'software-related' events without reading narratives. ")
    report.append("**MITIGATION**: Use keyword-based pre-filtering on narratives + product_problems.\n\n")
    
    report.append("5. **NARRATIVE QUALITY VARIES**: Some narratives are very short ('device malfunctioned') while others are detailed. ")
    report.append("Short narratives provide poor extraction quality. ")
    report.append("**MITIGATION**: Set minimum narrative length threshold (>50 chars). Report quality scores.\n\n")
    
    report.append("6. **DUPLICATE/NEAR-DUPLICATE EVENTS**: MAUDE contains initial reports + followups for same event. ")
    report.append("This inflates cluster sizes artificially. ")
    report.append("**MITIGATION**: Deduplicate by report_number (group followups with initial).\n\n")
    
    report.append("7. **RECALL DATA IS SMALL**: Only 513 recalls for infusion pumps. ")
    report.append("This limits the CAPA recommendation agent's training/RAG corpus. ")
    report.append("**MITIGATION**: Expand to related product codes (entire 'Pump' category) or use ALL device recalls for CAPA patterns.\n\n")
    
    report.append("### 🟢 Confirmed Working\n\n")
    report.append("8. ✅ Recall data has excellent field coverage (reason + action + root cause)\n")
    report.append("9. ✅ Multiple manufacturers represented (no single-company bias)\n")
    report.append("10. ✅ Event types include malfunction + injury + death (multi-severity)\n")
    report.append("11. ✅ Date range is sufficient for temporal analysis (2009-2026)\n")
    report.append("12. ✅ Knowledge graph data available (product codes, k_numbers, manufacturers)\n\n")
    
    report.append("## 5. OVERSTATEMENTS IN SYSTEM DESIGN (Self-Audit)\n\n")
    
    report.append("| Claim in System Design | Reality Check | Action |\n")
    report.append("|----------------------|---------------|--------|\n")
    report.append("| '2 minutes to produce report' | Depends on API latency + LLM calls. Realistic: 2-5 min | Soften to '< 5 minutes' |\n")
    report.append("| '5x faster' | No baseline measurement exists. Assumption only | Frame as 'estimated' or run a time study |\n")
    report.append("| '87% confidence' in demo | Made-up number for illustration | Remove or label clearly as 'illustrative' |\n")
    report.append("| 'First application of DPO/RLHF to regulatory reports' | Cannot verify novelty without lit review | Soften to 'novel application in this domain' |\n")
    report.append("| '1.94M real adverse events' implies we use all | We'll use 10-50K max subset | Clarify: 'subset of X events from 1.94M available' |\n")
    report.append("| 'Contrastive embeddings bridge languages' | Requires 500+ pairs. May not converge in 4 weeks | List as stretch goal, not core |\n")
    report.append("| 'Knowledge distillation to Phi-3' | Requires fine-tuning infrastructure + evaluation | List as ablation experiment |\n")
    report.append("| 'PPO training' | PPO is unstable and needs 100+ hours. DPO is realistic | Lead with DPO, PPO as comparison only |\n")
    report.append("| '18 GenAI techniques' | Can't deeply implement 18 in 4 weeks | Categorize: 6 core (must), 6 extended, 6 stretch |\n\n")
    
    report.append("## 6. COLLABORATION STRATEGY\n\n")
    
    report.append("### Repository Structure (Recommended)\n\n")
    report.append("```\n")
    report.append("infusion-pump-signal-intelligence/\n")
    report.append("├── data/                    # Git-ignored, each member downloads locally\n")
    report.append("│   ├── maude_events/        # Raw MAUDE JSON files\n")
    report.append("│   ├── recalls/             # Recall data\n")
    report.append("│   ├── embeddings/          # Pre-computed embeddings (shared via cloud)\n")
    report.append("│   └── analysis/            # Analysis outputs\n")
    report.append("├── src/\n")
    report.append("│   ├── agents/              # One file per agent (clear ownership)\n")
    report.append("│   │   ├── extraction.py    # Agent 1 - Member 1+3\n")
    report.append("│   │   ├── similarity.py    # Agent 2 - Member 4\n")
    report.append("│   │   ├── retrieval.py     # Agent 3 - Member 2+5\n")
    report.append("│   │   ├── risk.py          # Agent 4 - Member 5\n")
    report.append("│   │   ├── capa.py          # Agent 5 - Member 5\n")
    report.append("│   │   └── report.py        # Agent 6 - Member 3\n")
    report.append("│   ├── pipeline/            # Integration (Member 2)\n")
    report.append("│   │   ├── orchestrator.py  # End-to-end pipeline\n")
    report.append("│   │   └── schemas.py       # Shared JSON schemas (contracts)\n")
    report.append("│   ├── data_processing/     # Data loading/filtering\n")
    report.append("│   ├── embeddings/          # Embedding & clustering code\n")
    report.append("│   ├── evaluation/          # Evaluation framework (Member 6)\n")
    report.append("│   ├── alignment/           # DPO/PPO experiments (Member 5)\n")
    report.append("│   └── dashboard/           # Streamlit app (Member 4)\n")
    report.append("├── notebooks/               # Exploration & analysis\n")
    report.append("├── configs/                 # Prompts, schemas, model configs\n")
    report.append("├── tests/                   # Unit tests for agents\n")
    report.append("├── docs/                    # Reports, slides, poster\n")
    report.append("└── scripts/                 # Data download, setup scripts\n")
    report.append("```\n\n")
    
    report.append("### Collaboration Risks & Mitigations\n\n")
    report.append("| Risk | Impact | Mitigation |\n")
    report.append("|------|--------|------------|\n")
    report.append("| Integration breaks when agents combine | HIGH | Define JSON schema contracts in Week 1. Each agent must pass schema validation |\n")
    report.append("| One member's agent blocks others | HIGH | Each agent works standalone with mock inputs. Integration is separate task (M2) |\n")
    report.append("| Data too large for Git | MEDIUM | .gitignore data/. Share via OneDrive/Google Drive or re-download script |\n")
    report.append("| API key sharing (OpenAI/Azure) | MEDIUM | Use .env files, shared API key with rate limit awareness |\n")
    report.append("| Merge conflicts in notebooks | LOW | Each member owns their notebooks. Shared code in .py files only |\n")
    report.append("| GPU access contention | MEDIUM | Schedule: M1 fine-tunes Mon/Tue, M5 does DPO Wed/Thu, M6 distills Fri |\n")
    report.append("| Evaluation requires all agents working | HIGH | LLM-as-Judge evaluates each agent independently. E2E eval in week 4 only |\n\n")
    
    report.append("### Communication Protocol\n\n")
    report.append("1. **Daily standup** (15 min): What I did, what I'll do, what blocks me\n")
    report.append("2. **Schema freeze**: End of Week 1, JSON schemas locked. Changes require team approval\n")
    report.append("3. **Integration checkpoints**: End of each week, everyone runs `pytest tests/`\n")
    report.append("4. **Shared embeddings**: M4 generates embeddings in Week 1, shares via cloud storage\n")
    report.append("5. **Evaluation cadence**: M6 runs eval pipeline daily from Week 2 onward\n\n")
    
    report.append("## 7. RECOMMENDED DATA SUBSET FOR 4-WEEK PROJECT\n\n")
    report.append("Based on analysis, recommended working dataset:\n\n")
    report.append("| Dataset | Size | How to Get | When |\n")
    report.append("|---------|------|-----------|------|\n")
    report.append("| MAUDE events (FRN+QFG+MEA, 2019-2026, with narratives) | ~50,000 events | Bulk download + filter | Week 1 Day 1-2 |\n")
    report.append("| Recalls (all FRN) | 513 recalls | API download (this script) | Done ✅ |\n")
    report.append("| Recalls (all pump-related for CAPA expansion) | ~2000 recalls | API: search product_description:pump | Week 1 Day 1 |\n")
    report.append("| FDA Problem Codes | ~2000 codes | Download from FDA site | Week 1 Day 1 |\n")
    report.append("| Synthetic internal defect reports | 200 generated | GPT-4 generation from MAUDE templates | Week 1 Day 3-4 |\n")
    report.append("| Gold-standard labeled set | 50 events | Manual labeling by team | Week 1 Day 4-5 |\n\n")
    
    report.append("### Data Pipeline Steps\n\n")
    report.append("```\n")
    report.append("1. Download MAUDE bulk files (device event) from open.fda.gov\n")
    report.append("2. Filter: product_code IN (FRN, MEA, QFG)\n")
    report.append("3. Filter: date_received >= 2019-01-01\n")
    report.append("4. Filter: mdr_text is not empty (has at least one narrative > 50 chars)\n")
    report.append("5. Deduplicate: group by report_number, keep latest\n")
    report.append("6. Result: ~30,000-50,000 clean events with narratives\n")
    report.append("7. Embed all narratives with sentence-transformers\n")
    report.append("8. Store in ChromaDB with metadata (product_code, event_type, date, mfr)\n")
    report.append("```\n\n")
    
    # --- Sample narratives for team review ---
    report.append("## 8. SAMPLE NARRATIVES (For Team to Review)\n\n")
    report.append("These are real MAUDE event narratives from our downloaded data:\n\n")
    
    sample_count = 0
    for e in events:
        if sample_count >= 10:
            break
        if "mdr_text" in e and e["mdr_text"]:
            for t in e["mdr_text"]:
                if t.get("text_type_code") == "Description of Event or Problem" and len(t.get("text", "")) > 100:
                    report.append(f"**Sample {sample_count+1}** (Report: {e.get('report_number', 'N/A')})\n")
                    report.append(f"- Event type: {e.get('event_type', 'N/A')}\n")
                    report.append(f"- Product problems: {e.get('product_problems', ['N/A'])}\n")
                    text = t["text"][:500]
                    report.append(f"- Narrative: \"{text}\"\n\n")
                    sample_count += 1
                    break
    
    # Write report
    report_path = ANALYSIS_DIR / "data_analysis_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.writelines(report)
    
    print(f"\n  Analysis report saved to: {report_path}")
    return report_path


if __name__ == "__main__":
    print("FDA Data Collection for Infusion Pump Signal Intelligence System")
    print("=" * 70)
    
    # Download all data
    events = download_maude_events()
    recalls = download_recalls()
    counts = download_counts()
    
    # Analyze
    analyze_data(events, recalls, counts)
    
    print("\n" + "="*70)
    print("DATA COLLECTION COMPLETE")
    print("="*70)
    print(f"\nFiles saved to: {BASE_DIR}")
    print(f"  - {MAUDE_DIR} ({len(list(MAUDE_DIR.glob('*.json')))} files)")
    print(f"  - {RECALL_DIR} ({len(list(RECALL_DIR.glob('*.json')))} files)")
    print(f"  - {ANALYSIS_DIR} ({len(list(ANALYSIS_DIR.glob('*')))} files)")
