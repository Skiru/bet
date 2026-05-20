#!/usr/bin/env python3
"""Basketball rich-completion helper.

Loads recent finished basketball fixtures from the DB, fetches per-game stats
from the canonical or supporting provider path, and persists normalized matches
only through `fetch_api_stats._store_in_cache()`.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from bet.api_clients import RateLimiter, get_client
from bet.db.connection import get_db
from bet.db.repositories import SportRepo, TeamRepo
from bet.models.normalized import NormalizedMatchStats
from bet.stats.fallback_chains import RICH_COMPLETION_POLICY
from fetch_api_stats import _store_in_cache

logger = logging.getLogger(__name__)

_BASKETBALL_POLICY = RICH_COMPLETION_POLICY["basketball"]
_BASKETBALL_RICH_KEYS = list(_BASKETBALL_POLICY["required_rich_keys"])
_BASKETBALL_SOURCE_ORDER = [
    _BASKETBALL_POLICY["canonical_source"],
    *_BASKETBALL_POLICY["supporting_sources"],
]
_BASKETBALL_SUPPORTING_SOURCES = set(_BASKETBALL_POLICY["supporting_sources"])
_RATE_LIMITER = RateLimiter()


def get_basketball_rich_stat_keys(stats_or_keys) -> set[str]:
    if not stats_or_keys:
        return set()
    keys = stats_or_keys.keys() if hasattr(stats_or_keys, "keys") else stats_or_keys
    return {str(key) for key in keys if str(key) in _BASKETBALL_RICH_KEYS}


def get_missing_basketball_rich_stat_keys(stats_or_keys) -> list[str]:
    present = get_basketball_rich_stat_keys(stats_or_keys)
    return [key for key in _BASKETBALL_RICH_KEYS if key not in present]


def _get_recent_basketball_fixtures(team_name: str, limit: int) -> tuple[list[dict], str | None]:
    try:
        with get_db() as conn:
            sport_repo = SportRepo(conn)
            team_repo = TeamRepo(conn)
            sport = sport_repo.get_by_name("basketball")
            if not sport:
                return [], None

            team = team_repo.resolve(team_name, sport.id)
            if not team:
                return [], None

            rows = conn.execute(
                "SELECT f.id AS fixture_id, f.kickoff, f.status, "
                "home.name AS home_team, away.name AS away_team, "
                "COALESCE(c.name, '') AS competition "
                "FROM fixtures f "
                "JOIN teams home ON home.id = f.home_team_id "
                "JOIN teams away ON away.id = f.away_team_id "
                "LEFT JOIN competitions c ON c.id = f.competition_id "
                "WHERE f.sport_id = ? "
                "AND f.status = 'finished' "
                "AND (f.home_team_id = ? OR f.away_team_id = ?) "
                "ORDER BY f.kickoff DESC LIMIT ?",
                (sport.id, team.id, team.id, limit),
            ).fetchall()
    except Exception as exc:
        logger.debug("DB basketball fixture lookup failed for %s: %s", team_name, exc)
        return [], None

    fixtures = [
        {
            "fixture_id": row["fixture_id"],
            "kickoff": row["kickoff"],
            "status": row["status"],
            "competition": row["competition"],
            "home_team": row["home_team"],
            "away_team": row["away_team"],
        }
        for row in rows
    ]
    return fixtures, str(team.id)


def _build_normalized_match_stats(fixture: dict, stats: dict, source: str) -> NormalizedMatchStats:
    return NormalizedMatchStats(
        fixture_id=str(fixture.get("fixture_id", "")),
        source=source,
        sport="basketball",
        home_team=str(fixture.get("home_team", "")),
        away_team=str(fixture.get("away_team", "")),
        date=str(fixture.get("kickoff", ""))[:10],
        stats=stats,
    )


def _coerce_stats_payload(match_result) -> dict:
    if not match_result:
        return {}
    if isinstance(match_result, list):
        match_result = match_result[0] if match_result else None
    if not match_result:
        return {}
    if isinstance(match_result, dict):
        payload = match_result.get("stats")
        if isinstance(payload, dict):
            return payload
        return match_result if all(isinstance(value, dict) for value in match_result.values()) else {}
    payload = getattr(match_result, "stats", {})
    return payload if isinstance(payload, dict) else {}


def _is_unsupported_league_skip(source_name: str, competition: str, stats: dict) -> bool:
    if stats:
        return False
    if source_name not in _BASKETBALL_SUPPORTING_SOURCES:
        return False
    competition_name = (competition or "").lower()
    return "nba" not in competition_name


def complete_basketball_rich_stats(team_name: str, sport: str, max_fixtures: int = 5) -> dict:
    result = {
        "team": team_name,
        "sport": sport,
        "source": _BASKETBALL_POLICY["canonical_source"],
        "status": "failed",
        "fixtures_scanned": 0,
        "matches_persisted": 0,
        "rich_keys_found": [],
        "missing_rich_keys": list(_BASKETBALL_RICH_KEYS),
        "error": None,
        "failure_reason": None,
    }

    if sport != "basketball":
        result["status"] = "skipped"
        result["error"] = f"Unsupported sport for basketball completion: {sport}"
        result["failure_reason"] = "unsupported_sport"
        return result

    fixtures, team_id = _get_recent_basketball_fixtures(team_name, limit=max_fixtures)
    if not team_id:
        result["error"] = f"Basketball team not found in DB: {team_name}"
        result["failure_reason"] = "team_not_found"
        return result

    if not fixtures:
        result["error"] = "No recent basketball fixtures found in DB"
        result["failure_reason"] = "no_fixtures"
        return result

    persisted_matches: list[NormalizedMatchStats] = []
    rich_keys_found: set[str] = set()
    last_failure_reason: str | None = None
    last_error: str | None = None

    for fixture in fixtures[:max_fixtures]:
        result["fixtures_scanned"] += 1
        fixture_id = str(fixture.get("fixture_id", ""))
        if not fixture_id:
            last_failure_reason = "missing_fixture_id"
            continue

        combined_stats: dict = {}
        source_used: str | None = None

        for source_name in _BASKETBALL_SOURCE_ORDER:
            try:
                client = get_client(source_name, rate_limiter=_RATE_LIMITER)
            except Exception as exc:
                last_error = str(exc)
                last_failure_reason = "client_unavailable"
                continue

            if not client.is_available():
                continue

            try:
                match_result = client.get_fixture_stats(fixture_id)
            except Exception as exc:
                last_error = str(exc)
                last_failure_reason = "source_error"
                continue

            stats = _coerce_stats_payload(match_result)
            if _is_unsupported_league_skip(source_name, str(fixture.get("competition", "")), stats):
                last_failure_reason = "unsupported_league_skip"
                continue

            if not stats:
                last_failure_reason = "stats_missing"
                continue

            if not source_used:
                source_used = source_name
            combined_stats.update(stats)
            rich_keys_found.update(get_basketball_rich_stat_keys(combined_stats))

            if not get_missing_basketball_rich_stat_keys(rich_keys_found):
                break

        if combined_stats:
            persisted_matches.append(
                _build_normalized_match_stats(
                    fixture,
                    combined_stats,
                    source_used or _BASKETBALL_POLICY["canonical_source"],
                )
            )

            if not get_missing_basketball_rich_stat_keys(rich_keys_found):
                break

    result["rich_keys_found"] = [key for key in _BASKETBALL_RICH_KEYS if key in rich_keys_found]
    result["missing_rich_keys"] = get_missing_basketball_rich_stat_keys(rich_keys_found)
    result["matches_persisted"] = len(persisted_matches)

    if persisted_matches:
        result["source"] = persisted_matches[0].source
        _store_in_cache("basketball", team_name, persisted_matches, persisted_matches[0].source)
        result["status"] = "enriched" if not result["missing_rich_keys"] else "partial"
        if result["status"] != "enriched" and not result["failure_reason"]:
            result["failure_reason"] = last_failure_reason or ("stats_missing" if result["missing_rich_keys"] else None)
        return result

    result["failure_reason"] = last_failure_reason or "stats_missing"
    result["error"] = last_error or "No rich basketball stats found"
    return result


__all__ = [
    "complete_basketball_rich_stats",
    "get_basketball_rich_stat_keys",
    "get_missing_basketball_rich_stat_keys",
]