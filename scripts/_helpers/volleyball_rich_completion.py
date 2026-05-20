#!/usr/bin/env python3
"""Volleyball rich-completion helper.

Loads recent finished volleyball fixtures from the DB, resolves source-specific
fixture ids for the canonical/supporting providers, fetches per-match stats,
and persists normalized matches only through `fetch_api_stats._store_in_cache()`.
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

_VOLLEYBALL_POLICY = RICH_COMPLETION_POLICY["volleyball"]
_VOLLEYBALL_RICH_KEYS = list(_VOLLEYBALL_POLICY["required_rich_keys"])
_VOLLEYBALL_SOURCE_ORDER = [
    _VOLLEYBALL_POLICY["canonical_source"],
    *_VOLLEYBALL_POLICY["supporting_sources"],
]
_VOLLEYBALL_SUPPORTING_SOURCES = set(_VOLLEYBALL_POLICY["supporting_sources"])
_VOLLEYBALL_ESPN_UNSUPPORTED_TOKENS = ("ncaa", "women", "female", "girls", "junior")
_VOLLEYBALL_RATE_LIMITER = RateLimiter()


def _normalize_volleyball_key(stat_key: str) -> str:
    return "hitting_pct" if str(stat_key) == "attack_pct" else str(stat_key)


def get_volleyball_rich_stat_keys(stats_or_keys) -> set[str]:
    if not stats_or_keys:
        return set()
    keys = stats_or_keys.keys() if hasattr(stats_or_keys, "keys") else stats_or_keys
    normalized_keys = {_normalize_volleyball_key(str(key)) for key in keys}
    return {key for key in _VOLLEYBALL_RICH_KEYS if key in normalized_keys}


def get_missing_volleyball_rich_stat_keys(stats_or_keys) -> list[str]:
    present = get_volleyball_rich_stat_keys(stats_or_keys)
    return [key for key in _VOLLEYBALL_RICH_KEYS if key not in present]


def _get_volleyball_provider_ids(conn, fixture_ids: list[int]) -> dict[int, dict[str, str]]:
    if not fixture_ids:
        return {}

    fixture_placeholders = ", ".join("?" for _ in fixture_ids)
    source_placeholders = ", ".join("?" for _ in _VOLLEYBALL_SOURCE_ORDER)
    rows = conn.execute(
        f"SELECT fixture_id, source, external_id FROM fixture_sources "
        f"WHERE fixture_id IN ({fixture_placeholders}) AND source IN ({source_placeholders})",
        (*fixture_ids, *_VOLLEYBALL_SOURCE_ORDER),
    ).fetchall()

    provider_ids = {fixture_id: {} for fixture_id in fixture_ids}
    for row in rows:
        external_id = row["external_id"]
        if external_id:
            provider_ids[row["fixture_id"]][row["source"]] = external_id
    return provider_ids


def _get_recent_volleyball_fixtures(team_name: str, limit: int) -> tuple[list[dict], str | None]:
    try:
        with get_db() as conn:
            sport_repo = SportRepo(conn)
            team_repo = TeamRepo(conn)
            sport = sport_repo.get_by_name("volleyball")
            if not sport:
                return [], None

            team = team_repo.resolve(team_name, sport.id)
            if not team:
                return [], None

            rows = conn.execute(
                "SELECT f.id AS fixture_id, f.external_id, f.source AS fixture_source, f.kickoff, f.status, "
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

            provider_ids = _get_volleyball_provider_ids(
                conn,
                [row["fixture_id"] for row in rows],
            )
    except Exception as exc:
        logger.debug("DB volleyball fixture lookup failed for %s: %s", team_name, exc)
        return [], None

    fixtures = [
        {
            "fixture_id": row["fixture_id"],
            "external_id": row["external_id"],
            "fixture_source": row["fixture_source"],
            "kickoff": row["kickoff"],
            "status": row["status"],
            "competition": row["competition"],
            "home_team": row["home_team"],
            "away_team": row["away_team"],
            "provider_ids": provider_ids.get(row["fixture_id"], {}),
        }
        for row in rows
    ]
    return fixtures, str(team.id)


def _get_volleyball_provider_fixture_id(fixture: dict, source_name: str) -> str:
    provider_ids = fixture.get("provider_ids") or {}
    if isinstance(provider_ids, dict):
        provider_fixture_id = provider_ids.get(source_name)
        if provider_fixture_id:
            return str(provider_fixture_id)

    if fixture.get("fixture_source") == source_name and fixture.get("external_id"):
        return str(fixture["external_id"])

    return ""


def _build_normalized_volleyball_match_stats(
    fixture: dict,
    stats: dict,
    source: str,
    provider_fixture_id: str | None = None,
) -> NormalizedMatchStats:
    persisted_fixture_id = str(
        provider_fixture_id or _get_volleyball_provider_fixture_id(fixture, source) or fixture.get("fixture_id") or ""
    )
    return NormalizedMatchStats(
        fixture_id=persisted_fixture_id,
        source=source,
        sport="volleyball",
        home_team=str(fixture.get("home_team", "")),
        away_team=str(fixture.get("away_team", "")),
        date=str(fixture.get("kickoff", ""))[:10],
        stats=stats,
    )


def _coerce_volleyball_stats_payload(match_result) -> dict:
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


def _normalize_volleyball_stats(stats: dict) -> dict:
    if not isinstance(stats, dict):
        return {}
    normalized = dict(stats)
    attack_pct = normalized.pop("attack_pct", None)
    if attack_pct is not None and "hitting_pct" not in normalized:
        normalized["hitting_pct"] = attack_pct
    return normalized


def _is_unsupported_volleyball_league(source_name: str, competition: str, stats: dict) -> bool:
    if stats:
        return False
    if source_name not in _VOLLEYBALL_SUPPORTING_SOURCES:
        return False
    competition_name = (competition or "").lower()
    if not competition_name:
        return False
    if "fivb" not in competition_name:
        return True
    return any(token in competition_name for token in _VOLLEYBALL_ESPN_UNSUPPORTED_TOKENS)


def complete_volleyball_rich_stats(team_name: str, sport: str, max_fixtures: int = 5) -> dict:
    result = {
        "team": team_name,
        "sport": sport,
        "source": _VOLLEYBALL_POLICY["canonical_source"],
        "status": "failed",
        "fixtures_scanned": 0,
        "matches_persisted": 0,
        "rich_keys_found": [],
        "missing_rich_keys": list(_VOLLEYBALL_RICH_KEYS),
        "error": None,
        "failure_reason": None,
    }

    if sport != "volleyball":
        result["status"] = "skipped"
        result["error"] = f"Unsupported sport for volleyball completion: {sport}"
        result["failure_reason"] = "unsupported_sport"
        return result

    fixtures, team_id = _get_recent_volleyball_fixtures(team_name, limit=max_fixtures)
    if not team_id:
        result["error"] = f"Volleyball team not found in DB: {team_name}"
        result["failure_reason"] = "team_not_found"
        return result

    if not fixtures:
        result["error"] = "No recent volleyball fixtures found in DB"
        result["failure_reason"] = "no_fixtures"
        return result

    persisted_matches: list[NormalizedMatchStats] = []
    rich_keys_found: set[str] = set()
    last_failure_reason: str | None = None
    last_error: str | None = None

    for fixture in fixtures[:max_fixtures]:
        result["fixtures_scanned"] += 1

        combined_stats: dict = {}
        source_used: str | None = None
        source_fixture_ids: dict[str, str] = {}

        for source_name in _VOLLEYBALL_SOURCE_ORDER:
            source_fixture_id = _get_volleyball_provider_fixture_id(fixture, source_name)
            if not source_fixture_id:
                last_failure_reason = "missing_source_fixture_id"
                continue

            try:
                client = get_client(source_name, rate_limiter=_VOLLEYBALL_RATE_LIMITER)
            except Exception as exc:
                last_error = str(exc)
                last_failure_reason = "client_unavailable"
                continue

            if not client.is_available():
                continue

            try:
                match_result = client.get_fixture_stats(source_fixture_id)
            except Exception as exc:
                last_error = str(exc)
                last_failure_reason = "source_error"
                continue

            stats = _normalize_volleyball_stats(_coerce_volleyball_stats_payload(match_result))
            if _is_unsupported_volleyball_league(source_name, str(fixture.get("competition", "")), stats):
                if not combined_stats:
                    last_failure_reason = "unsupported_league_skip"
                continue

            if not stats:
                if last_failure_reason != "unsupported_league_skip":
                    last_failure_reason = "stats_missing"
                continue

            if not source_used or source_name == _VOLLEYBALL_POLICY["canonical_source"]:
                source_used = source_name
            source_fixture_ids[source_name] = source_fixture_id
            combined_stats.update(stats)
            rich_keys_found.update(get_volleyball_rich_stat_keys(combined_stats))

            if not get_missing_volleyball_rich_stat_keys(rich_keys_found):
                break

        if combined_stats:
            persisted_source = source_used or _VOLLEYBALL_POLICY["canonical_source"]
            persisted_matches.append(
                _build_normalized_volleyball_match_stats(
                    fixture,
                    combined_stats,
                    persisted_source,
                    provider_fixture_id=source_fixture_ids.get(persisted_source),
                )
            )
            if not get_missing_volleyball_rich_stat_keys(rich_keys_found):
                break

    result["rich_keys_found"] = [key for key in _VOLLEYBALL_RICH_KEYS if key in rich_keys_found]
    result["missing_rich_keys"] = get_missing_volleyball_rich_stat_keys(rich_keys_found)
    result["matches_persisted"] = len(persisted_matches)

    if persisted_matches:
        result["source"] = persisted_matches[0].source
        _store_in_cache("volleyball", team_name, persisted_matches, persisted_matches[0].source)
        result["status"] = "enriched" if not result["missing_rich_keys"] else "partial"
        if result["status"] != "enriched" and not result["failure_reason"]:
            result["failure_reason"] = last_failure_reason or (
                "stats_missing" if result["missing_rich_keys"] else None
            )
        return result

    result["failure_reason"] = last_failure_reason or "stats_missing"
    result["error"] = last_error or "No rich volleyball stats found"
    return result


__all__ = [
    "complete_volleyball_rich_stats",
    "get_missing_volleyball_rich_stat_keys",
    "get_volleyball_rich_stat_keys",
]
