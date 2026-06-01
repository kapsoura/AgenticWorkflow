"""
Explore FDA product codes for Medical Imaging, Molecular Diagnostics, MRI, and AI/ML devices.
Find which product areas have enough data (events + recalls + narratives) for our project.
"""
from urllib.request import urlopen, Request
import json
import time

def fetch(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    resp = urlopen(req, timeout=30)
    return json.loads(resp.read())

print("=" * 70)
print("EXPLORING PRODUCT AREAS: Medical Imaging / MRI / Molecular Dx / AI")
print("=" * 70)

# Strategy: search by generic_name keywords and see what product codes come up
# Also check event volumes

searches = [
    # MRI
    ("MRI / Magnetic Resonance", "device.generic_name:magnetic+resonance"),
    ("MRI imaging", "device.generic_name:MRI"),
    # CT / X-ray imaging
    ("CT Scanner", "device.generic_name:computed+tomography"),
    ("X-ray digital", "device.generic_name:x-ray+digital"),
    # Molecular diagnostics
    ("PCR / molecular", "device.generic_name:polymerase+chain+reaction"),
    ("Nucleic acid test", "device.generic_name:nucleic+acid"),
    ("Sequencing", "device.generic_name:sequencer"),
    # AI/ML medical devices
    ("AI radiology", "device.generic_name:artificial+intelligence"),
    ("CAD computer aided", "device.generic_name:computer+aided+detection"),
    ("Image analysis software", "device.generic_name:image+analysis"),
    # Ultrasound
    ("Ultrasound imaging", "device.generic_name:ultrasound+imaging"),
    # Digital pathology
    ("Digital pathology", "device.generic_name:digital+pathology"),
    ("Whole slide", "device.generic_name:whole+slide"),
]

print("\n--- ADVERSE EVENT VOLUMES BY SEARCH ---\n")
for name, search in searches:
    url = f"https://api.fda.gov/device/event.json?search={search}&limit=1"
    try:
        data = fetch(url)
        total = data["meta"]["results"]["total"]
        # Get a sample product code
        dev = data["results"][0].get("device", [{}])[0]
        pc = dev.get("device_report_product_code", "N/A")
        brand = dev.get("brand_name", "N/A")[:50]
        print(f"  {name:30s} | Events: {total:>10,} | Sample PC: {pc} | Brand: {brand}")
    except Exception as e:
        print(f"  {name:30s} | FAILED: {e}")
    time.sleep(1)

# Now check specific known product codes for imaging
print("\n\n--- SPECIFIC PRODUCT CODES (IMAGING/DX) ---\n")
product_codes = [
    ("LNH", "MRI System"),
    ("LNI", "MRI Coil"),
    ("JAK", "CT Scanner"),
    ("IZL", "Digital X-ray"),
    ("QAS", "CADe (Computer-Aided Detection)"),
    ("QBS", "CADx (Computer-Aided Diagnosis)"),
    ("QDQ", "Radiological CAD - AI/ML"),
    ("MQB", "Molecular Diagnostics Instrument"),
    ("QKO", "Molecular Dx (PCR platform)"),
    ("QFO", "Next-Gen Sequencing (Dx)"),
    ("OEI", "Picture Archiving (PACS)"),
    ("QIH", "AI/ML SaMD (radiology)"),
    ("LLZ", "Ultrasound imaging system"),
    ("PZZ", "Digital Pathology Whole Slide"),
]

for pc, desc in product_codes:
    url = f"https://api.fda.gov/device/event.json?search=device.device_report_product_code:{pc}&limit=1"
    try:
        data = fetch(url)
        total = data["meta"]["results"]["total"]
        print(f"  {pc} ({desc:40s}) | Events: {total:>8,}")
    except Exception as e:
        print(f"  {pc} ({desc:40s}) | No data or error")
    time.sleep(0.8)

# Check recalls for same codes
print("\n\n--- RECALL VOLUMES ---\n")
for pc, desc in product_codes:
    url = f"https://api.fda.gov/device/recall.json?search=product_code:{pc}&limit=1"
    try:
        data = fetch(url)
        total = data["meta"]["results"]["total"]
        print(f"  {pc} ({desc:40s}) | Recalls: {total:>5}")
    except Exception as e:
        print(f"  {pc} ({desc:40s}) | No recalls")
    time.sleep(0.8)
