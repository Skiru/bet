"""Understat xG data wrapper — top 6 EU football leagues.

Uses the `understat` Python package (async internally, wrapped with asyncio.run).
No API key required.
"""

import asyncio
from pathlib import Path

from .base_client import BaseAPIClient
from .rate_limiter import RateLimiter

try:
    from scripts.normalize_stats import NormalizedFixture, NormalizedMatchStats
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from normalize_stats import NormalizedFixture, NormalizedMatchStats

try:
    import understat as understat_pkg

    UNDERSTAT_AVAILABLE = True
except ImportError:
    UNDERSTAT_AVAILABLE = False


class UnderstatClient(BaseAPIClient):
    """Understat xG data — top 6 EU football leagues."""

    LEAGUE_MAP = {
        "Premier League": "EPL",
        "La Liga": "La_liga",
        "Bundesliga": "Bundesliga",
        "Serie A": "Serie_A",
        "Ligue 1": "Ligue_1",
        "RFPL": "RFPL",
    }

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="understat",
            base_url="https://understat.com",
            rate_limiter=rate_limiter,
        )
        if not UNDERSTAT_AVAILABLE:
            print(
                f"[{self.api_name}] WARNING: 'understat' package not installed. "
                "Install with: pip3 install understat"
            )

    def _build_headers(self) -> dict:
        """No auth needed for Understat."""
        return {"Accept": "application/json"}

    def _check_api_key(self) -> bool:
        """No API key needed — always returns True if package is available."""
        return UNDERSTAT_AVAILABLE

    def is_available(self) -> bool:
        """No API key needed — available if understat package is installed."""
        return UNDERSTAT_AVAILABLE

    def _run_async(self, coro):
        """Run an async coroutine synchronously."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Already in an async context — create a new loop in a thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        else:
            return asyncio.run(coro)

    def get_fixtures(self, date: str) -> list:
        """Not supported — understat doesn't have fixture lookup by date.

        Returns empty list.
        """
        return []

    def get_team_matches(self, team_name: str, league: str, season: str = None) -> list:
        """Get matches with xG data for a team.

        Args:
            team_name: Team name as used on Understat
            league: League name (will be mapped via LEAGUE_MAP)
            season: Season year (e.g., "2025"). Defaults to current year.

        Returns:
            List of NormalizedMatchStats with xG stat keys.
        """
        if not self._check_api_key():
            return []

        league_code = self.LEAGUE_MAP.get(league, league)
        if season is None:
            from datetime import datetime
            season = str(datetime.now().year)

        cache_key = f"understat/team/{team_name.lower().replace(' ', '_')}_{league_code}_{season}"
        cached = self._check_cache(cache_key, ttl_hours=12)
        if cached and "matches" in cached:
            return [NormalizedMatchStats(**m) for m in cached["matches"]]

        if not self.rate_limiter.can_request(self.api_name):
            print(f"[{self.api_name}] Rate limit reached, skipping")
            return []

        try:
            async def _fetch():
                async with understat_pkg.Understat() as us:
                    return await us.get_team_results(team_name, league_code, season)

            results = self._run_async(_fetch())
            self.rate_limiter.record_request(self.api_name, f"/team/{team_name}")
        except Exception as e:
            print(f"[{self.api_name}] Error fetching team matches for {team_name}: {e}")
            return []

        matches = []
        for r in results:
            home_team = r.get("h", {}).get("title", "")
            away_team = r.get("a", {}).get("title", "")
            match_stats = NormalizedMatchStats(
                fixture_id=str(r.get("id", "")),
                source=self.api_name,
                sport="football",
                home_team=home_team,
                away_team=away_team,
                date=r.get("datetime", ""),
                stats={
                    "xG": {
                        "home": float(r.get("xG", {}).get("h", 0) if isinstance(r.get("xG"), dict) else r.get("xG", 0)),
                        "away": float(r.get("xG", {}).get("a", 0) if isinstance(r.get("xG"), dict) else 0),
                    },
                    "goals": {
                        "home": int(r.get("h", {}).get("goals", 0) if isinstance(r.get("h"), dict) else 0),
                        "away": int(r.get("a", {}).get("goals", 0) if isinstance(r.get("a"), dict) else 0),
                    },
                },
            )
            matches.append(match_stats)

        from dataclasses import asdict
        self._save_cache(cache_key, {
            "matches": [asdict(m) for m in matches],
            "count": len(matches),
        })

        return matches

    def get_fixture_stats(self, fixture_id: str) -> dict:
        """Get match xG details.

        Returns NormalizedMatchStats or empty dict if unavailable.
        """
        if not self._check_api_key():
            return {}

        cache_key = f"understat/match/{fixture_id}"
        cached = self._check_cache(cache_key, ttl_hours=24)
        if cached and "match_stats" in cached:
            return NormalizedMatchStats(**cached["match_stats"])

        if not self.rate_limiter.can_request(self.api_name):
            print(f"[{self.api_name}] Rate limit reached, skipping")
            return {}

        try:
            async def _fetch():
                async with understat_pkg.Understat() as us:
                    return await us.get_match_shots(fixture_id)

            shots = self._run_async(_fetch())
            self.rate_limiter.record_request(self.api_name, f"/match/{fixture_id}")
        except Exception as e:
            print(f"[{self.api_name}] Error fetching match stats for {fixture_id}: {e}")
            return {}

        # Aggregate xG from shots
        home_xg = sum(float(s.get("xG", 0)) for s in shots.get("h", []))
        away_xg = sum(float(s.get("xG", 0)) for s in shots.get("a", []))

        match_stats = NormalizedMatchStats(
            fixture_id=str(fixture_id),
            source=self.api_name,
            sport="football",
            home_team="",
            away_team="",
            date="",
            stats={
                "xG": {"home": round(home_xg, 2), "away": round(away_xg, 2)},
                "shots": {
                    "home": len(shots.get("h", [])),
                    "away": len(shots.get("a", [])),
                },
            },
        )

        from dataclasses import asdict
        self._save_cache(cache_key, {"match_stats": asdict(match_stats)})
        return match_stats

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list:
        """Not directly supported by understat. Returns empty list."""
        return []
