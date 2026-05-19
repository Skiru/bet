"""ScraperNHL BaseAPIClient wrapper for enrichment pipeline.

Wraps the `scrapernhl` package (pip install scrapernhl) which provides
NHL play-by-play, advanced analytics (Corsi, Fenwick, on-ice stats),
player stats, and standings.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from .base_client import BaseAPIClient, APIError
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

try:
    from scrapernhl import HockeyScraper
    _HAS_SCRAPERNHL = True
except ImportError:
    _HAS_SCRAPERNHL = False

# NHL team tricode mapping (common names → tricodes)
_TEAM_TRICODES = {
    "anaheim ducks": "ANA", "arizona coyotes": "ARI", "boston bruins": "BOS",
    "buffalo sabres": "BUF", "carolina hurricanes": "CAR", "columbus blue jackets": "CBJ",
    "calgary flames": "CGY", "chicago blackhawks": "CHI", "colorado avalanche": "COL",
    "dallas stars": "DAL", "detroit red wings": "DET", "edmonton oilers": "EDM",
    "florida panthers": "FLA", "los angeles kings": "LAK", "minnesota wild": "MIN",
    "montreal canadiens": "MTL", "new jersey devils": "NJD", "nashville predators": "NSH",
    "new york islanders": "NYI", "new york rangers": "NYR", "ottawa senators": "OTT",
    "philadelphia flyers": "PHI", "pittsburgh penguins": "PIT", "san jose sharks": "SJS",
    "seattle kraken": "SEA", "st. louis blues": "STL", "st louis blues": "STL",
    "tampa bay lightning": "TBL", "toronto maple leafs": "TOR", "utah hockey club": "UTA",
    "vancouver canucks": "VAN", "vegas golden knights": "VGK", "winnipeg jets": "WPG",
    "washington capitals": "WSH",
}


def _resolve_tricode(team_name: str) -> str | None:
    """Resolve a team name to NHL tricode."""
    name_lower = team_name.lower().strip()
    # Direct match
    if name_lower in _TEAM_TRICODES:
        return _TEAM_TRICODES[name_lower]
    # Partial match (e.g., "Lightning" → TBL)
    for full_name, code in _TEAM_TRICODES.items():
        if name_lower in full_name or full_name in name_lower:
            return code
        # Match last word
        last_word = full_name.split()[-1]
        if last_word == name_lower or name_lower == code.lower():
            return code
    return None


def _current_season() -> str:
    """Get current NHL season in scrapernhl format (e.g., '20252026')."""
    from datetime import date
    today = date.today()
    if today.month >= 10:
        return f"{today.year}{today.year + 1}"
    return f"{today.year - 1}{today.year}"


class ScraperNHLClient(BaseAPIClient):
    """NHL advanced analytics via scrapernhl package."""

    def __init__(self, rate_limiter: RateLimiter | None = None, **kwargs):
        if rate_limiter is None:
            rate_limiter = RateLimiter()
        super().__init__(
            api_name="scrapernhl",
            base_url="https://api-web.nhle.com",
            rate_limiter=rate_limiter,
        )
        self.api_key = "no-key-needed"
        self._scraper = None

    def _get_scraper(self) -> "HockeyScraper":
        if self._scraper is None:
            self._scraper = HockeyScraper("nhl")
        return self._scraper

    def is_available(self) -> bool:
        return _HAS_SCRAPERNHL

    def _load_api_key(self) -> str | None:
        return "no-key-needed"

    def get_fixtures(self, date: str) -> list:
        return []

    def get_fixture_stats(self, fixture_id: str) -> list:
        return []

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list:
        return []

    def resolve_team_id(self, team_name: str, **kwargs) -> str | None:
        """Resolve team name to NHL tricode."""
        return _resolve_tricode(team_name)

    def get_team_last_fixtures(self, team_id: str, last_n: int = 10) -> list:
        """Get recent games for a team via scrapernhl schedule."""
        from normalize_stats import NormalizedFixture
        
        try:
            scraper = self._get_scraper()
            season = _current_season()
            schedule = scraper.schedule(team=team_id, season=season)
            
            if schedule is None or schedule.empty:
                return []
            
            # Filter to finished games, take last N
            # Schedule columns include game_id, date, home_team, away_team, etc.
            finished = schedule[schedule["game_state"].isin(["OFF", "FINAL"])] if "game_state" in schedule.columns else schedule
            recent = finished.tail(last_n)
            
            fixtures = []
            for _, row in recent.iterrows():
                game_id = str(row.get("game_id", row.get("id", "")))
                fixtures.append(NormalizedFixture(
                    fixture_id=game_id,
                    source="scrapernhl",
                    sport="hockey",
                    competition="NHL",
                    home_team=str(row.get("home_team", "")),
                    away_team=str(row.get("away_team", "")),
                    kickoff=str(row.get("date", "")),
                    status="FINISHED",
                ))
            return fixtures
        except Exception as e:
            logger.warning(f"[scrapernhl] schedule error for {team_id}: {e}")
            return []

    def get_team_advanced_stats(self, team_name: str) -> dict | None:
        """Get team advanced stats (Corsi, Fenwick, on-ice) from scrapernhl.
        
        Returns dict with stat keys or None.
        """
        tricode = _resolve_tricode(team_name)
        if not tricode:
            return None
        
        try:
            scraper = self._get_scraper()
            season = _current_season()
            stats_df = scraper.team_stats(team=tricode, season=season, session=2)
            
            if stats_df is None or stats_df.empty:
                return None
            
            # Convert first row to dict
            row = stats_df.iloc[0]
            stats = {}
            for col in stats_df.columns:
                try:
                    stats[col.lower()] = float(row[col])
                except (ValueError, TypeError):
                    pass
            return stats
        except Exception as e:
            logger.warning(f"[scrapernhl] team_stats error for {team_name}: {e}")
            return None