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
    
    # Get content for this page
    content = state.get("content", {})
    for page_key in content:
        page_data = content[page_key]
        if isinstance(page_data, list) and page_data:
            pd = page_data[0]
            print(f"\nPage: {page_key}")
            print(f"Keys: {list(pd.keys())}")
            
            # Check intro
            intro = pd.get("intro", "")
            if intro:
                intro_text = re.sub(r"<[^>]+>", " ", intro)
                intro_text = re.sub(r"\s+", " ", intro_text).strip()
                print(f"\nIntro: {intro_text[:400]}")
            
            # Check content (main body with picks)
            body = pd.get("content", "")
            if body:
                body_text = re.sub(r"<[^>]+>", " ", body)
                body_text = re.sub(r"\s+", " ", body_text).strip()
                print(f"\nContent ({len(body)} chars): {body_text[:800]}")
                
                # Look for pick/market patterns in content
                picks_found = re.findall(
                    r"(?:Best Bet|Our Pick|Prediction|Pick|Tip):\s*([^\n<]+)",
                    body, re.IGNORECASE
                )
                print(f"\nPicks in content: {picks_found[:10]}")
                
                ou_found = re.findall(
                    r"(?:Over|Under)\s+(\d+\.?\d+)\s*(?:goals?|corners?|cards?|fouls?|shots?)?",
                    body, re.IGNORECASE
                )
                print(f"Over/Under in content: {ou_found[:10]}")
            
            # Check FAQs
            faqs = pd.get("faqs", [])
            if faqs:
                print(f"\nFAQs: {len(faqs)}")
                for faq in faqs[:3]:
                    q = faq.get("question", "")
                    a_raw = faq.get("answer", "")
                    a = re.sub(r"<[^>]+>", " ", a_raw)
                    a = re.sub(r"\s+", " ", a).strip()
                    print(f"  Q: {q}")
                    print(f"  A: {a[:200]}")
    
    # Check sportPredictions on individual page
    sp = state.get("sportPredictions", {})
    if sp:
        print(f"\nsportPredictions keys: {list(sp.keys())}")
    
    # Check for prediction-specific data
    for key in state:
        if "predict" in key.lower() or "pick" in key.lower() or "bet" in key.lower():
            print(f"\n{key}: {type(state[key]).__name__}")
            if isinstance(state[key], (dict, list)):
                print(f"  {json.dumps(state[key])[:500]}")
