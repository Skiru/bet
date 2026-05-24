"""HLTV.org scraper — CS2 team and match statistics.

Access: Playwright stealth mode (Cloudflare-protected).
Rate limit: 4 seconds between requests (be respectful).
Coverage: All professional CS2 — ESL Pro League, BLAST, Majors, RMR, etc.
Fallback: bo3.gg (HTTP) if HLTV blocks.
"""

import logging
import re
import time
from typing import Any
from urllib.parse import quote

logger = logging.getLogger(__name__)

BASE_URL = "https://www.hltv.org"
RATE_LIMIT_SECONDS = 4.0


class HLTVScraper:
    """HLTV.org scraper for CS2 professional match statistics.

    Uses Playwright stealth to bypass Cloudflare protection.
    Falls back gracefully if blocked (circuit breaker in PlaywrightBaseClient).
    """

    def __init__(self):
        self._browser = None
        self._playwright = None
        self._last_request_time = 0.0
        self._team_id_cache: dict[str, int | None] = {}
        self._blocked = False

    def _ensure_browser(self):
        """Lazy-init Playwright browser with stealth."""
        if self._browser is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--no-sandbox",
                ],
            )
        except Exception as e:
            logger.error("HLTV: Failed to launch browser: %s", e)
            self._blocked = True

    def _get_page(self, url: str, wait_ms: int = 5000):
        """Load page with rate limiting and Cloudflare handling.

        Returns BeautifulSoup-parsed page or None.
        """
        if self._blocked:
            return None

        # Rate limiting
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < RATE_LIMIT_SECONDS:
            time.sleep(RATE_LIMIT_SECONDS - elapsed)

        self._ensure_browser()
        if self._blocked:
            return None

        try:
            from playwright_stealth import Stealth
        except ImportError:
            Stealth = None

        from bs4 import BeautifulSoup
        import random

        ua_list = [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        ]

        ctx = self._browser.new_context(
            user_agent=random.choice(ua_list),
            viewport={"width": 1920, "height": 1080},
            locale="en-GB",
        )
        try:
            page = ctx.new_page()
            if Stealth:
                Stealth().apply_stealth_sync(page)

            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(wait_ms)

            # Cloudflare check
            content = page.content()
            if "Just a moment" in content or "cf-browser-verification" in content:
                logger.info("HLTV: Cloudflare challenge, waiting 8s...")
                page.wait_for_timeout(8000)
                content = page.content()
                if "Just a moment" in content:
                    logger.warning("HLTV: Blocked by Cloudflare")
                    ctx.close()
                    self._blocked = True
                    return None

            self._last_request_time = time.monotonic()
            soup = BeautifulSoup(content, "html.parser")
            ctx.close()
            return soup
        except Exception as e:
            logger.warning("HLTV: Page load failed: %s — %s", url, e)
            try:
                ctx.close()
            except Exception:
                pass
            return None

    def search_team(self, name: str) -> int | None:
        """Resolve team name → HLTV team ID."""
        lower = name.lower().strip()
        if lower in self._team_id_cache:
            return self._team_id_cache[lower]

        soup = self._get_page(f"{BASE_URL}/search?query={quote(name)}&tab=team")
        if not soup:
            self._team_id_cache[lower] = None
            return None

        # Parse first team result
        team_link = soup.select_one("a.search-result__link[href*='/team/']")
        if team_link:
            href = team_link.get("href", "")
            match = re.search(r"/team/(\d+)/", href)
            if match:
                team_id = int(match.group(1))
                self._team_id_cache[lower] = team_id
                return team_id

        self._team_id_cache[lower] = None
        return None

    def get_team_stats(self, team_name: str) -> dict:
        """Scrape team overview stats from HLTV.

        Returns:
            {
                "maps_played": int,
                "maps_won": int,
                "map_win_rate": float,
                "rounds_won_avg": float,
                "kd_ratio": float,
                "rating_2_0": float,
                "win_rate_l10": float,
                "matches_found": int,
            }
        """
        team_id = self.search_team(team_name)
        if not team_id:
            logger.warning("HLTV: could not resolve team '%s'", team_name)
            return {}

        soup = self._get_page(f"{BASE_URL}/stats/teams/{team_id}/-?startDate=all")
        if not soup:
            return {}

        stats: dict[str, Any] = {}

        # Parse stat boxes
        stat_boxes = soup.select(".stats-row")
        for row in stat_boxes:
            label_el = row.select_one("span:first-child")
            value_el = row.select_one("span:last-child")
            if not label_el or not value_el:
                continue
            label = label_el.get_text().strip().lower()
            value_text = value_el.get_text().strip()

            try:
                if "maps played" in label:
                    stats["maps_played"] = int(value_text)
                elif "wins" in label and "loss" not in label:
                    stats["maps_won"] = int(value_text)
                elif "k/d ratio" in label:
                    stats["kd_ratio"] = float(value_text)
                elif "rating" in label:
                    stats["rating_2_0"] = float(value_text)
                elif "rounds won" in label:
                    stats["rounds_won_total"] = int(value_text)
                elif "rounds played" in label or "total rounds" in label:
                    stats["rounds_played_total"] = int(value_text)
            except (ValueError, TypeError):
                continue

        if "maps_played" in stats and "maps_won" in stats and stats["maps_played"] > 0:
            stats["map_win_rate"] = round(stats["maps_won"] / stats["maps_played"] * 100, 1)

        # Compute rounds_won_avg per map
        if "rounds_won_total" in stats and "maps_played" in stats and stats["maps_played"] > 0:
            stats["rounds_won_avg"] = round(stats["rounds_won_total"] / stats["maps_played"], 1)
            del stats["rounds_won_total"]
        if "rounds_played_total" in stats:
            del stats["rounds_played_total"]

        return stats

    def get_team_map_pool(self, team_name: str) -> dict:
        """Scrape per-map stats from HLTV team stats page.

        Returns:
            {"map_name": {"played": int, "won": int, "win_rate": float}, ...}
        """
        team_id = self.search_team(team_name)
        if not team_id:
            return {}

        soup = self._get_page(f"{BASE_URL}/stats/teams/maps/{team_id}/-")
        if not soup:
            return {}

        map_pool: dict[str, dict] = {}
        map_rows = soup.select(".stats-row, .map-stats-row")
        for row in map_rows:
            cells = row.select("span")
            if len(cells) >= 3:
                map_name = cells[0].get_text().strip()
                try:
                    played = int(cells[1].get_text().strip())
                    win_pct_text = cells[2].get_text().strip().replace("%", "")
                    win_pct = float(win_pct_text)
                    won = round(played * win_pct / 100)
                    map_pool[map_name] = {
                        "played": played,
                        "won": won,
                        "win_rate": win_pct,
                    }
                except (ValueError, IndexError):
                    continue

        return map_pool

    def get_h2h(self, team_a: str, team_b: str) -> dict:
        """Get head-to-head stats between two teams.

        Returns:
            {
                "matches_found": int,
                "team_a_wins": int,
                "team_b_wins": int,
                "avg_rounds_per_map": float,
            }
        """
        team_a_id = self.search_team(team_a)
        team_b_id = self.search_team(team_b)

        if not team_a_id or not team_b_id:
            return {"matches_found": 0, "team_a_wins": 0, "team_b_wins": 0, "avg_rounds_per_map": 0}

        soup = self._get_page(
            f"{BASE_URL}/results?team={team_a_id}&team={team_b_id}"
        )
        if not soup:
            return {"matches_found": 0, "team_a_wins": 0, "team_b_wins": 0, "avg_rounds_per_map": 0}

        a_wins = 0
        total_matches = 0

        result_rows = soup.select(".result-con")
        for row in result_rows:
            total_matches += 1
            # Check which team won
            winner_el = row.select_one(".team-won")
            if winner_el:
                winner_text = winner_el.get_text().strip().lower()
                if team_a.lower() in winner_text:
                    a_wins += 1

        return {
            "matches_found": total_matches,
            "team_a_wins": a_wins,
            "team_b_wins": total_matches - a_wins,
            "avg_rounds_per_map": 0,  # Would need per-match pages
        }

    def close(self):
        """Clean up browser resources."""
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
        self._browser = None
        self._playwright = None

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
