#!/usr/bin/env python3
"""Smoke test for the Playwright fetcher.

Fetches a set of Tier-A/Tier-B homepages and writes a JSON summary to
`betting/data/playwright_smoke.json`. Also relies on the fetcher to save
HTML snapshots under `betting/data/<domain>/`.
"""
import json
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE.parent / "betting" / "data"

try:
    from fetch_with_playwright import fetch
except Exception as e:
    print("Playwright fetcher import failed:", e)
    raise

URLS = [
    "https://www.flashscore.com/",
    "https://www.sofascore.com/",
    "https://www.betclic.pl/",
    "https://www.oddsportal.com/"
]


def run():
    results = []
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for url in URLS:
        try:
            html = fetch(url)
            results.append({"url": url, "ok": True, "length": len(html)})
        except Exception as e:
            results.append({"url": url, "ok": False, "error": str(e)})

    out = DATA_DIR / "playwright_smoke.json"
    meta = {"run_at": datetime.utcnow().isoformat() + "Z", "results": results}
    out.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"WROTE {out}")


if __name__ == "__main__":
    run()
