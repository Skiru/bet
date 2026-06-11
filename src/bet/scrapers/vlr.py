"""VLR.gg scraper — Valorant team and match statistics.

Access: Standard HTTP + BeautifulSoup (confirmed working without Playwright).
Rate limit: 1 request per 3 seconds (self-imposed).
Coverage: All VCT regions, Champions Tour, Challengers, Game Changers.
"""

import logging
import re
import time
import unicodedata
import urllib.parse
from typing import Any

import requests
from bs4 import BeautifulSoup

from bet.scrapers.constants import USER_AGENTS

logger = logging.getLogger(__name__)

BASE_URL = "https://www.vlr.gg"
RATE_LIMIT_SECONDS = 3.0


class VLRScraper:
    """VLR.gg scraper for Valorant team and match statistics."""

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
            logger.warning("VLR.gg request failed: %s — %s", url, e)
            return None

        self._last_request_time = time.monotonic()
        if resp.status_code != 200:
            logger.warning("VLR.gg %s returned %d", url, resp.status_code)
            return None
        return BeautifulSoup(resp.text, "html.parser")

    def search_team(self, name: str) -> str | None:
        """Resolve team name → VLR team URL path (e.g., '/team/123/sentinels').

        Uses VLR search and caches results. Prefers exact matches.
        """
        lower = name.lower().strip()
        if lower in self._team_url_cache:
            return self._team_url_cache[lower]
        
        # Normalize name for comparison (remove diacritics)
        def normalize_for_match(s):
            n = unicodedata.normalize('NFKD', s)
            return ''.join(c for c in n if not unicodedata.combining(c)).lower().strip()
        
        normalized_query = normalize_for_match(name)

        soup = self._get(f"{BASE_URL}/search/?q={requests.utils.quote(name)}&type=teams")
        if not soup:
            self._team_url_cache[lower] = None
            return None

        # Find all team results
        team_items = soup.select("a.search-item[href*='/search/r/team/']")
        best_match = None
        best_score = 0
        
        for item in team_items:
            title_el = item.select_one(".search-item-title")
            if not title_el:
                continue
            title = title_el.get_text().strip()
            href = item.get("href", "")
            title_normalized = normalize_for_match(title)
            
            # Score the match: exact = 100, starts_with = 50, contains = 25
            if title_normalized == normalized_query:
                score = 100
            elif title_normalized.startswith(normalized_query) or normalized_query.startswith(title_normalized):
                score = 50
            elif title_normalized in normalized_query or normalized_query in title_normalized:
                score = 25
            else:
                score = 0
            
            if score > best_score:
                best_score = score
                best_match = href

        if best_match:
            # Follow redirect to get final URL
            try:
                resp = self._session.head(f"{BASE_URL}{best_match}", allow_redirects=True, timeout=10)
                final_url = resp.url
                # Extract path from final URL
                parsed = urllib.parse.urlparse(final_url)
                href = parsed.path
                self._team_url_cache[lower] = href
                return href
            except Exception:
                # Fallback: use the redirect path
                self._team_url_cache[lower] = best_match
                return best_match

        self._team_url_cache[lower] = None
        return None

    def get_team_stats(self, team_name: str) -> dict:
        """Scrape team profile + recent matches.

        Returns:
            {
                "team_name": str,
                "team_tag": str | None,
                "maps_played": int,
                "maps_won": int,
                "map_win_rate": float,
                "avg_rounds_per_map": float,
                "win_rate_l10": float,
                "ranking": int | None,
                "matches_found": int,
            }
        """
        team_url = self.search_team(team_name)
        if not team_url:
            logger.warning("VLR: could not find team '%s'", team_name)
            return {}

        # Get team page
        soup = self._get(f"{BASE_URL}{team_url}")
        if not soup:
            return {}

        stats: dict[str, Any] = {}

        # Parse team name from team-header-name section
        team_name_el = soup.select_one(".team-header-name h1.wf-title")
        if team_name_el:
            stats["team_name"] = team_name_el.get_text().strip()
        
        team_tag_el = soup.select_one(".team-header-tag")
        if team_tag_el:
            stats["team_tag"] = team_tag_el.get_text().strip()

        # Parse record from team header (e.g., "Record: 45W - 12L")
        record_el = soup.select_one(".team-summary-container-2")
        if record_el:
            record_text = record_el.get_text()
            wins_match = re.search(r"(\d+)W", record_text)
            losses_match = re.search(r"(\d+)L", record_text)
            if wins_match and losses_match:
                wins = int(wins_match.group(1))
                losses = int(losses_match.group(1))
                total = wins + losses
                stats["maps_won"] = wins
                stats["maps_played"] = total
                stats["map_win_rate"] = round(wins / total * 100, 1) if total else 0

        # Get recent matches for L10 and round averages
        matches_url = f"{BASE_URL}{team_url}/?group=completed"
        matches_soup = self._get(matches_url)
        if matches_soup:
            match_items = matches_soup.select(".wf-card.fc-flex.m-item")[:10]
            wins = 0
            total_maps_won = 0
            total_maps_played = 0

            for item in match_items:
                # Check if team won
                score_spans = item.select(".m-item-result span")
                if len(score_spans) >= 2:
                    try:
                        s1 = int(score_spans[0].get_text().strip())
                        s2 = int(score_spans[1].get_text().strip())
                        if s1 > s2:
                            wins += 1
                        total_maps_won += s1
                        total_maps_played += s1 + s2
                    except (ValueError, IndexError):
                        pass

            n_matches = len(match_items)
            if n_matches > 0:
                stats["win_rate_l10"] = round(wins / n_matches * 100, 1)
                stats["matches_found"] = n_matches
                # Estimate rounds_won_avg per map: winning team avg ~13, losing ~11
                # Approximation from map win rate (Valorant maps are first-to-13)
                if total_maps_played > 0:
                    map_wr = total_maps_won / total_maps_played
                    stats["rounds_won_avg"] = round(11.0 + map_wr * 4.0, 1)  # 11-15 range

        # Try ranking
        rank_el = soup.select_one(".rank-num")
        if rank_el:
            try:
                stats["ranking"] = int(rank_el.get_text().strip().replace("#", ""))
            except ValueError:
                pass

        return stats

    def get_team_map_pool(self, team_name: str) -> dict:
        """Scrape map-specific stats from team stats page.

        Returns:
            {"map_name": {"played": int, "won": int, "win_rate": float}, ...}
        """
        team_url = self.search_team(team_name)
        if not team_url:
            return {}

        # VLR team stats page
        soup = self._get(f"{BASE_URL}{team_url}/?group=stats")
        if not soup:
            return {}

        map_pool: dict[str, dict] = {}
        # Look for map stats table
        map_rows = soup.select(".wf-table-inset tr")
        for row in map_rows:
            cells = row.select("td")
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
        """Find head-to-head matches between two teams.

        Returns:
            {
                "matches_found": int,
                "team_a_wins": int,
                "team_b_wins": int,
                "avg_rounds_per_map": float,
            }
        """
        team_a_url = self.search_team(team_a)
        if not team_a_url:
            return {"matches_found": 0, "team_a_wins": 0, "team_b_wins": 0, "avg_rounds_per_map": 0}

        # Get team A completed matches
        soup = self._get(f"{BASE_URL}{team_a_url}/?group=completed")
        if not soup:
            return {"matches_found": 0, "team_a_wins": 0, "team_b_wins": 0, "avg_rounds_per_map": 0}

        team_b_lower = team_b.lower()
        a_wins = 0
        h2h_count = 0

        match_items = soup.select(".wf-card.fc-flex.m-item")
        for item in match_items:
            # Check if opponent matches team_b
            teams = item.select(".m-item-team-name")
            opponent_name = ""
            for t in teams:
                t_text = t.get_text().strip().lower()
                if team_b_lower in t_text or t_text in team_b_lower:
                    opponent_name = t_text
                    break

            if not opponent_name:
                continue

            h2h_count += 1
            # Check result
            score_spans = item.select(".m-item-result span")
            if len(score_spans) >= 2:
                try:
                    s1 = int(score_spans[0].get_text().strip())
                    s2 = int(score_spans[1].get_text().strip())
                    if s1 > s2:
                        a_wins += 1
                except (ValueError, IndexError):
                    pass

        return {
            "matches_found": h2h_count,
            "team_a_wins": a_wins,
            "team_b_wins": h2h_count - a_wins,
            "avg_rounds_per_map": 0,  # Would need per-match detail pages
        }

    def get_upcoming_matches(self) -> list[dict]:
        """Scrape upcoming matches for fixture verification."""
        soup = self._get(f"{BASE_URL}/matches")
        if not soup:
            return []

        matches = []
        items = soup.select(".match-item")
        for item in items:
            teams = item.select(".match-item-vs-team-name")
            if len(teams) >= 2:
                home = teams[0].get_text().strip()
                away = teams[1].get_text().strip()

                time_el = item.select_one(".match-item-time")
                match_time = time_el.get_text().strip() if time_el else ""

                event_el = item.select_one(".match-item-event")
                event = event_el.get_text().strip() if event_el else ""

                matches.append({
                    "home_team": home,
                    "away_team": away,
                    "time": match_time,
                    "event": event,
                })

        return matches
