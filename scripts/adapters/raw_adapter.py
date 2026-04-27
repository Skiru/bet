"""A very small heuristic adapter that extracts match-like lines from HTML.

This is intentionally lightweight — it finds anchors or textual patterns that look
like "Team A - Team B" or "Team A vs Team B" and nearby time stamps. It's a
starting point and can be replaced with site-specific parsers later.
"""
from typing import List, Dict
from bs4 import BeautifulSoup
import re


TIME_RE = re.compile(r"\b(\d{1,2}:\d{2})\b")
# Require spaces around separators to avoid splitting team names like "Caravel" on "v"
# or times like "21:30" on ":"
VS_RE = re.compile(r"(.+?)\s+(?:vs\.?|v\.)\s+(.+)", re.I)
DASH_RE = re.compile(r"(.{3,}?)\s+[-–—]\s+(.{3,})")


def parse(html: str, url: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []

    # look for anchor/text that contains vs-like patterns
    for a in soup.find_all(["a", "div", "span", "p", "li"]):
        text = (a.get_text(separator=" ") or "").strip()
        if not text or len(text) > 200:
            continue
        m = VS_RE.search(text) or DASH_RE.search(text)
        if m:
            home = m.group(1).strip()
            away = m.group(2).strip()
            # Skip if home/away look like times or numbers
            if re.match(r"^\d{1,2}$", home) or re.match(r"^\d{1,2}$", away):
                continue
            if len(home) < 2 or len(away) < 2:
                continue
            # try to find time nearby (in parent or previous sibling)
            context = " ".join([s.get_text(separator=" ").strip() for s in a.parents][:2])
            time_m = TIME_RE.search(text) or TIME_RE.search(context)
            time = time_m.group(1) if time_m else None
            results.append({"home": home, "away": away, "time": time, "source_url": url, "raw": text})

    # deduplicate by (home,away,time)
    from adapters import dedup_results
    return dedup_results(results)
