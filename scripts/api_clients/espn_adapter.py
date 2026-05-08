"""ESPN adapter for the pipeline — wraps src/bet/api_clients/espn.py.

Registers per-sport ESPN clients (espn-football, espn-basketball, etc.)
that conform to the scripts/api_clients interface (NormalizedFixture/NormalizedMatchStats).

ESPN is FREE, unlimited, no API key. Covers football (36+ leagues),
basketball (NBA/WNBA), hockey (NHL), baseball (MLB).
"""

import sys
from pathlib import Path

from .base_client import BaseAPIClient, CACHE_DIR
from .rate_limiter import RateLimiter

# Import normalize_stats from scripts/
try:
    from scripts.normalize_stats import NormalizedFixture, NormalizedMatchStats
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from normalize_stats import NormalizedFixture, NormalizedMatchStats

# Import the real ESPN client from src/
_SRC_ROOT = Path(__file__).parent.parent.parent / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from bet.api_clients.espn import (
    ESPNClient,
    ESPN_LEAGUES,
    COMPETITION_TO_ESPN_LEAGUE,
    get_espn_league_for_competition,
)


class ESPNMultiLeagueClient(BaseAPIClient):
    """ESPN adapter that tries all leagues for a sport.

    For football, iterates through 36+ leagues to find teams.
    For basketball/hockey/baseball, there's only 1-2 leagues.
    """

    def __init__(self, sport: str, rate_limiter: RateLimiter):
        self.sport = sport
        self._rate_limiter = rate_limiter
        self._league_clients: dict[str, ESPNClient] = {}
        self._team_league_cache: dict[str, str] = {}  # team_name_lower → league_code
        self._teamid_league_cache: dict[str, str] = {}  # team_id → league_code
        self._fixtureid_league_cache: dict[str, str] = {}  # fixture_id → league_code

        super().__init__(
            api_name=f"espn-{sport}",
            base_url="http://site.api.espn.com/apis/site/v2/sports",
            rate_limiter=rate_limiter,
        )

    def _load_api_key(self) -> str:
        """ESPN needs no API key."""
        return "espn-no-key"

    def _build_headers(self) -> dict:
        return {"Accept": "application/json"}

    def is_available(self) -> bool:
        return True

    def _get_league_client(self, league: str) -> ESPNClient:
        """Get or create an ESPNClient for a specific league."""
        if league not in self._league_clients:
            self._league_clients[league] = ESPNClient(
                sport=self.sport,
                league=league,
                rate_limiter=self._rate_limiter,
            )
        return self._league_clients[league]

    def _get_leagues(self) -> list[str]:
        """Return all ESPN league codes for this sport."""
        return ESPN_LEAGUES.get(self.sport, [])

    def _guess_league_from_competition(self, competition: str) -> str | None:
        """Try to map a competition name to an ESPN league code."""
        return get_espn_league_for_competition(competition)

    # ─── BaseAPIClient interface ─────────────────────────────────────

    def get_fixtures(self, date: str) -> list[NormalizedFixture]:
        """Fetch fixtures across all leagues for this sport on a date."""
        all_fixtures = []
        for league in self._get_leagues():
            client = self._get_league_client(league)
            try:
                raw_fixtures = client.get_fixtures(date)
                for f in raw_fixtures:
                    nf = NormalizedFixture(
                        fixture_id=f.external_id,
                        source=self.api_name,
                        sport=self.sport,
                        competition=f.competition_name,
                        home_team=f.home_team_name,
                        away_team=f.away_team_name,
                        kickoff=f.kickoff,
                        status=f.status,
                    )
                    all_fixtures.append(nf)
            except Exception as e:
                print(f"[{self.api_name}] Error fetching fixtures for {league}: {e}")
                continue
        return all_fixtures

    def get_fixture_stats(self, fixture_id: str) -> NormalizedMatchStats | None:
        """Fetch match stats for a fixture. Uses fixture→league cache first."""
        # Determine which league(s) to try
        cached_league = self._fixtureid_league_cache.get(fixture_id)
        if cached_league:
            leagues_to_try = [cached_league]
        else:
            leagues_to_try = self._get_leagues()

        for league in leagues_to_try:
            client = self._get_league_client(league)
            try:
                raw_stats_list = client.get_fixture_stats(fixture_id)
                if not raw_stats_list:
                    continue
                # ESPNClient returns list[APIMatchStats], take first
                raw = raw_stats_list[0] if isinstance(raw_stats_list, list) else raw_stats_list
                return NormalizedMatchStats(
                    fixture_id=raw.external_id,
                    source=self.api_name,
                    sport=self.sport,
                    home_team=raw.home_team_name,
                    away_team=raw.away_team_name,
                    date="",
                    stats=raw.stats,
                )
            except Exception:
                continue
        return None

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list[NormalizedFixture]:
        """Get H2H data — resolve league from team cache, then query."""
        league = self._teamid_league_cache.get(team1_id)
        if not league:
            league = self._teamid_league_cache.get(team2_id)
        if not league:
            leagues = self._get_leagues()
            league = leagues[0] if leagues else None
        if not league:
            return []
        client = self._get_league_client(league)
        try:
            raw = client.get_h2h(team1_id, team2_id, last_n=last_n)
            # raw is list[dict] with {id, date, competitors}
            fixtures = []
            for game in raw:
                competitors = game.get("competitors", [])
                home_name = ""
                away_name = ""
                for c in competitors:
                    team_info = c.get("team", c)
                    if c.get("homeAway") == "home":
                        home_name = team_info.get("displayName", "")
                    else:
                        away_name = team_info.get("displayName", "")
                fixtures.append(NormalizedFixture(
                    fixture_id=str(game.get("id", "")),
                    source=self.api_name,
                    sport=self.sport,
                    competition="",
                    home_team=home_name,
                    away_team=away_name,
                    kickoff=game.get("date", ""),
                    status="FT",
                ))
            return fixtures
        except Exception:
            return []

    def resolve_team_id(self, team_name: str, competition: str = "") -> str | None:
        """Resolve team name to ESPN team ID, trying all leagues.

        If competition is provided, tries the matching league first (huge speedup
        for football with 36+ leagues).
        """
        name_lower = team_name.lower().strip()

        # Check team→league cache
        if name_lower in self._team_league_cache:
            league = self._team_league_cache[name_lower]
            client = self._get_league_client(league)
            team_id = client.resolve_team_id(team_name)
            if team_id:
                self._teamid_league_cache[team_id] = league
            return team_id

        # Build ordered league list: competition match first, then rest
        leagues = list(self._get_leagues())
        if competition:
            guessed = self._guess_league_from_competition(competition)
            if guessed and guessed in leagues:
                leagues.remove(guessed)
                leagues.insert(0, guessed)

        # Try each league
        for league in leagues:
            client = self._get_league_client(league)
            try:
                team_id = client.resolve_team_id(team_name)
                if team_id:
                    self._team_league_cache[name_lower] = league
                    self._teamid_league_cache[team_id] = league
                    return team_id
            except Exception:
                continue
        return None

    def get_team_last_fixtures(self, team_id: str, last_n: int = 10) -> list[NormalizedFixture]:
        """Get last N finished fixtures for a team."""
        league = self._teamid_league_cache.get(team_id)
        if not league:
            leagues = self._get_leagues()
            league = leagues[0] if leagues else None
        if not league:
            return []
        client = self._get_league_client(league)
        try:
            raw = client.get_team_last_fixtures(team_id, last_n=last_n)
            # raw is list[dict] with {id, date, home_team, away_team, score}
            fixtures = []
            for game in raw:
                fid = str(game.get("id", ""))
                self._fixtureid_league_cache[fid] = league
                fixtures.append(NormalizedFixture(
                    fixture_id=fid,
                    source=self.api_name,
                    sport=self.sport,
                    competition="",
                    home_team=game.get("home_team", ""),
                    away_team=game.get("away_team", ""),
                    kickoff=game.get("date", ""),
                    status="FT",
                ))
            return fixtures
        except Exception:
            return []

    def get_injuries(self, league: str = None) -> list[dict]:
        """Get injuries for a specific league (or first available)."""
        leagues = [league] if league else self._get_leagues()
        for lg in leagues:
            client = self._get_league_client(lg)
            try:
                injuries = client.get_injuries()
                if injuries:
                    return injuries
            except Exception:
                continue
        return []

    def get_standings(self, league: str = None) -> list[dict]:
        """Get standings for a specific league."""
        leagues = [league] if league else self._get_leagues()[:1]
        for lg in leagues:
            client = self._get_league_client(lg)
            try:
                standings = client.get_standings()
                if standings:
                    return standings
            except Exception:
                continue
        return []

    def get_team_roster(self, team_id: str) -> list[dict]:
        """Get team roster — resolves league from team cache."""
        league = self._teamid_league_cache.get(team_id)
        if not league:
            leagues = self._get_leagues()
            league = leagues[0] if leagues else None
        if not league:
            return []
        client = self._get_league_client(league)
        return client.get_team_roster(team_id)

    def get_depth_chart(self, team_id: str) -> dict:
        """Get depth chart — resolves league from team cache."""
        league = self._teamid_league_cache.get(team_id)
        if not league:
            leagues = self._get_leagues()
            league = leagues[0] if leagues else None
        if not league:
            return {}
        client = self._get_league_client(league)
        return client.get_depth_chart(team_id)

    def get_team_transactions(self, team_id: str, limit: int = 25) -> list[dict]:
        """Get team transactions — resolves league from team cache."""
        league = self._teamid_league_cache.get(team_id)
        if not league:
            leagues = self._get_leagues()
            league = leagues[0] if leagues else None
        if not league:
            return []
        client = self._get_league_client(league)
        return client.get_team_transactions(team_id, limit=limit)

    def get_scoreboard_odds(self, date: str, league: str = None) -> list[dict]:
        """Get DraftKings odds from ESPN scoreboard for all games on a date.

        Returns list of {event_name, home, away, odds: {...}} dicts.
        """
        results = []
        leagues = [league] if league else self._get_leagues()
        for lg in leagues:
            client = self._get_league_client(lg)
            try:
                date_compact = date.replace("-", "")
                data = client._request("/scoreboard", params={"dates": date_compact})
                for event in data.get("events", []):
                    odds = ESPNClient.extract_odds_from_event(event)
                    if odds:
                        comps = event.get("competitions", [])
                        competitors = comps[0].get("competitors", []) if comps else []
                        home = ""
                        away = ""
                        for c in competitors:
                            t = c.get("team", c.get("athlete", {}))
                            if c.get("homeAway") == "home":
                                home = t.get("displayName", "")
                            else:
                                away = t.get("displayName", "")

                        form = ESPNClient.extract_form_and_records(event)

                        results.append({
                            "event_id": str(event.get("id", "")),
                            "event_name": event.get("name", ""),
                            "home": home,
                            "away": away,
                            "competition": lg,
                            "odds": odds,
                            "form": form,
                        })
            except Exception:
                continue
        return results



# ─── Factory functions for CLIENT_REGISTRY ───────────────────────────


def _make_espn_football(rate_limiter: RateLimiter) -> ESPNMultiLeagueClient:
    return ESPNMultiLeagueClient(sport="football", rate_limiter=rate_limiter)


def _make_espn_basketball(rate_limiter: RateLimiter) -> ESPNMultiLeagueClient:
    return ESPNMultiLeagueClient(sport="basketball", rate_limiter=rate_limiter)


def _make_espn_hockey(rate_limiter: RateLimiter) -> ESPNMultiLeagueClient:
    return ESPNMultiLeagueClient(sport="hockey", rate_limiter=rate_limiter)


def _make_espn_baseball(rate_limiter: RateLimiter) -> ESPNMultiLeagueClient:
    return ESPNMultiLeagueClient(sport="baseball", rate_limiter=rate_limiter)


def _make_espn_tennis(rate_limiter: RateLimiter) -> ESPNMultiLeagueClient:
    return ESPNMultiLeagueClient(sport="tennis", rate_limiter=rate_limiter)


def _make_espn_mma(rate_limiter: RateLimiter) -> ESPNMultiLeagueClient:
    return ESPNMultiLeagueClient(sport="mma", rate_limiter=rate_limiter)


def _make_espn_volleyball(rate_limiter: RateLimiter) -> ESPNMultiLeagueClient:
    return ESPNMultiLeagueClient(sport="volleyball", rate_limiter=rate_limiter)


# Map of api_name → factory
ESPN_FACTORIES = {
    "espn-football": _make_espn_football,
    "espn-basketball": _make_espn_basketball,
    "espn-hockey": _make_espn_hockey,
    "espn-baseball": _make_espn_baseball,
    "espn-tennis": _make_espn_tennis,
    "espn-mma": _make_espn_mma,
    "espn-volleyball": _make_espn_volleyball,
}
