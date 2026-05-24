"""Odds-API.io source adapter — multi-sport fixture discovery with odds.

Covers all 5 core sports (football, volleyball, basketball, tennis, hockey).
Free tier: 5,000 requests/hour.
"""

from datetime import datetime, timezone

from bet.api_clients.odds_api_io import OddsAPIioClient, SPORT_SLUG_MAP
from bet.api_clients.rate_limiter import RateLimiter
from ..models import DiscoveredEvent
from .base import AbstractSourceAdapter


class OddsAPIioAdapter(AbstractSourceAdapter):
    """Primary replacement source — all 5 sports, 265 bookmakers, value bets.

    Replaces the expired the-odds-api.com and blocked SofaScore.
    """

    name = "odds-api-io"
    priority = 1  # Top priority — most reliable multi-sport source
    supported_sports = ["football", "volleyball", "basketball", "tennis", "hockey", "cs2", "dota2", "valorant"]

    # League name prefix → internal sport mapping
    ESPORTS_LEAGUE_PREFIX = {
        "Counter-Strike": "cs2",
        "CS2": "cs2",
        "CS:GO": "cs2",
        "Dota": "dota2",
        "Dota 2": "dota2",
        "Valorant": "valorant",
        "League of Legends": None,  # Out of scope — skip
        "StarCraft": None,          # Out of scope — skip
        "Overwatch": None,          # Out of scope — skip
    }

    ESPORTS_SPORTS = {"cs2", "dota2", "valorant"}

    def __init__(self, rate_limiter: RateLimiter | None = None):
        self._limiter = rate_limiter or RateLimiter()
        self._client = OddsAPIioClient(rate_limiter=self._limiter)
        self._esports_cache: dict[str, list[dict]] = {}  # date → raw events
        super().__init__()

    def is_available(self) -> bool:
        return self._client.is_available()

    def _fetch_events_impl(self, date: str, sport: str) -> list[DiscoveredEvent]:
        if sport in self.ESPORTS_SPORTS:
            return self._fetch_esports_filtered(date, sport)
            
        slug = SPORT_SLUG_MAP.get(sport, sport)
        from_dt = f"{date}T00:00:00Z"
        to_dt = f"{date}T23:59:59Z"

        raw_events = self._client.get_events(slug, status="pending", from_dt=from_dt, to_dt=to_dt)

        events = []
        for ev in raw_events:
            try:
                home = (ev.get("home") or "").strip()
                away = (ev.get("away") or "").strip()
                if not home or not away:
                    continue

                # Parse kickoff
                date_str = ev.get("date", "")
                if date_str:
                    kickoff = datetime.fromisoformat(
                        date_str.replace("Z", "+00:00")
                    )
                else:
                    kickoff = datetime(
                        *map(int, date.split("-")), tzinfo=timezone.utc
                    )

                if kickoff.tzinfo is None:
                    kickoff = kickoff.replace(tzinfo=timezone.utc)

                competition = ""
                league = ev.get("league")
                if isinstance(league, dict):
                    competition = league.get("name", "")
                elif isinstance(league, str):
                    competition = league

                events.append(DiscoveredEvent(
                    source="odds-api-io",
                    external_id=str(ev.get("id", "")),
                    sport=sport,
                    competition=competition,
                    home_team=home,
                    away_team=away,
                    kickoff=kickoff,
                    status=ev.get("status", "scheduled"),
                ))
            except Exception as e:
                self.logger.debug("Skipping odds-api-io event: %s", e)
                continue

        return events

    def _fetch_esports_filtered(self, date: str, target_sport: str) -> list[DiscoveredEvent]:
        """Fetch all esports events, return only those matching target_sport."""
        raw_events = self._get_esports_raw(date)
        
        events = []
        for ev in raw_events:
            league_name = ""
            league = ev.get("league")
            if isinstance(league, dict):
                league_name = league.get("name", "")
            elif isinstance(league, str):
                league_name = league
            
            parsed_sport = self._parse_esports_sport(league_name)
            if parsed_sport != target_sport:
                continue
            
            try:
                home = (ev.get("home") or "").strip()
                away = (ev.get("away") or "").strip()
                if not home or not away:
                    continue

                date_str = ev.get("date", "")
                if date_str:
                    kickoff = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                else:
                    kickoff = datetime(*map(int, date.split("-")), tzinfo=timezone.utc)

                if kickoff.tzinfo is None:
                    kickoff = kickoff.replace(tzinfo=timezone.utc)

                competition = self._clean_esports_competition(league_name)

                events.append(DiscoveredEvent(
                    source="odds-api-io",
                    external_id=str(ev.get("id", "")),
                    sport=target_sport,
                    competition=competition,
                    home_team=home,
                    away_team=away,
                    kickoff=kickoff,
                    status=ev.get("status", "scheduled"),
                ))
            except Exception as e:
                self.logger.debug("Skipping esports event: %s", e)
                continue
        
        return events

    def _get_esports_raw(self, date: str) -> list[dict]:
        """Fetch raw esports events with per-date caching."""
        if date not in self._esports_cache:
            from_dt = f"{date}T00:00:00Z"
            to_dt = f"{date}T23:59:59Z"
            self._esports_cache[date] = self._client.get_events(
                "esports", status="pending", from_dt=from_dt, to_dt=to_dt
            ) or []
        return self._esports_cache[date]

    def _parse_esports_sport(self, league_name: str) -> str | None:
        """Parse sub-game from league name like 'Counter-Strike - BLAST Premier'."""
        for prefix, sport in self.ESPORTS_LEAGUE_PREFIX.items():
            if league_name.startswith(prefix):
                return sport
        return None

    def _clean_esports_competition(self, league_name: str) -> str:
        """'Counter-Strike - BLAST Premier Spring' → 'BLAST Premier Spring'."""
        for prefix in self.ESPORTS_LEAGUE_PREFIX:
            if league_name.startswith(prefix):
                remainder = league_name[len(prefix):].lstrip(" -–—")
                return remainder if remainder else league_name
        return league_name
