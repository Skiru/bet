#!/usr/bin/env python3
"""Debug: check PicksWise rendered HTML for actual picks."""
import json
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from fetch_with_playwright import fetch

url = "https://www.pickswise.com/soccer/predictions/arsenal-vs-west-ham-united-predictions-512753/"
html = fetch(url)

# Find prediction-specific classes
classes = re.findall(r'class="([^"]*)"', html)
pred_classes = [c for c in classes if any(w in c.lower() for w in ["pick", "best", "bet", "odds", "market", "predict"])]
from collections import Counter
cc = Counter(pred_classes)
print("Prediction classes:")
for cls, cnt in cc.most_common(20):
    print(f"  {cnt}x  {cls}")

# Look for structured pick sections
# PicksWise typically has sections like "Best Bet", "Pick", etc.
text = re.sub(r"<[^>]+>", "\n", html)
text = re.sub(r"\n{3,}", "\n\n", text)

# Find "Best Bet" or "Pick" sections
for keyword in ["Best Bet", "Our Pick", "Prediction:", "Pick:", "Best bet", "BTTS", "Both Teams", "Over 2.5", "Under 2.5", "Correct Score", "corners", "cards"]:
    idx = text.find(keyword)
    if idx >= 0:
        snippet = text[max(0,idx-100):idx+300].strip()
        snippet = re.sub(r"\n{2,}", "\n", snippet)
        print(f"\n=== Found '{keyword}' at pos {idx} ===")
        print(snippet[:300])

# Look for structured pick data in rendered page
# PicksWise renders picks in specific div structures
pick_divs = re.findall(
    r'<div[^>]*class="[^"]*(?:pick|bestbet|prediction)[^"]*"[^>]*>(.*?)</div>',
    html, re.DOTALL | re.IGNORECASE
)
print(f"\n\nPick divs: {len(pick_divs)}")
for pd in pick_divs[:5]:
    clean = re.sub(r"<[^>]+>", " ", pd).strip()
    clean = re.sub(r"\s+", " ", clean)
    print(f"  {clean[:200]}")

# Look for h2/h3 headers with pick info
headers = re.findall(r"<h[23][^>]*>(.*?)</h[23]>", html, re.DOTALL)
pick_headers = [h for h in headers if any(w in h.lower() for w in ["pick", "prediction", "best bet", "over", "under", "btts", "corner", "card"])]
print(f"\nPick-related headers: {len(pick_headers)}")
for h in pick_headers[:10]:
    clean = re.sub(r"<[^>]+>", " ", h).strip()
    print(f"  {clean[:150]}")
