#!/usr/bin/env python3
"""Debug: find actual PicksWise pick in SelectionInfo_pick divs."""
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

# Find SelectionInfo area with generous context
idx = html.find("SelectionInfo")
if idx >= 0:
    context = html[max(0,idx-2000):idx+3000]
    text = re.sub(r"<[^>]+>", "\n", context)
    text = re.sub(r"\n{2,}", "\n", text).strip()
    # Remove empty lines
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    print("=== AROUND SelectionInfo ===")
    for line in lines:
        print(f"  {line[:150]}")

# Find PredictionDetail area
print("\n\n=== PREDICTION DETAIL STRUCTURE ===")
idx2 = html.find("PredictionDetail")
if idx2 >= 0:
    context2 = html[max(0,idx2-500):idx2+5000]
    # Extract meaningful text blocks
    text2 = re.sub(r"<[^>]+>", "\n", context2)
    lines2 = [l.strip() for l in text2.split("\n") if l.strip() and len(l.strip()) > 2]
    for line in lines2[:50]:
        print(f"  {line[:200]}")

# Also look for the actual prediction text with article body
print("\n\n=== ARTICLE BODY ===")
# PicksWise expert predictions section
expert_idx = html.find("Expert Predictions")
if expert_idx >= 0:
    body = html[expert_idx:expert_idx+10000]
    body_text = re.sub(r"<[^>]+>", "\n", body)
    lines3 = [l.strip() for l in body_text.split("\n") if l.strip() and len(l.strip()) > 5]
    for line in lines3[:40]:
        print(f"  {line[:200]}")
