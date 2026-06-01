"""Quick test to find correct openFDA API URL format."""
from urllib.request import urlopen, Request
import json

# Test different URL formats
urls = [
    # Format 1: no quotes around product code
    "https://api.fda.gov/device/event.json?search=device.product_code:FRN&limit=2",
    # Format 2: quoted product code
    'https://api.fda.gov/device/event.json?search=device.product_code:"FRN"&limit=2',
    # Format 3: with date filter
    'https://api.fda.gov/device/event.json?search=device.product_code:"FRN"+AND+date_received:[20200101+TO+20261231]&limit=2',
]

for i, url in enumerate(urls):
    print(f"\nTest {i+1}: {url[:80]}...")
    try:
        req = Request(url, headers={"User-Agent": "Test/1.0"})
        resp = urlopen(req, timeout=30)
        data = json.loads(resp.read())
        total = data["meta"]["results"]["total"]
        print(f"  SUCCESS! Total results: {total:,}")
    except Exception as e:
        print(f"  FAILED: {e}")
