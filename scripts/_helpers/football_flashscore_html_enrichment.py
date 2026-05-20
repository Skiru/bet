#!/usr/bin/env python3
"""Football Flashscore HTML completion helper.

This adapter loads recent football fixtures from the DB, resolves Flashscore
match pages through the shared HTML helper, normalizes rich stat families into
`NormalizedMatchStats`, and persists via `fetch_api_stats._store_in_cache()`.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from bet.db.connection import get_db
from bet.db.repositories import SportRepo, TeamRepo
from bet.models.normalized import NormalizedMatchStats
from fetch_api_stats import _store_in_cache
from _helpers.flashscore_match_page_stats import (
    FLASHSCORE_FOOTBALL_STAT_KEYS,
    fetch_flashscore_match_page_stats,
)

logger = logging.getLogger(__name__)

FOOTBALL_RICH_STAT_KEYS = FLASHSCORE_FOOTBALL_STAT_KEYS


def get_football_rich_stat_keys(stats_or_keys: Mapping[str, object] | Iterable[str] | None) -> set[str]:
    """Return the subset of football rich stat keys present in input data."""
    if not stats_or_keys:
        return set()
    keys = stats_or_keys.keys() if isinstance(stats_or_keys, Mapping) else stats_or_keys
    return {str(key) for key in keys if str(key) in FOOTBALL_RICH_STAT_KEYS}


def get_missing_football_rich_stat_keys(
    stats_or_keys: Mapping[str, object] | Iterable[str] | None,
) -> list[str]:
    """Return ordered football rich keys that are still missing."""
    present = get_football_rich_stat_keys(stats_or_keys)
    return [key for key in FOOTBALL_RICH_STAT_KEYS if key not in present]


def _get_recent_football_fixtures(team_name: str, limit: int) -> tuple[list[dict], str | None]:
    """Load recent finished football fixtures for a team from the DB."""
    try:
        with get_db() as conn:
            sport_repo = SportRepo(conn)
            team_repo = TeamRepo(conn)
            sport = sport_repo.get_by_name("football")
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
        logger.debug("DB football fixture lookup failed for %s: %s", team_name, exc)
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


def _build_normalized_match_stats(fixture: dict, stats: dict) -> NormalizedMatchStats:
    return NormalizedMatchStats(
        fixture_id=str(fixture.get("fixture_id", "")),
        source="flashscore-html",
        sport="football",
        home_team=str(fixture.get("home_team", "")),
        away_team=str(fixture.get("away_team", "")),
        date=str(fixture.get("kickoff", ""))[:10],
        stats=stats,
    )


def complete_football_flashscore_html_stats(
    team_name: str,
    sport: str,
    max_fixtures: int = 5,
    *,
    c_requests=None,
    sleep_seconds: float = 1.5,
    max_requests: int | None = None,
) -> dict:
    """Fetch and persist missing football rich stats through Flashscore HTML."""
    result = {
        "team": team_name,
        "sport": sport,
        "source": "flashscore-html",
        "status": "failed",
        "fixtures_scanned": 0,
        "matches_persisted": 0,
        "rich_keys_found": [],
        "missing_rich_keys": list(FOOTBALL_RICH_STAT_KEYS),
        "team_id": None,
        "error": None,
        "failure_reason": None,
    }

    if sport != "football":
        result["status"] = "skipped"
        result["error"] = f"Unsupported sport for football completion: {sport}"
        result["failure_reason"] = "unsupported_sport"
        return result

    fixtures, team_id = _get_recent_football_fixtures(team_name, limit=max_fixtures)
    result["team_id"] = team_id
    if not team_id:
        result["error"] = f"Football team not found in DB: {team_name}"
        result["failure_reason"] = "team_not_found"
        return result

    if not fixtures:
        result["error"] = "No recent football fixtures found in DB"
        result["failure_reason"] = "no_fixtures"
        return result

    persisted_matches: list[NormalizedMatchStats] = []
    rich_keys_found: set[str] = set()
    last_failure_reason: str | None = None
    last_error: str | None = None
    requests_used = 0

    for fixture in fixtures[:max_fixtures]:
        if max_requests is not None and requests_used >= max_requests:
            last_failure_reason = "request_budget_exhausted"
            break

        result["fixtures_scanned"] += 1
        match_result = fetch_flashscore_match_page_stats(
            str(fixture.get("home_team", "")),
            str(fixture.get("away_team", "")),
            sport,
            c_requests=c_requests,
            sleep_seconds=sleep_seconds,
            max_requests=None if max_requests is None else max_requests - requests_used,
        )
        requests_used += int(match_result.get("requests_used", 0) or 0)

        stats = match_result.get("stats") or {}
        if stats:
            rich_keys_found.update(get_football_rich_stat_keys(stats))
            persisted_matches.append(_build_normalized_match_stats(fixture, stats))
            if not get_missing_football_rich_stat_keys(rich_keys_found):
                break
            continue

        failure_reason = match_result.get("failure_reason")
        if failure_reason:
            last_failure_reason = str(failure_reason)
        error = match_result.get("error")
        if error:
            last_error = str(error)

    result["rich_keys_found"] = [key for key in FOOTBALL_RICH_STAT_KEYS if key in rich_keys_found]
    result["missing_rich_keys"] = get_missing_football_rich_stat_keys(rich_keys_found)
    result["matches_persisted"] = len(persisted_matches)

    if persisted_matches:
        _store_in_cache("football", team_name, persisted_matches, "flashscore-html")
        result["status"] = "enriched" if not result["missing_rich_keys"] else "partial"
        if result["status"] != "enriched" and not result["failure_reason"]:
            result["failure_reason"] = last_failure_reason or ("stats_missing" if result["missing_rich_keys"] else None)
        return result

    result["failure_reason"] = last_failure_reason or "stats_missing"
    result["error"] = last_error or "No rich Flashscore football stats found"
    return result


# Shared alias retained for live callers that use the generic rich-completion name.
complete_football_rich_stats = complete_football_flashscore_html_stats


__all__ = [
    "FOOTBALL_RICH_STAT_KEYS",
    "complete_football_flashscore_html_stats",
    "complete_football_rich_stats",
    "get_football_rich_stat_keys",
    "get_missing_football_rich_stat_keys",
]
