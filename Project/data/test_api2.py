"""Test openFDA API connectivity and correct endpoint."""
from urllib.request import urlopen, Request
import json

# Test basic connectivity to openFDA
urls = [
    # Basic endpoint test
    "https://api.fda.gov/device/event.json?limit=1",
    # Recall endpoint
    "https://api.fda.gov/device/recall.json?limit=1",
    # Drug endpoint (known working)
    "https://api.fda.gov/drug/event.json?limit=1",
    # Try without json extension
    "https://api.fda.gov/device/event?limit=1",
]

for i, url in enumerate(urls):
    print(f"\nTest {i+1}: {url}")
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urlopen(req, timeout=30)
        data = json.loads(resp.read())
        if "meta" in data:
            print(f"  SUCCESS! Total: {data['meta']['results']['total']:,}")
        else:
            print(f"  Got response: {list(data.keys())}")
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")
