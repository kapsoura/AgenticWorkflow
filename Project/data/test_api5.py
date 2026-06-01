"""Find correct searchable field for product code."""
from urllib.request import urlopen, Request
import json

urls = [
    # Try the actual field name from the schema
    "https://api.fda.gov/device/event.json?search=device.device_report_product_code:FRN&limit=2",
    "https://api.fda.gov/device/event.json?search=device.device_report_product_code:QFG&limit=2",
    "https://api.fda.gov/device/event.json?search=device.device_report_product_code:MEA&limit=2",
    # Also try openfda nested field  
    "https://api.fda.gov/device/event.json?search=device.openfda.device_name:infusion+pump&limit=2",
]

for url in urls:
    search_part = url.split("search=")[1].split("&")[0]
    print(f"\nSearch: {search_part}")
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urlopen(req, timeout=30)
        data = json.loads(resp.read())
        total = data["meta"]["results"]["total"]
        print(f"  SUCCESS! Total: {total:,}")
        if data["results"]:
            dev = data["results"][0].get("device", [{}])[0]
            print(f"  Brand: {dev.get('brand_name', 'N/A')}")
            print(f"  Product Code: {dev.get('device_report_product_code', 'N/A')}")
    except Exception as e:
        print(f"  FAILED: {e}")

# Now test with date filter
print("\n\n--- WITH DATE FILTER ---")
url = "https://api.fda.gov/device/event.json?search=device.device_report_product_code:FRN+AND+date_received:[20200101+TO+20261231]&limit=2"
print(f"URL: ...product_code:FRN+AND+date_received:[2020-2026]")
try:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    resp = urlopen(req, timeout=30)
    data = json.loads(resp.read())
    total = data["meta"]["results"]["total"]
    print(f"  SUCCESS! Total: {total:,}")
except Exception as e:
    print(f"  FAILED: {e}")
