"""Find correct field paths in openFDA device/event API."""
from urllib.request import urlopen, Request
import json

# Get a sample event and inspect the structure
url = "https://api.fda.gov/device/event.json?search=device.generic_name:infusion+pump&limit=1"
req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
resp = urlopen(req, timeout=30)
data = json.loads(resp.read())

event = data["results"][0]

print("TOP LEVEL KEYS:", list(event.keys()))
print("\n--- DEVICE STRUCTURE ---")
if "device" in event:
    for i, dev in enumerate(event["device"][:2]):
        print(f"\nDevice {i}:")
        for k, v in dev.items():
            val_str = str(v)[:80]
            print(f"  {k}: {val_str}")

print("\n--- MDR_TEXT ---")
if "mdr_text" in event:
    for t in event["mdr_text"][:2]:
        print(f"  type: {t.get('text_type_code')}, length: {len(t.get('text',''))}")
        print(f"  text[:100]: {t.get('text','')[:100]}")

print("\n--- PRODUCT PROBLEMS ---")
print(f"  {event.get('product_problems', 'NOT PRESENT')}")

print("\n--- Now testing correct product_code field ---")
# Try count to find the field
urls_count = [
    "https://api.fda.gov/device/event.json?count=device.openfda.device_class",
    "https://api.fda.gov/device/event.json?search=device.generic_name:infusion+pump&count=device.openfda.medical_specialty_description.exact",
]
for url in urls_count:
    print(f"\nCount: {url.split('count=')[1]}")
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urlopen(req, timeout=30)
        data = json.loads(resp.read())
        for item in data["results"][:5]:
            print(f"  {item['term']}: {item['count']:,}")
    except Exception as e:
        print(f"  FAILED: {e}")
