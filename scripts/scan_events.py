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
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import json
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE.parent / "betting" / "data"

# --- DB support (optional — falls back gracefully) ---
try:
    sys.path.insert(0, str(BASE.parent / "src"))
    from bet.db.connection import get_db
    from bet.db.repositories import SourceHealthRepo
    _HAS_DB = True
except ImportError:
    _HAS_DB = False

FETCH_DELAY_SECONDS = 0.5  # default delay between fetches
PER_PAGE_TIMEOUT = 45  # max seconds per page fetch

# Per-domain delays: rate-sensitive sites get higher delays
DOMAIN_DELAY_OVERRIDES = {
    "betclic.pl": 2.0,
    "soccerstats.com": 1.5,
    "totalcorner.com": 1.0,
    "hltv.org": 2.0,
    "dartsorakel.com": 2.0,
}

# Domains safe for intra-domain parallel fetching (value = max concurrent fetches)
PARALLEL_SAFE_DOMAINS = {
    "flashscore.com": 3,
    "sofascore.com": 2,
    "betexplorer.com": 2,
    "oddsportal.com": 2,
    "forebet.com": 2,
    "scores24.live": 2,
    "soccerway.com": 2,
}

SPORT_URL_PATTERNS = {
    "tennis": ["/tennis", "/tenis", "tennisabstract", "tennisexplorer"],
    "basketball": ["/basketball", "/koszykowka", "/nba", "teamrankings.com", "basketball-reference"],
    "hockey": ["/hockey", "/hokej", "/nhl", "hockey-reference", "/ice-hockey"],
    "baseball": ["/baseball", "/mlb", "baseballsavant"],
    "football": ["/football", "/pilka-nozna", "/soccer", "forebet", "predictz", "betideas", "soccerstats", "totalcorner", "soccerway", "aiscore", "xscores", "goaloo", "nowgoal", "feedinco", "bettingclosed", "tips180", "asiabet"],
    "volleyball": ["/volleyball", "/siatkowka"],
    "handball": ["/handball", "/pilka-reczna"],
    "snooker": ["/snooker", "cuetracker"],
    "esports": ["/esports", "/esport", "gosugamers", "bo3.gg", "hltv", "/csgo", "/lol"],
    "darts": ["/darts", "/rzutki", "dartsorakel"],
    "table_tennis": ["/table-tennis", "/tenis-stolowy"],
    "mma": ["/mma", "tapology", "ufcstats"],
    "padel": ["/padel", "premierpadel", "padelfip"],
    "speedway": ["/speedway", "/zuzel", "speedwayekstraliga"],
}

# Multi-sport tipster sites that cover ALL sports — URL-based sport detection
# is unreliable for these. Items from these sites should keep whatever sport
# the adapter/content sets, or remain untagged for fixture-level matching.
MULTI_SPORT_DOMAINS = {
    "zawodtyper.pl", "typersi.pl", "sportowefakty.wp.pl",
    "sportsgambler.com", "pickswise.com", "betaminic.com",
    "tipstrr.com",
}


def detect_sport(url: str) -> str:
    """Detect sport from URL path patterns.

    Returns empty string for multi-sport tipster sites where URL alone
    cannot determine the sport.
    """
    url_lower = url.lower()
    # Multi-sport tipster sites — cannot determine sport from URL
    for domain in MULTI_SPORT_DOMAINS:
        if domain in url_lower:
            return ""  # unknown — must be resolved downstream
    for sport, patterns in SPORT_URL_PATTERNS.items():
        for pat in patterns:
            if pat in url_lower:
                return sport
    return "football"  # default for football-specific sites

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


def _fetch_with_timeout(url: str, timeout_sec: int = PER_PAGE_TIMEOUT) -> str:
    """Fetch a URL with a hard timeout to prevent stalled pages."""
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(fetch, url)
        try:
            return future.result(timeout=timeout_sec)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"Page fetch timed out after {timeout_sec}s: {url}")


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


def _scan_domain_group(domain: str, urls: list[str], deep: bool, max_deep_links: int) -> tuple[dict, list]:
    """Scan all URLs for a single domain group. Returns (extracted_dict, errors_list)."""
    extracted = {}
    errors = []
    deep_links_found = 0
    delay = DOMAIN_DELAY_OVERRIDES.get(domain, FETCH_DELAY_SECONDS)
    intra_workers = PARALLEL_SAFE_DOMAINS.get(domain, 1)

    discover_deep_links = None
    if deep:
        try:
            from deep_link_discovery import discover_deep_links as _ddl
            discover_deep_links = _ddl
        except ImportError:
            pass

    adapter = get_adapter(domain)

    def _fetch_single_url(i: int, url: str) -> tuple:
        """Fetch and parse a single URL. Returns (url, items, local_errors, deep_items)."""
        print(f"  [{domain}] [{i+1}/{len(urls)}] Fetching {url}")
        local_errors = []
        try:
            html = _fetch_with_timeout(url)
        except Exception as e:
            msg = f"Failed to fetch {url}: {e}"
            print(msg)
            return url, None, [{"url": url, "error": str(e)}], {}
        if not html or len(html) < 100:
            msg = f"Empty or too-short response from {url} ({len(html or '')} chars)"
            print(msg)
            # Retry once with longer timeout for JS-heavy sites (e.g., BetExplorer)
            try:
                html = _fetch_with_timeout(url, timeout_sec=PER_PAGE_TIMEOUT * 2)
                if not html or len(html) < 100:
                    return url, None, [{"url": url, "error": msg}], {}
                print(f"  [{domain}] Retry succeeded ({len(html)} chars)")
            except Exception:
                return url, None, [{"url": url, "error": msg}], {}

        saved = save_html(domain, html)
        print(f"  [{domain}] Saved raw HTML to {saved}")
        date_warnings = validate_fetched_date(html, url, domain)
        for w in date_warnings:
            print(f"  [{domain}] ⚠️  {w}")
            local_errors.append({"url": url, "warning": w})

        sport = detect_sport(url)
        try:
            items = adapter(html, url)
        except Exception as e:
            print(f"  [{domain}] Adapter failed, falling back to raw parser: {e}")
            from adapters.raw_adapter import parse as raw_parse
            items = raw_parse(html, url)
        for item in items:
            if "sport" not in item:
                if sport:  # only set if URL-based detection returned a result
                    item["sport"] = sport
                # else: leave untagged — will be resolved by fixture matching
        sport_label = sport or "multi-sport"
        print(f"  [{domain}] Extracted {len(items)} candidate match lines [{sport_label}]")

        # Deep-link discovery
        deep_items = {}
        if discover_deep_links and domain in ("flashscore.com", "betexplorer.com", "sofascore.com", "soccerway.com", "forebet.com", "scores24.live", "oddsportal.com"):
            try:
                sub_links = discover_deep_links(html, url, domain, max_links=max_deep_links)
                new_links = [sl for sl in sub_links if sl not in urls and sl not in extracted]
                if new_links:
                    print(f"  [{domain}] [deep] Discovered {len(new_links)} sub-links")
                    for j, sub_url in enumerate(new_links[:max_deep_links]):
                        print(f"    [{domain}] [deep {j+1}/{len(new_links)}] Fetching {sub_url}")
                        try:
                            sub_html = _fetch_with_timeout(sub_url)
                        except Exception as e:
                            local_errors.append({"url": sub_url, "error": str(e), "source_type": "deep-link"})
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
                        deep_items[sub_url] = sub_extracted
                        print(f"    [{domain}] [deep] Extracted {len(sub_extracted)} from {sub_url}")
                        time.sleep(delay)
            except Exception as e:
                print(f"  [{domain}] [deep] Deep-link discovery error: {e}")

        return url, items, local_errors, deep_items

    # Use intra-domain parallelism for supported domains
    if intra_workers > 1 and len(urls) > 1:
        with ThreadPoolExecutor(max_workers=intra_workers) as executor:
            futures = {executor.submit(_fetch_single_url, i, url): url for i, url in enumerate(urls)}
            for future in as_completed(futures):
                try:
                    url, items, local_errors, deep_items = future.result()
                    errors.extend(local_errors)
                    if items is not None:
                        extracted[url] = items
                    if deep_items:
                        extracted.update(deep_items)
                        deep_links_found += len(deep_items)
                except Exception as e:
                    errors.append({"domain": domain, "error": str(e)})
    else:
        # Serial processing for rate-sensitive domains
        for i, url in enumerate(urls):
            url, items, local_errors, deep_items = _fetch_single_url(i, url)
            errors.extend(local_errors)
            if items is not None:
                extracted[url] = items
            if deep_items:
                extracted.update(deep_items)
                deep_links_found += len(deep_items)
            if i < len(urls) - 1:
                time.sleep(delay)

    if deep_links_found:
        print(f"  [{domain}] [deep] Total deep-links scanned: {deep_links_found}")

    return extracted, errors


def scan_urls(urls, deep=False, max_deep_links=30, workers=8):
    # Group URLs by domain
    domain_groups = defaultdict(list)
    for url in urls:
        domain_groups[domain_from_url(url)].append(url)

    print(f"Scanning {len(urls)} URLs across {len(domain_groups)} domains with {min(workers, len(domain_groups))} workers")

    all_extracted = {}
    errors = []

    # Run domain groups in parallel
    with ThreadPoolExecutor(max_workers=min(workers, len(domain_groups))) as executor:
        futures = {
            executor.submit(_scan_domain_group, domain, group_urls, deep, max_deep_links): domain
            for domain, group_urls in domain_groups.items()
        }
        for future in as_completed(futures):
            domain = futures[future]
            try:
                domain_extracted, domain_errors = future.result()
                all_extracted.update(domain_extracted)
                errors.extend(domain_errors)
            except Exception as e:
                print(f"[ERROR] Domain {domain} worker failed: {e}")
                errors.append({"domain": domain, "error": str(e)})

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

    # --- Record source health in DB ---
    _record_source_health(domain_groups, all_extracted, errors)

    return all_extracted


def _record_source_health(
    domain_groups: dict, all_extracted: dict, errors: list
) -> None:
    """Record per-domain scan success/failure in source_health table."""
    if not _HAS_DB:
        return

    try:
        # Collect successful and failed domains
        successful_domains: set[str] = set()
        for url in all_extracted:
            successful_domains.add(domain_from_url(url))

        failed_domains: set[str] = set()
        for err in errors:
            domain = err.get("domain", "")
            if not domain and err.get("url"):
                domain = domain_from_url(err["url"])
            if domain:
                failed_domains.add(domain)

        with get_db() as conn:
            health_repo = SourceHealthRepo(conn)
            for domain in successful_domains:
                health_repo.record_success(domain, response_ms=0.0)
            for domain in failed_domains - successful_domains:
                health_repo.record_failure(domain)

        total = len(successful_domains) + len(failed_domains - successful_domains)
        if total:
            print(f"[scan] DB: recorded source health for {total} domains")
    except Exception as e:
        print(f"[scan] DB source health error (non-fatal): {e}")


def _run_parallel_sport_scan(betting_date: str) -> dict:
    """Run all per-sport scanners in parallel with independent timeouts.

    This is the new parallel dispatch mode that replaces monolithic scanning.
    Each sport scanner runs independently with its own URL list and timeout.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    sys.path.insert(0, str(BASE))
    from scanners import get_all_scanners
    from scanners.domain_semaphore import DomainSemaphoreMap
    from scanners.merge_results import merge_scan_results

    semaphore_map = DomainSemaphoreMap()
    scanners = get_all_scanners()

    print(f"[parallel-sport] Launching {len(scanners)} sport scanners for {betting_date}")
    results = {}

    with ThreadPoolExecutor(max_workers=len(scanners)) as executor:
        futures = {
            executor.submit(scanner.scan, betting_date, semaphore_map): scanner.scanner_group
            for scanner in scanners
        }
        for future in as_completed(futures):
            group = futures[future]
            try:
                stats = future.result(timeout=900)  # 15 min max per scanner
                results[group] = {
                    "status": "completed",
                    "events_found": getattr(stats, "events_found", 0),
                    "urls_scanned": getattr(stats, "urls_scanned", 0),
                    "duration_sec": getattr(stats, "duration_sec", 0),
                }
                print(f"  ✓ {group}: {results[group]['events_found']} events")
            except Exception as e:
                results[group] = {"status": "failed", "error": str(e)}
                print(f"  ✗ {group}: {e}")

    # Merge all results into scan_summary.json
    merge_scan_results(betting_date)
    print(f"[parallel-sport] All scanners complete. Results merged to scan_summary.json")
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--urls", nargs="+", help="List of URLs to scan")
    parser.add_argument("--urls-file", help="JSON file with URL list (alternative to --urls)")
    parser.add_argument("--deep", action="store_true", help="Enable deep-link discovery for tournament sub-pages")
    parser.add_argument("--max-deep-links", type=int, default=50, help="Max sub-links per domain (default: 50)")
    parser.add_argument("--workers", type=int, default=6, help="Number of parallel domain workers (default: 6)")
    parser.add_argument("--parallel-sport", action="store_true",
                        help="Use per-sport parallel scanner dispatch instead of monolithic scan")
    parser.add_argument("--date", help="Betting date (YYYY-MM-DD) for parallel-sport mode")
    args = parser.parse_args()

    # Parallel sport dispatch mode
    if args.parallel_sport:
        from datetime import date as date_cls
        betting_date = args.date or date_cls.today().isoformat()
        results = _run_parallel_sport_scan(betting_date)
        total_events = sum(r.get("events_found", 0) for r in results.values() if r.get("status") == "completed")
        failed = [g for g, r in results.items() if r.get("status") == "failed"]
        print(f"\n[parallel-sport] Summary: {total_events} events, {len(failed)} failed groups")
        if failed:
            print(f"  Failed: {', '.join(failed)}")

        # Phase 2: Generate health report for agent-driven monitoring
        print(f"\n[parallel-sport] Generating health report...")
        try:
            from scan_health_report import generate_health_report, print_health_dashboard, write_health_json
            report = generate_health_report(betting_date)
            write_health_json(report, betting_date)
            print_health_dashboard(report)
        except Exception as e:
            print(f"[parallel-sport] WARNING: Health report generation failed: {e}")

        return

    # Legacy monolithic scan mode
    urls = []
    if args.urls_file:
        urls_data = json.loads(Path(args.urls_file).read_text(encoding="utf-8"))
        # Support new grouped format: extract flat URL list from _legacy_urls or all sport URLs
        if isinstance(urls_data, dict):
            if "_legacy_urls" in urls_data:
                file_urls = urls_data["_legacy_urls"]
            elif "urls" in urls_data:
                file_urls = urls_data["urls"]
            else:
                # New format without explicit legacy list — flatten all sport URLs
                file_urls = []
                for sport_data in urls_data.get("sports", {}).values():
                    file_urls.extend(sport_data.get("urls", []))
        else:
            file_urls = urls_data
        urls.extend(file_urls)
    if args.urls:
        urls.extend(args.urls)
    if not urls:
        parser.error("Either --urls, --urls-file, or --parallel-sport is required")

    scan_urls(urls, deep=args.deep, max_deep_links=args.max_deep_links, workers=args.workers)


if __name__ == "__main__":
    main()
