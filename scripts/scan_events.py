#!/usr/bin/env python3
"""Small scanning framework using the Playwright fetcher.

Usage: python scripts/scan_events.py --urls <url1> <url2> ...

The script will fetch each URL using `fetch_with_playwright.fetch`, save the
raw HTML under `betting/data/<domain>/`, and run the `raw_adapter.parse`
heuristic to produce a quick list of candidate matches.
"""
import sys
import argparse
from pathlib import Path
import json
from datetime import datetime

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE.parent / "betting" / "data"

sys.path.insert(0, str(BASE))
try:
    from fetch_with_playwright import fetch
except Exception:
    # Fallback simple fetcher using requests when Playwright is not available
    import requests

    def fetch(url: str) -> str:
        resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        return resp.text

from adapters import get_adapter


def save_html(domain: str, html: str) -> Path:
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    d = DATA_DIR / domain
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{ts}.html"
    p.write_text(html, encoding="utf-8")
    return p


def domain_from_url(url: str) -> str:
    from urllib.parse import urlparse
    return urlparse(url).netloc.replace("www.", "")


def scan_urls(urls):
    all_extracted = {}
    for url in urls:
        domain = domain_from_url(url)
        print(f"Fetching {url}")
        try:
            html = fetch(url)
        except Exception as e:
            print(f"Failed to fetch {url}: {e}")
            continue
        saved = save_html(domain, html)
        print(f"Saved raw HTML to {saved}")
        adapter = get_adapter(domain)
        try:
            extracted = adapter(html, url)
        except Exception as e:
            print(f"Adapter for {domain} failed, falling back to raw parser: {e}")
            from adapters.raw_adapter import parse as raw_parse
            extracted = raw_parse(html, url)
        all_extracted[url] = extracted
        print(f"Extracted {len(extracted)} candidate match lines from {domain}")

    # write a small JSON summary
    out = DATA_DIR / "scan_summary.json"
    out.write_text(json.dumps(all_extracted, indent=2, ensure_ascii=False), encoding="utf-8")
    # also write per-domain structured outputs (latest)
    for url, items in all_extracted.items():
        domain = domain_from_url(url)
        d = DATA_DIR / domain
        d.mkdir(parents=True, exist_ok=True)
        p = d / "structured_latest.json"
        p.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote summary to {out}")
    return all_extracted


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--urls", nargs="+", help="List of URLs to scan", required=True)
    args = parser.parse_args()
    scan_urls(args.urls)


if __name__ == "__main__":
    main()
