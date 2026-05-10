"""Sofascore Darts client — fixtures, per-match statistics, H2H.

Source: api.sofascore.com (free, no auth required)
Stats available per match:
  - Average 3 Darts
  - 180s thrown
  - 140+ and 100+ thrown
  - Highest Checkout
  - Checkouts over 100
  - Checkout Accuracy (made/total, %)

Sport ID: 22 (darts)
"""

from datetime import datetime, timezone
from pathlib import Path

from .base_client import BaseAPIClient, APINotFoundError, APIRateLimitError, APIError, CACHE_DIR
from .rate_limiter import RateLimiter
from normalize_stats import NormalizedFixture, NormalizedMatchStats


# Sofascore stat keys → our normalized keys
STAT_KEY_MAP = {
    "Average3Darts": "avg_score",
    "Thrown180": "one_eighties",
    "ThrownOver140": "thrown_over_140",
    "ThrownOver100": "thrown_over_100",
    "HighestCheckout": "highest_checkout",
    "CheckoutsOver100": "checkouts_over_100",
    "CheckoutsAccuracy": "checkout_pct",
}


class SofascoreDartsClient(BaseAPIClient):
    """Darts client using Sofascore public API (no auth)."""

    TIMEOUT = 20

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="sofascore-darts",
            base_url="https://api.sofascore.com/api/v1",
            rate_limiter=rate_limiter,
        )

    def is_available(self) -> bool:
        """Sofascore requires no API key."""
        return True

    def _load_api_key(self) -> str | None:
        """No API key needed for Sofascore."""
        return None

    def _build_headers(self) -> dict:
        """Sofascore needs no auth, just standard headers."""
        return {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        }

    def get_fixtures(self, date: str) -> list[NormalizedFixture]:
        """Get all darts matches on a date (YYYY-MM-DD).

        Returns list of NormalizedFixture.
        """
        cache_key = f"darts/fixtures/{date}"
        cached = self._check_cache(cache_key, ttl_hours=4)
        if cached:
            return [NormalizedFixture(**f) for f in cached.get("fixtures", [])]

        data = self._request(f"/sport/darts/scheduled-events/{date}")
        events = data.get("events", [])

        fixtures = []
        for ev in events:
            status_desc = ev.get("status", {}).get("type", "notstarted")
            tournament = ev.get("tournament", {})
            unique_tournament = tournament.get("uniqueTournament", {})
            competition_name = unique_tournament.get("name", tournament.get("name", "Unknown"))

            home_team = ev.get("homeTeam", {})
            away_team = ev.get("awayTeam", {})

            fixture = NormalizedFixture(
                fixture_id=str(ev.get("id", "")),
                source="sofascore-darts",
                sport="darts",
                competition=competition_name,
                home_team=home_team.get("name", "Unknown"),
                away_team=away_team.get("name", "Unknown"),
                home_team_id=str(home_team.get("id", "")),
                away_team_id=str(away_team.get("id", "")),
                kickoff=datetime.fromtimestamp(
                    ev.get("startTimestamp", 0), tz=timezone.utc
                ).isoformat() if ev.get("startTimestamp") else "",
                status=status_desc,
            )
            fixtures.append(fixture)

        # Cache results
        self._save_cache(cache_key, {
            "fixtures": [vars(f) for f in fixtures],
            "count": len(fixtures),
        })

        print(f"[sofascore-darts] Found {len(fixtures)} darts fixtures for {date}")
        return fixtures

    def get_fixture_stats(self, fixture_id: str) -> dict:
        """Get per-match statistics for a completed darts event.

        Returns normalized stats dict or empty dict if no stats available.
        """
        cache_key = f"darts/stats/{fixture_id}"
        cached = self._check_cache(cache_key, ttl_hours=168)  # 1 week for completed matches
        if cached and "stats" in cached:
            return cached["stats"]

        try:
            data = self._request(f"/event/{fixture_id}/statistics")
        except APINotFoundError:
            return {}

        statistics = data.get("statistics", [])
        if not statistics:
            return {}

        # Parse stats from ALL period (full match)
        normalized = {}
        for period_block in statistics:
            if period_block.get("period") != "ALL":
                continue
            for group in period_block.get("groups", []):
                for item in group.get("statisticsItems", []):
                    key = item.get("key", "")
                    our_key = STAT_KEY_MAP.get(key)
                    if not our_key:
                        continue

                    home_val = float(item.get("homeValue", 0) or 0)
                    away_val = float(item.get("awayValue", 0) or 0)

                    # Checkout accuracy: parse "4/4 (19%)" to percentage
                    if key == "CheckoutsAccuracy":
                        home_total = item.get("homeTotal", 0)
                        away_total = item.get("awayTotal", 0)
                        # Store both raw count and total for accuracy calc
                        normalized["checkout_made"] = {"home": home_val, "away": away_val}
                        normalized["checkout_total"] = {"home": home_total, "away": away_total}
                        # Pct = made/total * 100
                        home_pct = (home_val / home_total * 100) if home_total > 0 else 0
                        away_pct = (away_val / away_total * 100) if away_total > 0 else 0
                        normalized[our_key] = {"home": round(home_pct, 1), "away": round(away_pct, 1)}
                    else:
                        normalized[our_key] = {"home": home_val, "away": away_val}

        if normalized:
            self._save_cache(cache_key, {"stats": normalized, "fixture_id": fixture_id})

        return normalized

    def get_h2h(self, player1_id: str, player2_id: str, last_n: int = 10) -> list[dict]:
        """Get H2H matches between two players.

        Uses Sofascore's H2H endpoint.
        Returns list of match stat dicts.
        """
        cache_key = f"darts/h2h/{player1_id}_vs_{player2_id}"
        cached = self._check_cache(cache_key, ttl_hours=24)
        if cached and "matches" in cached:
            return cached["matches"]

        try:
            data = self._request(f"/event/{player1_id}/h2h/events", params={"page": "0"})
        except APINotFoundError:
            # H2H by event ID not found — fall back to team-based lookup
            return self._get_h2h_by_teams(player1_id, player2_id, last_n)
        except APIRateLimitError:
            raise  # Don't mask rate limits
        except APIError as e:
            print(f"[sofascore-darts] H2H lookup failed: {e}, falling back to team-based")
            return self._get_h2h_by_teams(player1_id, player2_id, last_n)

        events = data.get("events", [])[:last_n]
        matches = []
        for ev in events:
            match_stats = self.get_fixture_stats(str(ev.get("id", "")))
            if match_stats:
                matches.append({
                    "fixture_id": str(ev.get("id", "")),
                    "date": datetime.fromtimestamp(
                        ev.get("startTimestamp", 0), tz=timezone.utc
                    ).strftime("%Y-%m-%d"),
                    "home": ev.get("homeTeam", {}).get("name", ""),
                    "away": ev.get("awayTeam", {}).get("name", ""),
                    "stats": match_stats,
                })

        self._save_cache(cache_key, {"matches": matches})
        return matches

    def _get_h2h_by_teams(self, team1_id: str, team2_id: str, last_n: int) -> list:
        """Fallback H2H lookup using team IDs."""
        try:
            data = self._request(
                f"/team/{team1_id}/events/last/0",
            )
            events = data.get("events", [])
            h2h = []
            for ev in events:
                home_id = str(ev.get("homeTeam", {}).get("id", ""))
                away_id = str(ev.get("awayTeam", {}).get("id", ""))
                if team2_id in (home_id, away_id):
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
            return h2h
        except Exception:
            return []

    def get_player_last_matches(self, player_id: str, last_n: int = 10) -> list[dict]:
        """Get last N completed matches for a player with full stats.

        Args:
            player_id: Sofascore team/player ID
            last_n: Number of recent matches to retrieve

        Returns:
            List of dicts with fixture_id, date, opponent, stats
        """
        cache_key = f"darts/player_form/{player_id}"
        cached = self._check_cache(cache_key, ttl_hours=6)
        if cached and "matches" in cached:
            return cached["matches"][:last_n]

        try:
            data = self._request(f"/team/{player_id}/events/last/0")
        except Exception:
            return []

        events = data.get("events", [])
        matches = []
        for ev in events[:last_n * 2]:  # fetch extra in case some lack stats
            ev_id = str(ev.get("id", ""))
            stats = self.get_fixture_stats(ev_id)
            if not stats:
                continue

            home_name = ev.get("homeTeam", {}).get("name", "")
            away_name = ev.get("awayTeam", {}).get("name", "")
            home_id = str(ev.get("homeTeam", {}).get("id", ""))

            is_home = (home_id == player_id)
            opponent = away_name if is_home else home_name

            matches.append({
                "fixture_id": ev_id,
                "date": datetime.fromtimestamp(
                    ev.get("startTimestamp", 0), tz=timezone.utc
                ).strftime("%Y-%m-%d"),
                "opponent": opponent,
                "is_home": is_home,
                "stats": stats,
            })

            if len(matches) >= last_n:
                break

        self._save_cache(cache_key, {"matches": matches, "player_id": player_id})
        return matches

    def get_match_stats_normalized(self, fixture_id: str) -> NormalizedMatchStats | None:
        """Get full normalized match stats for pipeline integration."""
        stats = self.get_fixture_stats(fixture_id)
        if not stats:
            return None

        # We need event info too
        try:
            event_data = self._request(f"/event/{fixture_id}")
            event = event_data.get("event", event_data)
        except Exception:
            event = {}

        return NormalizedMatchStats(
            fixture_id=fixture_id,
            source="sofascore-darts",
            sport="darts",
            home_team=event.get("homeTeam", {}).get("name", "Unknown"),
            away_team=event.get("awayTeam", {}).get("name", "Unknown"),
            date=datetime.fromtimestamp(
                event.get("startTimestamp", 0), tz=timezone.utc
            ).strftime("%Y-%m-%d") if event.get("startTimestamp") else "",
            stats=stats,
        )
