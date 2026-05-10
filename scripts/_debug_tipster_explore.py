#!/usr/bin/env python3
"""Debug: explore PicksWise and Sportsgambler HTML structures for parsers."""
import json
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from fetch_with_playwright import fetch

def explore_pickswise():
    print("=== PICKSWISE ===")
    html = fetch("https://www.pickswise.com/soccer/predictions/")
    
    # JSON-LD SportsEvents — these have real match data
    ld_blocks = re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL
    )
    events = []
    for block in ld_blocks:
        try:
            d = json.loads(block)
            if d.get("@type") == "SportsEvent":
                events.append(d)
        except Exception:
            pass
    
    print(f"SportsEvent JSON-LD blocks: {len(events)}")
    for ev in events[:5]:
        print(f"  {ev.get('name')} | {ev.get('startDate')} | {ev.get('url','')}")
    
    # Now look for actual prediction content in the HTML
    # PicksWise uses CSS modules: EventInfo_*, EventGrid_*
    # Extract text between EventInfo blocks
    text = re.sub(r"<[^>]+>", "\n", html)
    text = re.sub(r"\n{3,}", "\n\n", text)
    
    # Look for pick-related patterns
    pick_patterns = [
        r"(Best Bet|Our Pick|Prediction|Pick):\s*(.+)",
        r"(Over|Under)\s+(\d+\.?\d+)",
        r"(BTTS|Both Teams to Score|Draw No Bet|Double Chance)",
        r"(Corners?|Cards?|Fouls?|Shots?)\s+(Over|Under)\s+(\d+\.?\d+)",
    ]
    
    for pattern in pick_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            print(f"\n  Pattern '{pattern[:40]}': {len(matches)} matches")
            for m in matches[:5]:
                print(f"    {m}")
    
    # Check for EventInfo detail divs with market info
    detail_blocks = re.findall(
        r'class="EventInfo_details[^"]*"[^>]*>(.*?)</div>',
        html, re.DOTALL
    )
    print(f"\nEventInfo_details blocks: {len(detail_blocks)}")
    for db in detail_blocks[:5]:
        clean = re.sub(r"<[^>]+>", " ", db).strip()
        print(f"  {clean[:150]}")
    
    # Look for __NEXT_DATA__ content deeper 
    nd_match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if nd_match:
        nd = json.loads(nd_match.group(1))
        state = nd.get("props", {}).get("pageProps", {}).get("initialState", {})
        extra = state.get("extraData", {})
        print(f"\ninitialState keys: {list(state.keys())}")
        if extra:
            print(f"extraData keys: {list(extra.keys())[:20]}")
            for k in extra:
                v = extra[k]
                if isinstance(v, list) and len(v) > 0:
                    print(f"  {k}: list[{len(v)}]")
                    print(f"    first: {json.dumps(v[0])[:300]}")
                elif isinstance(v, dict):
                    print(f"  {k}: dict keys={list(v.keys())[:10]}")


def explore_sportsgambler():
    print("\n\n=== SPORTSGAMBLER ===")
    html = fetch("https://www.sportsgambler.com/predictions/today/")
    
    # Look for JSON-LD SportsEvents
    ld_blocks = re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL
    )
    sports_events = []
    for block in ld_blocks:
        try:
            d = json.loads(block)
            if isinstance(d, dict) and d.get("@graph"):
                for item in d["@graph"]:
                    if item.get("@type") == "SportsEvent":
                        sports_events.append(item)
            elif isinstance(d, dict) and d.get("@type") == "SportsEvent":
                sports_events.append(d)
        except Exception:
            pass
    
    print(f"SportsEvent from JSON-LD: {len(sports_events)}")
    for ev in sports_events[:5]:
        print(f"  {ev.get('name')} | {ev.get('startDate')}")
    
    # Look for prediction classes
    pred_divs = re.findall(
        r'class="[^"]*(?:prediction|pick|tip|match-card|fixture)[^"]*"[^>]*>(.*?)</(?:div|article|section)>',
        html, re.DOTALL | re.IGNORECASE
    )
    print(f"\nPrediction divs: {len(pred_divs)}")
    for pd in pred_divs[:3]:
        clean = re.sub(r"<[^>]+>", " ", pd).strip()
        print(f"  {clean[:200]}")
    
    # Check for structured prediction data (Sportsgambler-specific)
    # Often uses: data-competition, data-home, data-away
    data_attrs = re.findall(
        r'(data-[a-z-]+)="([^"]*)"',
        html, re.IGNORECASE
    )
    attr_names = set()
    for name, val in data_attrs:
        attr_names.add(name)
    print(f"\nData attributes found: {sorted(attr_names)}")
    
    # Find match blocks with team names and predictions
    # Sportsgambler typically has prediction tables or cards
    table_rows = re.findall(
        r"<tr[^>]*>(.*?)</tr>",
        html, re.DOTALL
    )
    print(f"\nTable rows: {len(table_rows)}")
    for tr in table_rows[:5]:
        clean = re.sub(r"<[^>]+>", " | ", tr).strip()
        clean = re.sub(r"\s+", " ", clean)
        if "vs" in clean.lower() or len(clean) > 50:
            print(f"  {clean[:200]}")


def explore_betideas():
    print("\n\n=== BETIDEAS ===")
    html = fetch("https://www.betideas.com/tips/football")
    
    # Look for JSON-LD
    ld_blocks = re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL
    )
    print(f"JSON-LD blocks: {len(ld_blocks)}")
    
    # Look for __NEXT_DATA__
    nd_match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if nd_match:
        nd = json.loads(nd_match.group(1))
        props = nd.get("props", {}).get("pageProps", {})
        print(f"__NEXT_DATA__ pageProps keys: {list(props.keys())[:20]}")
        for k in props:
            v = props[k]
            if isinstance(v, list) and len(v) > 0:
                print(f"  {k}: list[{len(v)}]")
                # Show first item structure
                if isinstance(v[0], dict):
                    print(f"    keys: {list(v[0].keys())[:15]}")
                    print(f"    first: {json.dumps(v[0])[:400]}")
            elif isinstance(v, dict) and v:
                print(f"  {k}: dict keys={list(v.keys())[:15]}")
    else:
        # Look for NUXT or other framework data
        nuxt_match = re.search(r"window\.__NUXT__\s*=\s*(\{.*?\});", html, re.DOTALL)
        if nuxt_match:
            print("Found __NUXT__ data")
        
        # Look for any inline JSON with tip data
        json_blocks = re.findall(r'(\{[^}]*"tip[^}]*\})', html[:5000])
        print(f"Inline JSON with 'tip': {len(json_blocks)}")
    
    # Check HTML structure
    classes = re.findall(r'class="([^"]*)"', html)
    tip_classes = [c for c in classes if any(w in c.lower() for w in ["tip", "pick", "predict", "bet"])]
    from collections import Counter
    cc = Counter(tip_classes)
    print(f"\nTip-related classes: {len(cc)}")
    for cls, cnt in cc.most_common(15):
        print(f"  {cnt}x  {cls}")
    
    # Extract a sample of the HTML around prediction areas
    # BetIdeas typically shows tips in card format
    cards = re.findall(
        r'<(?:div|article)[^>]*class="[^"]*(?:tip|card|match|fixture)[^"]*"[^>]*>(.*?)</(?:div|article)>',
        html, re.DOTALL | re.IGNORECASE
    )
    print(f"\nTip/card blocks: {len(cards)}")
    for card in cards[:3]:
        clean = re.sub(r"<[^>]+>", " ", card).strip()
        clean = re.sub(r"\s+", " ", clean)
        print(f"  {clean[:200]}")


if __name__ == "__main__":
    explore_pickswise()
    explore_sportsgambler()
    explore_betideas()
