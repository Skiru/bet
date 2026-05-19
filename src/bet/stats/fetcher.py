"""Stateless functions for fetching team and H2H stats via API client chain.

Extracted from scripts/fetch_api_stats.py for reusability.
"""

import logging

from bet.api_clients import get_client, RateLimiter
from bet.api_clients.base_client import APIRateLimitError, APIError
from bet.stats.fallback_chains import FALLBACK_CHAINS

logger = logging.getLogger(__name__)


def fetch_team_stats(
    team_name: str,
    sport: str,
    last_n: int = 10,
    competition: str = "",
    rate_limiter: RateLimiter | None = None,
    chain_filter: set[str] | None = None,
) -> list:
    """Fetch last N matches with stats for a team, trying fallback chain.

    Args:
        team_name: Team or player name
        sport: Sport key (football, basketball, etc.)
        last_n: Number of recent matches to fetch
        competition: Optional competition hint for team resolution
        rate_limiter: Optional shared rate limiter
        chain_filter: If provided, only try these sources

    Returns:
        List of NormalizedMatchStats objects from the first successful source.
    """
    if rate_limiter is None:
        rate_limiter = RateLimiter()

    chain = FALLBACK_CHAINS.get(sport, [])
    if chain_filter:
        chain = [c for c in chain if c in chain_filter]

    for api_name in chain:
        try:
            client = get_client(api_name, rate_limiter=rate_limiter)
        except (ValueError, ImportError):
            continue

        try:
            # Resolve team ID
            try:
                team_id = client.resolve_team_id(team_name, competition=competition)
            except TypeError:
                team_id = client.resolve_team_id(team_name)

            if not team_id:
                continue

            # Get last N finished fixtures
            fixtures = client.get_team_last_fixtures(team_id, last_n=last_n)
            if not fixtures:
                continue

            # Fetch detailed stats per fixture
            match_stats = []
            for fixture in fixtures:
                try:
                    fid = fixture.fixture_id if hasattr(fixture, 'fixture_id') else fixture.get("id", "")
                    stats = client.get_fixture_stats(fid)
                except APIRateLimitError:
                    break
                except APIError:
                    continue

                if stats:
                    if not stats.date:
                        kickoff = fixture.kickoff if hasattr(fixture, 'kickoff') else fixture.get("date", "")
                        if kickoff:
                            stats.date = kickoff[:10]
                    match_stats.append(stats)

            if match_stats:
                logger.info(f"[{api_name}] Got {len(match_stats)} stats for '{team_name}'")
                return match_stats

        except (APIRateLimitError, APIError) as e:
            logger.debug(f"[{api_name}] Failed for '{team_name}': {e}")
            continue
        except Exception as e:
            logger.debug(f"[{api_name}] Unexpected error for '{team_name}': {e}")
            continue

    return []


def fetch_h2h_stats(
    team1_name: str,
    team2_name: str,
    sport: str,
    last_n: int = 10,
    competition: str = "",
    rate_limiter: RateLimiter | None = None,
    chain_filter: set[str] | None = None,
) -> list:
    """Fetch H2H meetings with stats, trying fallback chain.

    Args:
        team1_name: First team name
        team2_name: Second team name
        sport: Sport key
        last_n: Number of H2H meetings to fetch
        competition: Optional competition hint
        rate_limiter: Optional shared rate limiter
        chain_filter: If provided, only try these sources

    Returns:
        List of NormalizedMatchStats objects from the first successful source.
    """
    if rate_limiter is None:
        rate_limiter = RateLimiter()

    chain = FALLBACK_CHAINS.get(sport, [])
    if chain_filter:
        chain = [c for c in chain if c in chain_filter]

    for api_name in chain:
        try:
            client = get_client(api_name, rate_limiter=rate_limiter)
        except (ValueError, ImportError):
            continue

        try:
            try:
                team1_id = client.resolve_team_id(team1_name, competition=competition)
                team2_id = client.resolve_team_id(team2_name, competition=competition)
            except TypeError:
                team1_id = client.resolve_team_id(team1_name)
                team2_id = client.resolve_team_id(team2_name)

            if not team1_id or not team2_id:
                continue

            h2h_fixtures = client.get_h2h(team1_id, team2_id, last_n=last_n)
            if not h2h_fixtures:
                continue

            match_stats = []
            for fixture in h2h_fixtures:
                try:
                    fid = fixture.fixture_id if hasattr(fixture, 'fixture_id') else fixture.get("id", "")
                    stats = client.get_fixture_stats(fid)
                except APIRateLimitError:
                    break
                except APIError:
                    continue

                if stats:
                    if not stats.date:
                        kickoff = fixture.kickoff if hasattr(fixture, 'kickoff') else fixture.get("date", "")
                        if kickoff:
                            stats.date = kickoff[:10]
                    match_stats.append(stats)

            if match_stats:
                logger.info(f"[{api_name}] Got {len(match_stats)} H2H stats for "
                            f"'{team1_name}' vs '{team2_name}'")
                return match_stats

        except (APIRateLimitError, APIError) as e:
            logger.debug(f"[{api_name}] H2H failed: {e}")
            continue
        except Exception as e:
            logger.debug(f"[{api_name}] H2H unexpected error: {e}")
            continue

    return []
