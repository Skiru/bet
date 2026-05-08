"""OpenDota API client — Dota 2 match stats, player data, hero stats.

Source: api.opendota.com (FREE, no auth for basic endpoints)
Rate limit: 60 requests/min without key, 1200/min with key.

Endpoints:
  - /proMatches — recent pro matches
  - /matches/{match_id} — full match data
  - /players/{account_id}/matches — player match history
  - /heroes — hero list
  - /teams — team list
  - /teams/{team_id}/matches — team matches

Per-match stats available:
  - kills, deaths, assists per player
  - GPM, XPM (gold/experience per minute)
  - hero_damage, tower_damage
  - last_hits, denies
  - teamfight participation
  - wards placed/destroyed
  - first blood, Roshan kills
"""

from datetime import datetime, timezone
from pathlib import Path

from .base_client import BaseAPIClient, APINotFoundError, CACHE_DIR
from .rate_limiter import RateLimiter
from normalize_stats import NormalizedFixture, NormalizedMatchStats


class OpenDotaClient(BaseAPIClient):
    """Dota 2 esports client using OpenDota public API."""

    TIMEOUT = 20
    MAX_RETRIES = 2

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="opendota",
            base_url="https://api.opendota.com/api",
            rate_limiter=rate_limiter,
        )

    def is_available(self) -> bool:
        """OpenDota works without a key (rate limited to 60/min)."""
        return True

    def _load_api_key(self) -> str | None:
        """Optional API key for higher rate limits."""
        key = super()._load_api_key()
        return key  # Returns None if not configured — still works

    def _build_headers(self) -> dict:
        """No auth header required; key goes in query params if available."""
        return {"Accept": "application/json"}

    def _request(self, endpoint: str, params: dict | None = None, cost: int = 1) -> dict | list:
        """Override to inject API key into params if available."""
        if params is None:
            params = {}
        if self.api_key:
            params["api_key"] = self.api_key
        return super()._request(endpoint, params, cost)

    def get_fixtures(self, date: str = None) -> list[NormalizedFixture]:
        """Get recent/upcoming pro matches.

        OpenDota /proMatches returns recent pro matches (no date filter).
        """
        cache_key = "esports/dota2/pro_matches"
        cached = self._check_cache(cache_key, ttl_hours=2)
        if cached:
            return [NormalizedFixture(**f) for f in cached.get("fixtures", [])]

        data = self._request("/proMatches")
        matches = data if isinstance(data, list) else []

        fixtures = []
        for match in matches[:50]:  # Cap at 50 most recent
            start_time = match.get("start_time")
            if not start_time:
                continue  # Skip matches with unknown start time
            match_date = datetime.fromtimestamp(start_time, tz=timezone.utc).strftime("%Y-%m-%d")

            # Filter by date if specified
            if date and match_date != date:
                continue

            fixture = NormalizedFixture(
                fixture_id=str(match.get("match_id", "")),
                source="opendota",
                sport="esports",
                competition=match.get("league_name", "Dota 2 Pro"),
                home_team=match.get("radiant_name", "Radiant") or "Radiant",
                away_team=match.get("dire_name", "Dire") or "Dire",
                home_team_id=str(match.get("radiant_team_id", "")),
                away_team_id=str(match.get("dire_team_id", "")),
                kickoff=datetime.fromtimestamp(start_time, tz=timezone.utc).isoformat(),
                status="finished",
            )
            fixtures.append(fixture)

        self._save_cache(cache_key, {
            "fixtures": [vars(f) for f in fixtures],
            "count": len(fixtures),
        })

        print(f"[opendota] Found {len(fixtures)} pro Dota 2 matches")
        return fixtures

    def get_fixture_stats(self, match_id: str) -> dict:
        """Get full match statistics for a Dota 2 match.

        Returns aggregated team stats (kills, deaths, GPM, etc.).
        """
        cache_key = f"esports/dota2/match/{match_id}"
        cached = self._check_cache(cache_key, ttl_hours=720)  # 30 days for completed
        if cached and "stats" in cached:
            return cached["stats"]

        try:
            data = self._request(f"/matches/{match_id}")
        except APINotFoundError:
            return {}

        if not data or not isinstance(data, dict):
            return {}

        # Aggregate per-team stats from player data
        players = data.get("players", [])
        radiant_stats = {"kills": 0, "deaths": 0, "assists": 0, "gpm": 0,
                         "xpm": 0, "hero_damage": 0, "tower_damage": 0,
                         "last_hits": 0, "denies": 0}
        dire_stats = {"kills": 0, "deaths": 0, "assists": 0, "gpm": 0,
                      "xpm": 0, "hero_damage": 0, "tower_damage": 0,
                      "last_hits": 0, "denies": 0}

        radiant_count = 0
        dire_count = 0

        for player in players:
            is_radiant = player.get("isRadiant", player.get("player_slot", 128) < 128)
            target = radiant_stats if is_radiant else dire_stats

            target["kills"] += player.get("kills", 0)
            target["deaths"] += player.get("deaths", 0)
            target["assists"] += player.get("assists", 0)
            target["gpm"] += player.get("gold_per_min", 0)
            target["xpm"] += player.get("xp_per_min", 0)
            target["hero_damage"] += player.get("hero_damage", 0)
            target["tower_damage"] += player.get("tower_damage", 0)
            target["last_hits"] += player.get("last_hits", 0)
            target["denies"] += player.get("denies", 0)

            if is_radiant:
                radiant_count += 1
            else:
                dire_count += 1

        # Average GPM/XPM per player
        if radiant_count > 0:
            radiant_stats["gpm"] = round(radiant_stats["gpm"] / radiant_count)
            radiant_stats["xpm"] = round(radiant_stats["xpm"] / radiant_count)
        if dire_count > 0:
            dire_stats["gpm"] = round(dire_stats["gpm"] / dire_count)
            dire_stats["xpm"] = round(dire_stats["xpm"] / dire_count)

        # Build normalized stats
        normalized = {
            "kills": {"home": radiant_stats["kills"], "away": dire_stats["kills"]},
            "deaths": {"home": radiant_stats["deaths"], "away": dire_stats["deaths"]},
            "assists": {"home": radiant_stats["assists"], "away": dire_stats["assists"]},
            "gpm": {"home": radiant_stats["gpm"], "away": dire_stats["gpm"]},
            "xpm": {"home": radiant_stats["xpm"], "away": dire_stats["xpm"]},
            "hero_damage": {"home": radiant_stats["hero_damage"], "away": dire_stats["hero_damage"]},
            "tower_damage": {"home": radiant_stats["tower_damage"], "away": dire_stats["tower_damage"]},
            "last_hits": {"home": radiant_stats["last_hits"], "away": dire_stats["last_hits"]},
            "denies": {"home": radiant_stats["denies"], "away": dire_stats["denies"]},
            "total_kills_combined": {
                "home": radiant_stats["kills"] + dire_stats["kills"],
                "away": radiant_stats["kills"] + dire_stats["kills"],
            },
        }

        # Match-level stats
        duration = data.get("duration", 0)
        normalized["duration_minutes"] = {"home": round(duration / 60, 1), "away": round(duration / 60, 1)}
        normalized["radiant_win"] = {"home": 1 if data.get("radiant_win") else 0, "away": 0 if data.get("radiant_win") else 1}

        # Tower kills — each team has 11 towers, bits set=standing, killed = 11 - popcount
        dire_towers = data.get("tower_status_dire")
        radiant_towers = data.get("tower_status_radiant")
        normalized["tower_kills"] = {
            "home": 11 - bin(dire_towers & 0x7FF).count("1") if dire_towers is not None else 0,
            "away": 11 - bin(radiant_towers & 0x7FF).count("1") if radiant_towers is not None else 0,
        }

        self._save_cache(cache_key, {"stats": normalized, "match_id": match_id, "duration": duration})
        return normalized

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list[dict]:
        """Get H2H matches between two Dota 2 teams."""
        cache_key = f"esports/dota2/h2h/{team1_id}_vs_{team2_id}"
        cached = self._check_cache(cache_key, ttl_hours=24)
        if cached and "matches" in cached:
            return cached["matches"][:last_n]

        # Get team matches and filter for opponent
        try:
            data = self._request(f"/teams/{team1_id}/matches")
        except Exception:
            return []

        matches_raw = data if isinstance(data, list) else []
        h2h = []

        for match in matches_raw:
            opposing_id = str(match.get("opposing_team_id", ""))
            if opposing_id == team2_id:
                match_stats = self.get_fixture_stats(str(match.get("match_id", "")))
                h2h.append({
                    "match_id": str(match.get("match_id", "")),
                    "date": datetime.fromtimestamp(
                        match.get("start_time", 0), tz=timezone.utc
                    ).strftime("%Y-%m-%d"),
                    "radiant_win": match.get("radiant_win"),
                    "is_radiant": match.get("radiant", False),
                    "stats": match_stats,
                })
                if len(h2h) >= last_n:
                    break

        self._save_cache(cache_key, {"matches": h2h})
        return h2h

    def get_team_matches(self, team_id: str, last_n: int = 20) -> list[dict]:
        """Get recent matches for a team with full stats."""
        cache_key = f"esports/dota2/team_matches/{team_id}"
        cached = self._check_cache(cache_key, ttl_hours=6)
        if cached and "matches" in cached:
            return cached["matches"][:last_n]

        try:
            data = self._request(f"/teams/{team_id}/matches")
        except Exception:
            return []

        matches_raw = data if isinstance(data, list) else []
        matches = []

        for match in matches_raw[:last_n]:
            match_id = str(match.get("match_id", ""))
            stats = self.get_fixture_stats(match_id)

            matches.append({
                "match_id": match_id,
                "date": datetime.fromtimestamp(
                    match.get("start_time", 0), tz=timezone.utc
                ).strftime("%Y-%m-%d"),
                "opponent": match.get("opposing_team_name", "Unknown"),
                "opponent_id": str(match.get("opposing_team_id", "")),
                "is_radiant": match.get("radiant", False),
                "radiant_win": match.get("radiant_win"),
                "league_name": match.get("league_name", ""),
                "stats": stats,
            })

        self._save_cache(cache_key, {"matches": matches, "team_id": team_id})
        print(f"[opendota] Team {team_id}: {len(matches)} recent matches")
        return matches

    def get_teams(self) -> list[dict]:
        """Get list of pro teams."""
        cache_key = "esports/dota2/teams"
        cached = self._check_cache(cache_key, ttl_hours=48)
        if cached and "teams" in cached:
            return cached["teams"]

        data = self._request("/teams")
        teams = data if isinstance(data, list) else []

        parsed = []
        for team in teams[:200]:  # Top 200 teams
            parsed.append({
                "team_id": str(team.get("team_id", "")),
                "name": team.get("name", "Unknown"),
                "tag": team.get("tag", ""),
                "rating": team.get("rating", 0),
                "wins": team.get("wins", 0),
                "losses": team.get("losses", 0),
            })

        self._save_cache(cache_key, {"teams": parsed})
        print(f"[opendota] Loaded {len(parsed)} pro teams")
        return parsed

    def get_match_stats_normalized(self, match_id: str) -> NormalizedMatchStats | None:
        """Get full normalized match stats for pipeline integration."""
        stats = self.get_fixture_stats(match_id)
        if not stats:
            return None

        # Reuse cached match data (already populated by get_fixture_stats)
        cache_key = f"esports/dota2/match/{match_id}"
        cached = self._check_cache(cache_key, ttl_hours=720)
        data = cached if cached and isinstance(cached, dict) else {}

        radiant_name = "Radiant"
        dire_name = "Dire"
        start_time = None

        # If cache doesn't have team names, fetch (this should rarely happen)
        if not data.get("radiant_team"):
            try:
                data = self._request(f"/matches/{match_id}")
            except Exception:
                data = {}

        if isinstance(data, dict):
            rt = data.get("radiant_team")
            dt = data.get("dire_team")
            if isinstance(rt, dict):
                radiant_name = rt.get("name", "Radiant")
            if isinstance(dt, dict):
                dire_name = dt.get("name", "Dire")
            start_time = data.get("start_time")

        return NormalizedMatchStats(
            fixture_id=match_id,
            source="opendota",
            sport="esports",
            home_team=radiant_name,
            away_team=dire_name,
            date=datetime.fromtimestamp(
                start_time, tz=timezone.utc
            ).strftime("%Y-%m-%d") if start_time else "",
            stats=stats,
        )
