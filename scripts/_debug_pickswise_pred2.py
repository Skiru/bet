#!/usr/bin/env python3
"""Debug: check PicksWise individual prediction page for pick data."""
import json
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from fetch_with_playwright import fetch

url = "https://www.pickswise.com/soccer/predictions/arsenal-vs-west-ham-united-predictions-512753/"
print(f"Fetching: {url}")
html = fetch(url)
print(f"HTML length: {len(html)}")

nd_match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
if nd_match:
    nd = json.loads(nd_match.group(1))
    state = nd.get("props", {}).get("pageProps", {}).get("initialState", {})
    
    content = state.get("content", {})
    for page_key in content:
        page_data = content[page_key]
        if isinstance(page_data, list) and page_data:
            pd = page_data[0]
            print(f"\nPage: {page_key}")
            
            # Print structure of each key
            for k in pd:
                v = pd[k]
                vtype = type(v).__name__
                if isinstance(v, str):
                    clean = re.sub(r"<[^>]+>", " ", v)
                    clean = re.sub(r"\s+", " ", clean).strip()
                    print(f"  {k} ({vtype}, {len(v)} chars): {clean[:200]}")
                elif isinstance(v, dict):
                    print(f"  {k} ({vtype}): {json.dumps(v)[:300]}")
                elif isinstance(v, list):
                    print(f"  {k} ({vtype}, len={len(v)})")
                    if v and isinstance(v[0], dict):
                        print(f"    first: {json.dumps(v[0])[:300]}")
                    elif v and isinstance(v[0], str):
                        print(f"    first: {v[0][:200]}")
                else:
                    print(f"  {k} ({vtype}): {v}")
