"""Test openFDA search parameter syntax."""
from urllib.request import urlopen, Request
from urllib.parse import quote
import json

# The issue is how the search parameter is encoded
# openFDA docs: search=field:value
# Spaces in values need quotes, special chars need URL encoding

urls = [
    # Try with proper URL encoding of the search param
    "https://api.fda.gov/device/event.json?search=device.product_code.exact:FRN&limit=2",
    "https://api.fda.gov/device/event.json?search=device.product_code:FRN&limit=2",
    'https://api.fda.gov/device/event.json?search=device.product_code.exact:"FRN"&limit=2',
    # Try percent-encoding the quotes
    "https://api.fda.gov/device/event.json?search=device.product_code.exact:%22FRN%22&limit=2",
    # Try with openfda field
    "https://api.fda.gov/device/event.json?search=device.openfda.device_name:infusion&limit=2",
    # Simple generic_name search
    "https://api.fda.gov/device/event.json?search=device.generic_name:infusion&limit=2",
]

for i, url in enumerate(urls):
    print(f"\nTest {i+1}: {url[:100]}...")
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urlopen(req, timeout=30)
        data = json.loads(resp.read())
        total = data["meta"]["results"]["total"]
        print(f"  SUCCESS! Total results: {total:,}")
        if data.get("results"):
            r = data["results"][0]
            devs = r.get("device", [{}])
            if devs:
                print(f"  Sample device: {devs[0].get('generic_name', 'N/A')[:60]}")
                print(f"  Product code: {devs[0].get('product_code', 'N/A')}")
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")
