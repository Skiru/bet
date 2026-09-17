import os
import json
import time
from concurrent.futures import ThreadPoolExecutor
from curl_cffi import requests

BASE_URL = "https://api.sofascore.com/api/v1"
EVIDENCE_DIR = "docs/sofascore-api/evidence"

def make_request(path, method="GET", params=None, save_as=None):
    s = requests.Session(impersonate="chrome124")
    s.headers.update({
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.sofascore.com/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    })
    
    url = f"{BASE_URL}{path}"
    print(f"Requesting: {url}")
    
    start = time.time()
    try:
        if method == "GET":
            r = s.get(url, params=params, timeout=15)
        elif method == "POST":
            r = s.post(url, json=params, timeout=15)
            
        elapsed = time.time() - start
        
        try:
            resp_json = r.json()
        except:
            resp_json = r.text
            
        evidence = {
            "request": {
                "method": method,
                "url": r.url,
                "headers": dict(r.request.headers),
                "params": params
            },
            "response": {
                "status_code": r.status_code,
                "headers": dict(r.headers),
                "body": resp_json,
                "elapsed_seconds": elapsed
            }
        }
        
        if save_as:
            filepath = os.path.join(EVIDENCE_DIR, save_as)
            with open(filepath, "w") as f:
                json.dump(evidence, f, indent=2)
                
        return r.status_code, resp_json
    except Exception as e:
        print(f"Error: {e}")
        return 0, str(e)

def test_rate_limit(path, num_requests=300, max_workers=20):
    print(f"Starting rate limit test: {num_requests} requests with {max_workers} workers to {path}")
    
    s = requests.Session(impersonate="chrome124")
    s.headers.update({
        "Accept": "application/json",
        "Referer": "https://www.sofascore.com/",
    })
    url = f"{BASE_URL}{path}"
    
    results = {"200": 0, "403": 0, "429": 0, "other": 0, "errors": 0}
    
    def fetch(_):
        try:
            r = s.get(url, timeout=10)
            if r.status_code == 200:
                results["200"] += 1
            elif r.status_code == 403:
                results["403"] += 1
            elif r.status_code == 429:
                results["429"] += 1
            else:
                results["other"] += 1
        except Exception:
            results["errors"] += 1

    start_time = time.time()
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        list(executor.map(fetch, range(num_requests)))
        
    duration = time.time() - start_time
    print(f"Completed in {duration:.2f} seconds. Rate: {num_requests/duration:.2f} req/s")
    print(f"Results: {results}")

if __name__ == '__main__':
    pass
