"""
Deep dive into best candidates for medical imaging / molecular dx project.
Check narrative availability, product problems, and related codes.
"""
from urllib.request import urlopen, Request
import json
import time

def fetch(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    resp = urlopen(req, timeout=30)
    return json.loads(resp.read())

# Best candidates from exploration:
# LNH (MRI) - 4,598 events + 699 recalls - EXCELLENT recall data
# JAK (CT Scanner) - 5,182 events + 857 recalls - EXCELLENT recall data
# LLZ (Ultrasound) - 19,482 events + 548 recalls - GREAT volume
# MQB (Molecular Dx) - 1,274 events + 194 recalls - Good
# QKO (PCR/Molecular) - 1,550 events + 31 recalls
# IZL (Digital X-ray) - 914 events + 167 recalls

# Let's check related codes to expand our data pool
print("=" * 70)
print("DEEP DIVE: Medical Imaging + Molecular Diagnostics Combined")
print("=" * 70)

# Check more imaging/radiology codes
more_codes = [
    ("IYE", "CT X-ray system"),
    ("JAA", "X-ray system, general"),
    ("IYO", "Fluoroscopic X-ray"),
    ("MYN", "Nuclear medicine (PET/SPECT)"),
    ("NQI", "Nuclear imaging"),
    ("DTK", "CT accessories"),
    ("KPG", "Image processing radiological"),
    ("LMD", "MRI accessories"),
    ("OOT", "Radiotherapy planning software"),
    ("QMT", "CADx AI imaging"),
    ("QPN", "AI/ML imaging analysis"),  
    ("NUP", "Ultrasound transducer"),
    ("QJR", "COVID/molecular rapid test"),
    ("QAS", "Genetic sequencing system"),
    ("NMB", "Chemistry analyzer"),
    ("JJX", "Clinical chemistry system"),
    ("GKZ", "Hematology analyzer"),
    ("CDC", "Immunoassay system"),
    ("OTL", "Mass spectrometer clinical"),
    ("MOS", "Real-time PCR"),
]

print("\n--- ADDITIONAL PRODUCT CODES ---\n")
for pc, desc in more_codes:
    url = f"https://api.fda.gov/device/event.json?search=device.device_report_product_code:{pc}&limit=1"
    try:
        data = fetch(url)
        total = data["meta"]["results"]["total"]
        # Also check recalls quickly
        rurl = f"https://api.fda.gov/device/recall.json?search=product_code:{pc}&limit=1"
        try:
            rdata = fetch(rurl)
            rtotal = rdata["meta"]["results"]["total"]
        except:
            rtotal = 0
        print(f"  {pc} ({desc:35s}) | Events: {total:>8,} | Recalls: {rtotal:>5}")
    except Exception as e:
        print(f"  {pc} ({desc:35s}) | No data")
    time.sleep(0.8)

# Now check sample events for our top picks to verify narrative quality
print("\n\n--- NARRATIVE QUALITY CHECK (Sample from top picks) ---\n")

top_picks = [
    ("LNH", "MRI System"),
    ("JAK", "CT Scanner"),
    ("LLZ", "Ultrasound System"),
    ("MQB", "Molecular Dx Instrument"),
]

for pc, desc in top_picks:
    url = f"https://api.fda.gov/device/event.json?search=device.device_report_product_code:{pc}&limit=5"
    data = fetch(url)
    events = data["results"]
    
    has_narrative = 0
    has_problems = 0
    sample_text = ""
    sample_problems = []
    
    for e in events:
        if "mdr_text" in e and e["mdr_text"]:
            for t in e["mdr_text"]:
                if t.get("text", "").strip() and len(t["text"]) > 30:
                    has_narrative += 1
                    if not sample_text:
                        sample_text = t["text"][:200]
                    break
        if "product_problems" in e and e["product_problems"]:
            has_problems += 1
            sample_problems.extend(e["product_problems"][:2])
    
    print(f"\n  {pc} - {desc}:")
    print(f"    Narratives in sample: {has_narrative}/5")
    print(f"    Product problems: {has_problems}/5")
    print(f"    Sample problems: {list(set(sample_problems))[:5]}")
    print(f"    Sample narrative: \"{sample_text[:150]}...\"")
    time.sleep(1)

# Check product_problems distribution for our picks
print("\n\n--- PRODUCT PROBLEMS DISTRIBUTION (Top Picks) ---\n")
for pc, desc in top_picks:
    url = f"https://api.fda.gov/device/event.json?search=device.device_report_product_code:{pc}+AND+date_received:[20200101+TO+20261231]&count=product_problems"
    try:
        data = fetch(url)
        print(f"\n  {pc} - {desc} (Top 10 problems, 2020-2026):")
        for item in data["results"][:10]:
            print(f"    {item['term']:50s} | {item['count']:>5}")
    except Exception as e:
        print(f"  {pc} - {desc}: count query failed ({e})")
    time.sleep(1.5)
