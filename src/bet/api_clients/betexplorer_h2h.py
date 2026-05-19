"""BetExplorer H2H scraper — fetches head-to-head data for all 5 sports.

Uses curl_cffi with TLS impersonation to access BetExplorer's H2H pages.
Writes to h2h_stats table via StatsRepo.

Rate limited: max 20 requests/minute.
"""

import logging
import re
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

try:
    from curl_cffi import requests as c_requests
except ImportError:
    c_requests = None


@dataclass
class H2HMeeting:
    date: str
    competition: str
    home_team: str
    away_team: str
    score: str
    home_goals: int
    away_goals: int


class BetExplorerH2H:
    """BetExplorer H2H scraper with rate limiting."""

    BASE_URL = "https://www.betexplorer.com"
    HEADERS = {
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    }
    # Rate limiting
    _last_request_time = 0.0
    _min_interval = 3.0  # 20 req/min = 3s between requests

    def __init__(self):
        if c_requests is None:
            raise ImportError("curl_cffi required for BetExplorerH2H")

    def _slugify(self, name: str) -> str:
        """Convert team name to BetExplorer URL slug."""
        s = name.lower().strip()
        s = re.sub(r"[^\w\s-]", "", s)
        s = re.sub(r"[\s_]+", "-", s)
        return s

    def _rate_limit(self):
        """Enforce minimum interval between requests."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()

    def fetch_h2h(self, team_a: str, team_b: str, sport: str = "football") -> list[H2HMeeting]:
        """Fetch H2H meetings between two teams.

        Args:
            team_a: First team name
            team_b: Second team name
            sport: Sport key (football, basketball, hockey, tennis, volleyball)

        Returns:
            List of H2HMeeting objects (most recent first), max 10.
        """
        slug_a = self._slugify(team_a)
        slug_b = self._slugify(team_b)

        # BetExplorer H2H URL pattern
        sport_path = {
            "football": "soccer",
            "basketball": "basketball",
            "hockey": "hockey",
            "tennis": "tennis",
            "volleyball": "volleyball",
        }.get(sport, "soccer")

        url = f"{self.BASE_URL}/{sport_path}/h2h/{slug_a}/{slug_b}/"

        self._rate_limit()
        try:
            resp = c_requests.get(
                url,
                headers=self.HEADERS,
                impersonate="chrome110",
                timeout=15,
            )
            if resp.status_code == 404:
                # Try reversed order
                url = f"{self.BASE_URL}/{sport_path}/h2h/{slug_b}/{slug_a}/"
                self._rate_limit()
                resp = c_requests.get(
                    url,
                    headers=self.HEADERS,
                    impersonate="chrome110",
                    timeout=15,
                )
            if resp.status_code != 200:
                logger.warning(f"BetExplorer H2H {resp.status_code} for {team_a} vs {team_b}")
                return []

            return self._parse_h2h_page(resp.text, team_a, team_b)

        except Exception as e:
            logger.warning(f"BetExplorer H2H failed for {team_a} vs {team_b}: {e}")
            return []

    def _parse_h2h_page(self, html: str, team_a: str, team_b: str) -> list[H2HMeeting]:
        """Parse H2H meetings from BetExplorer HTML."""
        meetings = []

        # BetExplorer uses table rows with class "h2h-row" or similar
        # Pattern: <td class="h2h-date">DD.MM.YYYY</td>
        #          <td class="h2h-comp">Competition</td>
        #          <td>Home</td><td>Score</td><td>Away</td>
        row_pattern = re.compile(
            r'<tr[^>]*>.*?'
            r'(\d{2}\.\d{2}\.\d{4}).*?'  # date
            r'<td[^>]*>([^<]*)</td>.*?'   # competition
            r'<td[^>]*>([^<]*)</td>.*?'   # home
            r'<td[^>]*>(\d+:\d+)</td>.*?' # score
            r'<td[^>]*>([^<]*)</td>',     # away
            re.DOTALL,
        )

        for match in row_pattern.finditer(html):
            date_str, comp, home, score, away = match.groups()
            try:
                parts = score.split(":")
                h_goals = int(parts[0])
                a_goals = int(parts[1])
            except (ValueError, IndexError):
                continue

            meetings.append(H2HMeeting(
                date=date_str.strip(),
                competition=comp.strip(),
                home_team=home.strip(),
                away_team=away.strip(),
                score=score.strip(),
                home_goals=h_goals,
                away_goals=a_goals,
            ))

            if len(meetings) >= 10:
                break

        return meetings
