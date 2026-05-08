"""ESPN Web API client — player gamelogs, splits, H2H, and statistical leaders.

Domain: site.web.api.espn.com/apis/common/v3/sports/{sport}/{league}/
Free, no API key, no documented rate limits.

Provides:
- Player game-by-game logs (NBA, MLB, NHL — NOT soccer)
- Player statistical splits (home/away, L5/L10)
- H2H athlete vs athlete stats
- League-wide statistical leaders by category
"""

import json
import time
from pathlib import Path

import requests

from .rate_limiter import RateLimiter

CACHE_DIR = Path(__file__).parent.parent.parent.parent / "betting" / "data" / "stats_cache"

# ESPN uses "soccer" not "football"
SPORT_MAP = {
    "football": "soccer",
    "basketball": "basketball",
    "hockey": "hockey",
    "baseball": "baseball",
    "tennis": "tennis",
    "mma": "mma",
}

# Sport → default categories for league leaders
LEADER_CATEGORIES = {
    "basketball": [
        ("scoring", "points:desc"),
        ("rebounds", "rebounds:desc"),
        ("assists", "assists:desc"),
        ("steals", "steals:desc"),
        ("blocks", "blocks:desc"),
    ],
    "baseball": [
        ("batting", "batting.homeRuns:desc"),
        ("batting", "batting.RBIs:desc"),
        ("pitching", "pitching.strikeouts:desc"),
        ("pitching", "pitching.ERA:asc"),
    ],
    "hockey": [
        ("points", "points:desc"),
        ("goals", "goals:desc"),
        ("assists", "assists:desc"),
        ("wins", "wins:desc"),
    ],
    "football": [
        ("scoring", "goals:desc"),
        ("assists", "assists:desc"),
    ],
}


class ESPNStatsClient:
    """ESPN Web API client for player stats, gamelogs, splits, and leaders."""

    WEB_BASE = "https://site.web.api.espn.com/apis/common/v3/sports"
    CORE_BASE = "https://sports.core.api.espn.com/v2/sports"
    SITE_BASE = "https://site.api.espn.com/apis/site/v2/sports"

    # Sports with gamelog support (confirmed working)
    GAMELOG_SPORTS = {"basketball", "baseball", "hockey"}

    TIMEOUT = 15
    MAX_RETRIES = 3
    BACKOFF_BASE = 1

    def __init__(self, rate_limiter: RateLimiter | None = None):
        self.rate_limiter = rate_limiter

    def _sport_slug(self, sport: str) -> str:
        """Map internal sport name to ESPN slug."""
        return SPORT_MAP.get(sport, sport)

    def _request(self, url: str, params: dict | None = None) -> dict:
        """Make HTTP request with retries and exponential backoff."""
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

            except requests.exceptions.RequestException:
                if attempt < self.MAX_RETRIES:
                    backoff = self.BACKOFF_BASE * (2 ** (attempt - 1))
                    time.sleep(backoff)

        return {}

    def _check_cache(self, cache_key: str, ttl_hours: int = 24) -> dict | None:
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

    def get_player_gamelog(
        self, sport: str, league: str, athlete_id: str, season: int | None = None
    ) -> list[dict]:
        """Fetch player game-by-game log.

        Only works for: basketball (NBA), baseball (MLB), hockey (NHL).
        Returns list of game entries with stats keyed by label names.
        """
        slug = self._sport_slug(sport)
        if slug not in self.GAMELOG_SPORTS:
            return []

        cache_key = f"espn_stats/{slug}/{league}/athletes/{athlete_id}/gamelog"
        if season:
            cache_key += f"_{season}"
        cached = self._check_cache(cache_key, ttl_hours=24)
        if cached is not None:
            return cached.get("games", [])

        url = f"{self.WEB_BASE}/{slug}/{league}/athletes/{athlete_id}/gamelog"
        params = {}
        if season:
            params["season"] = str(season)

        data = self._request(url, params=params if params else None)
        if not data:
            return []

        # ESPN gamelog v3 structure:
        # - labels: stat column names (e.g. ["MIN", "FG", "3PT", ...])
        # - events: dict of event_id → {id, links, atVs, opponent, ...} (metadata)
        # - seasonTypes[].categories[].events[]: [{eventId, stats: [...]}] (stat rows)
        labels = data.get("labels", [])
        events_meta = data.get("events", {})
        if isinstance(events_meta, list):
            # Old format fallback: events is a list of dicts
            events_meta = {str(e.get("id", i)): e for i, e in enumerate(events_meta) if isinstance(e, dict)}

        # Collect stat rows from seasonTypes → categories → events
        games = []
        season_types = data.get("seasonTypes", [])
        for st in season_types:
            if not isinstance(st, dict):
                continue
            for category in st.get("categories", []):
                if not isinstance(category, dict):
                    continue
                for event_row in category.get("events", []):
                    if not isinstance(event_row, dict):
                        continue
                    event_id = str(event_row.get("eventId", ""))
                    stats_raw = event_row.get("stats", [])

                    # Look up event metadata
                    meta = events_meta.get(event_id, {}) if isinstance(events_meta, dict) else {}

                    # Extract opponent info
                    opponent = ""
                    opp_data = meta.get("opponent", meta.get("atVs", ""))
                    if isinstance(opp_data, dict):
                        opponent = opp_data.get("displayName", opp_data.get("abbreviation", ""))
                    elif isinstance(opp_data, str):
                        opponent = opp_data

                    game_entry = {
                        "id": event_id,
                        "date": meta.get("gameDate", meta.get("date", "")),
                        "opponent": opponent,
                        "result": meta.get("gameResult", meta.get("result", "")),
                        "stats": {},
                    }
                    # Map positional stats to labels
                    for i, label in enumerate(labels):
                        if i < len(stats_raw):
                            game_entry["stats"][label] = stats_raw[i]
                    games.append(game_entry)

        self._save_cache(cache_key, {"games": games})
        return games

    def get_player_splits(self, sport: str, league: str, athlete_id: str) -> dict:
        """Fetch player statistical splits (home/away, monthly, etc.).

        Returns dict with split categories, each containing stat averages.
        """
        slug = self._sport_slug(sport)
        cache_key = f"espn_stats/{slug}/{league}/athletes/{athlete_id}/splits"
        cached = self._check_cache(cache_key, ttl_hours=24)
        if cached is not None:
            return cached

        url = f"{self.WEB_BASE}/{slug}/{league}/athletes/{athlete_id}/splits"
        data = self._request(url)
        if not data:
            return {}

        # Parse splits response into structured dict
        splits = {}
        categories = data.get("splitCategories", data.get("categories", []))
        for category in categories:
            if not isinstance(category, dict):
                continue
            cat_name = category.get("displayName", category.get("name", "unknown"))
            cat_splits = {}
            for split in category.get("splits", []):
                if not isinstance(split, dict):
                    continue
                split_name = split.get("displayName", split.get("name", ""))
                stat_values = {}
                for stat in split.get("stats", []):
                    if not isinstance(stat, dict):
                        continue
                    stat_name = stat.get("name", stat.get("displayName", ""))
                    stat_value = stat.get("value", stat.get("displayValue", ""))
                    if stat_name:
                        stat_values[stat_name] = stat_value
                if split_name:
                    cat_splits[split_name] = stat_values
            if cat_name:
                splits[cat_name] = cat_splits

        self._save_cache(cache_key, splits)
        return splits

    def get_h2h_athletes(
        self, sport: str, league: str, athlete_id: str, opponent_id: str
    ) -> dict:
        """Fetch head-to-head stats between two athletes.

        Uses Core API: athletes/{id}/vsathlete/{opponentId}
        Useful for tennis matchups, MMA fighter comparisons.
        """
        slug = self._sport_slug(sport)
        cache_key = f"espn_stats/{slug}/{league}/h2h/{athlete_id}_vs_{opponent_id}"
        cached = self._check_cache(cache_key, ttl_hours=48)
        if cached is not None:
            return cached

        url = (
            f"{self.CORE_BASE}/{slug}/leagues/{league}"
            f"/athletes/{athlete_id}/vsathlete/{opponent_id}"
        )
        data = self._request(url)
        if not data:
            return {}

        self._save_cache(cache_key, data)
        return data

    def get_league_leaders(
        self, sport: str, league: str, category: str | None = None, limit: int = 50
    ) -> list[dict]:
        """Fetch league-wide statistical leaders.

        If category is None, fetches leaders for all default categories for the sport.
        Returns list of player entries with stats and rankings.
        """
        slug = self._sport_slug(sport)

        if category:
            return self._fetch_single_leaders(slug, league, category, limit)

        # Fetch all default categories
        categories = LEADER_CATEGORIES.get(sport, LEADER_CATEGORIES.get(slug, []))
        all_leaders = []
        for cat, sort_field in categories:
            leaders = self._fetch_single_leaders(slug, league, cat, limit, sort_field)
            all_leaders.extend(leaders)
        return all_leaders

    def _fetch_single_leaders(
        self,
        slug: str,
        league: str,
        category: str,
        limit: int = 50,
        sort_field: str | None = None,
    ) -> list[dict]:
        """Fetch leaders for a single stat category."""
        cache_key = f"espn_stats/{slug}/{league}/leaders/{category}"
        cached = self._check_cache(cache_key, ttl_hours=12)
        if cached is not None:
            return cached.get("leaders", [])

        url = f"{self.WEB_BASE}/{slug}/{league}/statistics/byathlete"
        params = {"category": category, "limit": str(limit)}
        if sort_field:
            params["sort"] = sort_field

        data = self._request(url, params=params)
        if not data:
            return []

        # Parse leaders from response
        leaders = []
        athletes = data.get("athletes", data.get("leaders", []))
        for entry in athletes:
            athlete = entry.get("athlete", entry)
            leader = {
                "id": athlete.get("id", ""),
                "name": athlete.get("displayName", athlete.get("fullName", "")),
                "team": athlete.get("team", {}).get("displayName", ""),
                "category": category,
                "stats": entry.get("stats", entry.get("statistics", {})),
                "rank": entry.get("rank", 0),
            }
            leaders.append(leader)

        self._save_cache(cache_key, {"leaders": leaders})
        return leaders

    def get_team_leaders(self, sport: str, league: str, team_id: str) -> dict:
        """Fetch team statistical leaders (top performers per category).

        Uses Site API: teams/{id}/leaders
        Returns dict mapping stat categories to leader info.
        """
        slug = self._sport_slug(sport)
        cache_key = f"espn_stats/{slug}/{league}/teams/{team_id}/leaders"
        cached = self._check_cache(cache_key, ttl_hours=12)
        if cached is not None:
            return cached

        url = f"{self.SITE_BASE}/{slug}/{league}/teams/{team_id}/leaders"
        data = self._request(url)
        if not data:
            return {}

        # Parse team leaders response
        result = {}
        team_leaders = data.get("leaders", [])
        for category in team_leaders:
            cat_name = category.get("name", category.get("displayName", ""))
            cat_leaders = []
            for leader in category.get("leaders", []):
                athlete = leader.get("athlete", {})
                cat_leaders.append({
                    "id": athlete.get("id", ""),
                    "name": athlete.get("displayName", ""),
                    "value": leader.get("displayValue", leader.get("value", "")),
                    "stats": leader.get("statistics", {}),
                })
            if cat_name:
                result[cat_name] = cat_leaders

        self._save_cache(cache_key, result)
        return result
