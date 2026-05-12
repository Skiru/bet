"""BaseSportScanner — abstract base class for per-sport scanners.

All 11 sport scanners inherit from this class. It provides shared logic for:
- URL fetching with timeout and domain semaphore coordination
- Adapter dispatch (via scripts/adapters registry)
- Deep-link discovery
- DB writing (ScanResultRepo) + JSON debug output
- Source health recording (SourceHealthRepo)
- Validation framework (min events check)
"""
import json
import sys
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE.parent / "src"))

from bet.db.connection import get_db
from bet.db.models import ScanResult, ScanRunStats
from bet.db.repositories import ScanResultRepo, SourceHealthRepo
from adapters import normalize_adapter_output

try:
    from fetch_with_playwright import fetch
except Exception:
    import requests

    def fetch(url: str) -> str:
        resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        return resp.text

from adapters import get_adapter

try:
    from deep_link_discovery import discover_deep_links
except ImportError:
    discover_deep_links = None

DATA_DIR = BASE.parent / "betting" / "data"


def _domain_from_url(url: str) -> str:
    """Extract clean domain from URL."""
    return urlparse(url).netloc.replace("www.", "")


def _competition_from_url(url: str, domain: str) -> str:
    """Extract competition/league name from URL path structure.

    Works for sources that encode league info in URL paths:
    - flashscore.com/football/brazil/serie-a/  → "Brazil - Serie A"
    - forebet.com/en/football/brazil-serie-a/   → "Brazil Serie A"
    - betexplorer.com/football/brazil/serie-a/  → "Brazil - Serie A"
    - soccerway.com/national/brazil/serie-a/    → "Brazil - Serie A"

    Returns empty string if no meaningful competition can be extracted.
    """
    import re
    path = urlparse(url).path
    parts = [p for p in path.strip('/').split('/') if p]

    # Flashscore & BetExplorer: /{sport}/{country}/{league}/
    if domain in ("flashscore.com", "betexplorer.com"):
        if len(parts) >= 3:
            country = parts[1].replace('-', ' ').title()
            league = parts[2].replace('-', ' ').title()
            return f"{country} - {league}"
        if len(parts) >= 2 and parts[1] not in ('en', 'pl', 'com'):
            country = parts[1].replace('-', ' ').title()
            return country
    # Forebet: /en/football-tips/{country}-{league}-predictions/
    if domain == "forebet.com":
        m = re.search(r'/football-tips/([^/]+?)(?:-predictions)?/?$', url)
        if m:
            return m.group(1).replace('-', ' ').title()
    # Soccerway: /{lang}/national/{country}/{league}/
    if domain == "soccerway.com":
        m = re.search(r'/national/([^/]+)/([^/]+)', url)
        if m:
            country = m.group(1).replace('-', ' ').title()
            league = m.group(2).replace('-', ' ').title()
            return f"{country} - {league}"
    return ""


class BaseSportScanner(ABC):
    """Abstract base class for per-sport scanners."""

    @property
    @abstractmethod
    def sport_name(self) -> str:
        """Primary sport name (e.g. 'football')."""
        ...

    @property
    @abstractmethod
    def scanner_group(self) -> str:
        """Scanner group identifier (e.g. 'football', 'racket', 'niche')."""
        ...

    @property
    @abstractmethod
    def urls(self) -> list[str]:
        """List of seed URLs to scan."""
        ...

    @property
    @abstractmethod
    def timeout_per_page(self) -> int:
        """Max seconds allowed per page fetch."""
        ...

    @property
    @abstractmethod
    def max_deep_links(self) -> int:
        """Max number of deep links to follow per scan."""
        ...

    @property
    @abstractmethod
    def required_stat_keys(self) -> list[str]:
        """Stat keys this sport must produce."""
        ...

    @property
    @abstractmethod
    def min_expected_events(self) -> int:
        """Minimum events for scan to be considered successful."""
        ...

    def scan(self, betting_date: str, semaphore_map) -> ScanRunStats:
        """Run full scan lifecycle: fetch → parse → deep links → write → validate."""
        start_time = time.time()
        all_results: dict[str, list[dict]] = {}
        sources_ok = 0
        sources_failed = 0
        deep_links_found = 0

        # Combine seed URLs with any runtime-injected extra URLs
        scan_urls = list(self.urls)
        if hasattr(self, "_extra_urls") and self._extra_urls:
            scan_urls.extend(self._extra_urls)

        # Scan all seed URLs
        for url in scan_urls:
            domain = _domain_from_url(url)
            t0 = time.time()
            try:
                html = self._fetch_url(url, semaphore_map)
                response_ms = (time.time() - t0) * 1000
                self._record_health(domain, success=True, response_ms=response_ms)
                sources_ok += 1
            except Exception as e:
                response_ms = (time.time() - t0) * 1000
                self._record_health(domain, success=False, response_ms=response_ms)
                sources_failed += 1
                print(f"  [{self.scanner_group}] FAILED {url}: {e}")
                continue

            # Parse with adapter
            events = self._parse_url(url, html)
            if events:
                all_results[url] = events

            # Discover deep links
            if deep_links_found < self.max_deep_links and discover_deep_links:
                new_links = self._discover_deep_links(url, html)
                for link in new_links:
                    if deep_links_found >= self.max_deep_links:
                        break
                    link_domain = _domain_from_url(link)
                    t1 = time.time()
                    try:
                        link_html = self._fetch_url(link, semaphore_map)
                        link_ms = (time.time() - t1) * 1000
                        self._record_health(link_domain, success=True, response_ms=link_ms)
                        link_events = self._parse_url(link, link_html)
                        if link_events:
                            all_results[link] = link_events
                        deep_links_found += 1
                    except Exception:
                        self._record_health(link_domain, success=False)
                        sources_failed += 1

        # Write results
        events_count = self._write_results(betting_date, all_results)

        # Validate
        flat_results = [event for events in all_results.values() for event in events]
        valid, gaps = self.validate(events_count, flat_results)

        # If validation failed and we have fallbacks, try them
        if not valid:
            fallback_urls = self.get_fallback_urls()
            for url in fallback_urls:
                domain = _domain_from_url(url)
                t0 = time.time()
                try:
                    html = self._fetch_url(url, semaphore_map)
                    response_ms = (time.time() - t0) * 1000
                    self._record_health(domain, success=True, response_ms=response_ms)
                    sources_ok += 1
                    events = self._parse_url(url, html)
                    if events:
                        all_results[url] = events
                except Exception:
                    self._record_health(domain, success=False)
                    sources_failed += 1

            # Re-write and re-validate with fallback data
            if fallback_urls:
                events_count = self._write_results(betting_date, all_results)
                flat_results = [event for events in all_results.values() for event in events]
                valid, gaps = self.validate(events_count, flat_results)

        duration = time.time() - start_time

        stats = ScanRunStats(
            id=None,
            betting_date=betting_date,
            sport=self.sport_name,
            scanner_group=self.scanner_group,
            events_found=events_count,
            sources_ok=sources_ok,
            sources_failed=sources_failed,
            deep_links_found=deep_links_found,
            duration_seconds=round(duration, 2),
            validation_passed=valid,
            gaps_description=gaps,
        )

        # Record run stats to DB
        try:
            with get_db() as conn:
                repo = ScanResultRepo(conn)
                repo.record_run_stats(stats)
        except Exception as e:
            print(f"  [{self.scanner_group}] Warning: could not record run stats: {e}")

        return stats

    def _fetch_url(self, url: str, semaphore_map) -> str:
        """Fetch URL respecting domain semaphore and timeout."""
        domain = _domain_from_url(url)
        with semaphore_map.hold(domain):
            with ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(fetch, url)
                try:
                    return future.result(timeout=self.timeout_per_page)
                except FuturesTimeoutError:
                    raise TimeoutError(
                        f"Page fetch timed out after {self.timeout_per_page}s: {url}"
                    )

    def _parse_url(self, url: str, html: str) -> list[dict]:
        """Parse HTML using appropriate adapter."""
        domain = _domain_from_url(url)
        adapter = get_adapter(domain)
        try:
            return adapter(html, url)
        except Exception as e:
            print(f"  [{self.scanner_group}] Adapter error for {domain}: {e}")
            return []

    def _discover_deep_links(self, url: str, html: str) -> list[str]:
        """Discover sub-page links from a page."""
        if discover_deep_links is None:
            return []
        domain = _domain_from_url(url)
        try:
            return discover_deep_links(html, url, domain)
        except Exception:
            return []

    def _write_results(self, betting_date: str, results: dict[str, list[dict]]) -> int:
        """Dual-write to DB and JSON debug file. Returns total events count."""
        scan_results = []
        now_ts = datetime.now(timezone.utc).isoformat()

        for url, events in results.items():
            domain = _domain_from_url(url)
            url_competition = _competition_from_url(url, domain)
            for event in events:
                home = event.get("home", "")
                away = event.get("away", "")
                event_key = f"{home}|{away}|{event.get('time', '')}".lower().strip()
                if not event_key or event_key == "||":
                    continue
                normalized = normalize_adapter_output(event, source_type=domain)
                if normalized is None:
                    continue
                # Use normalized fields — normalizer handles legacy field mapping
                norm_home = normalized.get("home") or home
                norm_away = normalized.get("away") or away
                # Check both "league" and "competition" keys (adapters use both)
                competition = (
                    normalized.get("league", "")
                    or event.get("competition", "")
                    or url_competition
                )
                scan_results.append(
                    ScanResult(
                        id=None,
                        betting_date=betting_date,
                        sport=normalized.get("sport") or event.get("sport", self.sport_name),
                        source_domain=domain,
                        event_key=event_key,
                        home_team=norm_home,
                        away_team=norm_away,
                        competition=competition,
                        kickoff=event.get("time", ""),
                        raw_data=normalized,
                        scan_timestamp=now_ts,
                    )
                )

        # Write to DB
        inserted = 0
        try:
            with get_db() as conn:
                repo = ScanResultRepo(conn)
                inserted = repo.bulk_insert(scan_results)
        except Exception as e:
            print(f"  [{self.scanner_group}] DB write error: {e}")

        # Write JSON debug file
        json_path = DATA_DIR / f"sport_scan_{self.scanner_group}.json"
        try:
            json_path.parent.mkdir(parents=True, exist_ok=True)
            json_path.write_text(
                json.dumps(results, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"  [{self.scanner_group}] JSON write error: {e}")

        return len(scan_results)

    def _record_health(self, domain: str, success: bool, response_ms: float = 0.0) -> None:
        """Record source health to DB."""
        try:
            with get_db() as conn:
                repo = SourceHealthRepo(conn)
                if success:
                    repo.record_success(domain, response_ms)
                else:
                    repo.record_failure(domain)
        except Exception:
            pass  # Health recording is best-effort

    def validate(self, events_found: int, scan_results: list | None = None) -> tuple[bool, list[str]]:
        """Validate scan completeness. Returns (passed, list_of_gap_descriptions)."""
        gaps = []
        passed = True
        if events_found < self.min_expected_events:
            gaps.append(
                f"{self.scanner_group}: found {events_found} events, "
                f"expected >= {self.min_expected_events}"
            )
            passed = False

        # Stat coverage check (warning-level, does not affect pass/fail)
        if scan_results and self.required_stat_keys:
            stat_count = 0
            for sr in scan_results:
                raw = sr.raw_data if hasattr(sr, 'raw_data') else (sr if isinstance(sr, dict) else {})
                if isinstance(raw, dict):
                    raw_str = str(raw).lower()
                    if any(key in raw_str for key in self.required_stat_keys):
                        stat_count += 1
            if stat_count == 0 and events_found > 0:
                gaps.append(
                    f"{self.scanner_group}: WARNING — 0/{events_found} events have required stats "
                    f"({', '.join(self.required_stat_keys)})"
                )

        return (passed, gaps)

    def get_fallback_urls(self) -> list[str]:
        """Return fallback URLs when primary sources fail. Override in subclasses."""
        return []
