"""ESPN Core API client — odds, ATS records, O/U records, probabilities.

Domain: sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/
Free, no API key, no documented rate limits.

Provides:
- Multi-provider betting odds (DraftKings, FanDuel, BetMGM, Bet365, ESPN BET)
- Team ATS (Against The Spread) records
- Team O/U (Over/Under) records
- Win probabilities and ESPN predictor
- Power Index (BPI for basketball)
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from .rate_limiter import RateLimiter

CACHE_DIR = Path(__file__).parent.parent.parent.parent / "betting" / "data" / "stats_cache"

# ESPN uses "soccer" not "football"
ESPN_SPORT_SLUGS = {
    "football": "soccer",
    "basketball": "basketball",
    "hockey": "hockey",
    "baseball": "baseball",
    "tennis": "tennis",
    "mma": "mma",
    "volleyball": "volleyball",
    "rugby": "rugby",
}

# Known provider IDs from ESPN Core API
ESPN_PROVIDERS = {
    1001: "Caesars",
    1002: "FanDuel",
    1003: "DraftKings",
    1004: "ESPN BET",
    45: "Bet365",
    58: "BetMGM",
}


def _american_to_decimal(odds: int | float) -> float:
    """Convert American odds to decimal.

    +X → 1 + X/100
    -X → 1 + 100/|X|
    """
    if odds > 0:
        return 1 + odds / 100
    elif odds < 0:
        return 1 + 100 / abs(odds)
    return 1.0


class ESPNOddsClient:
    """ESPN Core API client for odds, ATS, O/U records, and probabilities."""

    CORE_BASE = "https://sports.core.api.espn.com/v2/sports"
    TIMEOUT = 15
    MAX_RETRIES = 3
    BACKOFF_BASE = 1

    def __init__(self, rate_limiter: RateLimiter | None = None):
        self.rate_limiter = rate_limiter

    def _request(self, url: str, params: dict | None = None) -> dict:
        """Make HTTP request with retries and exponential backoff."""
        last_error = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = requests.get(
                    url,
                    params=params,
                    headers={"Accept": "application/json"},
                    timeout=self.TIMEOUT,
                )

                if response.status_code == 404:
                    return {}
                if response.status_code == 429:
                    if attempt < self.MAX_RETRIES:
                        backoff = self.BACKOFF_BASE * (2 ** (attempt - 1))
                        time.sleep(backoff)
                        continue
                    return {}
                if response.status_code >= 400:
                    return {}

                return response.json()

            except requests.exceptions.RequestException as e:
                last_error = e
                if attempt < self.MAX_RETRIES:
                    backoff = self.BACKOFF_BASE * (2 ** (attempt - 1))
                    time.sleep(backoff)

        return {}

    def _check_cache(self, cache_key: str, ttl_hours: int = 6) -> dict | None:
        """Check disk cache for a cached response."""
        if not cache_key or ".." in cache_key or cache_key.startswith("/"):
            return None
        cache_path = CACHE_DIR / f"{cache_key}.json"
        if not cache_path.exists():
            return None
        try:
            mtime = cache_path.stat().st_mtime
            age_hours = (time.time() - mtime) / 3600
            if age_hours > ttl_hours:
                return None
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def _save_cache(self, cache_key: str, data: dict) -> None:
        """Save response data to disk cache."""
        if not cache_key or ".." in cache_key or cache_key.startswith("/"):
            return
        cache_path = CACHE_DIR / f"{cache_key}.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _sport_slug(self, sport: str) -> str:
        """Map internal sport name to ESPN slug."""
        return ESPN_SPORT_SLUGS.get(sport, sport)

    def _build_url(self, sport: str, league: str, *path_parts: str) -> str:
        """Build Core API URL."""
        slug = self._sport_slug(sport)
        parts = [self.CORE_BASE, slug, "leagues", league] + list(path_parts)
        return "/".join(parts)

    def get_event_odds(self, sport: str, league: str, event_id: str, comp_id: str | None = None) -> list:
        """Fetch odds from all providers for an event.

        Returns list of dicts with normalized odds data.
        comp_id defaults to event_id (most events have 1 competition).
        """
        if comp_id is None:
            comp_id = event_id

        cache_key = f"espn_odds/{sport}/{league}/events/{event_id}/odds"
        cached = self._check_cache(cache_key, ttl_hours=1)
        if cached:
            return cached.get("odds", [])

        url = self._build_url(
            sport, league, "events", event_id, "competitions", comp_id, "odds"
        )
        data = self._request(url)
        if not data:
            return []

        odds_list = self._parse_odds_response(data, event_id, sport)
        self._save_cache(cache_key, {"odds": odds_list, "event_id": event_id})
        return odds_list

    def get_all_events_odds(self, sport: str, league: str, date: str) -> dict[str, list]:
        """Fetch odds for ALL events on a date for a sport/league.

        Uses scoreboard (site API) to discover events, then fetches odds for each.
        Returns dict mapping event_id → list of odds dicts.
        """
        # Discover events from site API scoreboard
        slug = self._sport_slug(sport)
        date_compact = date.replace("-", "")
        scoreboard_url = (
            f"http://site.api.espn.com/apis/site/v2/sports/{slug}/{league}/scoreboard"
        )
        sb_data = self._request(scoreboard_url, params={"dates": date_compact})
        if not sb_data:
            return {}

        results: dict[str, list] = {}
        for event in sb_data.get("events", []):
            event_id = event.get("id", "")
            if not event_id:
                continue
            odds = self.get_event_odds(sport, league, event_id)
            if odds:
                results[event_id] = odds

        return results

    def get_team_ats(
        self,
        sport: str,
        league: str,
        team_id: str,
        season_year: int | None = None,
        season_type: int = 2,
    ) -> dict:
        """Fetch team's Against The Spread record.

        Returns: {"wins": int, "losses": int, "pushes": int, "home": {...}, "away": {...}}
        Only works for US sports (NBA, NHL, MLB, NFL). Returns {} for soccer.
        """
        if season_year is None:
            season_year = datetime.now(timezone.utc).year

        cache_key = f"espn_odds/{sport}/{league}/ats/{team_id}/{season_year}/{season_type}"
        cached = self._check_cache(cache_key, ttl_hours=12)
        if cached:
            return cached

        url = self._build_url(
            sport, league,
            "seasons", str(season_year), "types", str(season_type),
            "teams", team_id, "ats",
        )
        data = self._request(url)
        if not data:
            return {}

        result = self._parse_ats_response(data)
        if result:
            self._save_cache(cache_key, result)
        return result

    def get_team_odds_records(
        self,
        sport: str,
        league: str,
        team_id: str,
        season_year: int | None = None,
        season_type: int = 2,
    ) -> dict:
        """Fetch team's O/U (over/under) record.

        Returns: {"overs": int, "unders": int, "pushes": int, "home": {...}, "away": {...}}
        """
        if season_year is None:
            season_year = datetime.now(timezone.utc).year

        cache_key = f"espn_odds/{sport}/{league}/odds_records/{team_id}/{season_year}/{season_type}"
        cached = self._check_cache(cache_key, ttl_hours=12)
        if cached:
            return cached

        url = self._build_url(
            sport, league,
            "seasons", str(season_year), "types", str(season_type),
            "teams", team_id, "odds-records",
        )
        data = self._request(url)
        if not data:
            return {}

        result = self._parse_odds_records_response(data)
        if result:
            self._save_cache(cache_key, result)
        return result

    def get_win_probabilities(
        self, sport: str, league: str, event_id: str, comp_id: str | None = None
    ) -> dict:
        """Fetch ESPN win probabilities for an event.

        Returns: {"home_win_pct": float, "away_win_pct": float, "tie_pct": float}
        """
        if comp_id is None:
            comp_id = event_id

        cache_key = f"espn_odds/{sport}/{league}/probabilities/{event_id}"
        cached = self._check_cache(cache_key, ttl_hours=2)
        if cached:
            return cached

        url = self._build_url(
            sport, league,
            "events", event_id, "competitions", comp_id, "probabilities",
        )
        data = self._request(url)
        if not data:
            return {}

        result = self._parse_probabilities_response(data)
        if result:
            self._save_cache(cache_key, result)
        return result

    def get_predictor(
        self, sport: str, league: str, event_id: str, comp_id: str | None = None
    ) -> dict:
        """Fetch ESPN predictor data for an event.

        Returns dict with predictor factors and projections.
        """
        if comp_id is None:
            comp_id = event_id

        cache_key = f"espn_odds/{sport}/{league}/predictor/{event_id}"
        cached = self._check_cache(cache_key, ttl_hours=2)
        if cached:
            return cached

        url = self._build_url(
            sport, league,
            "events", event_id, "competitions", comp_id, "predictor",
        )
        data = self._request(url)
        if not data:
            return {}

        result = self._parse_predictor_response(data)
        if result:
            self._save_cache(cache_key, result)
        return result

    def get_power_index(
        self, sport: str, league: str, season_year: int | None = None
    ) -> list[dict]:
        """Fetch ESPN Power Index (BPI for basketball, FPI for football).

        Returns list of team rankings with offensive/defensive ratings.
        """
        if season_year is None:
            season_year = datetime.now(timezone.utc).year

        cache_key = f"espn_odds/{sport}/{league}/powerindex/{season_year}"
        cached = self._check_cache(cache_key, ttl_hours=24)
        if cached:
            return cached.get("teams", [])

        url = self._build_url(
            sport, league, "seasons", str(season_year), "powerindex",
        )
        data = self._request(url)
        if not data:
            return []

        teams = self._parse_power_index_response(data)
        if teams:
            self._save_cache(cache_key, {"teams": teams})
        return teams

    # ------------------------------------------------------------------
    # Response parsers
    # ------------------------------------------------------------------

    def _parse_odds_response(self, data: dict, event_id: str, sport: str) -> list:
        """Parse Core API odds response into normalized odds dicts."""
        results = []

        # Core API returns items array or direct odds
        items = data.get("items", [data]) if "items" not in data else data["items"]

        for item in items:
            provider_info = item.get("provider", {})
            provider_id = provider_info.get("id")
            provider_name = ESPN_PROVIDERS.get(provider_id, provider_info.get("name", "Unknown"))

            odds_entry = {
                "event_id": event_id,
                "source": "espn-odds",
                "sport": sport,
                "bookmaker": provider_name,
                "provider_id": provider_id,
                "timestamp": item.get("lastUpdated", ""),
                "markets": {},
            }

            # Moneyline / H2H
            home_ml = item.get("homeTeamOdds", {}).get("moneyLine")
            away_ml = item.get("awayTeamOdds", {}).get("moneyLine")
            draw_ml = item.get("drawOdds", {}).get("moneyLine") if item.get("drawOdds") else None

            if home_ml is not None and away_ml is not None:
                odds_entry["markets"]["moneyline"] = {
                    "home": _american_to_decimal(home_ml),
                    "away": _american_to_decimal(away_ml),
                    "draw": _american_to_decimal(draw_ml) if draw_ml is not None else None,
                    "home_american": home_ml,
                    "away_american": away_ml,
                    "draw_american": draw_ml,
                }

            # Spread
            spread = item.get("spread")
            home_spread_odds = item.get("homeTeamOdds", {}).get("spreadOdds")
            away_spread_odds = item.get("awayTeamOdds", {}).get("spreadOdds")
            if spread is not None and home_spread_odds is not None:
                odds_entry["markets"]["spread"] = {
                    "home": _american_to_decimal(home_spread_odds),
                    "away": _american_to_decimal(away_spread_odds) if away_spread_odds else None,
                    "line": float(spread),
                }

            # Totals (over/under)
            over_under = item.get("overUnder")
            over_odds = item.get("overOdds")
            under_odds = item.get("underOdds")
            if over_under is not None and over_odds is not None:
                odds_entry["markets"]["totals"] = {
                    "over": _american_to_decimal(over_odds),
                    "under": _american_to_decimal(under_odds) if under_odds else None,
                    "line": float(over_under),
                }

            # Opening lines
            opening = {}
            open_spread = item.get("homeTeamOdds", {}).get("spreadLine")
            open_over_under = item.get("openingOverUnder")
            if open_spread is not None:
                opening["spread_line"] = float(open_spread)
            if open_over_under is not None:
                opening["totals_line"] = float(open_over_under)
            if opening:
                odds_entry["opening_line"] = opening

            results.append(odds_entry)

        return results

    def _parse_ats_response(self, data: dict) -> dict:
        """Parse ATS endpoint response."""
        records = data.get("records", data.get("items", []))
        if not records and not data.get("wins"):
            return {}

        # Direct format: {"wins": X, "losses": Y, "pushes": Z}
        if "wins" in data:
            return {
                "wins": data.get("wins", 0),
                "losses": data.get("losses", 0),
                "pushes": data.get("pushes", 0),
            }

        result = {}
        for record in records:
            rec_type = record.get("type", "overall")
            wins = record.get("wins", 0)
            losses = record.get("losses", 0)
            pushes = record.get("pushes", 0)
            entry = {"wins": wins, "losses": losses, "pushes": pushes}

            if rec_type == "overall" or rec_type == "total":
                result.update(entry)
            elif rec_type == "home":
                result["home"] = entry
            elif rec_type == "away":
                result["away"] = entry

        return result

    def _parse_odds_records_response(self, data: dict) -> dict:
        """Parse odds-records endpoint response (O/U records)."""
        records = data.get("records", data.get("items", []))
        if not records and not data.get("overs"):
            return {}

        if "overs" in data:
            return {
                "overs": data.get("overs", 0),
                "unders": data.get("unders", 0),
                "pushes": data.get("pushes", 0),
            }

        result = {}
        for record in records:
            rec_type = record.get("type", "overall")
            overs = record.get("overs", record.get("wins", 0))
            unders = record.get("unders", record.get("losses", 0))
            pushes = record.get("pushes", 0)
            entry = {"overs": overs, "unders": unders, "pushes": pushes}

            if rec_type == "overall" or rec_type == "total":
                result.update(entry)
            elif rec_type == "home":
                result["home"] = entry
            elif rec_type == "away":
                result["away"] = entry

        return result

    def _parse_probabilities_response(self, data: dict) -> dict:
        """Parse win probabilities response."""
        # Probabilities endpoint returns items array with time-series
        items = data.get("items", [])
        if not items:
            # Try direct format
            if "homeWinPercentage" in data:
                return {
                    "home_win_pct": data.get("homeWinPercentage", 0.0),
                    "away_win_pct": data.get("awayWinPercentage", 0.0),
                    "tie_pct": data.get("tiePercentage", 0.0),
                }
            return {}

        # Get the most recent (pre-game) probability
        last = items[-1] if items else {}
        return {
            "home_win_pct": last.get("homeWinPercentage", 0.0),
            "away_win_pct": last.get("awayWinPercentage", 0.0),
            "tie_pct": last.get("tiePercentage", 0.0),
        }

    def _parse_predictor_response(self, data: dict) -> dict:
        """Parse predictor endpoint response."""
        result = {}

        home_team = data.get("homeTeam", {})
        away_team = data.get("awayTeam", {})

        if home_team:
            result["home"] = {
                "id": home_team.get("id", ""),
                "win_pct": home_team.get("gameProjection", 0.0),
                "team_chance_loss": home_team.get("teamChanceLoss", 0.0),
            }
        if away_team:
            result["away"] = {
                "id": away_team.get("id", ""),
                "win_pct": away_team.get("gameProjection", 0.0),
                "team_chance_loss": away_team.get("teamChanceLoss", 0.0),
            }

        # Additional predictor fields
        if "header" in data:
            result["header"] = data["header"]
        if "title" in data:
            result["title"] = data["title"]

        return result

    def _parse_power_index_response(self, data: dict) -> list[dict]:
        """Parse power index response.

        ESPN returns items with stats as an array of {name, value} dicts
        and team as a $ref link that needs resolving.
        """
        items = data.get("items", [])
        teams = []

        for item in items:
            # Items may be $ref links — resolve if needed
            if "$ref" in item and not item.get("team"):
                ref_data = self._request(item["$ref"])
                if ref_data:
                    item = ref_data

            # Resolve team $ref to get team name/id
            team_info = item.get("team", {})
            if "$ref" in team_info and not team_info.get("displayName"):
                resolved = self._request(team_info["$ref"])
                if resolved:
                    team_info = resolved

            # Extract stats from array format [{name, value}, ...]
            stats_dict: dict[str, float] = {}
            for stat in item.get("stats", []):
                name = stat.get("name", "")
                val = stat.get("value")
                if name and val is not None:
                    try:
                        stats_dict[name] = float(val)
                    except (ValueError, TypeError):
                        pass

            team_entry = {
                "team_id": team_info.get("id", item.get("id", "")),
                "team_name": team_info.get("displayName", ""),
                "abbreviation": team_info.get("abbreviation", ""),
                "rank": int(stats_dict.get("bpirank", item.get("rank", 0))),
                "bpi": stats_dict.get("bpi", item.get("bpiRating", item.get("rating", 0.0))),
                "offensive_rating": stats_dict.get("bpioffense", item.get("offensiveRating", 0.0)),
                "defensive_rating": stats_dict.get("bpidefense", item.get("defensiveRating", 0.0)),
                "strength_of_schedule": stats_dict.get("strengthofschedule", item.get("strengthOfSchedule", 0.0)),
            }
            teams.append(team_entry)

        return teams
