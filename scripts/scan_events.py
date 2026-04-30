#!/usr/bin/env python3
"""Small scanning framework using the Playwright fetcher.

Usage: python scripts/scan_events.py --urls <url1> <url2> ...

The script will fetch each URL using `fetch_with_playwright.fetch`, save the
raw HTML under `betting/data/<domain>/`, and run the `raw_adapter.parse`
heuristic to produce a quick list of candidate matches.
"""
import sys
import argparse
import re
from pathlib import Path
import json
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE.parent / "betting" / "data"

FETCH_DELAY_SECONDS = 3  # delay between fetches to avoid anti-bot triggers

SPORT_URL_PATTERNS = {
    "tennis": ["/tennis", "/tenis", "tennisabstract", "tennisexplorer"],
    "basketball": ["/basketball", "/koszykowka", "/nba", "teamrankings.com", "basketball-reference"],
    "hockey": ["/hockey", "/hokej", "/nhl", "hockey-reference"],
    "baseball": ["/baseball", "/mlb", "baseballsavant"],
    "football": ["/football", "/pilka-nozna", "/soccer", "forebet", "predictz", "betideas", "soccerstats", "totalcorner", "soccerway", "aiscore", "xscores", "goaloo", "nowgoal", "feedinco", "bettingclosed", "tips180", "asiabet"],
    "volleyball": ["/volleyball", "/siatkowka"],
    "handball": ["/handball", "/pilka-reczna"],
    "snooker": ["/snooker", "cuetracker"],
    "esports": ["/esports", "/esport", "gosugamers", "bo3.gg", "hltv"],
    "darts": ["/darts", "/rzutki", "dartsorakel"],
    "table_tennis": ["/table-tennis", "/tenis-stolowy"],
    "mma": ["/mma", "tapology", "ufcstats"],
    "padel": ["/padel", "premierpadel", "padelfip"],
    "speedway": ["/speedway", "/zuzel", "speedwayekstraliga"],
}


def detect_sport(url: str) -> str:
    """Detect sport from URL path patterns."""
    url_lower = url.lower()
    for sport, patterns in SPORT_URL_PATTERNS.items():
        for pat in patterns:
            if pat in url_lower:
                return sport
    return "football"  # default

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
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    d = DATA_DIR / domain
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{ts}.html"
    p.write_text(html, encoding="utf-8")
    return p


def domain_from_url(url: str) -> str:
    return urlparse(url).netloc.replace("www.", "")


def validate_fetched_date(html: str, url: str, domain: str) -> list[str]:
    """Validate that fetched HTML content is from the current year/date.

    Returns list of warning strings (empty if all OK).
    """
    warnings = []
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Europe/Warsaw"))
    except ImportError:
        now = datetime.now()
    current_year = str(now.year)

    # Check datePublished meta tag
    date_match = re.search(r'"datePublished"\s*:\s*"(\d{4})-', html[:5000])
    if date_match:
        pub_year = date_match.group(1)
        if pub_year != current_year:
            warnings.append(
                f"STALE_CONTENT: {domain} datePublished year={pub_year}, expected={current_year}"
            )

    # ZawodTyper-specific: verify day-of-week in URL matches today
    if "zawodtyper" in domain:
        PL_DAYS = {
            0: "poniedzialek", 1: "wtorek", 2: "sroda",
            3: "czwartek", 4: "piatek", 5: "sobota", 6: "niedziela"
        }
        expected_day = PL_DAYS[now.weekday()]
        url_lower = url.lower()
        for day_name in PL_DAYS.values():
            if day_name in url_lower and day_name != expected_day:
                warnings.append(
                    f"ZT_DAY_MISMATCH: URL contains '{day_name}' but today is '{expected_day}'"
                )
                break

    return warnings


def scan_urls(urls, deep=False, max_deep_links=50):
    all_extracted = {}
    errors = []
    deep_links_found = 0

    # Import deep-link discovery if deep mode is enabled
    if deep:
        try:
            from deep_link_discovery import discover_deep_links
        except ImportError:
            print("[WARNING] deep_link_discovery module not found — deep mode disabled")
            deep = False

    for i, url in enumerate(urls):
        domain = domain_from_url(url)
        print(f"[{i+1}/{len(urls)}] Fetching {url}")
        try:
            html = fetch(url)
        except Exception as e:
            msg = f"Failed to fetch {url}: {e}"
            print(msg)
            errors.append({"url": url, "error": str(e)})
            continue
        if not html or len(html) < 100:
            msg = f"Empty or too-short response from {url} ({len(html or '')} chars)"
            print(msg)
            errors.append({"url": url, "error": msg})
            continue
        saved = save_html(domain, html)
        print(f"  Saved raw HTML to {saved}")
        # Validate fetched content date
        date_warnings = validate_fetched_date(html, url, domain)
        for w in date_warnings:
            print(f"  ⚠️  {w}")
            errors.append({"url": url, "warning": w})
        adapter = get_adapter(domain)
        sport = detect_sport(url)
        try:
            extracted = adapter(html, url)
        except Exception as e:
            print(f"  Adapter for {domain} failed, falling back to raw parser: {e}")
            from adapters.raw_adapter import parse as raw_parse
            extracted = raw_parse(html, url)
        # Tag each item with detected sport
        for item in extracted:
            if "sport" not in item:
                item["sport"] = sport
        all_extracted[url] = extracted
        print(f"  Extracted {len(extracted)} candidate match lines from {domain} [{sport}]")

        # Deep-link discovery: follow tournament sub-links
        if deep and domain in ("flashscore.com", "betexplorer.com", "sofascore.com", "soccerway.com"):
            try:
                sub_links = discover_deep_links(html, url, domain, max_links=max_deep_links)
                new_links = [sl for sl in sub_links if sl not in urls and sl not in all_extracted]
                if new_links:
                    deep_links_found += len(new_links)
                    print(f"  [deep] Discovered {len(new_links)} sub-links from {domain}")
                    for j, sub_url in enumerate(new_links[:max_deep_links]):
                        print(f"    [deep {j+1}/{len(new_links)}] Fetching {sub_url}")
                        try:
                            sub_html = fetch(sub_url)
                        except Exception as e:
                            errors.append({"url": sub_url, "error": str(e), "source_type": "deep-link"})
                            continue
                        if not sub_html or len(sub_html) < 100:
                            continue
                        save_html(domain, sub_html)
                        sub_sport = detect_sport(sub_url)
                        try:
                            sub_extracted = adapter(sub_html, sub_url)
                        except Exception:
                            from adapters.raw_adapter import parse as raw_parse
                            sub_extracted = raw_parse(sub_html, sub_url)
                        for item in sub_extracted:
                            if "sport" not in item:
                                item["sport"] = sub_sport
                            item["source_type"] = "deep-link"
                        all_extracted[sub_url] = sub_extracted
                        print(f"    [deep] Extracted {len(sub_extracted)} from {sub_url}")
                        time.sleep(FETCH_DELAY_SECONDS)
            except Exception as e:
                print(f"  [deep] Deep-link discovery error for {domain}: {e}")

        # Rate limit between fetches
        if i < len(urls) - 1:
            time.sleep(FETCH_DELAY_SECONDS)

    # write a small JSON summary
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / "scan_summary.json"
    out.write_text(json.dumps(all_extracted, indent=2, ensure_ascii=False), encoding="utf-8")
    # also write per-domain structured outputs (latest)
    for url, items in all_extracted.items():
        domain = domain_from_url(url)
        d = DATA_DIR / domain
        d.mkdir(parents=True, exist_ok=True)
        p = d / "structured_latest.json"
        p.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    # write error log if any
    if errors:
        err_path = DATA_DIR / "scan_errors.json"
        err_path.write_text(json.dumps(errors, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[WARNING] {len(errors)} source(s) failed. See {err_path}")
    print(f"Wrote summary to {out} ({len(all_extracted)} sources OK, {len(errors)} failed)")
    if deep:
        print(f"[deep] Total deep-links discovered and scanned: {deep_links_found}")
    return all_extracted


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--urls", nargs="+", help="List of URLs to scan", required=True)
    parser.add_argument("--deep", action="store_true", help="Enable deep-link discovery for tournament sub-pages")
    parser.add_argument("--max-deep-links", type=int, default=50, help="Max sub-links per domain (default: 50)")
    args = parser.parse_args()
    scan_urls(args.urls, deep=args.deep, max_deep_links=args.max_deep_links)


if __name__ == "__main__":
    main()
