#!/usr/bin/env python3
"""Debug script — examine tipster site HTML structures."""

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from fetch_with_playwright import fetch


def analyze_html(url, name):
    print(f"\n{'='*60}")
    print(f"Analyzing: {name} — {url}")
    print(f"{'='*60}")
    
    html = fetch(url)
    print(f"HTML length: {len(html)}")
    
    # JSON-LD structured data
    ld_matches = re.findall(
        r"<script[^>]*type=['\"]application/ld\+json['\"][^>]*>(.*?)</script>",
        html, re.DOTALL
    )
    print(f"JSON-LD blocks: {len(ld_matches)}")
    for i, ld in enumerate(ld_matches[:3]):
        try:
            d = json.loads(ld)
            print(f"  LD #{i}: {json.dumps(d, indent=2)[:500]}")
        except Exception:
            pass
    
    # Prediction-related CSS classes
    classes = re.findall(
        r"class=['\"]([^'\"]*(?:predict|pick|tip|bet|match|event|fixture)[^'\"]*)['\"]",
        html, re.IGNORECASE
    )
    cc = Counter(classes)
    print(f"\nPrediction-related classes ({len(cc)}):")
    for cls, cnt in cc.most_common(20):
        print(f"  {cnt}x  {cls}")
    
    # Data attributes
    data_attrs = re.findall(
        r"data-(?:match|event|fixture|prediction|pick|team|sport)[^=]*=['\"]([^'\"]*)['\"]",
        html, re.IGNORECASE
    )
    print(f"\nData attributes: {len(data_attrs)}")
    for da in data_attrs[:15]:
        print(f"  {da[:100]}")
    
    # Look for Over/Under patterns in raw HTML (before stripping)
    ou_in_html = re.findall(
        r"(?:over|under|O|U)\s*(\d+\.?\d*)",
        html, re.IGNORECASE
    )[:20]
    print(f"\nOver/Under values found: {len(ou_in_html)}")
    print(f"  Samples: {ou_in_html[:15]}")
    
    # Look for structured prediction blocks
    # Check for Next.js __NEXT_DATA__
    next_data = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if next_data:
        try:
            nd = json.loads(next_data.group(1))
            # Find predictions in the data
            props = nd.get("props", {}).get("pageProps", {})
            print(f"\n__NEXT_DATA__ pageProps keys: {list(props.keys())[:20]}")
            # Print first level of interesting data
            for key in props:
                val = props[key]
                if isinstance(val, list) and len(val) > 0:
                    print(f"  {key}: list[{len(val)}] first={json.dumps(val[0], indent=2)[:300]}")
                elif isinstance(val, dict):
                    print(f"  {key}: dict keys={list(val.keys())[:10]}")
        except Exception as e:
            print(f"  __NEXT_DATA__ parse failed: {e}")
    
    # Save raw HTML for manual inspection
    out_path = ROOT_DIR / "betting" / "data" / f"_debug_{name.lower()}.html"
    out_path.write_text(html[:50000], encoding="utf-8")
    print(f"\nSaved first 50KB to {out_path.name}")
    
    return html


if __name__ == "__main__":
    sites = [
        ("https://www.pickswise.com/soccer/predictions/", "PicksWise"),
        ("https://www.sportsgambler.com/predictions/today/", "Sportsgambler"),
        ("https://www.betideas.com/tips/football", "BetIdeas"),
    ]
    
    for url, name in sites:
        try:
            analyze_html(url, name)
        except Exception as e:
            print(f"FAILED {name}: {e}")
