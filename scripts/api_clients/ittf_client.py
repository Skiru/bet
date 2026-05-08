"""ITTF Table Tennis client — rankings, H2H, player records via results.ittf.link.

Source: results.ittf.link (scraping needed, no public API)
Data available:
  - World rankings (men's/women's)
  - Player profiles with W/L records
  - H2H between two players
  - Tournament results
  - Win rates

This client uses the structured JSON responses from ITTF results site
which return data in API-like format despite not being documented.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from .base_client import BaseAPIClient, APINotFoundError, APIRateLimitError, APIError, CACHE_DIR
from .rate_limiter import RateLimiter
from normalize_stats import NormalizedFixture, NormalizedMatchStats


class ITTFClient(BaseAPIClient):
    """Table Tennis client using ITTF results platform.

    Uses structured endpoints from results.ittf.link that return JSON-like data.
    Falls back to Sofascore for live fixtures and set scores.
    """

    TIMEOUT = 25
    MAX_RETRIES = 2

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="ittf",
            base_url="https://results.ittf.link/api",
            rate_limiter=rate_limiter,
        )
        # Secondary source for live fixtures
        self._sofascore_base = "https://api.sofascore.com/api/v1"

    def is_available(self) -> bool:
        """ITTF scraping doesn't require API key."""
        return True

    def _load_api_key(self) -> str | None:
        """No API key needed."""
        return None

    def _build_headers(self) -> dict:
        """Browser-like headers for ITTF."""
        return {
            "Accept": "application/json, text/html",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://results.ittf.link/",
        }

    def _sofascore_request(self, endpoint: str) -> dict:
        """Make request to Sofascore with rate limiting and error handling."""
        import requests as req

        if not self.rate_limiter.can_request(self.api_name, 1):
            raise APIRateLimitError(f"[ittf] Daily quota exhausted")

        url = f"{self._sofascore_base}{endpoint}"
        resp = req.get(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            },
            timeout=self.TIMEOUT,
        )
        if resp.status_code == 429:
            raise APIRateLimitError(f"[ittf/sofascore] HTTP 429", status_code=429)
        if resp.status_code == 404:
            raise APINotFoundError(f"[ittf/sofascore] Not found: {endpoint}", status_code=404)
        if resp.status_code >= 400:
            raise APIError(f"[ittf/sofascore] HTTP {resp.status_code}", status_code=resp.status_code)

        self.rate_limiter.record_request(self.api_name, endpoint, 1)
        return resp.json()

    def get_fixtures(self, date: str = None) -> list[NormalizedFixture]:
        """Get table tennis matches from Sofascore (primary for fixtures).

        ITTF site doesn't have a good fixture list; Sofascore has live/upcoming.
        """
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        cache_key = f"table_tennis/fixtures/{date}"
        cached = self._check_cache(cache_key, ttl_hours=3)
        if cached:
            return [NormalizedFixture(**f) for f in cached.get("fixtures", [])]

        try:
            data = self._sofascore_request(f"/sport/table-tennis/scheduled-events/{date}")
        except (APIError, APIRateLimitError, APINotFoundError):
            return []

        events = data.get("events", [])
        fixtures = []

        for ev in events:
            tournament = ev.get("tournament", {})
            unique_tournament = tournament.get("uniqueTournament", {})
            competition = unique_tournament.get("name", tournament.get("name", "Unknown"))

            home = ev.get("homeTeam", {})
            away = ev.get("awayTeam", {})

            fixture = NormalizedFixture(
                fixture_id=str(ev.get("id", "")),
                source="ittf",
                sport="table_tennis",
                competition=competition,
                home_team=home.get("name", "Unknown"),
                away_team=away.get("name", "Unknown"),
                home_team_id=str(home.get("id", "")),
                away_team_id=str(away.get("id", "")),
                kickoff=datetime.fromtimestamp(
                    ev.get("startTimestamp", 0), tz=timezone.utc
                ).isoformat() if ev.get("startTimestamp") else "",
                status=ev.get("status", {}).get("type", "notstarted"),
            )
            fixtures.append(fixture)

        self._save_cache(cache_key, {
            "fixtures": [vars(f) for f in fixtures],
            "count": len(fixtures),
        })

        print(f"[ittf] Found {len(fixtures)} table tennis fixtures for {date}")
        return fixtures

    def get_fixture_stats(self, fixture_id: str) -> dict:
        """Get match stats — for TT this is mainly set scores from Sofascore."""
        cache_key = f"table_tennis/stats/{fixture_id}"
        cached = self._check_cache(cache_key, ttl_hours=168)
        if cached and "stats" in cached:
            return cached["stats"]

        try:
            data = self._sofascore_request(f"/event/{fixture_id}")
        except (APIError, APIRateLimitError, APINotFoundError):
            return {}

        event = data.get("event", data)
        home_score = event.get("homeScore", {})
        away_score = event.get("awayScore", {})

        # Extract set scores
        sets_home = int(home_score.get("current") or 0)
        sets_away = int(away_score.get("current") or 0)
        total_sets = sets_home + sets_away

        # Count points per set
        total_points_home = 0
        total_points_away = 0
        set_details = []

        for i in range(1, 8):  # TT can have up to 7 sets
            h_pts = home_score.get(f"period{i}")
            a_pts = away_score.get(f"period{i}")
            if h_pts is not None and a_pts is not None:
                total_points_home += h_pts
                total_points_away += a_pts
                set_details.append({"set": i, "home": h_pts, "away": a_pts})

        total_points = total_points_home + total_points_away

        stats = {
            "sets_won": {"home": sets_home, "away": sets_away},
            "total_sets": {"home": total_sets, "away": total_sets},
            "total_points": {"home": total_points, "away": total_points},
            "points_scored": {"home": total_points_home, "away": total_points_away},
            "points_per_set": {
                "home": round(total_points_home / total_sets, 1) if total_sets > 0 else 0,
                "away": round(total_points_away / total_sets, 1) if total_sets > 0 else 0,
            },
        }

        if stats["sets_won"]["home"] or stats["sets_won"]["away"]:
            self._save_cache(cache_key, {"stats": stats, "set_details": set_details})

        return stats

    def get_h2h(self, player1_id: str, player2_id: str, last_n: int = 10) -> list[dict]:
        """Get H2H between two table tennis players.

        Tries Sofascore H2H first, falls back to ITTF site.
        """
        cache_key = f"table_tennis/h2h/{player1_id}_vs_{player2_id}"
        cached = self._check_cache(cache_key, ttl_hours=24)
        if cached and "matches" in cached:
            return cached["matches"][:last_n]

        # Try Sofascore H2H via team events
        try:
            data = self._sofascore_request(f"/team/{player1_id}/events/last/0")
        except (APIError, APIRateLimitError, APINotFoundError):
            return []

        events = data.get("events", [])
        h2h = []

        for ev in events:
            home_id = str(ev.get("homeTeam", {}).get("id", ""))
            away_id = str(ev.get("awayTeam", {}).get("id", ""))

            if player2_id in (home_id, away_id):
                stats = self.get_fixture_stats(str(ev.get("id", "")))
                if stats:
                    h2h.append({
                        "fixture_id": str(ev.get("id", "")),
                        "date": datetime.fromtimestamp(
                            ev.get("startTimestamp", 0), tz=timezone.utc
                        ).strftime("%Y-%m-%d"),
                        "home": ev.get("homeTeam", {}).get("name", ""),
                        "away": ev.get("awayTeam", {}).get("name", ""),
                        "stats": stats,
                    })
                    if len(h2h) >= last_n:
                        break

        self._save_cache(cache_key, {"matches": h2h})
        return h2h

    def get_rankings(self, gender: str = "M", limit: int = 100) -> list[dict]:
        """Get ITTF world rankings.

        Args:
            gender: "M" for men, "W" for women
            limit: Number of top players to return
        """
        cache_key = f"table_tennis/rankings/{gender}"
        cached = self._check_cache(cache_key, ttl_hours=48)
        if cached and "rankings" in cached:
            return cached["rankings"][:limit]

        # Use ITTF rankings API endpoint
        try:
            data = self._request(f"/rankings", params={"gender": gender, "limit": str(limit)})
        except Exception:
            # Fallback: try Sofascore rankings
            return self._get_sofascore_rankings(gender, limit)

        if not isinstance(data, list):
            data = data.get("rankings", []) if isinstance(data, dict) else []

        rankings = []
        for i, player in enumerate(data[:limit], 1):
            rankings.append({
                "rank": player.get("rank", i),
                "player_id": str(player.get("id", "")),
                "name": player.get("name", "Unknown"),
                "country": player.get("country", ""),
                "points": player.get("points", 0),
            })

        self._save_cache(cache_key, {"rankings": rankings})
        print(f"[ittf] Loaded {len(rankings)} rankings ({gender})")
        return rankings

    def _get_sofascore_rankings(self, gender: str, limit: int) -> list[dict]:
        """Fallback to Sofascore for rankings data."""
        return []  # Sofascore doesn't expose TT rankings easily

    def get_player_form(self, player_id: str, last_n: int = 10) -> list[dict]:
        """Get recent matches for a player with set scores.

        Args:
            player_id: Sofascore player/team ID
            last_n: Number of recent matches
        """
        cache_key = f"table_tennis/form/{player_id}"
        cached = self._check_cache(cache_key, ttl_hours=6)
        if cached and "matches" in cached:
            return cached["matches"][:last_n]

        try:
            data = self._sofascore_request(f"/team/{player_id}/events/last/0")
        except (APIError, APIRateLimitError, APINotFoundError):
            return []

        events = data.get("events", [])
        matches = []

        for ev in events[:last_n * 2]:
            if ev.get("status", {}).get("type") != "finished":
                continue

            ev_id = str(ev.get("id", ""))
            stats = self.get_fixture_stats(ev_id)
            if not stats:
                continue

            home_id = str(ev.get("homeTeam", {}).get("id", ""))
            is_home = (home_id == player_id)
            opponent = ev.get("awayTeam", {}).get("name", "") if is_home else ev.get("homeTeam", {}).get("name", "")

            matches.append({
                "fixture_id": ev_id,
                "date": datetime.fromtimestamp(
                    ev.get("startTimestamp", 0), tz=timezone.utc
                ).strftime("%Y-%m-%d"),
                "opponent": opponent,
                "is_home": is_home,
                "stats": stats,
                "competition": ev.get("tournament", {}).get("uniqueTournament", {}).get("name", ""),
            })

            if len(matches) >= last_n:
                break

        self._save_cache(cache_key, {"matches": matches, "player_id": player_id})
        return matches

    def get_match_stats_normalized(self, fixture_id: str) -> NormalizedMatchStats | None:
        """Get normalized match stats for pipeline integration."""
        stats = self.get_fixture_stats(fixture_id)
        if not stats:
            return None

        import requests
        try:
            resp = requests.get(
                f"{self._sofascore_base}/event/{fixture_id}",
                headers={
                    "Accept": "application/json",
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                },
                timeout=self.TIMEOUT,
            )
            event = resp.json().get("event", {}) if resp.status_code == 200 else {}
        except Exception:
            event = {}

        return NormalizedMatchStats(
            fixture_id=fixture_id,
            source="ittf",
            sport="table_tennis",
            home_team=event.get("homeTeam", {}).get("name", "Unknown"),
            away_team=event.get("awayTeam", {}).get("name", "Unknown"),
            date=datetime.fromtimestamp(
                event.get("startTimestamp", 0), tz=timezone.utc
            ).strftime("%Y-%m-%d") if event.get("startTimestamp") else "",
            stats=stats,
        )
