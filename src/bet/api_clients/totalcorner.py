"""TotalCorner client — football corner predictions via Playwright."""
import logging
import re
from datetime import datetime
from typing import Dict, Any, List
from urllib.parse import urlparse

from .api_football import APIFixture
from .base_client import APIError
from .playwright_base import PlaywrightBaseClient
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

_JS_EXTRACT_MATCHES = """() => {
    const table = document.querySelector('#inplay_match_table');
    if (!table) return [];
    const rows = Array.from(table.querySelectorAll('tr'));
    // Skip header rows (rows without match data cells)
    return rows.filter(row => row.querySelector('.match_home')).map(row => {
        // Extract each cell by class...
        const league = row.querySelector('.td_league a');
        const home = row.querySelector('.match_home a');
        const away = row.querySelector('.match_away a');
        const time = row.querySelector('td:nth-child(3)');  // Time column
        const corner = row.querySelector('.span_match_corner');
        const halfCorner = row.querySelector('.span_half_corner');
        const dangerousFull = row.querySelector('.match_dangerous_attacks_div');
        const dangerousHalf = row.querySelector('.match_dangerous_attacks_half_div');
        const goalLine = row.querySelector('.match_total_goal_div');
        const handicap = row.querySelector('.match_handicap');
        const score = row.querySelector('.match_goal');
        const status = row.querySelector('.match_status_minutes');
        const statsLink = row.querySelector('a[href*="/stats/"]');
        
        return {
            league: league ? league.textContent.trim() : '',
            home: home ? home.textContent.trim() : '',
            away: away ? away.textContent.trim() : '',
            time: time ? time.textContent.trim() : '',
            corner: corner ? corner.textContent.trim() : '',
            half_corner: halfCorner ? halfCorner.textContent.trim() : '',
            dangerous_attacks: dangerousFull ? dangerousFull.textContent.trim() : '',
            dangerous_attacks_half: dangerousHalf ? dangerousHalf.textContent.trim() : '',
            goal_line: goalLine ? goalLine.textContent.trim() : '',
            handicap: handicap ? handicap.textContent.trim() : '',
            score: score ? score.textContent.trim() : '',
            status_minutes: status ? status.textContent.trim() : '',
            stats_url: statsLink ? statsLink.getAttribute('href') : '',
        };
    });
}"""


class TotalCornerClient(PlaywrightBaseClient):
    """TotalCorner client — football corner predictions via Playwright.
    
    Football only. Provides: corner data from match listings,
    corner predictions from detail pages, dangerous attack stats.
    """
    
    _COOKIE_SELECTOR = ".qc-cmp2-summary-buttons [mode='primary']"
    _COOKIE_TIMEOUT = 3000
    
    def __init__(self, rate_limiter: "RateLimiter | None" = None):
        super().__init__(api_name="totalcorner", base_url="https://www.totalcorner.com", rate_limiter=rate_limiter)
        self._corner_cache: dict = {}
        
    def _parse_dash_string(self, text: str) -> tuple[int, int]:
        """Parse strings like '46 - 72' into (46, 72)."""
        if not text:
            return 0, 0
        try:
            parts = [int(re.sub(r'\D', '', p.strip())) for p in text.split('-') if re.sub(r'\D', '', p.strip())]
            if len(parts) == 2:
                return parts[0], parts[1]
        except Exception:
            pass
        return 0, 0

    def get_fixtures(self, date: str, sport: str = "football") -> list:
        """Get football fixtures for a date from TotalCorner.

        URL: https://www.totalcorner.com/match/today (or /match/YYYYMMDD)
        Extract from #inplay_match_table rows.
        Returns list of APIFixture objects.
        Football only — ignores sport parameter.
        """
        if sport.lower() != "football":
            return []

        if not date:
            date = datetime.now().strftime("%Y-%m-%d")
        date_str = date.replace("-", "")
        url = f"{self.base_url}/match/{date_str}"

        cache_key = f"totalcorner/fixtures/{date_str}"
        cached = self._check_cache(cache_key, ttl_hours=4)
        if cached:
            return [APIFixture(**f) for f in cached.get("fixtures", [])]

        if not self.rate_limiter.can_request("totalcorner-scraper"):
            logger.warning("[Totalcorner] Rate limit exceeded")
            return []

        fixtures = []
        self._corner_cache.clear()  # Reset corner cache for this fetch
        ctx = None
        try:
            ctx, page = self._load_page(url)
            self.rate_limiter.record_request("totalcorner-scraper", url[:100])
            data = self._evaluate_js(page, _JS_EXTRACT_MATCHES)

            if not data:
                logger.warning("[Totalcorner] No data from DOM — table missing or JS failed")

            if data:
                logger.info(f"[Totalcorner] Extracted {len(data)} raw rows from DOM")
                for row in data:
                    if not row.get("home") or not row.get("away"):
                        continue

                    stats_url = row.get("stats_url", "")
                    ext_id = stats_url.split("/")[-1] if stats_url else ""
                    if not ext_id:
                        ext_id = f"tc-{row['home']}-{row['away']}".replace(" ", "-").lower()

                    # Parse time → kickoff ISO
                    time_str = row.get("time", "").strip()
                    kickoff = f"{date}T00:00:00Z"
                    if date and re.match(r"^\d{1,2}:\d{2}$", time_str):
                        kickoff = f"{date}T{time_str.zfill(5)}:00Z"

                    # Determine status
                    status_min = str(row.get("status_minutes", "")).strip()
                    if status_min.upper() in ("FT", "AET", "PEN"):
                        status = "finished"
                    elif status_min.isdigit():
                        status = "live"
                    else:
                        status = "scheduled"

                    fixtures.append(APIFixture(
                        external_id=ext_id,
                        source="totalcorner",
                        sport="football",
                        competition_name=row.get("league", ""),
                        home_team_name=row.get("home", ""),
                        away_team_name=row.get("away", ""),
                        kickoff=kickoff,
                        status=status,
                    ))

                    # Cache corner data for this match
                    corner_h, corner_a = self._parse_dash_string(row.get("corner", ""))
                    da_h, da_a = self._parse_dash_string(row.get("dangerous_attacks", ""))
                    ht_h, ht_a = self._parse_half_corner(row.get("half_corner", ""))
                    self._corner_cache[ext_id] = {
                        "home_corners": corner_h,
                        "away_corners": corner_a,
                        "total_corners": corner_h + corner_a,
                        "ht_home_corners": ht_h,
                        "ht_away_corners": ht_a,
                        "dangerous_attacks_home": da_h,
                        "dangerous_attacks_away": da_a,
                        "handicap": row.get("handicap", "").strip(),
                        "goal_line": row.get("goal_line", "").strip(),
                        "stats_url": stats_url,
                    }

                logger.info(f"[Totalcorner] Extracted {len(fixtures)} fixtures from {len(data)} rows")

            self._save_cache(cache_key, {"fixtures": [f.__dict__ for f in fixtures]})

        except APIError:
            raise
        except Exception as e:
            logger.error(f"[Totalcorner] get_fixtures error: {e}")
        finally:
            if ctx:
                try:
                    ctx.close()
                except Exception:
                    pass

        return fixtures

    def _parse_half_corner(self, text: str) -> tuple[int, int]:
        """Parse half-time corner strings like '(2-2)' into (2, 2)."""
        if not text:
            return 0, 0
        cleaned = text.strip().strip("()")
        return self._parse_dash_string(cleaned)

    def get_corner_predictions(self, match_id: str) -> dict:
        """Get corner data for a match.

        First checks in-memory cache from get_fixtures listing.
        Falls back to navigating the match stats page if available.

        Args:
            match_id: TotalCorner match ID or external_id from get_fixtures.

        Returns:
            dict with corner and dangerous attack data.
        """
        # Check in-memory cache populated by get_fixtures
        if match_id in self._corner_cache:
            return self._corner_cache[match_id]

        # Check file cache
        cache_key = f"totalcorner/corners/{match_id}"
        cached = self._check_cache(cache_key, ttl_hours=4)
        if cached:
            return cached

        # Try loading from stats page if we have a URL-like ID
        stats_url = match_id if match_id.startswith("/") or match_id.startswith("http") else None
        if not stats_url:
            logger.debug(f"[Totalcorner] No stats URL for {match_id}, returning empty")
            return {}

        if stats_url.startswith("http"):
            parsed = urlparse(stats_url)
            if parsed.netloc not in ("www.totalcorner.com", "totalcorner.com"):
                logger.error(f"[Totalcorner] Rejected non-totalcorner URL: {stats_url}")
                return {}
            url = stats_url
        else:
            url = f"{self.base_url}{stats_url}"

        if not self.rate_limiter.can_request("totalcorner-scraper"):
            logger.warning("[Totalcorner] Rate limit exceeded for corner predictions")
            return {}
        ctx = None
        try:
            ctx, page = self._load_page(url)
            self.rate_limiter.record_request("totalcorner-scraper", url[:100])
            body_text = page.inner_text('body')
            # Parse corner stats from the stats page body text
            predictions = self._parse_stats_page(body_text)
            if predictions:
                self._save_cache(cache_key, predictions)
            return predictions
        except APIError:
            raise
        except Exception as e:
            logger.error(f"[Totalcorner] get_corner_predictions error: {e}")
            return {}
        finally:
            if ctx:
                try:
                    ctx.close()
                except Exception:
                    pass

    def _parse_stats_page(self, body_text: str) -> dict:
        """Parse corner statistics from a TotalCorner stats page body text."""
        result = {}
        lines = [l.strip() for l in body_text.splitlines() if l.strip()]
        for i, line in enumerate(lines):
            lower = line.lower()
            if "corner" in lower and "avg" in lower:
                # Try to find numeric value nearby
                for j in range(i, min(i + 3, len(lines))):
                    m = re.search(r'(\d+\.?\d*)', lines[j])
                    if m:
                        result.setdefault("total_corner_avg", float(m.group(1)))
                        break
            if "dangerous attack" in lower:
                for j in range(i, min(i + 3, len(lines))):
                    m = re.search(r'(\d+\.?\d*)\s*[-:]\s*(\d+\.?\d*)', lines[j])
                    if m:
                        result["dangerous_attacks_home"] = float(m.group(1))
                        result["dangerous_attacks_away"] = float(m.group(2))
                        break
        return result

    def get_fixture_stats(self, fixture_id: str) -> list:
        """Get corner stats for a fixture as a stats list."""
        preds = self.get_corner_predictions(fixture_id)
        if not preds:
            return []
        return [{"source": "totalcorner", "type": "corners", "data": preds}]

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list[dict]:
        """Not supported by TotalCorner — returns empty list."""
        return []
