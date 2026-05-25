"""bo3.gg scraper — CS2 & Valorant statistics and odds (HTTP fallback for HLTV).

Access: Standard HTTP + BeautifulSoup (no Cloudflare issues).
Rate limit: 3 seconds between requests (self-imposed).
Coverage: Professional CS2 & Valorant — similar to HLTV but less detailed.
Purpose: Fallback when HLTV is blocked by Cloudflare, plus odds extraction.
"""

import logging
import re
import time
from typing import Any

import requests
from bs4 import BeautifulSoup

from bet.scrapers.constants import USER_AGENTS

logger = logging.getLogger(__name__)

BASE_URL = "https://bo3.gg"
RATE_LIMIT_SECONDS = 3.0


class Bo3GGScraper:
    """bo3.gg scraper for CS2 team and match statistics.

    HTTP-accessible fallback when HLTV Cloudflare blocks.
    """

    def __init__(self):
        self._last_request_time = 0.0
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENTS[0]})
        self._team_url_cache: dict[str, str | None] = {}

    def _get(self, url: str) -> BeautifulSoup | None:
        """Rate-limited HTTP GET returning parsed HTML."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < RATE_LIMIT_SECONDS:
            time.sleep(RATE_LIMIT_SECONDS - elapsed)

        try:
            resp = self._session.get(url, timeout=15)
        except requests.RequestException as e:
            self._last_request_time = time.monotonic()
            logger.warning("bo3.gg request failed: %s — %s", url, e)
            return None

        self._last_request_time = time.monotonic()
        if resp.status_code != 200:
            logger.warning("bo3.gg %s returned %d", url, resp.status_code)
            return None
        return BeautifulSoup(resp.text, "html.parser")

    def search_team(self, name: str) -> str | None:
        """Resolve team name → bo3.gg team URL path (Playwright required — SPA)."""
        lower = name.lower().strip()
        if lower in self._team_url_cache:
            return self._team_url_cache[lower]

        # bo3.gg is a JS-rendered SPA — must use Playwright
        soup = self._get_rendered(
            f"{BASE_URL}/search?q={requests.utils.quote(name)}",
            wait_selector="a[href*='/team']",
            timeout_ms=10000,
        )
        if not soup:
            self._team_url_cache[lower] = None
            return None

        # Find first team link in search results
        team_link = soup.select_one("a[href*='/team/']")
        if team_link:
            href = team_link.get("href", "")
            self._team_url_cache[lower] = href
            return href

        self._team_url_cache[lower] = None
        return None

    def get_team_stats(self, team_name: str) -> dict:
        """Scrape team statistics from bo3.gg (Playwright required — SPA).

        Returns:
            {
                "maps_played": int,
                "maps_won": int,
                "map_win_rate": float,
                "win_rate_l10": float,
                "matches_found": int,
                "rating": float | None,
            }
        """
        team_url = self.search_team(team_name)
        if not team_url:
            logger.warning("bo3.gg: could not find team '%s'", team_name)
            return {}

        # bo3.gg is fully JS-rendered — must use Playwright
        soup = self._get_rendered(
            f"{BASE_URL}{team_url}",
            wait_selector="body",
            timeout_ms=12000,
        )
        if not soup:
            return {}

        stats: dict[str, Any] = {}

        # Look for overall stats in team profile
        stat_items = soup.select(".team-stat, .stat-item, .stats-row")
        for item in stat_items:
            text = item.get_text().strip().lower()
            # Try to extract maps/wins/losses
            maps_match = re.search(r"maps?[:\s]+(\d+)", text)
            wins_match = re.search(r"wins?[:\s]+(\d+)", text)
            rate_match = re.search(r"win\s*rate[:\s]+([\d.]+)%?", text)

            if maps_match:
                stats["maps_played"] = int(maps_match.group(1))
            if wins_match:
                stats["maps_won"] = int(wins_match.group(1))
            if rate_match:
                stats["map_win_rate"] = float(rate_match.group(1))

        # Also try to parse from full page text (SPA often uses different selectors)
        page_text = soup.get_text(" ", strip=True)
        if "maps_played" not in stats:
            mp = re.search(r"(\d+)\s*maps?\s*played", page_text, re.IGNORECASE)
            if mp:
                stats["maps_played"] = int(mp.group(1))
        if "map_win_rate" not in stats:
            wr = re.search(r"win\s*rate[:\s]*([\d.]+)\s*%", page_text, re.IGNORECASE)
            if wr:
                stats["map_win_rate"] = float(wr.group(1))

        # Recent matches for L10
        matches_soup = self._get_rendered(
            f"{BASE_URL}{team_url}/matches",
            wait_selector="body",
            timeout_ms=12000,
        )
        if matches_soup:
            match_rows = matches_soup.select(".match-row, .result-row")[:10]
            wins = 0
            for row in match_rows:
                # Look for win indicator
                if "win" in (row.get("class") or []) or row.select_one(".win, .match-won"):
                    wins += 1
                else:
                    # Check score
                    scores = row.select(".score, .match-score")
                    if len(scores) >= 2:
                        try:
                            s1 = int(re.search(r"\d+", scores[0].get_text()).group())
                            s2 = int(re.search(r"\d+", scores[1].get_text()).group())
                            if s1 > s2:
                                wins += 1
                        except (ValueError, AttributeError):
                            pass

            n = len(match_rows)
            if n > 0:
                stats["win_rate_l10"] = round(wins / n * 100, 1)
                stats["matches_found"] = n

        return stats

    def get_team_map_pool(self, team_name: str) -> dict:
        """Scrape map-specific stats (Playwright required — SPA).

        Returns:
            {"map_name": {"played": int, "won": int, "win_rate": float}, ...}
        """
        team_url = self.search_team(team_name)
        if not team_url:
            return {}

        soup = self._get_rendered(
            f"{BASE_URL}{team_url}/maps",
            wait_selector="body",
            timeout_ms=12000,
        )
        if not soup:
            return {}

        map_pool: dict[str, dict] = {}
        map_items = soup.select(".map-stat, .map-row")
        for item in map_items:
            name_el = item.select_one(".map-name, .name")
            if not name_el:
                continue
            map_name = name_el.get_text().strip()

            played = 0
            win_rate = 0.0
            # Extract numbers from row
            numbers = re.findall(r"[\d.]+", item.get_text())
            if len(numbers) >= 2:
                try:
                    played = int(numbers[0])
                    win_rate = float(numbers[1])
                except (ValueError, IndexError):
                    pass

            if played > 0:
                map_pool[map_name] = {
                    "played": played,
                    "won": round(played * win_rate / 100),
                    "win_rate": win_rate,
                }

        return map_pool

    def get_h2h(self, team_a: str, team_b: str) -> dict:
        """Head-to-head between two teams (Playwright required — SPA).

        Returns:
            {
                "matches_found": int,
                "team_a_wins": int,
                "team_b_wins": int,
            }
        """
        team_a_url = self.search_team(team_a)
        if not team_a_url:
            return {"matches_found": 0, "team_a_wins": 0, "team_b_wins": 0}

        # Try team A's matches page and filter for team B
        soup = self._get_rendered(
            f"{BASE_URL}{team_a_url}/matches",
            wait_selector="body",
            timeout_ms=12000,
        )
        if not soup:
            return {"matches_found": 0, "team_a_wins": 0, "team_b_wins": 0}

        team_b_lower = team_b.lower()
        a_wins = 0
        h2h_count = 0

        match_rows = soup.select(".match-row, .result-row")
        for row in match_rows:
            opponent = row.select_one(".opponent, .team-name")
            if not opponent:
                continue
            opp_text = opponent.get_text().strip().lower()
            if team_b_lower not in opp_text and opp_text not in team_b_lower:
                continue

            h2h_count += 1
            if "win" in " ".join(row.get("class", [])) or row.select_one(".win, .match-won"):
                a_wins += 1
            else:
                scores = row.select(".score, .match-score")
                if len(scores) >= 2:
                    try:
                        s1 = int(re.search(r"\d+", scores[0].get_text()).group())
                        s2 = int(re.search(r"\d+", scores[1].get_text()).group())
                        if s1 > s2:
                            a_wins += 1
                    except (ValueError, AttributeError):
                        pass

        return {
            "matches_found": h2h_count,
            "team_a_wins": a_wins,
            "team_b_wins": h2h_count - a_wins,
        }

    # --- Playwright-based methods for JS-rendered pages (odds, match details) ---

    def _ensure_browser(self):
        """Lazy-init Playwright browser for JS-rendered bo3.gg pages."""
        if hasattr(self, "_browser") and self._browser is not None:
            return True
        try:
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            return True
        except Exception as e:
            logger.warning("bo3.gg: Playwright not available: %s", e)
            self._browser = None
            return False

    def _get_rendered(self, url: str, wait_selector: str = "a[href*='/matches/']", timeout_ms: int = 12000, use_networkidle: bool = False) -> BeautifulSoup | None:
        """Fetch a JS-rendered page via Playwright with rate limiting."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < RATE_LIMIT_SECONDS:
            time.sleep(RATE_LIMIT_SECONDS - elapsed)

        if not self._ensure_browser():
            return None

        page = None
        try:
            page = self._browser.new_page(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
            )
            wait_until = "networkidle" if use_networkidle else "domcontentloaded"
            page.goto(url, wait_until=wait_until, timeout=15000)
            page.wait_for_selector(wait_selector, timeout=timeout_ms)
            time.sleep(4 if use_networkidle else 1)  # Longer sleep for detail pages
            html = page.content()
            return BeautifulSoup(html, "html.parser")
        except Exception as e:
            logger.warning("bo3.gg rendered fetch failed: %s — %s", url, e)
            return None
        finally:
            if page:
                try:
                    page.close()
                except Exception:
                    pass
            self._last_request_time = time.monotonic()

    def close_browser(self):
        """Close Playwright browser."""
        if hasattr(self, "_browser") and self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if hasattr(self, "_pw") and self._pw:
            try:
                self._pw.stop()
            except Exception:
                pass
            self._pw = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close_browser()

    def get_valorant_matches_with_odds(self) -> list[dict]:
        """Fetch current Valorant matches with ML odds from bo3.gg (Playwright).

        Returns list of dicts with: home_team, away_team, match_url, format,
        odds_home, odds_away, kickoff_time, n_extra_markets, tournament.
        """
        soup = self._get_rendered(
            f"{BASE_URL}/valorant/matches/current",
            wait_selector="a[href*='/valorant/matches/']",
        )
        if not soup:
            return []
        return self._parse_matches_from_soup(soup, "/valorant/matches/")

    def get_cs2_matches_with_odds(self) -> list[dict]:
        """Fetch current CS2 matches with ML odds from bo3.gg (Playwright)."""
        soup = self._get_rendered(
            f"{BASE_URL}/matches/current",
            wait_selector="a[href*='/matches/']",
        )
        if not soup:
            return []
        return [m for m in self._parse_matches_from_soup(soup, "/matches/")
                if "/valorant/" not in m["match_url"]]

    def _parse_matches_from_soup(self, soup: BeautifulSoup, match_path: str) -> list[dict]:
        """Parse match list page for teams, odds, format."""
        matches: list[dict] = []
        seen_urls: set[str] = set()

        # Find all match links containing "vs" (individual match pages)
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if match_path not in href or "vs" not in href:
                continue
            if href.endswith("/predictions") or href.endswith("/stats"):
                continue

            text = a_tag.get_text(" ", strip=True)
            if not text or len(text) < 5:
                continue

            # Skip navigation/pagination links
            if not re.search(r"\bBo[135]\b", text):
                continue

            full_url = href if href.startswith("http") else f"{BASE_URL}{href}"
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            # Extract format
            fmt_match = re.search(r"\b(Bo[135])\b", text)
            fmt = fmt_match.group(1) if fmt_match else "Bo3"

            # Extract time
            time_match = re.match(r"^(LIVE|\d{1,2}:\d{2})", text)
            kickoff_time = time_match.group(1) if time_match else ""
            if kickoff_time:
                text = text[len(kickoff_time):].strip()

            # Split by BoN to get team names
            parts = re.split(r"\bBo[135]\b", text)
            if len(parts) < 2:
                continue
            home_team = parts[0].strip()
            away_raw = parts[1].strip()
            # Remove trailing number (extra markets count)
            away_team = re.sub(r"\s+\d+$", "", away_raw).strip()

            if not home_team or not away_team:
                continue

            # Look for odds in sibling elements
            odds_home, odds_away, n_extra = None, None, 0
            parent = a_tag.parent
            if parent:
                parent_text = parent.get_text(" ", strip=True)
                odds_match = re.search(
                    r"(\d+\.\d{2})\s+(\d+\.\d{2})(?:\s+\+(\d+))?", parent_text
                )
                if odds_match:
                    odds_home = float(odds_match.group(1))
                    odds_away = float(odds_match.group(2))
                    if odds_match.group(3):
                        n_extra = int(odds_match.group(3))

            matches.append({
                "home_team": home_team,
                "away_team": away_team,
                "match_url": full_url,
                "format": fmt,
                "odds_home": odds_home,
                "odds_away": odds_away,
                "tournament": "",
                "kickoff_time": kickoff_time,
                "n_extra_markets": n_extra,
            })

        return matches

    def get_cs2_match_detail(self, match_url: str) -> dict:
        """Fetch CS2 match page with team form, map winrates, H2H (Playwright).

        Extracts structured data from bo3.gg match pages including:
        - Team form (last 5 matches with scores)
        - Historical map winrate per map (6 months)
        - Head to head results
        - ML odds
        - Lineups
        - Analytics insights (text)

        Returns dict with per-team stats suitable for team_form enrichment.
        """
        soup = self._get_rendered(match_url, wait_selector="body", timeout_ms=15000, use_networkidle=True)
        if not soup:
            return {}

        text = soup.get_text(" ", strip=True)
        details: dict[str, Any] = {
            "home_team": "",
            "away_team": "",
            "ml_odds": {},
            "format": "Bo3",
            "h2h": [],
            "form_home": [],
            "form_away": [],
            "map_winrate_home": {},
            "map_winrate_away": {},
            "lineups_home": [],
            "lineups_away": [],
            "insights": [],
        }

        # Format
        fmt_match = re.search(r"\b(Bo[135])\b", text)
        if fmt_match:
            details["format"] = fmt_match.group(1)

        # ML odds: "1 X.XX 2 X.XX"
        ml_match = re.search(r"\b1\s+(\d+\.\d+)\s+2\s+(\d+\.\d+)\b", text)
        if ml_match:
            details["ml_odds"] = {
                "home": float(ml_match.group(1)),
                "away": float(ml_match.group(2)),
            }

        # Team names from h1 heading: "TeamA vs TeamB at Tournament"
        h1 = soup.select_one("h1")
        if h1:
            h1_text = h1.get_text(strip=True)
            vs_match = re.match(r"(.+?)\s+vs\s+(.+?)\s+at\s+", h1_text)
            if vs_match:
                details["home_team"] = vs_match.group(1).strip()
                details["away_team"] = vs_match.group(2).strip()

        # Team Form: Parse match results (W/L from score lines)
        # Look for patterns like "BIG Academy\nBERG\n2\n0" or with odds
        form_sections = soup.find_all(string=re.compile(r"TEAM FORM", re.IGNORECASE))
        if form_sections:
            # Get the parent container
            form_container = form_sections[0].find_parent()
            if form_container:
                # Find all score patterns: number pairs like "2 0", "2 1", "1 2"
                # Parse by looking at elements after TEAM FORM
                pass

        # Parse form from text - look for consecutive match scores
        # Pattern: Team won if first score > second score in each match
        form_pattern = re.findall(
            r"(\d+)\s+days?\s+ago.*?(\d)\s+(\d)",
            text, re.DOTALL
        )

        # Lineups from player links
        player_links = soup.find_all("a", href=lambda h: h and "/players/" in h)
        player_names = []
        seen_players: set[str] = set()
        for pl in player_links:
            name = pl.get_text(strip=True)
            if name and name not in seen_players and len(name) < 20:
                seen_players.add(name)
                player_names.append(name)
        if len(player_names) >= 10:
            details["lineups_home"] = player_names[:5]
            details["lineups_away"] = player_names[5:10]
        elif len(player_names) >= 5:
            details["lineups_home"] = player_names[:5]

        # Map winrate: Parse percentages per map
        # Pattern: "Anubis 50% ... Overpass 85%" etc.
        map_names = ["Anubis", "Overpass", "Nuke", "Mirage", "Inferno", "Ancient", "Dust II", "Vertigo", "Train"]
        # Find "HISTORICAL MAPS WINRATE" section
        maps_section = re.search(
            r"(?:Historical|HISTORICAL)\s+Maps?\s+(?:winrate|WINRATE)(.+?)(?:HEAD TO HEAD|Head to head|COMMENTS|Comments)",
            text, re.IGNORECASE | re.DOTALL
        )
        if maps_section:
            maps_text = maps_section.group(1)
            # Parse map winrates - look for "MapName XX%" patterns
            # Structure is usually: MapName | HomeWR% | AwayWR%
            for map_name in map_names:
                # Try to find all percentages after the map name
                pct_matches = re.findall(
                    rf"{map_name}.*?(\d+)%.*?(\d+)%",
                    maps_text, re.DOTALL
                )
                if pct_matches:
                    details["map_winrate_home"][map_name] = int(pct_matches[0][0])
                    details["map_winrate_away"][map_name] = int(pct_matches[0][1])

        # H2H section
        h2h_section = re.search(
            r"(?:HEAD TO HEAD|Head to head)(.+?)(?:COMMENTS|Comments|$)",
            text, re.IGNORECASE | re.DOTALL
        )
        if h2h_section:
            # Look for score patterns: "TeamA X - Y TeamB" or "X : Y"
            h2h_matches = re.findall(
                r"(\d+)\s*[-–:]\s*(\d+)",
                h2h_section.group(1)
            )
            for m in h2h_matches:
                details["h2h"].append({
                    "home_score": int(m[0]),
                    "away_score": int(m[1]),
                })

        # Analytics insights
        insights_section = re.search(
            r"(?:ANALYTICS INSIGHTS|Analytics Insights)(.+?)(?:TEAM FORM|Team Form)",
            text, re.IGNORECASE | re.DOTALL
        )
        if insights_section:
            # Extract bullet points
            sentences = [s.strip() for s in insights_section.group(1).split(".")
                        if len(s.strip()) > 20]
            details["insights"] = sentences[:8]

        # Calculate win_rate from form (if available from page structure)
        # Use score pattern: look for "SCORE" columns in team form tables
        score_cells = soup.select("[class*='score'], [class*='Score']")
        if score_cells:
            # Try to parse home/away form from score columns
            scores = []
            for cell in score_cells:
                t = cell.get_text(strip=True)
                if re.match(r"^\d+$", t):
                    scores.append(int(t))

            # Scores come in pairs (home_score, away_score per match)
            if len(scores) >= 4:
                # First half = home team matches, second half = away team matches
                mid = len(scores) // 2
                home_scores = list(zip(scores[:mid:2], scores[1:mid:2]))
                away_scores = list(zip(scores[mid::2], scores[mid + 1::2]))

                home_wins = sum(1 for s1, s2 in home_scores if s1 > s2)
                away_wins = sum(1 for s1, s2 in away_scores if s1 > s2)

                if home_scores:
                    details["form_home"] = [
                        "W" if s1 > s2 else "L" for s1, s2 in home_scores
                    ]
                if away_scores:
                    details["form_away"] = [
                        "W" if s1 > s2 else "L" for s1, s2 in away_scores
                    ]

        return details

    def get_valorant_match_detail(self, match_url: str) -> dict:
        """Fetch detailed match page: odds, H2H, map pool, lineups (Playwright).

        Returns dict with ml_odds, handicap, h2h, map_pool_home/away,
        form_home/away, lineups_home/away, format, tournament, stage.
        """
        soup = self._get_rendered(match_url, wait_selector="body", timeout_ms=15000, use_networkidle=True)
        if not soup:
            return {}

        details: dict[str, Any] = {
            "ml_odds": {},
            "handicap": {},
            "h2h": [],
            "map_pool_home": {},
            "map_pool_away": {},
            "form_home": [],
            "form_away": [],
            "lineups_home": [],
            "lineups_away": [],
            "format": "Bo3",
            "tournament": "",
            "stage": "",
        }

        text = soup.get_text(" ", strip=True)

        # Format
        fmt_match = re.search(r"\b(Bo[135])\b", text)
        if fmt_match:
            details["format"] = fmt_match.group(1)

        # ML odds: pattern "1 2.05 2 1.74"
        ml_match = re.search(r"\b1\s+(\d+\.\d+)\s+2\s+(\d+\.\d+)\b", text)
        if ml_match:
            details["ml_odds"] = {
                "home": float(ml_match.group(1)),
                "away": float(ml_match.group(2)),
            }

        # Handicap: "G2 Esports handicap (maps) +1.5"
        hc_match = re.search(
            r"(\w[\w\s]+?)\s+handicap\s*\(maps\)\s*\+?([\d.]+)",
            text, re.IGNORECASE,
        )
        if hc_match:
            # Look for odds after handicap
            hc_rest = text[hc_match.end():]
            hc_odds_m = re.search(r"(\d+\.\d+)", hc_rest[:30])
            details["handicap"] = {
                "team": hc_match.group(1).strip(),
                "line": float(hc_match.group(2)),
                "odds": float(hc_odds_m.group(1)) if hc_odds_m else None,
            }

        # H2H: "Leviatán 2 - 1 G2 Esports"
        h2h_pattern = re.finditer(
            r"(\d+\s+(?:day|week|month|year)s?\s+ago)\s+([\w\s]+?)\s+(\d+)\s*[-–]\s*(\d+)\s+([\w\s]+?)(?=\d+\s+(?:day|week|month|year)|$)",
            text,
        )
        for m in h2h_pattern:
            details["h2h"].append({
                "date": m.group(1).strip(),
                "team_a": m.group(2).strip(),
                "score_a": int(m.group(3)),
                "score_b": int(m.group(4)),
                "team_b": m.group(5).strip(),
            })

        # Form: W/L sequences
        form_section = re.search(r"TEAM\s+FORM(.*?)(?:HEAD TO HEAD|LINEUPS|$)", text, re.IGNORECASE | re.DOTALL)
        if form_section:
            wl = re.findall(r"\b([WL])\b", form_section.group(1))
            if len(wl) >= 10:
                details["form_home"] = wl[:5]
                details["form_away"] = wl[5:10]
            elif len(wl) >= 5:
                details["form_home"] = wl[:5]

        # Lineups: player names from /players/ links
        player_links = soup.find_all("a", href=lambda h: h and "/players/" in h)
        player_names = []
        seen_players: set[str] = set()
        for pl in player_links:
            name = pl.get_text(strip=True)
            if name and name not in seen_players and len(name) < 20:
                seen_players.add(name)
                player_names.append(name)
        if len(player_names) >= 10:
            details["lineups_home"] = player_names[:5]
            details["lineups_away"] = player_names[5:10]

        # Map pool win rates
        map_names = ["LOTUS", "ABYSS", "BREEZE", "ASCENT", "FRACTURE",
                     "PEARL", "CORRODE", "SPLIT", "HAVEN", "BIND", "SUNSET"]
        for map_name in map_names:
            pattern = re.search(
                rf"{map_name}\s+(\d+)%",
                text, re.IGNORECASE,
            )
            if pattern:
                details["map_pool_home"][map_name.capitalize()] = {
                    "wr": float(pattern.group(1)),
                }

        return details
