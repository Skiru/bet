#!/usr/bin/env python3
"""Tennis rich-completion helper.

Loads recent finished tennis fixtures from the DB, fetches per-match serve and
return stats from the canonical or supporting provider path, filters out
baseline-owned keys, and persists normalized matches only through
`fetch_api_stats._store_in_cache()`.
"""

from __future__ import annotations

import logging
import sys
import unicodedata
from collections import defaultdict
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

# Well-known tournament → surface mapping
_TOURNAMENT_SURFACE_MAP = {
    "roland garros": "clay",
    "french open": "clay",
    "wimbledon": "grass",
    "australian open": "hard",
    "us open": "hard",
    "madrid": "clay",
    "rome": "clay",
    "monte carlo": "clay",
    "barcelona": "clay",
    "geneva": "clay",
    "lyon": "clay",
    "hamburg": "clay",
    "bastad": "clay",
    "kitzbuhel": "clay",
    "umag": "clay",
    "bucharest": "clay",
    "gstaad": "clay",
    "indian wells": "hard",
    "miami": "hard",
    "shanghai": "hard",
    "cincinnati": "hard",
    "toronto": "hard",
    "montreal": "hard",
    "dubai": "hard",
    "doha": "hard",
    "brisbane": "hard",
    "adelaide": "hard",
    "auckland": "hard",
    "halle": "grass",
    "queens": "grass",
    "s-hertogenbosch": "grass",
    "eastbourne": "grass",
    "mallorca": "grass",
    "stuttgart": "clay",
    "beijing": "hard",
    "tokyo": "hard",
    "vienna": "hard",
    "basel": "hard",
    "paris": "hard",  # Paris Masters (indoor hard)
}


def _infer_surface_from_league(league_name: str) -> str | None:
    """Infer surface from tournament/league name."""
    if not league_name:
        return None
    league_lower = league_name.lower()
    for key, surface in _TOURNAMENT_SURFACE_MAP.items():
        if key in league_lower:
            return surface
    return None


def _update_fixture_surface(fixture_id: int, surface: str) -> None:
    """Update the surface column of a fixture if not already set."""
    if not surface or not fixture_id:
        return
    valid_surfaces = {"hard", "clay", "grass", "carpet"}
    surface_lower = surface.lower().strip()
    if surface_lower not in valid_surfaces:
        return
    try:
        with get_db() as conn:
            conn.execute(
                "UPDATE fixtures SET surface = ? WHERE id = ? AND (surface IS NULL OR surface = '')",
                (surface_lower, fixture_id),
            )
            conn.commit()
    except Exception as e:
        logger.debug(f"Failed to update fixture surface: {e}")

_TENNIS_POLICY = RICH_COMPLETION_POLICY["tennis"]
_TENNIS_RICH_KEYS = list(_TENNIS_POLICY["required_rich_keys"])
_TENNIS_BASELINE_KEYS = set(_TENNIS_POLICY["baseline_keys"])
_TENNIS_SOURCE_ORDER = [
    _TENNIS_POLICY["canonical_source"],
    *_TENNIS_POLICY["supporting_sources"],
]
_RATE_LIMITER = RateLimiter()


def get_tennis_rich_stat_keys(stats_or_keys) -> set[str]:
    if not stats_or_keys:
        return set()
    keys = stats_or_keys.keys() if hasattr(stats_or_keys, "keys") else stats_or_keys
    return {str(key) for key in keys if str(key) in _TENNIS_RICH_KEYS}


def get_missing_tennis_rich_stat_keys(stats_or_keys) -> list[str]:
    present = get_tennis_rich_stat_keys(stats_or_keys)
    return [key for key in _TENNIS_RICH_KEYS if key not in present]


def get_tennis_baseline_stat_keys(stats_or_keys) -> set[str]:
    if not stats_or_keys:
        return set()
    keys = stats_or_keys.keys() if hasattr(stats_or_keys, "keys") else stats_or_keys
    return {str(key) for key in keys if str(key) in _TENNIS_BASELINE_KEYS}


def _normalize_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(name or ""))
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    return "".join(ch.lower() for ch in ascii_name if ch.isalnum())


def _fuzzy_names_match(name_a: str, name_b: str, threshold: int = 80) -> bool:
    """Fuzzy compare two player names (handles diacritics, abbreviations, order)."""
    a_norm = _normalize_name(name_a)
    b_norm = _normalize_name(name_b)
    
    # Exact normalized match
    if a_norm == b_norm:
        return True
    
    # Try rapidfuzz if available
    try:
        from rapidfuzz import fuzz
        if fuzz.ratio(a_norm, b_norm) >= threshold:
            return True
        if fuzz.token_sort_ratio(a_norm, b_norm) >= threshold:
            return True
    except ImportError:
        pass
    
    # Last-name fallback (most identifying part of tennis player names)
    parts_a = name_a.strip().split()
    parts_b = name_b.strip().split()
    if parts_a and parts_b and len(parts_a[-1]) > 3 and len(parts_b[-1]) > 3:
        if _normalize_name(parts_a[-1]) == _normalize_name(parts_b[-1]):
            return True
    
    return False


def _extract_opponent(team_name: str, home_team: str, away_team: str) -> str | None:
    team_norm = _normalize_name(team_name)
    home_norm = _normalize_name(home_team)
    away_norm = _normalize_name(away_team)

    if team_norm and home_norm == team_norm:
        return away_team or None
    if team_norm and away_norm == team_norm:
        return home_team or None
    return None


def _lookup_key(opponent: str, match_date: str) -> tuple[str, str] | None:
    date_key = str(match_date or "")[:10]
    opponent_key = _normalize_name(opponent)
    if not date_key or not opponent_key:
        return None
    return date_key, opponent_key


def _get_recent_tennis_fixtures(team_name: str, limit: int) -> tuple[list[dict], str | None]:
    try:
        with get_db() as conn:
            sport_repo = SportRepo(conn)
            team_repo = TeamRepo(conn)
            sport = sport_repo.get_by_name("tennis")
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
        logger.debug("DB tennis fixture lookup failed for %s: %s", team_name, exc)
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


def _is_aggregate_only_match(match: NormalizedMatchStats | None) -> bool:
    if not match:
        return False
    fixture_id = str(getattr(match, "fixture_id", "") or "")
    away_team = str(getattr(match, "away_team", "") or "")
    return fixture_id.startswith("sack_season_") or away_team == "season_aggregate"


def _filter_rich_only_stats(stats: dict | None) -> dict:
    filtered: dict[str, float | int] = {}
    for key, value in (stats or {}).items():
        stat_key = str(key)
        if stat_key not in _TENNIS_RICH_KEYS:
            continue
        if isinstance(value, (int, float)):
            filtered[stat_key] = value
    return filtered


def _copy_match_with_filtered_stats(match: NormalizedMatchStats, stats: dict) -> NormalizedMatchStats:
    return NormalizedMatchStats(
        fixture_id=str(getattr(match, "fixture_id", "") or ""),
        source=str(getattr(match, "source", "") or ""),
        sport="tennis",
        home_team=str(getattr(match, "home_team", "") or ""),
        away_team=str(getattr(match, "away_team", "") or ""),
        date=str(getattr(match, "date", "") or "")[:10],
        stats=stats,
    )


def _load_source_matches(team_name: str, source_name: str, max_fixtures: int) -> list[NormalizedMatchStats]:
    try:
        client = get_client(source_name, rate_limiter=_RATE_LIMITER)
    except Exception as exc:
        logger.debug("Tennis completion client unavailable for %s: %s", source_name, exc)
        return []

    if not client.is_available():
        return []

    if source_name == "tennis-abstract":
        try:
            matches = client.get_fixture_stats_for_player(team_name, last_n=max_fixtures * 3)
        except Exception as exc:
            logger.debug("Tennis Abstract completion failed for %s: %s", team_name, exc)
            return []

        normalized = []
        for match in matches or []:
            filtered = _filter_rich_only_stats(getattr(match, "stats", {}) or {})
            if filtered:
                normalized.append(_copy_match_with_filtered_stats(match, filtered))
        return normalized

    try:
        team_id = client.resolve_team_id(team_name)
    except Exception as exc:
        logger.debug("Tennis completion team resolution failed for %s/%s: %s", team_name, source_name, exc)
        return []

    if not team_id:
        return []

    try:
        fixtures = client.get_team_last_fixtures(team_id, last_n=max_fixtures * 3)
    except Exception as exc:
        logger.debug("Tennis completion fixture load failed for %s/%s: %s", team_name, source_name, exc)
        return []

    matches: list[NormalizedMatchStats] = []
    for fixture in fixtures or []:
        fixture_id = str(getattr(fixture, "fixture_id", "") or "")
        if not fixture_id:
            continue
        try:
            match = client.get_fixture_stats(fixture_id)
        except Exception as exc:
            logger.debug("Tennis completion stats load failed for %s/%s/%s: %s", team_name, source_name, fixture_id, exc)
            continue

        if not match or _is_aggregate_only_match(match):
            continue

        filtered = _filter_rich_only_stats(getattr(match, "stats", {}) or {})
        if not filtered:
            continue
        matches.append(_copy_match_with_filtered_stats(match, filtered))

    return matches


def _index_matches_by_fixture_key(team_name: str, matches: list[NormalizedMatchStats]) -> dict[tuple[str, str], list[NormalizedMatchStats]]:
    indexed: dict[tuple[str, str], list[NormalizedMatchStats]] = defaultdict(list)
    for match in matches:
        opponent = _extract_opponent(team_name, getattr(match, "home_team", ""), getattr(match, "away_team", ""))
        key = _lookup_key(opponent or "", getattr(match, "date", ""))
        if not key:
            continue
        indexed[key].append(match)
    return indexed


def complete_tennis_rich_stats(team_name: str, sport: str, max_fixtures: int = 5) -> dict:
    result = {
        "team": team_name,
        "sport": sport,
        "source": _TENNIS_POLICY["canonical_source"],
        "status": "failed",
        "fixtures_scanned": 0,
        "matches_persisted": 0,
        "rich_keys_found": [],
        "missing_rich_keys": list(_TENNIS_RICH_KEYS),
        "error": None,
        "failure_reason": None,
    }

    if sport != "tennis":
        result["status"] = "skipped"
        result["error"] = f"Unsupported sport for tennis completion: {sport}"
        result["failure_reason"] = "unsupported_sport"
        return result

    fixtures, team_id = _get_recent_tennis_fixtures(team_name, limit=max_fixtures)
    if not team_id:
        result["error"] = f"Tennis player not found in DB: {team_name}"
        result["failure_reason"] = "team_not_found"
        return result

    if not fixtures:
        result["error"] = "No recent tennis fixtures found in DB"
        result["failure_reason"] = "no_fixtures"
        return result

    source_indexes = {
        source_name: _index_matches_by_fixture_key(
            team_name,
            _load_source_matches(team_name, source_name, max_fixtures),
        )
        for source_name in _TENNIS_SOURCE_ORDER
    }

    persisted_matches: list[NormalizedMatchStats] = []
    rich_keys_found: set[str] = set()
    last_failure_reason: str | None = None

    for fixture in fixtures[:max_fixtures]:
        result["fixtures_scanned"] += 1
        opponent = _extract_opponent(team_name, fixture.get("home_team", ""), fixture.get("away_team", ""))
        key = _lookup_key(opponent or "", fixture.get("kickoff", ""))
        if not key:
            last_failure_reason = "fixture_mismatch"
            continue

        combined_stats: dict[str, float | int] = {}
        source_used: str | None = None

        for source_name in _TENNIS_SOURCE_ORDER:
            candidates = source_indexes.get(source_name, {}).get(key, [])
            
            # Fallback to fuzzy match if exact key not found
            if not candidates and opponent:
                source_dict = source_indexes.get(source_name, {})
                for (d_key, o_key), matches in source_dict.items():
                    if d_key == key[0]:  # match date exactly
                        for m in matches:
                            m_opp = _extract_opponent(team_name, getattr(m, "home_team", ""), getattr(m, "away_team", ""))
                            if m_opp and _fuzzy_names_match(m_opp, opponent):
                                candidates.append(m)
                                break  # only need to match it once

            if not candidates:
                continue

            match = candidates.pop(0)
            rich_stats = _filter_rich_only_stats(getattr(match, "stats", {}) or {})
            if not rich_stats:
                last_failure_reason = "stats_missing"
                continue

            if not source_used:
                source_used = source_name
            combined_stats.update(rich_stats)
            rich_keys_found.update(get_tennis_rich_stat_keys(combined_stats))

            if not get_missing_tennis_rich_stat_keys(rich_keys_found):
                break

        if combined_stats:
            persisted_matches.append(
                NormalizedMatchStats(
                    fixture_id=str(fixture.get("fixture_id", "") or ""),
                    source=source_used or _TENNIS_POLICY["canonical_source"],
                    sport="tennis",
                    home_team=str(fixture.get("home_team", "") or ""),
                    away_team=str(fixture.get("away_team", "") or ""),
                    date=str(fixture.get("kickoff", "") or "")[:10],
                    stats=combined_stats,
                )
            )

            if not get_missing_tennis_rich_stat_keys(rich_keys_found):
                break

    # Fallback: direct player lookup from tennis-abstract if we have < 5 matches
    if len(persisted_matches) < 5:
        try:
            ta_client = get_client("tennis-abstract", rate_limiter=_RATE_LIMITER)
            if ta_client.is_available():
                player_fixtures = ta_client.get_team_last_fixtures(team_name, last_n=10)
                if player_fixtures:
                    existing_ids = {m.fixture_id for m in persisted_matches}
                    for match in player_fixtures:
                        if len(persisted_matches) >= 5:
                            break
                        if _is_aggregate_only_match(match):
                            continue
                        rich_stats = _filter_rich_only_stats(getattr(match, "stats", {}) or {})
                        if rich_stats and match.fixture_id not in existing_ids:
                            # Try to update fixture surface if we have a fixture ID and surface from source
                            m_surface = getattr(match, "surface", None) or (getattr(match, "stats", {}) or {}).get("surface")
                            if m_surface and match.fixture_id:
                                try:
                                    _update_fixture_surface(int(match.fixture_id), m_surface)
                                except ValueError:
                                    pass
                                
                            persisted_matches.append(_copy_match_with_filtered_stats(match, rich_stats))
                            rich_keys_found.update(get_tennis_rich_stat_keys(rich_stats))
                            existing_ids.add(match.fixture_id)
        except Exception as e:
            logger.debug("Fallback tennis-abstract direct lookup failed: %s", e)

    result["rich_keys_found"] = [key for key in _TENNIS_RICH_KEYS if key in rich_keys_found]
    result["missing_rich_keys"] = get_missing_tennis_rich_stat_keys(rich_keys_found)
    result["matches_persisted"] = len(persisted_matches)

    if persisted_matches:
        result["source"] = persisted_matches[0].source
        _store_in_cache("tennis", team_name, persisted_matches, persisted_matches[0].source)
        result["status"] = "enriched" if not result["missing_rich_keys"] else "partial"
        if result["status"] != "enriched":
            result["failure_reason"] = last_failure_reason or "stats_missing"
        return result

    result["failure_reason"] = last_failure_reason or "stats_missing"
    result["error"] = "No rich tennis stats found"
    return result


__all__ = [
    "complete_tennis_rich_stats",
    "get_tennis_baseline_stat_keys",
    "get_tennis_rich_stat_keys",
    "get_missing_tennis_rich_stat_keys",
]