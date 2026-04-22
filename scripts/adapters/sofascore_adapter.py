"""Site adapter for SofaScore (best-effort).

Currently uses the generic raw adapter as a fallback; kept as a separate
module for future site-specific parsing improvements.
"""
from typing import List, Dict
from bs4 import BeautifulSoup
import re
from .raw_adapter import parse as raw_parse


def parse(html: str, url: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")

    results = []
    # Require spaces around separators to avoid splitting team names on "v"
    vs_re = re.compile(r"(.+?)\s+(?:vs\.?|v\.)\s+(.+)", re.I)
    dash_re = re.compile(r"(.{3,}?)\s+[-–—]\s+(.{3,})")

    # SofaScore uses structured event cards; try to find elements mentioning vs or dash
    for el in soup.find_all(True, class_=lambda c: c and re.search(r"event|match|fixture|card|row", " ".join(c) if isinstance(c, (list, tuple)) else c, re.I)):
        text = (el.get_text(separator=" ") or "").strip()
        if not text or len(text) > 300:
            continue
        m = vs_re.search(text) or dash_re.search(text)
        if m:
            home = m.group(1).strip()
            away = m.group(2).strip()
            if len(home) < 2 or len(away) < 2:
                continue
            time_m = re.search(r"\b(\d{1,2}:\d{2})\b", text)
            time = time_m.group(1) if time_m else None
            results.append({"home": home, "away": away, "time": time, "source_url": url, "raw": text})

    if results:
        # dedupe
        seen = set()
        dedup = []
        for r in results:
            key = (r.get("home"), r.get("away"), r.get("time"))
            if key in seen:
                continue
            seen.add(key)
            dedup.append(r)
        return dedup

    return raw_parse(html, url)
