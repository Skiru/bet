"""Snooker API client — fixtures, results, H2H, player stats via api.snooker.org.

Source: api.snooker.org (FREE, requires X-Requested-By header)
Endpoints:
  - t=6&e={eventId}  — matches by event
  - t=8&p={playerId} — player matches
  - p1={id1}&p2={id2} — H2H
  - t=14               — upcoming matches
  - t=15               — results (recent)
  - t=7                — ongoing matches
  - t=3&s={season}     — rankings
  - t=5&s={season}     — events in season

Data available:
  - Frame scores, century breaks (in parentheses)
  - Player rankings, nationality, DOB
  - H2H records
"""

from datetime import datetime, timezone
from pathlib import Path

from .base_client import BaseAPIClient, APINotFoundError, CACHE_DIR
from .rate_limiter import RateLimiter
from normalize_stats import NormalizedFixture, NormalizedMatchStats


class SnookerOrgClient(BaseAPIClient):
    """Snooker API client using api.snooker.org (free for non-commercial use).

    IMPORTANT: Requires an approved X-Requested-By value.
    Contact webmaster@snooker.org to register your application name.
    Set SNOOKER_ORG_APP_NAME env var or add "snooker_org_app_name" to api_keys.json.
    """

    TIMEOUT = 20
    MAX_RETRIES = 2

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="snooker-org",
            base_url="https://api.snooker.org",
            rate_limiter=rate_limiter,
        )

    def is_available(self) -> bool:
        """Requires approved X-Requested-By header — check if configured."""
        return self._get_app_name() is not None

    def _get_app_name(self) -> str | None:
        """Get registered app name from env or config."""
        import os
        name = os.environ.get("SNOOKER_ORG_APP_NAME")
        if name:
            return name
        # Check api_keys.json
        keys_file = Path(__file__).parent.parent.parent / "config" / "api_keys.json"
        if keys_file.exists():
            import json as _json
            keys = _json.loads(keys_file.read_text(encoding="utf-8"))
            return keys.get("snooker_org_app_name")
        return None

    def _load_api_key(self) -> str | None:
        """No API key needed."""
        return None

    def _build_headers(self) -> dict:
        """Required X-Requested-By header per API docs (must be approved value)."""
        app_name = self._get_app_name() or "bet-pipeline"
        return {
            "Accept": "application/json",
            "X-Requested-By": app_name,
        }

    def get_fixtures(self, date: str = None) -> list[NormalizedFixture]:
        """Get upcoming snooker matches.

        Note: api.snooker.org doesn't filter by date directly.
        t=14 returns upcoming matches; t=15 returns recent results.
        """
        cache_key = f"snooker/fixtures/upcoming_{date or 'all'}"
        cached = self._check_cache(cache_key, ttl_hours=3)
        if cached:
            return [NormalizedFixture(**f) for f in cached.get("fixtures", [])]

        data = self._request("", params={"t": "14"})
        # API returns a list directly
        matches = data if isinstance(data, list) else []

        fixtures = []
        for match in matches:
            fixture = NormalizedFixture(
                fixture_id=str(match.get("ID", "")),
                source="snooker-org",
                sport="snooker",
                competition=match.get("EventName", "Unknown"),
                home_team=match.get("Player1Name", "Unknown"),
                away_team=match.get("Player2Name", "Unknown"),
                home_team_id=str(match.get("Player1ID", "")),
                away_team_id=str(match.get("Player2ID", "")),
                kickoff=match.get("ScheduledDate", ""),
                status="scheduled",
            )
            fixtures.append(fixture)

        self._save_cache(cache_key, {
            "fixtures": [vars(f) for f in fixtures],
            "count": len(fixtures),
        })

        print(f"[snooker-org] Found {len(fixtures)} upcoming snooker matches")
        return fixtures

    def get_recent_results(self) -> list[dict]:
        """Get recently completed snooker matches (t=15)."""
        cache_key = "snooker/results/recent"
        cached = self._check_cache(cache_key, ttl_hours=2)
        if cached and "results" in cached:
            return cached["results"]

        data = self._request("", params={"t": "15"})
        matches = data if isinstance(data, list) else []

        results = []
        for match in matches:
            results.append(self._parse_match(match))

        self._save_cache(cache_key, {"results": results})
        print(f"[snooker-org] Fetched {len(results)} recent results")
        return results

    def get_fixture_stats(self, fixture_id: str) -> dict:
        """Get match stats for a specific snooker match.

        For snooker, stats come from the match record itself:
        frames won, centuries, etc. Frame-by-frame data isn't available
        via a stats endpoint — it's embedded in the match result.
        """
        cache_key = f"snooker/stats/{fixture_id}"
        cached = self._check_cache(cache_key, ttl_hours=168)
        if cached and "stats" in cached:
            return cached["stats"]

        # Fetch match details — no dedicated stats endpoint for individual match
        # We use event matches (t=6) which includes frame scores
        # For now, use the match data from results
        return {}

    def get_event_matches(self, event_id: str) -> list[dict]:
        """Get all matches for a specific tournament event.

        Args:
            event_id: Snooker event/tournament ID

        Returns:
            List of parsed match dicts with stats
        """
        cache_key = f"snooker/event/{event_id}"
        cached = self._check_cache(cache_key, ttl_hours=6)
        if cached and "matches" in cached:
            return cached["matches"]

        data = self._request("", params={"t": "6", "e": event_id})
        matches = data if isinstance(data, list) else []

        parsed = []
        for match in matches:
            parsed.append(self._parse_match(match))

        self._save_cache(cache_key, {"matches": parsed, "event_id": event_id})
        print(f"[snooker-org] Event {event_id}: {len(parsed)} matches")
        return parsed

    def get_h2h(self, player1_id: str, player2_id: str, last_n: int = 10) -> list[dict]:
        """Get H2H history between two snooker players.

        Uses the built-in H2H endpoint: ?p1={id}&p2={id}
        """
        cache_key = f"snooker/h2h/{player1_id}_vs_{player2_id}"
        cached = self._check_cache(cache_key, ttl_hours=24)
        if cached and "matches" in cached:
            return cached["matches"][:last_n]

        data = self._request("", params={"p1": player1_id, "p2": player2_id})
        matches = data if isinstance(data, list) else []

        parsed = []
        for match in matches[:last_n]:
            parsed.append(self._parse_match(match))

        self._save_cache(cache_key, {"matches": parsed})
        print(f"[snooker-org] H2H {player1_id} vs {player2_id}: {len(parsed)} matches")
        return parsed

    def get_player_matches(self, player_id: str, season: int = None) -> list[dict]:
        """Get all matches for a specific player.

        Args:
            player_id: Snooker player ID
            season: Season year (e.g. 2025). Defaults to current.
        """
        if season is None:
            season = datetime.now().year

        cache_key = f"snooker/player_matches/{player_id}_{season}"
        cached = self._check_cache(cache_key, ttl_hours=12)
        if cached and "matches" in cached:
            return cached["matches"]

        data = self._request("", params={"t": "8", "p": player_id, "s": str(season)})
        matches = data if isinstance(data, list) else []

        parsed = []
        for match in matches:
            parsed.append(self._parse_match(match))

        self._save_cache(cache_key, {"matches": parsed, "player_id": player_id})
        print(f"[snooker-org] Player {player_id}: {len(parsed)} matches in {season}")
        return parsed

    def get_ongoing_matches(self) -> list[dict]:
        """Get currently ongoing snooker matches (t=7)."""
        data = self._request("", params={"t": "7"})
        matches = data if isinstance(data, list) else []
        return [self._parse_match(m) for m in matches]

    def get_season_events(self, season: int = None) -> list[dict]:
        """Get all events/tournaments in a season (t=5)."""
        if season is None:
            season = datetime.now().year

        cache_key = f"snooker/events/{season}"
        cached = self._check_cache(cache_key, ttl_hours=48)
        if cached and "events" in cached:
            return cached["events"]

        data = self._request("", params={"t": "5", "s": str(season)})
        events = data if isinstance(data, list) else []

        parsed = []
        for ev in events:
            parsed.append({
                "event_id": str(ev.get("ID", "")),
                "name": ev.get("Name", ""),
                "start_date": ev.get("StartDate", ""),
                "end_date": ev.get("EndDate", ""),
                "city": ev.get("City", ""),
                "country": ev.get("Country", ""),
                "type": ev.get("Type", ""),
            })

        self._save_cache(cache_key, {"events": parsed})
        return parsed

    def get_rankings(self, season: int = None) -> list[dict]:
        """Get world rankings for a season (t=3)."""
        if season is None:
            season = datetime.now().year

        cache_key = f"snooker/rankings/{season}"
        cached = self._check_cache(cache_key, ttl_hours=24)
        if cached and "rankings" in cached:
            return cached["rankings"]

        data = self._request("", params={"t": "3", "s": str(season)})
        rankings = data if isinstance(data, list) else []

        parsed = []
        for r in rankings:
            parsed.append({
                "player_id": str(r.get("PlayerID", "")),
                "name": f"{r.get('FirstName', '')} {r.get('LastName', '')}".strip(),
                "position": r.get("Position", 0),
                "prize_money": r.get("Sum", 0),
            })

        self._save_cache(cache_key, {"rankings": parsed})
        print(f"[snooker-org] Loaded {len(parsed)} ranked players for {season}")
        return parsed

    def _parse_match(self, match: dict) -> dict:
        """Parse raw API match record into normalized dict."""
        # Frame scores — Score1 and Score2 are final frame counts
        score1 = match.get("Score1", 0) or 0
        score2 = match.get("Score2", 0) or 0
        total_frames = score1 + score2

        # Century breaks (stored in parentheses in notes or separate fields)
        # The API provides century breaks via separate fields in some events

        return {
            "match_id": str(match.get("ID", "")),
            "event_name": match.get("EventName", ""),
            "round": match.get("Round", ""),
            "player1_id": str(match.get("Player1ID", "")),
            "player1_name": match.get("Player1Name", "Unknown"),
            "player2_id": str(match.get("Player2ID", "")),
            "player2_name": match.get("Player2Name", "Unknown"),
            "score1": score1,
            "score2": score2,
            "total_frames": total_frames,
            "winner_id": str(match.get("WinnerID", "")),
            "scheduled_date": match.get("ScheduledDate", ""),
            "start_date": match.get("StartDate", ""),
            "end_date": match.get("EndDate", ""),
            "best_of": match.get("Distance", 0),  # best-of-N frames
            "stats": {
                "frames_won": {"home": score1, "away": score2},
                "total_frames": {"home": total_frames, "away": total_frames},
            },
        }

    def get_match_stats_normalized(self, match: dict) -> NormalizedMatchStats:
        """Convert parsed match dict to NormalizedMatchStats."""
        return NormalizedMatchStats(
            fixture_id=match.get("match_id", ""),
            source="snooker-org",
            sport="snooker",
            home_team=match.get("player1_name", "Unknown"),
            away_team=match.get("player2_name", "Unknown"),
            date=match.get("scheduled_date", "")[:10],
            stats=match.get("stats", {}),
        )
