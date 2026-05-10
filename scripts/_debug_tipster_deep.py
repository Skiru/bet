#!/usr/bin/env python3
"""Debug: deep-dive into PicksWise sportPredictions and Sportsgambler divs."""
import json
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from fetch_with_playwright import fetch

def pickswise_predictions():
    print("=== PICKSWISE sportPredictions ===")
    html = fetch("https://www.pickswise.com/soccer/predictions/")
    
    nd_match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not nd_match:
        print("No __NEXT_DATA__ found")
        return
    
    nd = json.loads(nd_match.group(1))
    state = nd.get("props", {}).get("pageProps", {}).get("initialState", {})
    
    sp = state.get("sportPredictions")
    if sp:
        print(f"sportPredictions type: {type(sp).__name__}")
        if isinstance(sp, dict):
            print(f"  keys: {list(sp.keys())[:20]}")
            for k in sp:
                v = sp[k]
                if isinstance(v, list):
                    print(f"  {k}: list[{len(v)}]")
                    if v:
                        print(f"    first: {json.dumps(v[0], indent=2)[:500]}")
                elif isinstance(v, dict):
                    print(f"  {k}: dict keys={list(v.keys())[:15]}")
                    print(f"    sample: {json.dumps(v, indent=2)[:500]}")
                else:
                    print(f"  {k}: {v}")
        elif isinstance(sp, list):
            print(f"  length: {len(sp)}")
            if sp:
                print(f"  first: {json.dumps(sp[0], indent=2)[:600]}")
    
    # Also check content
    content = state.get("content")
    if content:
        print(f"\ncontent type: {type(content).__name__}")
        if isinstance(content, dict):
            print(f"  keys: {list(content.keys())[:20]}")
            for k in list(content.keys())[:5]:
                v = content[k]
                if isinstance(v, list) and v:
                    print(f"  {k}: list[{len(v)}]")
                    if isinstance(v[0], dict):
                        print(f"    first keys: {list(v[0].keys())[:15]}")
                elif isinstance(v, dict):
                    print(f"  {k}: dict keys={list(v.keys())[:10]}")
    
    # Individual prediction page — fetch one to see the structure
    jsonld = nd.get("props", {}).get("pageProps", {}).get("jsonLd", [])
    if jsonld:
        first_url = jsonld[0].get("url", "")
        if first_url:
            full_url = f"https://www.pickswise.com{first_url}"
            print(f"\n=== Fetching individual prediction: {full_url} ===")
            pred_html = fetch(full_url)
            
            nd2 = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', pred_html, re.DOTALL)
            if nd2:
                nd2_data = json.loads(nd2.group(1))
                props2 = nd2_data.get("props", {}).get("pageProps", {})
                print(f"  pageProps keys: {list(props2.keys())[:20]}")
                state2 = props2.get("initialState", {})
                content2 = state2.get("content")
                if content2:
                    print(f"  content type: {type(content2).__name__}")
                    if isinstance(content2, dict):
                        print(f"  content keys: {list(content2.keys())[:20]}")
                        # Look for predictions/picks in content
                        for k in content2:
                            v = content2[k]
                            if isinstance(v, dict):
                                inner = list(v.keys())[:10]
                                # Check for pick-related keys
                                pick_keys = [ik for ik in inner if any(w in ik.lower() for w in ["pick", "predict", "bet", "market", "odds", "tip"])]
                                if pick_keys:
                                    print(f"    {k} pick-keys: {pick_keys}")
                                    for pk in pick_keys:
                                        print(f"      {pk}: {json.dumps(v[pk])[:300]}")
                            elif isinstance(v, list) and v and isinstance(v[0], dict):
                                print(f"    {k}: list[{len(v)}] first_keys={list(v[0].keys())[:10]}")


def sportsgambler_divs():
    print("\n\n=== SPORTSGAMBLER prediction divs ===")
    html = fetch("https://www.sportsgambler.com/predictions/today/")
    
    # Extract all prediction blocks — look for match containers
    # From debug: the divs contain competition name, time, team names
    # Let's find the actual prediction/match container pattern
    
    # Look for match blocks containing "vs"
    vs_blocks = re.findall(
        r'(<(?:div|article|li)[^>]*>(?:(?!<(?:div|article|li)[^>]*>).)*?vs\s*(?:(?!</(?:div|article|li)>).)*?</(?:div|article|li)>)',
        html, re.DOTALL | re.IGNORECASE
    )
    print(f"Blocks with 'vs': {len(vs_blocks)}")
    for block in vs_blocks[:5]:
        clean = re.sub(r"<[^>]+>", " ", block).strip()
        clean = re.sub(r"\s+", " ", clean)
        print(f"  {clean[:200]}")
    
    # Try larger container pattern
    # Look for match cards / fixture blocks
    fixture_pattern = re.findall(
        r'<a[^>]*href="[^"]*prediction[^"]*"[^>]*>(.*?)</a>',
        html, re.DOTALL | re.IGNORECASE
    )
    print(f"\nPrediction links: {len(fixture_pattern)}")
    for fp in fixture_pattern[:10]:
        clean = re.sub(r"<[^>]+>", " ", fp).strip()
        clean = re.sub(r"\s+", " ", clean)
        if clean.strip():
            print(f"  {clean[:200]}")
    
    # Extract prediction URLs
    pred_urls = re.findall(
        r'href="(/[^"]*prediction[^"]*)"',
        html, re.IGNORECASE
    )
    unique_urls = list(dict.fromkeys(pred_urls))
    print(f"\nUnique prediction URLs: {len(unique_urls)}")
    for u in unique_urls[:10]:
        print(f"  {u}")
    
    # Look for specific Sportsgambler structure
    # They show "1X2" predictions with percentages
    pct_blocks = re.findall(r'(\d{1,3})%', html)
    print(f"\nPercentage values found: {len(pct_blocks)}")
    
    # Extract a larger section around a team match
    sample_match = re.search(r'(West Ham.*?Arsenal|Arsenal.*?West Ham)', html, re.DOTALL)
    if sample_match:
        context_start = max(0, sample_match.start() - 500)
        context_end = min(len(html), sample_match.end() + 500)
        context = html[context_start:context_end]
        # Clean for display
        context_clean = re.sub(r"<[^>]+>", "\n", context)
        context_clean = re.sub(r"\n{3,}", "\n\n", context_clean)
        print(f"\nContext around West Ham/Arsenal:")
        print(context_clean[:600])
    
    # Save full HTML for manual inspection
    Path(ROOT_DIR / "betting" / "data" / "_debug_sportsgambler.html").write_text(
        html[:100000], encoding="utf-8"
    )
    print(f"\nSaved first 100KB of HTML")


if __name__ == "__main__":
    pickswise_predictions()
    sportsgambler_divs()
