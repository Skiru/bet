#!/usr/bin/env python3
"""Debug: check BetIdeas, Tips180, BettingClosed HTML structure."""
import json
import re
import sys
from pathlib import Path
from collections import Counter

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))
from fetch_with_playwright import fetch

def check_site(url, name):
    print(f"\n=== {name}: {url} ===")
    html = fetch(url)
    print(f"HTML length: {len(html)}")
    
    # Strip tags and look for "vs" patterns
    text = re.sub(r'<(?:br|hr|/p|/div|/li|/tr)[^>]*>', '\n', html, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'[ \t]+', ' ', text)
    
    vs_matches = re.findall(
        r'([A-ZÀ-Ž][A-Za-zÀ-ž\.]+(?:\s+[A-Za-zÀ-ž\.]+){0,4}?)'
        r'\s+(?:vs\.?|v\.?)\s+'
        r'([A-ZÀ-Ž][A-Za-zÀ-ž\.]+(?:\s+[A-Za-zÀ-ž\.]+){0,4})',
        text
    )
    print(f"'vs' matches: {len(vs_matches)}")
    for h, a in vs_matches[:10]:
        print(f"  {h} vs {a}")
    
    # Look for " - " patterns (common in BetIdeas/BettingClosed)
    dash_matches = re.findall(
        r'([A-ZÀ-Ž][A-Za-zÀ-ž\.]+(?:\s+[A-Za-zÀ-ž\.]+){0,4}?)'
        r'\s+[-–—]\s+'
        r'([A-ZÀ-Ž][A-Za-zÀ-ž\.]+(?:\s+[A-Za-zÀ-ž\.]+){0,4})',
        text
    )
    print(f"' - ' matches: {len(dash_matches)}")
    for h, a in dash_matches[:10]:
        print(f"  {h} - {a}")
    
    # Look for prediction classes
    classes = re.findall(r'class="([^"]*)"', html)
    tip_classes = [c for c in classes if any(w in c.lower() for w in ["tip", "pick", "predict", "bet", "match", "fixture"])]
    cc = Counter(tip_classes)
    print(f"Tip classes: {len(cc)}")
    for cls, cnt in cc.most_common(10):
        print(f"  {cnt}x  {cls}")
    
    # Look for links to individual predictions
    pred_links = re.findall(r'href="([^"]*(?:tip|predict|pick|match|fixture)[^"]*)"', html, re.IGNORECASE)
    unique_links = list(dict.fromkeys(pred_links))
    print(f"Prediction links: {len(unique_links)}")
    for link in unique_links[:10]:
        print(f"  {link[:100]}")

sites = [
    ("https://www.betideas.com/tips/football", "BetIdeas"),
    ("https://tips180.com/", "Tips180"),
    ("https://www.bettingclosed.com/", "BettingClosed"),
]

for url, name in sites:
    try:
        check_site(url, name)
    except Exception as e:
        print(f"FAILED {name}: {e}")
