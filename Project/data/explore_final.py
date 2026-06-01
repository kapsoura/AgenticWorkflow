"""
Final product selection analysis - get problem counts with tighter date range
and recall quality check.
"""
from urllib.request import urlopen, Request
import json
import time

def fetch(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    resp = urlopen(req, timeout=30)
    return json.loads(resp.read())

# Use very recent date range for counts (smaller dataset = no 500 errors)
print("=" * 70)
print("PRODUCT PROBLEMS - TIGHT DATE RANGE (2024-2026)")
print("=" * 70)

codes = [
    ("LNH", "MRI System"),
    ("JAK", "CT Scanner"),
    ("IYE", "CT X-ray System"),
    ("LLZ", "Ultrasound System"),
    ("MQB", "Molecular Dx Instrument"),
    ("QKO", "PCR Platform"),
    ("GKZ", "Hematology Analyzer"),
    ("QJR", "COVID/Molecular Rapid Test"),
]

for pc, desc in codes:
    url = f"https://api.fda.gov/device/event.json?search=device.device_report_product_code:{pc}+AND+date_received:[20240101+TO+20261231]&count=product_problems"
    try:
        data = fetch(url)
        print(f"\n  {pc} - {desc}:")
        for item in data["results"][:8]:
            print(f"    {item['term']:55s} | {item['count']:>4}")
    except Exception as e:
        print(f"\n  {pc} - {desc}: FAILED ({type(e).__name__})")
    time.sleep(1.5)

# Check recall narratives quality
print("\n\n" + "=" * 70)
print("RECALL NARRATIVE QUALITY CHECK")
print("=" * 70)

for pc, desc in [("LNH", "MRI"), ("JAK", "CT"), ("LLZ", "Ultrasound"), ("MQB", "Mol Dx")]:
    url = f"https://api.fda.gov/device/recall.json?search=product_code:{pc}&limit=3"
    try:
        data = fetch(url)
        print(f"\n  {pc} - {desc} (sample recalls):")
        for r in data["results"][:2]:
            reason = r.get("reason_for_recall", "N/A")[:200]
            root = r.get("root_cause_description", "N/A")
            action = r.get("action", "N/A")[:100]
            firm = r.get("recalling_firm", "N/A")
            print(f"    Firm: {firm}")
            print(f"    Root cause: {root}")
            print(f"    Reason: {reason}...")
            print(f"    Action: {action}...")
            print()
    except Exception as e:
        print(f"  {pc}: FAILED")
    time.sleep(1.5)

# Event type distribution (recent)
print("\n\n" + "=" * 70)
print("EVENT TYPE DISTRIBUTION (2024-2026)")
print("=" * 70)

for pc, desc in [("LNH", "MRI"), ("JAK", "CT"), ("LLZ", "Ultrasound"), ("MQB", "Mol Dx")]:
    url = f"https://api.fda.gov/device/event.json?search=device.device_report_product_code:{pc}+AND+date_received:[20240101+TO+20261231]&count=event_type"
    try:
        data = fetch(url)
        print(f"\n  {pc} - {desc}:")
        for item in data["results"]:
            print(f"    {item['term']:20s} | {item['count']:>5}")
    except:
        print(f"  {pc}: FAILED")
    time.sleep(1)

# Manufacturer distribution
print("\n\n" + "=" * 70)
print("TOP MANUFACTURERS (2024-2026)")
print("=" * 70)

for pc, desc in [("LNH", "MRI"), ("JAK", "CT"), ("LLZ", "Ultrasound")]:
    url = f"https://api.fda.gov/device/event.json?search=device.device_report_product_code:{pc}+AND+date_received:[20240101+TO+20261231]&count=device.manufacturer_d_name.exact"
    try:
        data = fetch(url)
        print(f"\n  {pc} - {desc}:")
        for item in data["results"][:8]:
            print(f"    {item['term']:50s} | {item['count']:>5}")
    except:
        print(f"  {pc}: FAILED")
    time.sleep(1.5)

# Combined totals summary
print("\n\n" + "=" * 70)
print("FINAL SUMMARY: COMBINED DATA VOLUMES")
print("=" * 70)

combos = [
    ("Medical Imaging (MRI+CT+Ultrasound+X-ray)", ["LNH", "JAK", "IYE", "LLZ", "IZL"]),
    ("Molecular Diagnostics (PCR+Mol+Hematology)", ["MQB", "QKO", "GKZ", "QJR", "JJX", "MOS"]),
    ("All Combined", ["LNH", "JAK", "IYE", "LLZ", "IZL", "MQB", "QKO", "GKZ", "QJR", "JJX", "MOS"]),
]

for name, pcs in combos:
    total_events = 0
    total_recalls = 0
    for pc in pcs:
        try:
            url = f"https://api.fda.gov/device/event.json?search=device.device_report_product_code:{pc}&limit=1"
            data = fetch(url)
            total_events += data["meta"]["results"]["total"]
        except:
            pass
        try:
            url = f"https://api.fda.gov/device/recall.json?search=product_code:{pc}&limit=1"
            data = fetch(url)
            total_recalls += data["meta"]["results"]["total"]
        except:
            pass
        time.sleep(0.5)
    print(f"\n  {name}:")
    print(f"    Total Events: {total_events:>10,}")
    print(f"    Total Recalls: {total_recalls:>8,}")
