"""Sofascore API client — advanced stats, form, H2H, and odds.

Provides deep statistics and event discovery for:
- Football (soccer)
- Basketball
- Tennis
- Hockey
- Volleyball
and more.

Base URL: https://api.sofascore.com/api/v1/
"""

import logging
import re
from typing import Dict, List, Optional, Any
import requests

from .base_client import BaseAPIClient, APIError, APINotFoundError
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/115.0",
    "Accept": "application/json",
}

class SofascoreClient(BaseAPIClient):
    """Deep data client for Sofascore."""

    # Circuit breaker: after N consecutive stealth failures, skip Playwright
    _stealth_failures = 0
    _stealth_circuit_open = False
    _STEALTH_FAILURE_THRESHOLD = 2  # After 2 failures, stop trying stealth

    # Shared Playwright browser — reused across fallback requests to avoid
    # expensive per-request browser launches (~3-5s each).
    _pw_instance = None
    _pw_browser = None

    @staticmethod
    def _is_sofascore_id(event_id: str) -> bool:
        """Return True only for numeric-only strings (valid Sofascore event IDs)."""
        return bool(event_id and re.fullmatch(r"\d+", str(event_id)))

    def __init__(self, rate_limiter: RateLimiter | None = None):
        if rate_limiter is None:
            rate_limiter = RateLimiter()
        super().__init__("sofascore", "https://api.sofascore.com/api/v1", rate_limiter)
        self.api_key = "no-key-needed"
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _request(self, endpoint: str, params: dict | None = None) -> dict:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        if hasattr(self.rate_limiter, 'wait'):
            self.rate_limiter.wait("sofascore")
        
        try:
            resp = self.session.get(url, params=params, timeout=self.TIMEOUT)
            
            if resp.status_code == 404:
                raise APINotFoundError(f"Resource not found: {url}")
            if resp.status_code in (403, 429):
                if SofascoreClient._stealth_circuit_open:
                    raise APIError(f"Sofascore blocked ({resp.status_code}) and stealth circuit is OPEN — skipping Playwright")
                logger.warning(f"Sofascore blocked HTTP request ({resp.status_code}) for {url}. Falling back to Playwright...")
                return self._request_playwright(url, params)
                
            resp.raise_for_status()
            # Reset circuit on HTTP success
            SofascoreClient._stealth_failures = 0
            SofascoreClient._stealth_circuit_open = False
            return resp.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, "response") and e.response is not None and e.response.status_code in (403, 429):
                if SofascoreClient._stealth_circuit_open:
                    raise APIError(f"Sofascore blocked and stealth circuit is OPEN")
                return self._request_playwright(url, params)
            raise APIError(f"Sofascore Network error: {e}")

    def _request_playwright(self, url: str, params: dict | None = None) -> dict:
        """Stealth Playwright — intercept Sofascore's own API calls from schedule page."""
        import threading
        # Playwright sync API cannot run inside ThreadPoolExecutor workers (greenlet crash).
        # If we're NOT in the main thread, skip Playwright and raise immediately.
        if threading.current_thread() is not threading.main_thread():
            SofascoreClient._stealth_failures += 1
            if SofascoreClient._stealth_failures >= SofascoreClient._STEALTH_FAILURE_THRESHOLD:
                SofascoreClient._stealth_circuit_open = True
            raise APIError(f"Sofascore Playwright fallback disabled in worker thread (would crash greenlet)")

        from playwright.sync_api import sync_playwright
        from playwright_stealth import Stealth
        import urllib.parse
        import time
        import random
        import json as _json
        
        try:
            from scripts.stealth_utils import USER_AGENTS, BROWSER_ARGS
        except ImportError:
            try:
                from stealth_utils import USER_AGENTS, BROWSER_ARGS
            except ImportError:
                USER_AGENTS = [
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
                ]
                BROWSER_ARGS = ['--disable-blink-features=AutomationControlled', '--disable-infobars', '--no-sandbox']
        
        if params:
            query = urllib.parse.urlencode(params)
            full_url = f"{url}?{query}"
        else:
            full_url = url
        
        # Extract the API path to know what response to intercept
        # e.g. /sport/football/scheduled-events/2026-05-13
        api_path = full_url.replace(self.base_url, "").lstrip("/")
        
        def _safe_close(ctx):
            try:
                ctx.close()
            except Exception:
                pass
        
        # Reuse shared browser instance to avoid expensive per-request launches
        if SofascoreClient._pw_browser is None:
            SofascoreClient._pw_instance = sync_playwright().start()
            SofascoreClient._pw_browser = SofascoreClient._pw_instance.chromium.launch(
                headless=True, args=BROWSER_ARGS,
            )
        browser = SofascoreClient._pw_browser
        
        # Build the schedule page URL from the API endpoint
        # /sport/{sport}/scheduled-events/{date} → sofascore.com/{sport}/{date}
        schedule_url = None
        m = re.match(r"sport/([^/]+)/scheduled-events/(\d{4}-\d{2}-\d{2})", api_path)
        if m:
            sport_slug = m.group(1)
            date_str = m.group(2)
            schedule_url = f"https://www.sofascore.com/{sport_slug}/{date_str}"
        
        # For event-specific endpoints, extract event ID
        event_match = re.match(r"event/(\d+)/", api_path)
        event_id = event_match.group(1) if event_match else None
            
        for attempt, backoff in enumerate([5, 12], 1):
            captured_data = {}
            ua = random.choice(USER_AGENTS)
            context = browser.new_context(
                user_agent=ua,
                viewport={"width": 1440, "height": 900},
                locale="en-US",
            )
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            # Set up response interceptor for API calls
            all_api_responses = []
            
            def handle_response(response):
                resp_url = response.url
                # Capture ALL Sofascore API responses
                if response.status == 200 and (
                    "api.sofascore.com" in resp_url or "/api/v1/" in resp_url
                ):
                    try:
                        json_data = response.json()
                        all_api_responses.append({"url": resp_url, "json": json_data})
                        # Check if this is the one we want
                        if api_path in resp_url:
                            captured_data["json"] = json_data
                            captured_data["url"] = resp_url
                            logger.info(f"[Sofascore stealth] Captured target: {resp_url[:100]}")
                        else:
                            logger.debug(f"[Sofascore stealth] Captured other: {resp_url[:100]}")
                    except Exception:
                        pass
            
            page.on("response", handle_response)
            
            try:
                # Navigate to the appropriate Sofascore page
                wants_event_statistics = bool(event_id and api_path.startswith(f"event/{event_id}/statistics"))
                if schedule_url:
                    nav_url = schedule_url
                elif event_id:
                    nav_url = f"https://www.sofascore.com/event/{event_id}"
                else:
                    raise APIError(f"Sofascore stealth: no valid navigation target for path '{api_path}'")
                
                logger.info(f"[Sofascore stealth] Attempt {attempt}: navigating to {nav_url}")
                page.goto(nav_url, wait_until="domcontentloaded", timeout=25000)
                
                # Wait for JS hydration + API calls
                page.wait_for_timeout(6000)
                
                # Handle Cloudflare challenge
                content = page.content()
                if "Just a moment" in content:
                    logger.info("[Sofascore stealth] Cloudflare challenge, waiting 8s...")
                    page.wait_for_timeout(8000)
                
                # Check if we already captured API data during page load
                if captured_data.get("json"):
                    logger.info(f"[Sofascore stealth] Intercepted during load: {captured_data.get('url', '?')[:80]}")
                    result = captured_data["json"]
                    _safe_close(context)
                    return result
                
                # Wait more — Sofascore may lazy-load after hydration
                page.wait_for_timeout(5000)
                
                if captured_data.get("json"):
                    logger.info(f"[Sofascore stealth] Intercepted after wait")
                    result = captured_data["json"]
                    _safe_close(context)
                    return result
                
                # Try scrolling to trigger lazy loading
                page.evaluate("window.scrollBy(0, 500)")
                page.wait_for_timeout(3000)
                
                if captured_data.get("json"):
                    logger.info(f"[Sofascore stealth] Intercepted after scroll")
                    result = captured_data["json"]
                    _safe_close(context)
                    return result

                if wants_event_statistics:
                    redirected_url = page.url.rstrip("/")
                    if redirected_url and redirected_url != nav_url.rstrip("/") and not redirected_url.endswith("/statistics"):
                        stats_url = f"{redirected_url}/statistics"
                        logger.info(f"[Sofascore stealth] Retrying on redirected statistics page: {stats_url}")
                        page.goto(stats_url, wait_until="domcontentloaded", timeout=25000)
                        page.wait_for_timeout(6000)

                        content = page.content()
                        if "Just a moment" in content:
                            logger.info("[Sofascore stealth] Cloudflare challenge on statistics page, waiting 8s...")
                            page.wait_for_timeout(8000)

                        if captured_data.get("json"):
                            logger.info(f"[Sofascore stealth] Intercepted on redirected statistics page")
                            result = captured_data["json"]
                            _safe_close(context)
                            return result

                        page.wait_for_timeout(5000)
                        if captured_data.get("json"):
                            logger.info(f"[Sofascore stealth] Intercepted on redirected statistics page after wait")
                            result = captured_data["json"]
                            _safe_close(context)
                            return result

                        page.evaluate("window.scrollBy(0, 500)")
                        page.wait_for_timeout(3000)
                        if captured_data.get("json"):
                            logger.info(f"[Sofascore stealth] Intercepted on redirected statistics page after scroll")
                            result = captured_data["json"]
                            _safe_close(context)
                            return result
                
                # Last resort: check all captured API responses
                logger.info(f"[Sofascore stealth] No exact match for {api_path}. Captured {len(all_api_responses)} API responses.")
                for resp in all_api_responses:
                    logger.info(f"  - {resp['url'][:120]}")
                
                # Try to find events in any captured response
                for resp in all_api_responses:
                    if "events" in resp.get("json", {}):
                        logger.info(f"[Sofascore stealth] Found events in: {resp['url'][:100]}")
                        result = resp["json"]
                        _safe_close(context)
                        return result
                
                if wants_event_statistics:
                    dom_items = self._extract_statistics_from_dom(page)
                    if dom_items:
                        logger.info(f"[Sofascore stealth] Extracted {len(dom_items)} statistics items from DOM")
                        _safe_close(context)
                        return {
                            "statistics": [
                                {
                                    "period": "ALL",
                                    "groups": [{"statisticsItems": dom_items}],
                                }
                            ]
                        }

                # Fallback: try __NEXT_DATA__ from SSR (has event data on event pages)
                try:
                    next_data = page.evaluate("""() => {
                        const el = document.getElementById('__NEXT_DATA__');
                        return el ? JSON.parse(el.textContent) : null;
                    }""")
                    if next_data:
                        logger.info(f"[Sofascore stealth] Extracted __NEXT_DATA__ (keys: {list(next_data.get('props',{}).get('pageProps',{}).keys())[:5]})")
                        _safe_close(context)
                        return next_data
                except Exception:
                    pass
                
                logger.warning(f"[Sofascore stealth] No API response captured on attempt {attempt}")
                SofascoreClient._stealth_failures += 1
                if SofascoreClient._stealth_failures >= SofascoreClient._STEALTH_FAILURE_THRESHOLD:
                    SofascoreClient._stealth_circuit_open = True
                    logger.warning(f"[Sofascore stealth] Circuit breaker OPEN after {SofascoreClient._stealth_failures} failures")
                _safe_close(context)
                if attempt < 2:
                    time.sleep(backoff)
                    continue
                raise APIError(f"Sofascore stealth: no data intercepted for {api_path}")
                
            except (APIError, APINotFoundError):
                _safe_close(context)
                raise
            except Exception as e:
                logger.warning(f"[Sofascore stealth] Attempt {attempt} error: {e}")
                _safe_close(context)
                if attempt < 2:
                    time.sleep(backoff)
                    continue
                raise APIError(f"Sofascore stealth failed: {e}")

        raise APIError(f"Sofascore stealth exhausted retries for {full_url}")

    @staticmethod
    def _extract_statistics_from_dom(page) -> list[dict[str, str]]:
        """Extract visible football statistics from the rendered statistics page DOM."""
        try:
            return page.evaluate(
                r"""() => {
                    const labels = new Map([
                        ['ball possession', 'Ball possession'],
                        ['corner kicks', 'Corner kicks'],
                        ['corners', 'Corner kicks'],
                        ['fouls', 'Fouls'],
                        ['yellow cards', 'Yellow Cards'],
                        ['red cards', 'Red Cards'],
                        ['total shots', 'Total Shots'],
                        ['shots on target', 'Shots on Target'],
                        ['shots on goal', 'Shots on Target'],
                        ['shots off target', 'Shots Off Target'],
                    ]);

                    const parseValue = (text) => {
                        if (!text) return null;
                        const match = text.replace(/,/g, '.').match(/-?\d+(?:\.\d+)?%?/);
                        return match ? match[0] : null;
                    };

                    const seen = new Set();
                    const items = [];
                    const nodes = Array.from(document.querySelectorAll('div, span, p, strong, b, li'));

                    for (const el of nodes) {
                        const text = (el.textContent || '').trim();
                        const canonical = labels.get(text.toLowerCase());
                        if (!canonical || seen.has(canonical)) continue;

                        let extracted = null;
                        let node = el;
                        for (let depth = 0; depth < 5 && node; depth += 1, node = node.parentElement) {
                            const childTexts = Array.from(node.children)
                                .map((child) => (child.innerText || child.textContent || '').trim())
                                .filter(Boolean);
                            if (!childTexts.length) continue;
                            const labelIndex = childTexts.findIndex((value) => value.toLowerCase() === canonical.toLowerCase());
                            if (labelIndex === -1) continue;
                            const values = childTexts
                                .filter((_, index) => index !== labelIndex)
                                .map(parseValue)
                                .filter(Boolean);
                            if (values.length >= 2) {
                                extracted = {name: canonical, home: values[0], away: values[values.length - 1]};
                                break;
                            }
                        }

                        if (!extracted) {
                            const rowText = ((el.parentElement && el.parentElement.innerText) || el.innerText || '')
                                .replace(/\n+/g, ' ')
                                .trim();
                            const values = rowText.match(/-?\d+(?:\.\d+)?%?/g) || [];
                            if (values.length >= 2) {
                                extracted = {name: canonical, home: values[0], away: values[values.length - 1]};
                            }
                        }

                        if (extracted) {
                            seen.add(canonical);
                            items.push(extracted);
                        }
                    }

                    return items;
                }"""
            ) or []
        except Exception:
            return []

    @classmethod
    def close_playwright(cls):
        """Clean up shared Playwright browser resources."""
        if cls._pw_browser:
            try:
                cls._pw_browser.close()
            except Exception:
                pass
            cls._pw_browser = None
        if cls._pw_instance:
            try:
                cls._pw_instance.stop()
            except Exception:
                pass
            cls._pw_instance = None

    # -------- REQUIRED INTERFACE IMPLEMENTATIONS --------

    def get_fixtures(self, date: str, sport: str = "football") -> list:
        """Get all scheduled events for a sport on a specific date (YYYY-MM-DD).
        
        Returns list of APIFixture objects (matching the common contract).
        """
        from .api_football import APIFixture
        from datetime import datetime, timezone
        
        try:
            data = self._request(f"/sport/{sport}/scheduled-events/{date}")
        except (APINotFoundError, APIError):
            return []
        
        raw_events = data.get("events", [])
        fixtures = []
        for ev in raw_events:
            try:
                event_id = str(ev.get("id", ""))
                tournament = ev.get("tournament", {})
                comp_name = tournament.get("name", "Unknown")
                home = ev.get("homeTeam", {}).get("name", "Unknown")
                away = ev.get("awayTeam", {}).get("name", "Unknown")
                
                # Convert Unix timestamp to ISO format
                ts = ev.get("startTimestamp")
                if ts:
                    kickoff = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                else:
                    kickoff = date + "T00:00:00Z"
                
                status_desc = ev.get("status", {}).get("description", "Not started")
                
                fixtures.append(APIFixture(
                    external_id=event_id,
                    source="sofascore",
                    sport=sport if sport != "ice-hockey" else "hockey",
                    competition_name=comp_name,
                    home_team_name=home,
                    away_team_name=away,
                    kickoff=kickoff,
                    status=status_desc,
                ))
            except Exception as e:
                logger.debug(f"Skipping Sofascore event: {e}")
                continue
        
        return fixtures

    # Mapping SofaScore stat names → normalized stat keys
    _STAT_NAME_MAP = {
        "corner kicks": "corners",
        "corners": "corners",
        "total shots": "shots",
        "shots": "shots",
        "shots on target": "shots_on_target",
        "shot on target": "shots_on_target",
        "shots on goal": "shots_on_target",
        "shots off target": "shots_off_target",
        "fouls": "fouls",
        "yellow cards": "yellow_cards",
        "yellow card": "yellow_cards",
        "red cards": "red_cards",
        "red card": "red_cards",
        "ball possession": "possession",
        "possession": "possession",
        "offsides": "offsides",
        "free kicks": "free_kicks",
        "goal kicks": "goal_kicks",
        "throw-ins": "throw_ins",
        "big chances": "big_chances",
        "big chances missed": "big_chances_missed",
        "saves": "saves",
        "tackles": "tackles",
        "passes": "passes",
        "accurate passes": "accurate_passes",
        "long balls": "long_balls",
        "crosses": "crosses",
        "dribbles": "dribbles",
        "blocked shots": "blocked_shots",
        "interceptions": "interceptions",
        "clearances": "clearances",
        "total points": "points",
        "rebounds": "rebounds",
        "assists": "assists",
        "turnovers": "turnovers",
        "steals": "steals",
        "blocks": "blocks",
        "aces": "aces",
        "double faults": "double_faults",
        "service points won": "service_points_won",
    }

    def get_fixture_stats(self, event_id: str):
        """Get match statistics for a specific fixture as NormalizedMatchStats."""
        from bet.models.normalized import NormalizedMatchStats
        
        if not self._is_sofascore_id(event_id):
            logger.debug(f"Skipping get_fixture_stats — non-Sofascore ID: {event_id}")
            return None
        try:
            data = self._request(f"/event/{event_id}/statistics")
            statistics = data.get("statistics", [])
            if not statistics:
                return None
            
            # Get event info for team names
            try:
                event_data = self._request(f"/event/{event_id}")
                event = event_data.get("event", event_data)
                home_team = event.get("homeTeam", {}).get("name", "")
                away_team = event.get("awayTeam", {}).get("name", "")
                start_ts = event.get("startTimestamp", 0)
                date_str = ""
                if start_ts:
                    from datetime import datetime, timezone
                    date_str = datetime.fromtimestamp(start_ts, tz=timezone.utc).strftime("%Y-%m-%d")
            except Exception:
                home_team, away_team, date_str = "", "", ""
            
            # Parse stats — take "ALL" period if available
            all_period = None
            for period_data in statistics:
                if str(period_data.get("period", "")).upper() == "ALL":
                    all_period = period_data
                    break
            if not all_period:
                for period_data in statistics:
                    if period_data.get("groups"):
                        all_period = period_data
                        break
            if not all_period and statistics:
                all_period = statistics[0]
            
            if not all_period:
                return None
            
            stats_dict = {}
            for group in all_period.get("groups", []):
                for item in group.get("statisticsItems", []):
                    name = item.get("name", "").lower()
                    stat_key = self._STAT_NAME_MAP.get(name)
                    if not stat_key:
                        continue
                    home_val = self._parse_stat_value(item.get("home", "0"))
                    away_val = self._parse_stat_value(item.get("away", "0"))
                    if home_val is not None and away_val is not None:
                        stats_dict[stat_key] = {"home": home_val, "away": away_val}
            
            if not stats_dict:
                return None
            
            return NormalizedMatchStats(
                fixture_id=str(event_id),
                source="sofascore",
                sport="football",  # Will be overridden by caller if needed
                home_team=home_team,
                away_team=away_team,
                date=date_str,
                stats=stats_dict,
            )
        except APINotFoundError:
            return None

    @staticmethod
    def _parse_stat_value(val) -> float | None:
        """Parse SofaScore stat value (can be '58%', '15', etc.)."""
        if val is None:
            return None
        s = str(val).strip().rstrip("%")
        try:
            return float(s)
        except (ValueError, TypeError):
            return None

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list[dict]:
        """Sofascore usually provides H2H via the event endpoint.
        If we want direct team-to-team H2H, we could query historical data or 
        fetch from known event's h2h endpoint.
        """
        logger.warning("get_h2h directly via team ids is not supported in Sofascore without event_id. Use get_event_h2h instead.")
        return []

    def resolve_team_id(self, team_name: str, **kwargs) -> str | None:
        """Search SofaScore for a team and return its numeric ID."""
        try:
            data = self._request(f"/search/teams/{team_name}")
            teams = data.get("teams", [])
            if not teams:
                return None
            # Return first match
            return str(teams[0].get("id", ""))
        except (APIError, APINotFoundError):
            return None
        
    def get_team_last_fixtures(self, team_id: str, last_n: int = 10) -> list:
        """Get the latest form/results for a team as NormalizedFixture objects."""
        from bet.models.normalized import NormalizedFixture
        
        if not self._is_sofascore_id(team_id):
            logger.debug(f"Skipping get_team_last_fixtures — non-Sofascore ID: {team_id}")
            return []
        try:
            # endpoint: /team/{id}/events/last/0 
            data = self._request(f"/team/{team_id}/events/last/0")
            events = data.get("events", [])
            fixtures = []
            for ev in events[:last_n]:
                event_id = str(ev.get("id", ""))
                home = ev.get("homeTeam", {})
                away = ev.get("awayTeam", {})
                tournament = ev.get("tournament", {})
                # Convert unix timestamp to ISO
                start_ts = ev.get("startTimestamp", 0)
                kickoff = ""
                if start_ts:
                    from datetime import datetime, timezone
                    kickoff = datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat()
                fixtures.append(NormalizedFixture(
                    fixture_id=event_id,
                    source="sofascore",
                    sport=tournament.get("category", {}).get("sport", {}).get("slug", "football"),
                    competition=tournament.get("name", ""),
                    home_team=home.get("name", ""),
                    away_team=away.get("name", ""),
                    kickoff=kickoff,
                    status="FINISHED" if ev.get("status", {}).get("type") == "finished" else "scheduled",
                ))
            return fixtures
        except APINotFoundError:
            return []

    # -------- ADVANCED SOFASCORE SPECIFIC ENDPOINTS --------

    def get_pregame_form(self, event_id: str) -> dict:
        """Get pregame form data (W/L/D sequences, standings position, points)."""
        if not self._is_sofascore_id(event_id):
            logger.debug(f"Skipping get_pregame_form — non-Sofascore ID: {event_id}")
            return {}
        try:
            return self._request(f"/event/{event_id}/pregame-form")
        except (APINotFoundError, APIError):
            return {}

    def get_event_h2h(self, event_id: str) -> dict:
        """Get rich H2H stats for a specific event."""
        if not self._is_sofascore_id(event_id):
            logger.debug(f"Skipping get_event_h2h — non-Sofascore ID: {event_id}")
            return {}
        try:
            return self._request(f"/event/{event_id}/h2h")
        except (APINotFoundError, APIError):
            return {}
            
    def get_event_odds(self, event_id: str) -> dict:
        """Get pre-match odds for an event (usually 1x2 and O/U)."""
        if not self._is_sofascore_id(event_id):
            logger.debug(f"Skipping get_event_odds — non-Sofascore ID: {event_id}")
            return {}
        try:
            return self._request(f"/event/{event_id}/odds/1/all")
        except (APINotFoundError, APIError):
            return {}

    def get_event_incidents(self, event_id: str) -> list:
        """Get match incidents (goals, cards, substitutions)."""
        if not self._is_sofascore_id(event_id):
            logger.debug(f"Skipping get_event_incidents — non-Sofascore ID: {event_id}")
            return []
        try:
            data = self._request(f"/event/{event_id}/incidents")
            return data.get("incidents", [])
        except APINotFoundError:
            return []

    def get_lineups(self, event_id: str) -> dict:
        """Get starting lineups, benches, and formations."""
        if not self._is_sofascore_id(event_id):
            logger.debug(f"Skipping get_lineups — non-Sofascore ID: {event_id}")
            return {}
        try:
            return self._request(f"/event/{event_id}/lineups")
        except APINotFoundError:
            return {}
            
    def get_player_stats(self, event_id: str) -> dict:
        """Get individual player summary statistics for a match."""
        if not self._is_sofascore_id(event_id):
            logger.debug(f"Skipping get_player_stats — non-Sofascore ID: {event_id}")
            return {}
        try:
            return self._request(f"/event/{event_id}/lineups/statistics")
        except APINotFoundError:
            return {}
