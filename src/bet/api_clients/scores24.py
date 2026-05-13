"""Scores24 API client — multi-sport deep data with trends."""
import logging
import re
from datetime import datetime
from urllib.parse import urlparse

from .base_client import APIError
from .playwright_base import PlaywrightBaseClient
from .api_football import APIFixture
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

# JS to extract match links AND the surrounding text context for team names
_JS_EXTRACT_MATCHES = """() => {
    const links = document.querySelectorAll('a[href*="/m-"]');
    const matches = [];
    for (const link of links) {
        const href = link.getAttribute('href') || '';
        if (!href.includes('/m-')) continue;
        // Get the parent container which usually has team names
        const parent = link.closest('[class*="match"], [class*="event"], article, li, section');
        const text = parent ? parent.textContent.trim() : link.textContent.trim();
        matches.push({
            href: href,
            text: text.substring(0, 200),
        });
    }
    return matches;
}"""

# NOTE: Listing data extracted via page.inner_text('body') + _parse_listing_text()
# rather than JS evaluation, since the React SPA uses styled-components.

class Scores24Client(PlaywrightBaseClient):
    """Scores24 client — multi-sport deep data via Playwright.
    
    Provides: fixture listings, H2H, team form, odds, and structured
    betting trends with hit rates. Trends are the unique value.
    """
    
    SPORT_PATHS = {
        "football": "/en/soccer",
        "tennis": "/en/tennis",
        "basketball": "/en/basketball",
        "hockey": "/en/ice-hockey",
        "volleyball": "/en/volleyball",
    }
    
    # Override cookie selector defined in base class
    _COOKIE_SELECTOR = ""
    
    def __init__(self, rate_limiter: "RateLimiter | None" = None):
        super().__init__(api_name="scores24", base_url="https://scores24.live", rate_limiter=rate_limiter)
    
    def get_fixtures(self, date: str, sport: str = "football") -> list:
        """Get fixtures for a sport from Scores24 listing page.

        Extracts match links and parses body text for team names + kickoff times.
        Returns list of APIFixture objects.
        """
        path = self.SPORT_PATHS.get(sport, "/en/soccer")
        url = f"{self.base_url}{path}"

        cache_key = f"scores24/{sport}/fixtures/{date}"
        cached = self._check_cache(cache_key, ttl_hours=4)
        if cached:
            return [APIFixture(**f) for f in cached.get("fixtures", [])]

        ctx = None
        try:
            if not self.rate_limiter.can_request("scores24-scraper"):
                logger.warning("[Scores24] Rate limit exceeded")
                return []

            ctx, page = self._load_page(url, wait_ms=6000)
            self.rate_limiter.record_request("scores24-scraper", url[:100])

            # Get match links
            matches_data = self._evaluate_js(page, _JS_EXTRACT_MATCHES)
            if not matches_data:
                matches_data = []

            # Also parse body text for structured match data
            body_text = page.inner_text('body')
            text_matches = self._parse_listing_text(body_text, date, sport)

            # Build fixtures from links (for detail URLs) merged with text matches
            fixtures = []
            seen = set()

            # First, use links which give us detail URLs
            for match in matches_data:
                href = match.get("href", "")
                if not href or "/m-" not in href:
                    continue

                home, away, match_date = self._parse_match_slug(href)
                if not home or not away:
                    continue

                # Filter: only include matches for the requested date
                if match_date and match_date != date:
                    continue

                key = f"{home.lower()}_{away.lower()}"
                if key in seen:
                    continue
                seen.add(key)

                kickoff = f"{match_date}T00:00:00Z" if match_date else f"{date}T00:00:00Z"

                fixtures.append(APIFixture(
                    external_id=href,
                    source="scores24",
                    sport=sport,
                    competition_name="",
                    home_team_name=home,
                    away_team_name=away,
                    kickoff=kickoff,
                ))

            # Merge with text-parsed matches that have competition info
            for tm in text_matches:
                key = f"{tm['home'].lower()}_{tm['away'].lower()}"
                if key in seen:
                    # Update competition name from text parsing
                    for f in fixtures:
                        fkey = f"{f.home_team_name.lower()}_{f.away_team_name.lower()}"
                        if fkey == key and not f.competition_name:
                            f.competition_name = tm.get("competition", "")
                            if tm.get("time"):
                                f.kickoff = f"{date}T{tm['time'].zfill(5)}:00Z"
                    continue
                seen.add(key)
                kickoff = f"{date}T{tm['time'].zfill(5)}:00Z" if tm.get("time") else f"{date}T00:00:00Z"
                fixtures.append(APIFixture(
                    external_id=f"s24-{key}",
                    source="scores24",
                    sport=sport,
                    competition_name=tm.get("competition", ""),
                    home_team_name=tm["home"],
                    away_team_name=tm["away"],
                    kickoff=kickoff,
                ))

            self._save_cache(cache_key, {"fixtures": [f.__dict__ for f in fixtures]})
            logger.info(f"[Scores24] Returning {len(fixtures)} fixtures for {sport}")
            return fixtures

        except APIError:
            raise
        except Exception as e:
            logger.error(f"[Scores24] get_fixtures error: {e}")
            return []
        finally:
            if ctx:
                try:
                    ctx.close()
                except Exception:
                    pass

    def _parse_match_slug(self, href: str) -> tuple[str, str, str]:
        """Parse Scores24 match URL slug into (home, away, date).

        URL pattern: /en/soccer/m-DD-MM-YYYY-team1-slug-team2-slug-prediction
        The challenge: team names can have variable word counts.
        We extract the date portion and split the remainder at the midpoint.
        Known limitation: asymmetric team names (e.g., 'PSV Eindhoven' vs 'Ajax')
        may split incorrectly. Text-parsed matches from _parse_listing_text provide
        accurate team names and are merged in get_fixtures.
        """
        # Get the slug part after /m-
        parts = href.split("/m-")
        if len(parts) < 2:
            return "", "", ""

        slug = parts[1].rstrip("/")
        # Remove -prediction suffix
        slug = re.sub(r"-prediction$", "", slug)

        # Extract date: DD-MM-YYYY at the start
        date_match = re.match(r"(\d{2})-(\d{2})-(\d{4})-(.+)", slug)
        if not date_match:
            return "", "", ""

        day, month, year = date_match.group(1), date_match.group(2), date_match.group(3)
        match_date = f"{year}-{month}-{day}"
        team_slug = date_match.group(4)

        # Team slug is like: "arka-gdynia-gornik-zabrze" or "manchester-city-crystal-palace"
        # We can't reliably split this without context, so title-case the whole thing
        # and let downstream matching handle it
        words = team_slug.split("-")

        # Heuristic: try common split points
        # If we have text context from the link, use that instead
        if len(words) >= 2:
            # Try splitting at each position and pick the most balanced
            best_split = len(words) // 2
            home = " ".join(words[:best_split]).title()
            away = " ".join(words[best_split:]).title()
            return home, away, match_date

        return "", "", match_date

    def _parse_listing_text(self, body_text: str, date: str, sport: str) -> list[dict]:
        """Parse structured text from listing page body to extract matches.

        Body text pattern:
        Country
        Competition
        (N matches)
        HH:MM
        DD Mon
        HomeTeam
        AwayTeam
        -
        -
        """
        matches = []
        lines = [l.strip() for l in body_text.splitlines() if l.strip()]

        current_competition = ""
        i = 0
        while i < len(lines) - 3:
            line = lines[i]

            # Detect competition header: line followed by "(N match/es)"
            if i + 1 < len(lines) and re.match(r"\(\d+ match", lines[i + 1]):
                current_competition = line
                i += 2
                continue

            # Detect match: time pattern followed by date, then two team names
            time_match = re.match(r"^(\d{1,2}:\d{2})$", line)
            if time_match and i + 3 < len(lines):
                time_str = time_match.group(1)
                # Next line should be date (e.g., "13 May")
                date_line = lines[i + 1]
                if re.match(r"\d{1,2}\s+\w+", date_line):
                    home = lines[i + 2]
                    away = lines[i + 3]
                    # Validate: team names shouldn't be scores or single chars
                    if len(home) > 1 and len(away) > 1 and not home.startswith("("):
                        matches.append({
                            "home": home,
                            "away": away,
                            "time": time_str,
                            "competition": current_competition,
                        })
                        i += 4
                        # Skip score dashes if present
                        while i < len(lines) and lines[i] in ("-", ""):
                            i += 1
                        continue

            i += 1

        return matches

    def get_match_detail(self, detail_url: str) -> dict:
        """Get full match detail: H2H, form, odds, predictions.

        Navigate to match detail page and extract structured data from body text.
        Returns dict with keys: match_info, odds, h2h, form_home, form_away.
        """
        slug = re.sub(r'[^a-zA-Z0-9_-]', '_', detail_url.split("/")[-1])
        cache_key = f"scores24/detail/{slug}"
        cached = self._check_cache(cache_key, ttl_hours=6)
        if cached:
            return cached

        url = self.base_url + detail_url if detail_url.startswith('/') else detail_url

        # SSRF protection: validate domain for absolute URLs
        if url.startswith("http"):
            parsed = urlparse(url)
            if parsed.netloc not in ("scores24.live", "www.scores24.live"):
                logger.error(f"[Scores24] Rejected non-scores24 URL: {url}")
                return data

        if not self.rate_limiter.can_request("scores24-scraper"):
            logger.warning("[Scores24] Rate limit exceeded for match detail")
            return data

        ctx = None
        data = {
            "match_info": {},
            "odds": {},
            "h2h": {"summary": {}, "matches": []},
            "form_home": [],
            "form_away": [],
        }

        try:
            ctx, page = self._load_page(url, wait_ms=6000)
            self.rate_limiter.record_request("scores24-scraper", url[:100])
            body_text = page.inner_text('body')

            # Parse H2H summary
            if "H2H Stats Matches and Previous Teams Results" in body_text:
                data["h2h"]["summary"] = self._parse_h2h_summary(body_text)

            # Parse odds (W1/X/W2 pattern)
            odds_match = re.search(r'W1\s*\n\s*([\d.]+)\s*\n\s*X\s*\n\s*([\d.]+)\s*\n\s*W2\s*\n\s*([\d.]+)', body_text)
            if odds_match:
                data["odds"] = {
                    "w1": float(odds_match.group(1)),
                    "x": float(odds_match.group(2)),
                    "w2": float(odds_match.group(3)),
                }

            found = []
            if data["odds"]:
                found.append("odds")
            if data["h2h"]["summary"]:
                found.append("h2h")
            logger.info(f"[Scores24] Match detail for {slug}: found {', '.join(found) or 'nothing'}")

            self._save_cache(cache_key, data)
            return data
        except APIError:
            raise
        except Exception as e:
            logger.error(f"[Scores24] get_match_detail error: {e}")
            return data
        finally:
            if ctx:
                try:
                    ctx.close()
                except Exception:
                    pass

    def _parse_h2h_summary(self, body_text: str) -> dict:
        """Extract H2H summary stats from body text."""
        summary = {}
        lines = body_text.splitlines()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == "Total games" and i + 1 < len(lines):
                try:
                    summary["total_games"] = int(lines[i + 1].strip())
                except ValueError:
                    pass
            elif stripped == "Total Goals Avg" and i + 1 < len(lines):
                try:
                    summary["total_goals_avg"] = float(lines[i + 1].strip())
                except ValueError:
                    pass
            elif stripped == "Both teams scored" and i + 1 < len(lines):
                pct = lines[i + 1].strip().rstrip("%")
                try:
                    summary["btts_pct"] = float(pct)
                except ValueError:
                    pass
        return summary

    def get_trends(self, detail_url: str) -> list[dict]:
        """Get betting trends from match detail page.

        Navigate to detail URL with #trends hash to load trends tab.
        Returns list of trend dicts with: category, tip, odds, description.

        This is the UNIQUE VALUE of Scores24 — structured betting tips
        with categories (Match Result, Over/Under, Corners, Cards, etc.)
        """
        url = self.base_url + detail_url if detail_url.startswith('/') else detail_url
        if "#trends" not in url:
            url += "#trends"

        # SSRF protection
        parsed = urlparse(url.split("#")[0])
        if parsed.netloc not in ("scores24.live", "www.scores24.live"):
            logger.error(f"[Scores24] Rejected non-scores24 URL: {url}")
            return []

        slug = re.sub(r'[^a-zA-Z0-9_-]', '_', detail_url.split("/")[-1])
        cache_key = f"scores24/trends/{slug}"
        cached = self._check_cache(cache_key, ttl_hours=6)
        if cached:
            return cached

        if not self.rate_limiter.can_request("scores24-scraper"):
            logger.warning("[Scores24] Rate limit exceeded for trends")
            return []

        ctx = None
        trends = []
        try:
            ctx, page = self._load_page(url, wait_ms=6000)

            # Try clicking Trends tab if hash navigation didn't work
            try:
                trends_tab = page.locator('text=Trends')
                if trends_tab.is_visible(timeout=3000):
                    trends_tab.click()
                    page.wait_for_timeout(2000)
            except Exception:
                pass

            body_text = page.inner_text('body')
            trends = self._parse_trends_text(body_text)

            self._save_cache(cache_key, trends)
            return trends
        except APIError:
            raise
        except Exception as e:
            logger.error(f"[Scores24] get_trends error: {e}")
            return []
        finally:
            if ctx:
                try:
                    ctx.close()
                except Exception:
                    pass

    def _parse_trends_text(self, body_text: str) -> list[dict]:
        """Parse trends from body text.

        Pattern observed:
        Match Result predictions
        (1)
        2.06
        Gornik have drawn in the 1st half
        in last 6 away games (Ekstraklasa).
        1st Half Draw
        2.06
        Over/Under predictions
        (7)
        1.19 - 2.06
        Corners predictions
        (3)
        1.35 - 1.55
        """
        trends = []
        lines = [l.strip() for l in body_text.splitlines() if l.strip()]

        current_category = ""
        i = 0
        while i < len(lines):
            line = lines[i]

            # Detect category header: ends with "predictions"
            if line.endswith("predictions"):
                current_category = line.replace(" predictions", "")
                i += 1
                # Skip count like "(7)" and odds range like "1.19 - 2.06"
                # Do NOT consume single bare odds — those belong to individual tips
                while i < len(lines) and (
                    re.match(r'^\(\d+\)$', lines[i]) or
                    re.match(r'^[\d.]+ - [\d.]+$', lines[i])
                ):
                    # Capture the odds range for this category
                    if re.match(r'^[\d.]+ - [\d.]+$', lines[i]):
                        odds_parts = lines[i].split(' - ')
                        trends.append({
                            "category": current_category,
                            "tip": current_category,
                            "odds_low": float(odds_parts[0]),
                            "odds_high": float(odds_parts[1]),
                            "description": "",
                        })
                    i += 1
                continue

            # Detect individual tip within a category
            if current_category and i + 1 < len(lines):
                odds_match = re.match(r'^([\d.]+)$', lines[i])
                if odds_match:
                    # Line before odds = tip name, line before that = description
                    tip_name = lines[i - 1] if i > 0 else ""
                    desc = lines[i - 2] if i > 1 else ""
                    trends.append({
                        "category": current_category,
                        "tip": tip_name,
                        "odds": float(odds_match.group(1)),
                        "description": desc,
                    })

            i += 1

        return trends

    def get_fixture_stats(self, fixture_id: str) -> list:
        """Get stats via match detail page. fixture_id should be a detail URL."""
        data = self.get_match_detail(fixture_id)
        h2h_summary = data.get("h2h", {}).get("summary", {})
        if not h2h_summary:
            return []
        return [{"source": "scores24", "type": "h2h_summary", "data": h2h_summary}]

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list[dict]:
        """Not directly supported — use get_match_detail(detail_url) instead."""
        return []
