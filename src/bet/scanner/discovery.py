"""API-first parallel fixture discovery with Flashscore fallback.

Strategy per sport:
1. API clients (async, wrapped in executor) for sports with API coverage
2. Flashscore scraping (PlaywrightPool) for gaps
3. Upsert all into DB via repositories
"""

import asyncio
import logging
from datetime import date, datetime, timezone

from bet.db.models import Fixture
from bet.db.repositories import (
    CompetitionRepo,
    FixtureRepo,
    SourceHealthRepo,
    SportRepo,
    TeamRepo,
)
from bet.utils.team_names import normalize_team_name

logger = logging.getLogger(__name__)

# Sports with dedicated API clients
API_SPORTS = {
    "football": "api-football",
    "basketball": "api-basketball",
    "hockey": "api-hockey",
    "volleyball": "api-volleyball",
}

# ESPN free API — primary source for supported sports
API_ESPN = {
    "football": "espn-football",
    "basketball": "espn-basketball",
    "hockey": "espn-hockey",
    "baseball": "espn-baseball",
}

# Flashscore URL patterns per sport
FLASHSCORE_URLS = {
    "football": "https://www.flashscore.com/football/",
    "basketball": "https://www.flashscore.com/basketball/",
    "hockey": "https://www.flashscore.com/hockey/",
    "tennis": "https://www.flashscore.com/tennis/",
    "volleyball": "https://www.flashscore.com/volleyball/",
    "snooker": "https://www.flashscore.com/snooker/",
    "speedway": "https://www.flashscore.com/motorsport/speedway/",
}


async def discover_fixtures(
    target_date: date,
    sports: list[str],
    db_conn,
    playwright_pool=None,
) -> dict[str, int]:
    """Discover fixtures for all sports in parallel.

    Strategy:
    1. API calls (asyncio.gather) for sports with API coverage
    2. Flashscore scraping (Playwright pool) for gaps
    3. Upsert all into DB, deduplicating by (sport, home, away, kickoff)

    Returns: {"football": 45, "basketball": 12, ...} — fixture counts per sport.
    """
    date_str = target_date.isoformat()
    counts: dict[str, int] = {}

    # Phase 1: API discovery (parallel)
    api_tasks = []
    api_sport_names = []
    for sport in sports:
        if sport in API_SPORTS:
            api_tasks.append(_discover_api(sport, date_str, db_conn))
            api_sport_names.append(sport)

    if api_tasks:
        api_results = await asyncio.gather(*api_tasks, return_exceptions=True)
        for sport_name, result in zip(api_sport_names, api_results):
            if isinstance(result, Exception):
                logger.warning("API discovery failed for %s: %s", sport_name, result)
                counts[sport_name] = 0
            else:
                counts[sport_name] = result

    # Phase 2: Flashscore for sports without API or with zero API results
    if playwright_pool:
        flash_tasks = []
        flash_sport_names = []
        for sport in sports:
            if counts.get(sport, 0) == 0 and sport in FLASHSCORE_URLS:
                flash_tasks.append(
                    _discover_flashscore(sport, date_str, playwright_pool, db_conn)
                )
                flash_sport_names.append(sport)

        if flash_tasks:
            flash_results = await asyncio.gather(*flash_tasks, return_exceptions=True)
            for sport_name, result in zip(flash_sport_names, flash_results):
                if isinstance(result, Exception):
                    logger.warning("Flashscore discovery failed for %s: %s", sport_name, result)
                    counts.setdefault(sport_name, 0)
                else:
                    counts[sport_name] = counts.get(sport_name, 0) + result

    # Ensure all requested sports appear in counts
    for sport in sports:
        counts.setdefault(sport, 0)

    return counts


async def _discover_api(sport: str, date_str: str, db_conn) -> int:
    """Fetch fixtures from the sport-specific API client.

    Runs the synchronous API call in an executor to avoid blocking the loop.
    """
    client_name = API_SPORTS.get(sport)
    if not client_name:
        return 0

    loop = asyncio.get_running_loop()

    def _fetch():
        from bet.api_clients import get_client
        client = get_client(client_name)
        if not client.is_available():
            logger.info("[%s] API key not configured, skipping", client_name)
            return []
        try:
            return client.get_fixtures(date_str)
        except Exception as exc:
            logger.warning("[%s] get_fixtures failed: %s", client_name, exc)
            _record_failure(db_conn, client_name)
            return []

    fixtures = await loop.run_in_executor(None, _fetch)

    # Upsert fixtures into DB
    count = 0
    sport_repo = SportRepo(db_conn)
    sport_obj = sport_repo.get_by_name(sport)
    if not sport_obj:
        return 0

    fixture_repo = FixtureRepo(db_conn)
    team_repo = TeamRepo(db_conn)
    comp_repo = CompetitionRepo(db_conn)

    for fix in fixtures:
        try:
            home_team = team_repo.find_or_create(fix.home_team_name, sport_obj.id)
            away_team = team_repo.find_or_create(fix.away_team_name, sport_obj.id)

            comp_id = None
            if fix.competition_name:
                comp_id = comp_repo.find_or_create(fix.competition_name, sport_obj.id)

            fixture = Fixture(
                id=None,
                sport_id=sport_obj.id,
                competition_id=comp_id,
                home_team_id=home_team.id,
                away_team_id=away_team.id,
                kickoff=fix.kickoff,
                status=fix.status,
                external_id=fix.external_id,
                source=fix.source,
                fetched_at=datetime.now(timezone.utc).isoformat(),
            )
            fixture_repo.upsert(fixture)
            count += 1
        except Exception as exc:
            logger.debug("Failed to upsert fixture: %s", exc)

    db_conn.commit()
    _record_success(db_conn, client_name)
    logger.info("[%s] Discovered %d fixtures for %s", client_name, count, date_str)
    return count


async def _discover_flashscore(
    sport: str, date_str: str, pool, db_conn
) -> int:
    """Scrape Flashscore for fixtures using the Playwright pool."""
    url = FLASHSCORE_URLS.get(sport)
    if not url:
        return 0

    try:
        html = await pool.scrape_page(url, timeout_ms=20000)
    except Exception as exc:
        logger.warning("Flashscore scrape failed for %s: %s", sport, exc)
        _record_failure(db_conn, "flashscore")
        return 0

    # Parse with the flashscore adapter
    from bet.adapters.flashscore import FlashscoreAdapter
    adapter = FlashscoreAdapter()
    parsed = adapter.parse_fixtures(html, sport)

    sport_repo = SportRepo(db_conn)
    sport_obj = sport_repo.get_by_name(sport)
    if not sport_obj:
        return 0

    fixture_repo = FixtureRepo(db_conn)
    team_repo = TeamRepo(db_conn)
    count = 0

    for entry in parsed:
        try:
            home_team = team_repo.find_or_create(entry["home"], sport_obj.id)
            away_team = team_repo.find_or_create(entry["away"], sport_obj.id)

            kickoff = entry.get("kickoff", f"{date_str}T00:00:00")
            fixture = Fixture(
                id=None,
                sport_id=sport_obj.id,
                competition_id=None,
                home_team_id=home_team.id,
                away_team_id=away_team.id,
                kickoff=kickoff,
                status="scheduled",
                source="flashscore",
                fetched_at=datetime.now(timezone.utc).isoformat(),
            )
            fixture_repo.upsert(fixture)
            count += 1
        except Exception as exc:
            logger.debug("Failed to upsert flashscore fixture: %s", exc)

    db_conn.commit()
    if count > 0:
        _record_success(db_conn, "flashscore")
    logger.info("[flashscore] Discovered %d %s fixtures for %s", count, sport, date_str)
    return count


def _record_success(db_conn, source: str) -> None:
    """Record a successful source access."""
    try:
        repo = SourceHealthRepo(db_conn)
        repo.record_success(source, 0.0)
        db_conn.commit()
    except Exception:
        pass


def _record_failure(db_conn, source: str) -> None:
    """Record a failed source access."""
    try:
        repo = SourceHealthRepo(db_conn)
        repo.record_failure(source)
        db_conn.commit()
    except Exception:
        pass
