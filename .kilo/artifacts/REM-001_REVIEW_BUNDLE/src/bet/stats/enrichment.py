"""Incremental stat enrichment — fetch team stats only when stale/missing.

API clients first, scraping fallback. Updates team_form table with
computed L10/L5 averages and trend.
"""

import asyncio
import logging
from datetime import datetime, timezone

from bet.db.models import Fixture, TeamForm
from bet.db.repositories import (
    SourceHealthRepo,
    SportRepo,
    StatsRepo,
    TeamRepo,
)
from bet.stats.market_ranking import SPORT_STAT_KEYS

logger = logging.getLogger(__name__)


async def enrich_fixtures(
    fixtures: list[Fixture],
    db_conn,
    playwright_pool=None,
    max_age_hours: int = 12,
) -> dict[str, int]:
    """Enrich fixtures with team stats. Only fetches stale/missing data.

    For each fixture:
    1. Check if team_form exists and is fresh (< max_age_hours old)
    2. If stale: fetch L10 stats from API → save to match_stats + team_form
    3. If no API: scrape from Flashscore/Scores24
    4. Compute L10/L5 averages, detect trend

    Returns: {"fetched": N, "cached": M, "failed": K}
    """
    stats_repo = StatsRepo(db_conn)
    sport_repo = SportRepo(db_conn)
    team_repo = TeamRepo(db_conn)
    counters = {"fetched": 0, "cached": 0, "failed": 0}

    # Build unique set of (team_id, sport_id) pairs
    team_sport_pairs: set[tuple[int, int]] = set()
    for fix in fixtures:
        team_sport_pairs.add((fix.home_team_id, fix.sport_id))
        team_sport_pairs.add((fix.away_team_id, fix.sport_id))

    # Check staleness and enrich
    tasks = []
    for team_id, sport_id in team_sport_pairs:
        sport_obj = sport_repo.get_by_name(_sport_id_to_name(sport_id, sport_repo))
        if not sport_obj:
            continue

        stat_keys = SPORT_STAT_KEYS.get(sport_obj.name, [])
        if not stat_keys:
            continue

        # Check if ANY stat key is stale
        needs_fetch = any(
            stats_repo.is_stale(team_id, sk, max_age_hours)
            for sk in stat_keys[:3]  # Check first 3 keys as proxy
        )

        if not needs_fetch:
            counters["cached"] += 1
            continue

        team = team_repo.get_by_id(team_id)
        if not team:
            continue

        tasks.append(_enrich_team(
            team, sport_obj.name, stat_keys, db_conn, playwright_pool
        ))

    if tasks:
        # Run sequentially to avoid concurrent writes to shared sqlite3.Connection
        # (sqlite3 connections are not thread-safe for concurrent writes)
        for task_coro in tasks:
            try:
                r = await task_coro
                if r:
                    counters["fetched"] += 1
                else:
                    counters["failed"] += 1
            except Exception as exc:
                logger.warning("Enrichment failed for team: %s", exc)
                counters["failed"] += 1

    db_conn.commit()
    return counters


async def _enrich_team(
    team, sport: str, stat_keys: list[str], db_conn, pool
) -> bool:
    """Fetch and store stats for a single team. Returns True if data was fetched."""
    stats_repo = StatsRepo(db_conn)
    sport_repo = SportRepo(db_conn)
    sport_obj = sport_repo.get_by_name(sport)
    if not sport_obj:
        return False

    fetched = False

    # Try API — run synchronously to avoid SQLite threading issues
    # (sqlite3 connections cannot be shared across threads)
    api_fetched = _try_api_fetch(team, sport, stat_keys, db_conn)

    if api_fetched:
        fetched = True

    # Compute form from match_stats even if no new data fetched
    for stat_key in stat_keys:
        l10_values = stats_repo.get_form(team.id, stat_key, n=10)
        if not l10_values:
            continue

        form = compute_form(l10_values)
        l5_values = l10_values[:5] if len(l10_values) >= 5 else l10_values

        team_form = TeamForm(
            id=None,
            team_id=team.id,
            sport_id=sport_obj.id,
            stat_key=stat_key,
            l10_values=l10_values,
            l5_values=l5_values,
            l10_avg=form["l10_avg"],
            l5_avg=form["l5_avg"],
            trend=form["trend"],
            updated_at=datetime.now(timezone.utc).isoformat(),
            source="computed",
        )
        stats_repo.save_team_form(team_form)
        fetched = True

    return fetched


def _try_api_fetch(team, sport: str, stat_keys: list[str], db_conn) -> bool:
    """Try to fetch stats from sport-specific API client.

    Strategy: ESPN first (free, unlimited), then API-Sports as fallback.
    Fetches the team's last 10 fixtures with stats from the API,
    aggregates per-stat values, and saves directly to team_form.
    Checks match_stats table first to avoid redundant API calls.
    """
    # Try ESPN first (free, unlimited)
    espn_result = _try_espn_fetch(team, sport, stat_keys, db_conn)
    if espn_result:
        return True

    # Fall back to API-Sports
    return _try_api_sports_fetch(team, sport, stat_keys, db_conn)


def _try_espn_fetch(team, sport: str, stat_keys: list[str], db_conn) -> bool:
    """Try ESPN as primary stat source. Returns True if successful."""
    from bet.api_clients import API_ESPN
    from bet.api_clients.espn import ESPNClient, get_espn_league_for_competition, ESPN_LEAGUES

    espn_client_name = API_ESPN.get(sport)
    if not espn_client_name:
        return False

    try:
        from bet.api_clients import get_client, RateLimiter

        # For football, we need to determine the league
        league = None
        if sport == "football":
            # Try to get competition from team's fixtures
            row = db_conn.execute(
                "SELECT c.name FROM competitions c "
                "JOIN fixtures f ON f.competition_id = c.id "
                "WHERE (f.home_team_id = ? OR f.away_team_id = ?) "
                "ORDER BY f.kickoff DESC LIMIT 1",
                (team.id, team.id),
            ).fetchone()
            if row:
                league = get_espn_league_for_competition(row["name"] if isinstance(row, dict) else row[0])
            if not league:
                return False
        else:
            # Non-football: use default league
            leagues = ESPN_LEAGUES.get(sport, [])
            league = leagues[0] if leagues else None
            if not league:
                return False

        rate_limiter = RateLimiter()
        client = ESPNClient(sport=sport, league=league, rate_limiter=rate_limiter)
        if not client.is_available():
            return False

        api_team_id = client.resolve_team_id(team.name)
        if not api_team_id:
            return False

        last_fixtures = client.get_team_last_fixtures(api_team_id, last_n=10)
        if not last_fixtures:
            return False

        # Aggregate stat values per key from last fixtures
        stat_values: dict[str, list[float]] = {k: [] for k in stat_keys}

        for fix_data in last_fixtures:
            fix_id = str(fix_data.get("id", ""))
            if not fix_id:
                continue

            # Check if stats already exist in match_stats table
            existing = db_conn.execute(
                "SELECT stat_key, stat_value FROM match_stats WHERE fixture_id = ("
                "  SELECT id FROM fixtures WHERE external_id = ? LIMIT 1"
                ") AND team_id = ?",
                (fix_id, team.id),
            ).fetchall()

            if existing:
                for row in existing:
                    sk = row["stat_key"] if isinstance(row, dict) else row[0]
                    sv = row["stat_value"] if isinstance(row, dict) else row[1]
                    if sk in stat_keys:
                        stat_values[sk].append(float(sv))
                continue

            fix_stats = client.get_fixture_stats(fix_id)
            if not fix_stats:
                continue
            for ms in fix_stats:
                for stat_key, sides in ms.stats.items():
                    if stat_key not in stat_keys:
                        continue
                    if _is_home_team(team.name, ms.home_team_name):
                        val = sides.get("home")
                    else:
                        val = sides.get("away")
                    if isinstance(val, (int, float)):
                        stat_values[stat_key].append(float(val))

        if not any(stat_values.values()):
            return False

        stats_repo = StatsRepo(db_conn)
        sport_repo = SportRepo(db_conn)
        sport_obj = sport_repo.get_by_name(sport)
        now = datetime.now(timezone.utc).isoformat()

        for stat_key, values in stat_values.items():
            if not values:
                continue
            form = compute_form(values)
            l5_values = values[:5] if len(values) >= 5 else values
            team_form = TeamForm(
                id=None,
                team_id=team.id,
                sport_id=sport_obj.id if sport_obj else 0,
                stat_key=stat_key,
                l10_values=values[:10],
                l5_values=l5_values,
                l10_avg=form["l10_avg"],
                l5_avg=form["l5_avg"],
                trend=form["trend"],
                updated_at=now,
                source=f"espn-{sport}",
            )
            stats_repo.save_team_form(team_form)

        _record_source_success(db_conn, f"espn-{sport}")
        return True

    except Exception as exc:
        logger.debug("ESPN fetch failed for %s/%s: %s", sport, team.name, exc)
        return False


def _try_api_sports_fetch(team, sport: str, stat_keys: list[str], db_conn) -> bool:
    """Try API-Sports as fallback stat source. Returns True if successful."""
    from bet.api_clients import API_SPORTS

    client_name = API_SPORTS.get(sport)
    if not client_name:
        return False

    try:
        from bet.api_clients import get_client
        client = get_client(client_name)
        if not client.is_available():
            return False

        api_team_id = client.resolve_team_id(team.name)
        if not api_team_id:
            return False

        last_fixtures = client.get_team_last_fixtures(api_team_id, last_n=10)
        if not last_fixtures:
            return False

        # Aggregate stat values per key from last fixtures
        stat_values: dict[str, list[float]] = {k: [] for k in stat_keys}

        for fix_data in last_fixtures:
            fix_id = str(fix_data.get("id", ""))
            if not fix_id:
                continue

            # Check if stats already exist in match_stats table for this fixture
            existing = db_conn.execute(
                "SELECT stat_key, stat_value FROM match_stats WHERE fixture_id = ("
                "  SELECT id FROM fixtures WHERE external_id = ? LIMIT 1"
                ") AND team_id = ?",
                (fix_id, team.id),
            ).fetchall()

            if existing:
                # Use cached DB data instead of API call
                for row in existing:
                    sk = row["stat_key"]
                    if sk in stat_keys:
                        stat_values[sk].append(float(row["stat_value"]))
                continue

            # Check remaining API budget before making a stats call
            if not client.rate_limiter.can_request(client.api_name):
                logger.debug("API budget exhausted for %s, skipping fixture %s", client.api_name, fix_id)
                continue

            fix_stats = client.get_fixture_stats(fix_id)
            if not fix_stats:
                continue
            for ms in fix_stats:
                for stat_key, sides in ms.stats.items():
                    if stat_key not in stat_keys:
                        continue
                    if _is_home_team(team.name, ms.home_team_name):
                        val = sides.get("home", 0)
                    else:
                        val = sides.get("away", 0)
                    if isinstance(val, (int, float)):
                        stat_values[stat_key].append(float(val))

        # Save aggregated form data to team_form table
        if not any(stat_values.values()):
            return False

        stats_repo = StatsRepo(db_conn)
        sport_repo = SportRepo(db_conn)
        sport_obj = sport_repo.get_by_name(sport)
        now = datetime.now(timezone.utc).isoformat()

        for stat_key, values in stat_values.items():
            if not values:
                continue
            form = compute_form(values)
            l5_values = values[:5] if len(values) >= 5 else values
            team_form = TeamForm(
                id=None,
                team_id=team.id,
                sport_id=sport_obj.id if sport_obj else 0,
                stat_key=stat_key,
                l10_values=values[:10],
                l5_values=l5_values,
                l10_avg=form["l10_avg"],
                l5_avg=form["l5_avg"],
                trend=form["trend"],
                updated_at=now,
                source=client_name,
            )
            stats_repo.save_team_form(team_form)

        _record_source_success(db_conn, client_name)
        return True

    except Exception as exc:
        logger.debug("API fetch failed for %s/%s: %s", sport, team.name, exc)
        return False


def compute_form(values: list[float], n: int = 10) -> dict:
    """Compute L10/L5 avg and trend from raw values.

    Args:
        values: Raw stat values, most recent first.
        n: Window size (default 10).

    Returns: {"l10_avg": float, "l5_avg": float, "trend": "up"|"down"|"stable"}
    """
    if not values:
        return {"l10_avg": 0.0, "l5_avg": 0.0, "trend": "stable"}

    l10 = values[:n]
    l5 = values[:5] if len(values) >= 5 else values

    l10_avg = sum(l10) / len(l10) if l10 else 0.0
    l5_avg = sum(l5) / len(l5) if l5 else 0.0

    # Trend: up if L5 > L10 by ≥5%, down if L5 < L10 by ≥5%, else stable
    if l10_avg > 0:
        pct_change = (l5_avg - l10_avg) / l10_avg * 100
        if pct_change >= 5:
            trend = "up"
        elif pct_change <= -5:
            trend = "down"
        else:
            trend = "stable"
    else:
        trend = "stable"

    return {
        "l10_avg": round(l10_avg, 2),
        "l5_avg": round(l5_avg, 2),
        "trend": trend,
    }


def _sport_id_to_name(sport_id: int, sport_repo: SportRepo) -> str:
    """Resolve a sport_id to its name."""
    for s in sport_repo.get_all():
        if s.id == sport_id:
            return s.name
    return ""


def _is_home_team(team_name: str, home_team_name: str) -> bool:
    """Check if team_name matches the home team, using equality first then containment."""
    t = team_name.lower().strip()
    h = home_team_name.lower().strip()
    # Exact match first
    if t == h:
        return True
    # Then check if one name contains the other (but both must be non-trivial)
    if len(t) >= 4 and (t in h or h in t):
        return True
    return False


def _record_source_success(db_conn, source: str) -> None:
    try:
        repo = SourceHealthRepo(db_conn)
        repo.record_success(source, 0.0)
    except Exception:
        pass
