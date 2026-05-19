"""SofaScore Tennis adapter — per-match serve statistics via SofaScore API.

SofaScore's internal API provides detailed per-event statistics for tennis:
aces, double faults, first serve %, break points won/saved, total games won.

Endpoint: /event/{id}/statistics (returns structured stat groups)
Player search: /search/teams/{name} (SofaScore treats players as "teams")
Player events: /team/{id}/events/last/0

No API key required, but aggressive rate-limiting (403/429 if too fast).
"""

import logging
import time

from .base_client import BaseAPIClient, APIError, APINotFoundError, CACHE_DIR
from .rate_limiter import RateLimiter
from bet.models.normalized import NormalizedFixture, NormalizedMatchStats

logger = logging.getLogger(__name__)


class SofascoreTennisClient(BaseAPIClient):
    """SofaScore tennis-specific adapter returning NormalizedMatchStats."""

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="sofascore-tennis",
            base_url="https://api.sofascore.com/api/v1",
            rate_limiter=rate_limiter,
        )
        # Reuse the general SofascoreClient's request logic
        from .sofascore import SofascoreClient
        self._sofa = SofascoreClient(rate_limiter=rate_limiter)

    # ─── BaseAPIClient overrides ─────────────────────────────────────

    def _load_api_key(self) -> str:
        return "sofascore-no-key"

    def is_available(self) -> bool:
        return True

    def _build_headers(self) -> dict:
        return {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/115.0",
            "Accept": "application/json",
        }

    def get_fixtures(self, date: str) -> list[NormalizedFixture]:
        """Get scheduled tennis events for a date."""
        try:
            data = self._sofa._request(f"/sport/tennis/scheduled-events/{date}")
            events = data.get("events", [])
            fixtures = []
            for ev in events:
                tournament = ev.get("tournament", {})
                home = ev.get("homeTeam", {}).get("name", "")
                away = ev.get("awayTeam", {}).get("name", "")
                if not home or not away:
                    continue
                from datetime import datetime, timezone
                start_ts = ev.get("startTimestamp", 0)
                kickoff = datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat() if start_ts else ""
                fixtures.append(NormalizedFixture(
                    fixture_id=str(ev.get("id", "")),
                    source="sofascore-tennis",
                    sport="tennis",
                    competition=tournament.get("name", ""),
                    home_team=home,
                    away_team=away,
                    kickoff=kickoff,
                    status=ev.get("status", {}).get("type", "notstarted"),
                ))
            return fixtures
        except (APIError, Exception) as e:
            logger.debug(f"[sofascore-tennis] get_fixtures failed: {e}")
            return []

    def get_fixture_stats(self, fixture_id: str) -> NormalizedMatchStats | None:
        """Get serve statistics for a specific event."""
        if not fixture_id or not fixture_id.isdigit():
            return None

        try:
            data = self._sofa._request(f"/event/{fixture_id}/statistics")
            stat_groups = data.get("statistics", [])
            if not stat_groups:
                return None

            # Also get event info for team names
            event_data = self._sofa._request(f"/event/{fixture_id}")
            event = event_data.get("event", event_data)
            home_name = event.get("homeTeam", {}).get("name", "")
            away_name = event.get("awayTeam", {}).get("name", "")
            start_ts = event.get("startTimestamp", 0)
            from datetime import datetime, timezone
            date_str = datetime.fromtimestamp(start_ts, tz=timezone.utc).strftime("%Y-%m-%d") if start_ts else ""

            stats = self._parse_tennis_stats(stat_groups)
            if not stats:
                return None

            return NormalizedMatchStats(
                fixture_id=fixture_id,
                source="sofascore-tennis",
                sport="tennis",
                home_team=home_name,
                away_team=away_name,
                date=date_str,
                stats=stats,
            )
        except (APIError, APINotFoundError) as e:
            logger.debug(f"[sofascore-tennis] get_fixture_stats({fixture_id}) failed: {e}")
            return None

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list[dict]:
        """Not directly supported without event_id."""
        return []

    def resolve_team_id(self, team_name: str, **kwargs) -> str | None:
        """Search SofaScore for a tennis player (treated as 'team')."""
        try:
            return self._sofa.resolve_team_id(team_name)
        except Exception:
            return None

    def get_team_last_fixtures(self, team_id: str, last_n: int = 10) -> list[NormalizedFixture]:
        """Get last N finished events for a player."""
        if not team_id or not team_id.isdigit():
            return []

        try:
            data = self._sofa._request(f"/team/{team_id}/events/last/0")
            events = data.get("events", [])
            fixtures = []
            for ev in events[:last_n]:
                status = ev.get("status", {}).get("type", "")
                if status != "finished":
                    continue
                home = ev.get("homeTeam", {}).get("name", "")
                away = ev.get("awayTeam", {}).get("name", "")
                from datetime import datetime, timezone
                start_ts = ev.get("startTimestamp", 0)
                kickoff = datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat() if start_ts else ""
                fixtures.append(NormalizedFixture(
                    fixture_id=str(ev.get("id", "")),
                    source="sofascore-tennis",
                    sport="tennis",
                    competition=ev.get("tournament", {}).get("name", ""),
                    home_team=home,
                    away_team=away,
                    kickoff=kickoff,
                    status="FT",
                ))
                if len(fixtures) >= last_n:
                    break
            return fixtures
        except (APIError, Exception) as e:
            logger.debug(f"[sofascore-tennis] get_team_last_fixtures failed: {e}")
            return []

    # ─── Tennis stat parsing ─────────────────────────────────────────

    def _parse_tennis_stats(self, stat_groups: list) -> dict:
        """Parse SofaScore tennis statistics structure.

        SofaScore returns stats as:
        [{"period": "ALL", "groups": [{"groupName": "Service", "statisticsItems": [...]}]}]
        """
        stats = {}

        for period_block in stat_groups:
            period = period_block.get("period", "")
            if period != "ALL":
                continue

            groups = period_block.get("groups", [])
            for group in groups:
                group_name = (group.get("groupName", "") or "").lower()
                items = group.get("statisticsItems", [])

                for item in items:
                    name = (item.get("name", "") or "").lower().replace(" ", "_")
                    home_val = item.get("home", "")
                    away_val = item.get("away", "")

                    # Map SofaScore stat names to our normalized names
                    mapped = self._map_stat_name(name, group_name)
                    if mapped:
                        stats[f"home_{mapped}"] = self._parse_stat_value(home_val)
                        stats[f"away_{mapped}"] = self._parse_stat_value(away_val)

        return stats if stats else {}

    @staticmethod
    def _map_stat_name(name: str, group_name: str) -> str | None:
        """Map SofaScore stat names to our pipeline stat names."""
        mapping = {
            "aces": "aces",
            "double_faults": "double_faults",
            "first_serve": "first_serve_pct",
            "first_serve_percentage": "first_serve_pct",
            "first_serve_points_won": "first_serve_win_pct",
            "second_serve_points_won": "second_serve_win_pct",
            "break_points_won": "break_points_won",
            "break_points_saved": "break_points_saved",
            "break_points_converted": "break_pct",
            "service_games_won": "hold_pct",
            "return_games_won": "return_games_won",
            "total_games_won": "games_won",
            "max_games_in_a_row": "max_games_streak",
            "service_points_won": "service_points_won",
            "receiver_points_won": "return_points_won",
            "total_points_won": "total_points_won",
            "max_points_in_a_row": "max_points_streak",
        }
        return mapping.get(name)

    @staticmethod
    def _parse_stat_value(val) -> float | int:
        """Parse SofaScore stat value (can be '67%', '5', etc.)."""
        if val is None:
            return 0
        if isinstance(val, (int, float)):
            return val
        s = str(val).strip().replace("%", "")
        try:
            if "." in s:
                return float(s)
            return int(s)
        except (ValueError, TypeError):
            return 0
