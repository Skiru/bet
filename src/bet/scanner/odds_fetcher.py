"""Odds fetcher — The-Odds-API integration with DB fixture matching.

Fetches odds from The-Odds-API for supported sports and fuzzy-matches
events to DB fixtures by team name.
"""

import asyncio
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

from bet.db.models import Fixture, OddsRecord
from bet.db.repositories import FixtureRepo, OddsRepo, SourceHealthRepo, TeamRepo
from bet.utils.team_names import normalize_team_name

logger = logging.getLogger(__name__)

BASE_URL = "https://api.the-odds-api.com/v4"
CONFIG_DIR = Path(__file__).parent.parent.parent.parent / "config"

# Map internal sport names to Odds API sport keys
SPORT_KEY_MAP: dict[str, list[str]] = {
    "football": [
        "soccer_epl", "soccer_germany_bundesliga", "soccer_spain_la_liga",
        "soccer_italy_serie_a", "soccer_france_ligue_one",
        "soccer_netherlands_eredivisie", "soccer_portugal_primeira_liga",
        "soccer_turkey_super_league", "soccer_poland_ekstraklasa",
        "soccer_usa_mls", "soccer_uefa_champs_league", "soccer_uefa_europa_league",
        "soccer_efl_champ",
    ],
    "basketball": ["basketball_nba", "basketball_euroleague", "basketball_ncaab"],
    "hockey": ["icehockey_nhl", "icehockey_shl"],
    "tennis": [
        "tennis_atp_french_open", "tennis_wta_french_open",
        "tennis_atp_aus_open", "tennis_wta_aus_open",
        "tennis_atp_us_open", "tennis_wta_us_open",
        "tennis_atp_wimbledon", "tennis_wta_wimbledon",
    ],
    # No API coverage
    "volleyball": [],
    "snooker": [],
    "speedway": [],
}


def _get_api_key() -> str | None:
    """Load The-Odds-API key from env var, api_keys.json, or key file."""
    key = os.environ.get("ODDS_API_KEY")
    if key and key.strip():
        return key.strip()

    import json
    keys_json = CONFIG_DIR / "api_keys.json"
    if keys_json.exists():
        try:
            keys = json.loads(keys_json.read_text(encoding="utf-8"))
            key = keys.get("odds-api", "").strip()
            if key:
                return key
        except Exception:
            pass

    key_file = CONFIG_DIR / "odds_api_key.txt"
    if key_file.exists():
        for line in key_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line

    return None


async def fetch_odds(
    target_date: date,
    sports: list[str],
    db_conn,
) -> dict[str, int]:
    """Fetch odds from The-Odds-API and store in odds_history.

    Returns: {"football": 120, ...} — odds records saved per sport.
    """
    api_key = _get_api_key()
    if not api_key:
        logger.warning("No Odds API key found — skipping odds fetch")
        return {s: 0 for s in sports}

    counts: dict[str, int] = {}

    for sport in sports:
        sport_keys = SPORT_KEY_MAP.get(sport, [])
        if not sport_keys:
            counts[sport] = 0
            continue

        # Run synchronously to avoid SQLite threading issues
        count = _fetch_sport_odds(
            api_key,
            sport,
            sport_keys,
            target_date,
            db_conn,
        )
        counts[sport] = count

    return counts


def _fetch_sport_odds(
    api_key: str,
    sport: str,
    sport_keys: list[str],
    target_date: date,
    db_conn,
) -> int:
    """Fetch odds for all keys of a single sport. Returns total records saved."""
    now = datetime.now(timezone.utc)
    commence_from = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    commence_to = (now + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")

    all_events = []
    for sport_key in sport_keys:
        try:
            events = _api_fetch_odds(api_key, sport_key, commence_from, commence_to)
            for e in events:
                e["_our_sport"] = sport
            all_events.extend(events)
        except Exception as exc:
            logger.debug("Odds API error for %s: %s", sport_key, exc)

    if not all_events:
        return 0

    # Get all fixtures for this sport on the target date
    from bet.db.repositories import SportRepo
    sport_repo = SportRepo(db_conn)
    sport_obj = sport_repo.get_by_name(sport)
    if not sport_obj:
        return 0

    fixture_repo = FixtureRepo(db_conn)
    fixtures = fixture_repo.get_by_date(target_date.isoformat(), sport_id=sport_obj.id)

    # Match odds events to fixtures
    count = match_odds_to_fixtures(all_events, fixtures, db_conn)

    try:
        repo = SourceHealthRepo(db_conn)
        repo.record_success("odds-api", 0.0)
        db_conn.commit()
    except Exception:
        pass

    return count


def _api_fetch_odds(
    api_key: str,
    sport_key: str,
    commence_from: str,
    commence_to: str,
) -> list[dict]:
    """Fetch odds for a single sport key from The-Odds-API."""
    params = {
        "apiKey": api_key,
        "regions": "eu",
        "markets": "h2h,totals",
        "oddsFormat": "decimal",
        "commenceTimeFrom": commence_from,
        "commenceTimeTo": commence_to,
    }
    resp = requests.get(
        f"{BASE_URL}/sports/{sport_key}/odds",
        params=params,
        timeout=15,
    )
    if resp.status_code in (404, 422):
        return []
    resp.raise_for_status()
    return resp.json()


def match_odds_to_fixtures(
    odds_events: list[dict],
    fixtures: list[Fixture],
    db_conn,
) -> int:
    """Match API odds events to DB fixtures by team name similarity.

    Returns number of matched odds records saved.
    """
    odds_repo = OddsRepo(db_conn)
    team_repo = TeamRepo(db_conn)
    count = 0

    # Build lookup: normalized team pair → fixture
    fixture_lookup: dict[tuple[str, str], Fixture] = {}
    for fix in fixtures:
        home = team_repo.get_by_id(fix.home_team_id)
        away = team_repo.get_by_id(fix.away_team_id)
        if home and away:
            key = (
                normalize_team_name(home.name),
                normalize_team_name(away.name),
            )
            fixture_lookup[key] = fix

    for event in odds_events:
        home_norm = normalize_team_name(event.get("home_team", ""))
        away_norm = normalize_team_name(event.get("away_team", ""))

        # Try exact normalized match
        matched_fixture = fixture_lookup.get((home_norm, away_norm))

        # Try reversed (away/home swap)
        if not matched_fixture:
            matched_fixture = fixture_lookup.get((away_norm, home_norm))

        # Try fuzzy partial match
        if not matched_fixture:
            matched_fixture = _fuzzy_match(home_norm, away_norm, fixture_lookup)

        if not matched_fixture:
            continue

        # Extract and save odds for each bookmaker
        for bm in event.get("bookmakers", []):
            bm_name = bm.get("title", "unknown")
            for market in bm.get("markets", []):
                market_key = market.get("key", "")
                for outcome in market.get("outcomes", []):
                    selection = outcome.get("name", "")
                    point = outcome.get("point")
                    if point is not None:
                        selection = f"{selection}_{point}"

                    record = OddsRecord(
                        id=None,
                        fixture_id=matched_fixture.id,
                        bookmaker=bm_name,
                        market=market_key,
                        selection=selection,
                        odds=outcome.get("price", 0.0),
                        line=point,
                        fetched_at=datetime.now(timezone.utc).isoformat(),
                    )
                    odds_repo.save_odds(record)
                    count += 1

    db_conn.commit()
    return count


def _fuzzy_match(
    home_norm: str,
    away_norm: str,
    fixture_lookup: dict[tuple[str, str], Fixture],
) -> Fixture | None:
    """Fuzzy match by checking if normalized names are substrings."""
    for (fh, fa), fix in fixture_lookup.items():
        if (home_norm in fh or fh in home_norm) and (
            away_norm in fa or fa in away_norm
        ):
            return fix
    return None
