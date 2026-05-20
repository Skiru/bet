#!/usr/bin/env python3
"""Self-healing data enrichment agent — fetches missing team stats via API clients.

Thin orchestrator around scripts/api_clients/ and scripts/fetch_api_stats.py.
Detects teams missing from stats cache, fetches via proper API fallback chains
(ESPN → API-Football/Basketball/Hockey → Google Sports → Flashscore curl_cffi last resort).

Usage:
    python3 scripts/data_enrichment_agent.py --team "FC Barcelona" --sport football
    python3 scripts/data_enrichment_agent.py --batch betting/data/missing_teams.json
    python3 scripts/data_enrichment_agent.py --date 2026-05-08
    python3 scripts/data_enrichment_agent.py --date 2026-05-18 --news --verbose
"""

import argparse
import concurrent.futures
import json
import logging
import math
import re
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Imports from the proper API client infrastructure
# ---------------------------------------------------------------------------
from bet.api_clients import get_client, RateLimiter, CLIENT_REGISTRY
from bet.api_clients.base_client import APIRateLimitError, APIError
from fetch_api_stats import (
    fetch_team_stats,
    fetch_h2h_stats,
    FALLBACK_CHAINS,
    _store_in_cache,
)
from flashscore_enricher import _try_flashscore, _get_flashscore_entity
from _helpers.basketball_rich_completion import (
    complete_basketball_rich_stats,
    get_basketball_rich_stat_keys,
    get_missing_basketball_rich_stat_keys,
)
from _helpers.hockey_rich_completion import (
    complete_hockey_rich_stats,
    get_hockey_rich_stat_keys,
    get_missing_hockey_rich_stat_keys,
)
from _helpers.tennis_rich_completion import (
    complete_tennis_rich_stats,
    get_missing_tennis_rich_stat_keys,
    get_tennis_baseline_stat_keys,
    get_tennis_rich_stat_keys,
)
from _helpers.volleyball_rich_completion import (
    complete_volleyball_rich_stats,
    get_missing_volleyball_rich_stat_keys,
    get_volleyball_rich_stat_keys,
)
from _helpers.football_flashscore_html_enrichment import (
    complete_football_rich_stats,
    get_football_rich_stat_keys,
    get_missing_football_rich_stat_keys,
)
from bet.db.connection import get_db
from bet.db.models import TeamForm
from bet.db.repositories import SportRepo, StatsRepo, TeamRepo, KnownMissingRepo
from bet.stats.fallback_chains import RICH_COMPLETION_POLICY
from bet.stats.market_ranking import SPORT_STAT_KEYS
from bet.stats.rich_coverage import classify_rich_coverage

_TENNIS_POLICY = RICH_COMPLETION_POLICY["tennis"]
_TENNIS_ALLOWED_SOURCES = {
    _TENNIS_POLICY["canonical_source"],
    *_TENNIS_POLICY["supporting_sources"],
}
_TENNIS_BASELINE_SOURCES = set(_TENNIS_POLICY.get("baseline_sources", []))
_HOCKEY_POLICY = RICH_COMPLETION_POLICY["hockey"]
_HOCKEY_ALLOWED_SOURCES = {
    _HOCKEY_POLICY["canonical_source"],
    *_HOCKEY_POLICY["supporting_sources"],
}
_VOLLEYBALL_POLICY = RICH_COMPLETION_POLICY["volleyball"]
_VOLLEYBALL_ALLOWED_SOURCES = {
    _VOLLEYBALL_POLICY["canonical_source"],
    *_VOLLEYBALL_POLICY["supporting_sources"],
}

# ---------------------------------------------------------------------------
# Known missing teams — DB-based (replaces old JSON file)
# ---------------------------------------------------------------------------


def _mark_missing(team_name: str, sport: str, reason: str = "", source: str = ""):
    with _known_missing_lock:
        try:
            with get_db() as conn:
                repo = KnownMissingRepo(conn)
                repo.mark_missing(team_name, sport, reason=reason, source=source)
                conn.commit()
        except Exception as e:
            logger.debug(f"Failed to mark missing: {team_name} ({sport}): {e}")


def _is_known_missing(team_name: str, sport: str) -> bool:
    """Check if a team is known to 404. Entries expire after 7 days."""
    with _known_missing_lock:
        try:
            with get_db() as conn:
                repo = KnownMissingRepo(conn)
                return repo.is_missing(team_name, sport)
        except Exception:
            return False

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_DIR = ROOT_DIR / "betting" / "data"
CACHE_DIR = DATA_DIR / "stats_cache"

# Per-sport expected stat value ranges for sanity checking
from bet.stats.value_ranges import SPORT_VALUE_RANGES

# Per-source circuit breaker (thread-safe)
_source_failures: dict[str, int] = {}
_source_trip_time: dict[str, float] = {}
_source_cb_lock = threading.Lock()
CIRCUIT_BREAKER_THRESHOLD = 3
CIRCUIT_BREAKER_HALF_OPEN_SECS = 60
_db_write_lock = threading.Lock()
_known_missing_lock = threading.Lock()

# Shared rate limiter instance
_rate_limiter = RateLimiter()


def _source_is_down(source: str) -> bool:
    with _source_cb_lock:
        if _source_failures.get(source, 0) < CIRCUIT_BREAKER_THRESHOLD:
            return False
        trip_time = _source_trip_time.get(source, 0)
        if time.monotonic() - trip_time > CIRCUIT_BREAKER_HALF_OPEN_SECS:
            # Half-open: allow one probe request
            _source_failures[source] = CIRCUIT_BREAKER_THRESHOLD - 1
            return False
        return True


def _record_source_failure(source: str) -> None:
    with _source_cb_lock:
        _source_failures[source] = _source_failures.get(source, 0) + 1
        if _source_failures[source] == CIRCUIT_BREAKER_THRESHOLD:
            _source_trip_time[source] = time.monotonic()
            logger.warning(f"[Circuit Breaker] {source} marked DOWN — {CIRCUIT_BREAKER_THRESHOLD} consecutive failures")


def _record_source_success(source: str) -> None:
    with _source_cb_lock:
        _source_failures[source] = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'[\s-]+', '-', s)
    return s.strip('-')


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_avg(values: list) -> float | None:
    nums = [v for v in values if isinstance(v, (int, float))]
    if not nums:
        return None
    return round(sum(nums) / len(nums), 2)


def _result_stat_keys(result: dict) -> set[str]:
    return {str(key) for key in (result.get("stats_found") or {}).keys()}


def _set_result_status(result: dict) -> None:
    found_keys = _result_stat_keys(result)
    sport = result.get("sport", "")

    if sport == "football":
        rich_keys = get_football_rich_stat_keys(found_keys)
        missing_rich = get_missing_football_rich_stat_keys(found_keys)
        result["football_rich_keys_found"] = sorted(rich_keys)
        result["football_missing_rich_keys"] = missing_rich
        result["football_rich_complete"] = bool(rich_keys) and not missing_rich
        if found_keys:
            result["status"] = "enriched" if result["football_rich_complete"] else "partial"
        else:
            result["status"] = "failed"
        return

    if sport == "basketball":
        rich_keys = get_basketball_rich_stat_keys(found_keys)
        missing_rich = get_missing_basketball_rich_stat_keys(found_keys)
        result["basketball_rich_keys_found"] = sorted(rich_keys)
        result["basketball_missing_rich_keys"] = missing_rich
        result["basketball_rich_complete"] = bool(rich_keys) and not missing_rich
        if found_keys:
            result["status"] = "enriched" if result["basketball_rich_complete"] else "partial"
        else:
            result["status"] = "failed"
        return

    if sport == "tennis":
        baseline_keys = get_tennis_baseline_stat_keys(found_keys)
        rich_keys = get_tennis_rich_stat_keys(found_keys)
        missing_rich = get_missing_tennis_rich_stat_keys(found_keys)
        result["tennis_baseline_keys_found"] = sorted(baseline_keys)
        result["tennis_has_baseline"] = bool(baseline_keys)
        result["tennis_rich_keys_found"] = sorted(rich_keys)
        result["tennis_missing_rich_keys"] = missing_rich
        result["tennis_rich_complete"] = bool(rich_keys) and not missing_rich
        if found_keys:
            result["status"] = "enriched" if result["tennis_rich_complete"] else "partial"
        else:
            result["status"] = "failed"
        return

    if sport == "hockey":
        rich_keys = get_hockey_rich_stat_keys(found_keys)
        missing_rich = get_missing_hockey_rich_stat_keys(found_keys)
        result["hockey_rich_keys_found"] = sorted(rich_keys)
        result["hockey_missing_rich_keys"] = missing_rich
        result["hockey_rich_complete"] = bool(rich_keys) and not missing_rich
        if found_keys:
            result["status"] = "enriched" if result["hockey_rich_complete"] else "partial"
        else:
            result["status"] = "failed"
        return

    if sport == "volleyball":
        rich_keys = get_volleyball_rich_stat_keys(found_keys)
        missing_rich = get_missing_volleyball_rich_stat_keys(found_keys)
        result["volleyball_rich_keys_found"] = sorted(rich_keys)
        result["volleyball_missing_rich_keys"] = missing_rich
        result["volleyball_rich_complete"] = bool(rich_keys) and not missing_rich
        if found_keys:
            result["status"] = "enriched" if result["volleyball_rich_complete"] else "partial"
        else:
            result["status"] = "failed"
        return

    expected = set(SPORT_STAT_KEYS.get(sport, []))
    if found_keys >= expected:
        result["status"] = "enriched"
    elif found_keys:
        result["status"] = "partial"
    else:
        result["status"] = "failed"


def _needs_football_rich_completion(result: dict) -> bool:
    return result.get("sport") == "football" and bool(
        get_missing_football_rich_stat_keys(_result_stat_keys(result))
    )


def _apply_football_rich_completion(result: dict, max_fixtures: int = 5) -> dict:
    if result.get("sport") != "football":
        return result

    _set_result_status(result)
    completion = result.setdefault(
        "football_completion",
        {
            "needed": False,
            "attempted": False,
            "success": False,
            "source": "flashscore-html",
            "status": "not_needed",
            "fixtures_scanned": 0,
            "matches_persisted": 0,
            "rich_keys_added": [],
            "missing_after": [],
            "error": None,
        },
    )

    error_text = (result.get("error") or "").lower()
    if "known missing team" in error_text or "missing team name" in error_text:
        completion.update(
            {
                "needed": False,
                "attempted": False,
                "success": False,
                "status": "skipped",
                "error": result.get("error"),
                "missing_after": result.get("football_missing_rich_keys", []),
            }
        )
        return result

    completion["needed"] = _needs_football_rich_completion(result)
    if not completion["needed"]:
        completion["status"] = "not_needed"
        completion["missing_after"] = result.get("football_missing_rich_keys", [])
        return result

    existing_rich = set(result.get("football_rich_keys_found", []))
    helper_result = complete_football_rich_stats(
        result["team"],
        result["sport"],
        max_fixtures=max_fixtures,
        rate_limiter=_rate_limiter,
    )
    added_rich = [
        key for key in helper_result.get("rich_keys_found", []) if key not in existing_rich
    ]

    completion.update(
        {
            "needed": True,
            "attempted": True,
            "source": helper_result.get("source", "flashscore-html"),
            "status": helper_result.get("status", "failed"),
            "fixtures_scanned": helper_result.get("fixtures_scanned", 0),
            "matches_persisted": helper_result.get("matches_persisted", 0),
            "rich_keys_added": added_rich,
            "error": helper_result.get("error"),
        }
    )

    if helper_result.get("status") in ("enriched", "partial") and helper_result.get("rich_keys_found"):
        for stat_key in helper_result["rich_keys_found"]:
            result.setdefault("stats_found", {})[stat_key] = True
        if result.get("source") and result["source"] != "flashscore-html":
            supplementary_sources = result.setdefault("supplementary_sources", [])
            if "flashscore-html" not in supplementary_sources:
                supplementary_sources.append("flashscore-html")
        else:
            result["source"] = "flashscore-html"
        result["error"] = None
    elif helper_result.get("error"):
        errors = [
            message
            for message in [result.get("error"), f"flashscore-html-completion: {helper_result['error']}"]
            if message
        ]
        result["error"] = "; ".join(errors[-2:])

    completion["success"] = bool(added_rich)
    _set_result_status(result)
    completion["missing_after"] = result.get("football_missing_rich_keys", [])
    return result


def _needs_basketball_rich_completion(result: dict) -> bool:
    return result.get("sport") == "basketball" and bool(
        get_missing_basketball_rich_stat_keys(_result_stat_keys(result))
    )


def _apply_basketball_rich_completion(
    result: dict,
    max_fixtures: int = 5,
    allow_basketball_rich_completion: bool = True,
) -> dict:
    if result.get("sport") != "basketball":
        return result

    _set_result_status(result)
    completion = result.setdefault(
        "basketball_completion",
        {
            "needed": False,
            "attempted": False,
            "success": False,
            "source": "api-basketball",
            "status": "not_needed",
            "fixtures_scanned": 0,
            "matches_persisted": 0,
            "rich_keys_added": [],
            "missing_after": [],
            "error": None,
            "failure_reason": None,
        },
    )

    error_text = (result.get("error") or "").lower()
    if "known missing team" in error_text or "missing team name" in error_text:
        completion.update(
            {
                "needed": False,
                "attempted": False,
                "success": False,
                "status": "skipped",
                "error": result.get("error"),
                "missing_after": result.get("basketball_missing_rich_keys", []),
            }
        )
        return result

    completion["needed"] = _needs_basketball_rich_completion(result)
    if not completion["needed"]:
        completion["status"] = "not_needed"
        completion["missing_after"] = result.get("basketball_missing_rich_keys", [])
        return result

    if not allow_basketball_rich_completion:
        completion.update(
            {
                "needed": True,
                "attempted": False,
                "success": False,
                "status": "skipped",
                "error": result.get("error"),
                "failure_reason": "disabled",
                "missing_after": result.get("basketball_missing_rich_keys", []),
            }
        )
        return result

    existing_rich = set(result.get("basketball_rich_keys_found", []))
    helper_result = complete_basketball_rich_stats(result["team"], result["sport"], max_fixtures=max_fixtures)
    added_rich = [
        key for key in helper_result.get("rich_keys_found", []) if key not in existing_rich
    ]

    completion.update(
        {
            "needed": True,
            "attempted": True,
            "source": helper_result.get("source", "api-basketball"),
            "status": helper_result.get("status", "failed"),
            "fixtures_scanned": helper_result.get("fixtures_scanned", 0),
            "matches_persisted": helper_result.get("matches_persisted", 0),
            "rich_keys_added": added_rich,
            "error": helper_result.get("error"),
            "failure_reason": helper_result.get("failure_reason"),
        }
    )

    if helper_result.get("status") in ("enriched", "partial") and helper_result.get("rich_keys_found"):
        for stat_key in helper_result["rich_keys_found"]:
            result.setdefault("stats_found", {})[stat_key] = True
        if result.get("source") and result["source"] != "api-basketball":
            supplementary_sources = result.setdefault("supplementary_sources", [])
            if "api-basketball" not in supplementary_sources:
                supplementary_sources.append("api-basketball")
        else:
            result["source"] = "api-basketball"
        result["error"] = None
    elif helper_result.get("error"):
        errors = [
            message
            for message in [result.get("error"), f"basketball-completion: {helper_result['error']}" ]
            if message
        ]
        result["error"] = "; ".join(errors[-2:])

    # Success means the helper added at least one rich key; `status` still
    # carries whether the team reached full 11-key coverage or remains partial.
    completion["success"] = bool(added_rich)
    _set_result_status(result)
    completion["missing_after"] = result.get("basketball_missing_rich_keys", [])
    return result


def _default_tennis_coverage_detail() -> dict:
    return {
        "bucket": "no_data",
        "eligible": False,
        "stat_keys": [],
        "sources": [],
        "rich_keys_found": [],
        "missing_rich_keys": list(_TENNIS_POLICY["required_rich_keys"]),
    }


def _default_hockey_coverage_detail() -> dict:
    return {
        "bucket": "no_data",
        "eligible": False,
        "stat_keys": [],
        "sources": [],
        "rich_keys_found": [],
        "missing_rich_keys": list(_HOCKEY_POLICY["required_rich_keys"]),
    }


def _default_volleyball_coverage_detail() -> dict:
    return {
        "bucket": "no_data",
        "eligible": False,
        "stat_keys": [],
        "sources": [],
        "rich_keys_found": [],
        "missing_rich_keys": list(_VOLLEYBALL_POLICY["required_rich_keys"]),
    }


def _get_hockey_coverage_detail(team_name: str) -> dict:
    try:
        with get_db() as conn:
            sport_repo = SportRepo(conn)
            team_repo = TeamRepo(conn)
            sport = sport_repo.get_by_name("hockey")
            if not sport:
                return _default_hockey_coverage_detail()

            team = team_repo.resolve(team_name, sport.id)
            if not team:
                return _default_hockey_coverage_detail()

            rows = conn.execute(
                "SELECT stat_key, source FROM team_form WHERE team_id = ? AND sport_id = ?",
                (team.id, sport.id),
            ).fetchall()
    except Exception as exc:
        logger.debug("Failed to inspect hockey coverage for %s: %s", team_name, exc)
        return _default_hockey_coverage_detail()

    return classify_rich_coverage(
        rows,
        _HOCKEY_POLICY["required_rich_keys"],
        _HOCKEY_ALLOWED_SOURCES,
    )


def _merge_hockey_coverage_into_result(result: dict, detail: dict) -> None:
    result["hockey_rich_keys_found"] = list(detail.get("rich_keys_found", []))
    result["hockey_missing_rich_keys"] = list(detail.get("missing_rich_keys", []))
    result["hockey_rich_complete"] = detail.get("bucket") == "rich"

    bucket = detail.get("bucket", "no_data")
    if bucket == "rich":
        result["status"] = "enriched"
    elif bucket in {"baseline_only", "partial"}:
        result["status"] = "partial"
    else:
        result["status"] = "partial" if result.get("stats_found") else "failed"


def _refresh_hockey_coverage_result(result: dict) -> dict:
    if result.get("sport") != "hockey":
        return result
    detail = _get_hockey_coverage_detail(result["team"])
    _merge_hockey_coverage_into_result(result, detail)
    return result


def _get_volleyball_coverage_detail(team_name: str) -> dict:
    try:
        with get_db() as conn:
            sport_repo = SportRepo(conn)
            team_repo = TeamRepo(conn)
            sport = sport_repo.get_by_name("volleyball")
            if not sport:
                return _default_volleyball_coverage_detail()

            team = team_repo.resolve(team_name, sport.id)
            if not team:
                return _default_volleyball_coverage_detail()

            rows = conn.execute(
                "SELECT stat_key, source FROM team_form WHERE team_id = ? AND sport_id = ?",
                (team.id, sport.id),
            ).fetchall()
    except Exception as exc:
        logger.debug("Failed to inspect volleyball coverage for %s: %s", team_name, exc)
        return _default_volleyball_coverage_detail()

    return classify_rich_coverage(
        rows,
        _VOLLEYBALL_POLICY["required_rich_keys"],
        _VOLLEYBALL_ALLOWED_SOURCES,
    )


def _merge_volleyball_coverage_into_result(result: dict, detail: dict) -> None:
    result["volleyball_rich_keys_found"] = list(detail.get("rich_keys_found", []))
    result["volleyball_missing_rich_keys"] = list(detail.get("missing_rich_keys", []))
    result["volleyball_rich_complete"] = detail.get("bucket") == "rich"

    bucket = detail.get("bucket", "no_data")
    if bucket == "rich":
        result["status"] = "enriched"
    elif bucket in {"baseline_only", "partial"}:
        result["status"] = "partial"
    else:
        result["status"] = "partial" if result.get("stats_found") else "failed"


def _needs_volleyball_rich_completion(result: dict, coverage_detail: dict) -> bool:
    return result.get("sport") == "volleyball" and bool(result.get("volleyball_missing_rich_keys")) and (
        coverage_detail.get("bucket") in {"baseline_only", "partial"} or bool(result.get("stats_found"))
    )


def _apply_volleyball_rich_completion(result: dict, max_fixtures: int = 5) -> dict:
    if result.get("sport") != "volleyball":
        return result

    coverage_before = _get_volleyball_coverage_detail(result["team"])
    _merge_volleyball_coverage_into_result(result, coverage_before)

    completion = result.setdefault(
        "volleyball_completion",
        {
            "needed": False,
            "attempted": False,
            "success": False,
            "source": _VOLLEYBALL_POLICY["canonical_source"],
            "status": "not_needed",
            "fixtures_scanned": 0,
            "matches_persisted": 0,
            "rich_keys_added": [],
            "missing_after": [],
            "error": None,
            "failure_reason": None,
        },
    )

    error_text = (result.get("error") or "").lower()
    if "known missing team" in error_text or "missing team name" in error_text:
        completion.update(
            {
                "needed": False,
                "attempted": False,
                "success": False,
                "status": "skipped",
                "error": result.get("error"),
                "missing_after": result.get("volleyball_missing_rich_keys", []),
            }
        )
        return result

    completion["needed"] = _needs_volleyball_rich_completion(result, coverage_before)
    if not completion["needed"]:
        completion["status"] = "not_needed"
        completion["missing_after"] = result.get("volleyball_missing_rich_keys", [])
        return result

    existing_rich = set(result.get("volleyball_rich_keys_found", []))
    helper_result = complete_volleyball_rich_stats(result["team"], result["sport"], max_fixtures=max_fixtures)
    added_rich = [
        key for key in helper_result.get("rich_keys_found", []) if key not in existing_rich
    ]

    completion.update(
        {
            "needed": True,
            "attempted": True,
            "source": helper_result.get("source", _VOLLEYBALL_POLICY["canonical_source"]),
            "status": helper_result.get("status", "failed"),
            "fixtures_scanned": helper_result.get("fixtures_scanned", 0),
            "matches_persisted": helper_result.get("matches_persisted", 0),
            "rich_keys_added": added_rich,
            "error": helper_result.get("error"),
            "failure_reason": helper_result.get("failure_reason"),
        }
    )

    if helper_result.get("status") in ("enriched", "partial") and helper_result.get("rich_keys_found"):
        for stat_key in helper_result["rich_keys_found"]:
            result.setdefault("stats_found", {})[stat_key] = True
        helper_source = helper_result.get("source", _VOLLEYBALL_POLICY["canonical_source"])
        supplementary_sources = result.setdefault("supplementary_sources", [])
        supplementary_sources[:] = [source for source in supplementary_sources if source != helper_source]
        current_source = result.get("source")
        if current_source and current_source != helper_source and current_source not in supplementary_sources:
            supplementary_sources.append(current_source)
        result["source"] = helper_source
        result["error"] = None
    elif helper_result.get("error"):
        errors = [
            message
            for message in [result.get("error"), f"volleyball-completion: {helper_result['error']}"]
            if message
        ]
        result["error"] = "; ".join(errors[-2:])

    coverage_after = _get_volleyball_coverage_detail(result["team"])
    _merge_volleyball_coverage_into_result(result, coverage_after)
    completion["success"] = bool(added_rich)
    completion["missing_after"] = result.get("volleyball_missing_rich_keys", [])
    return result


def _record_hockey_supplementary_source(result: dict, source_name: str) -> None:
    if result.get("source") == source_name:
        return
    supplementary_sources = result.setdefault("supplementary_sources", [])
    if source_name not in supplementary_sources:
        supplementary_sources.append(source_name)


def _needs_hockey_rich_completion(result: dict, coverage_detail: dict) -> bool:
    return result.get("sport") == "hockey" and bool(result.get("hockey_missing_rich_keys")) and (
        coverage_detail.get("bucket") in {"baseline_only", "partial"} or bool(result.get("stats_found"))
    )


def _apply_hockey_rich_completion(result: dict, max_fixtures: int = 5) -> dict:
    if result.get("sport") != "hockey":
        return result

    coverage_before = _get_hockey_coverage_detail(result["team"])
    _merge_hockey_coverage_into_result(result, coverage_before)

    completion = result.setdefault(
        "hockey_completion",
        {
            "needed": False,
            "attempted": False,
            "success": False,
            "source": _HOCKEY_POLICY["canonical_source"],
            "status": "not_needed",
            "fixtures_scanned": 0,
            "matches_persisted": 0,
            "rich_keys_added": [],
            "missing_after": [],
            "error": None,
            "failure_reason": None,
        },
    )

    error_text = (result.get("error") or "").lower()
    if "known missing team" in error_text or "missing team name" in error_text:
        completion.update(
            {
                "needed": False,
                "attempted": False,
                "success": False,
                "status": "skipped",
                "error": result.get("error"),
                "missing_after": result.get("hockey_missing_rich_keys", []),
            }
        )
        return result

    completion["needed"] = _needs_hockey_rich_completion(result, coverage_before)
    if not completion["needed"]:
        completion["status"] = "not_needed"
        completion["missing_after"] = result.get("hockey_missing_rich_keys", [])
        return result

    existing_rich = set(result.get("hockey_rich_keys_found", []))
    helper_result = complete_hockey_rich_stats(result["team"], result["sport"], max_fixtures=max_fixtures)
    added_rich = [
        key for key in helper_result.get("rich_keys_found", []) if key not in existing_rich
    ]

    completion.update(
        {
            "needed": True,
            "attempted": True,
            "source": helper_result.get("source", _HOCKEY_POLICY["canonical_source"]),
            "status": helper_result.get("status", "failed"),
            "fixtures_scanned": helper_result.get("fixtures_scanned", 0),
            "matches_persisted": helper_result.get("matches_persisted", 0),
            "rich_keys_added": added_rich,
            "error": helper_result.get("error"),
            "failure_reason": helper_result.get("failure_reason"),
        }
    )

    if helper_result.get("status") in ("enriched", "partial") and helper_result.get("rich_keys_found"):
        for stat_key in helper_result["rich_keys_found"]:
            result.setdefault("stats_found", {})[stat_key] = True
        helper_source = helper_result.get("source", _HOCKEY_POLICY["canonical_source"])
        if result.get("source") and result["source"] != helper_source:
            supplementary_sources = result.setdefault("supplementary_sources", [])
            if helper_source not in supplementary_sources:
                supplementary_sources.append(helper_source)
        else:
            result["source"] = helper_source
        result["error"] = None
    elif helper_result.get("error"):
        errors = [
            message
            for message in [result.get("error"), f"hockey-completion: {helper_result['error']}"]
            if message
        ]
        result["error"] = "; ".join(errors[-2:])

    _refresh_hockey_coverage_result(result)
    completion["success"] = bool(added_rich)
    completion["missing_after"] = result.get("hockey_missing_rich_keys", [])
    return result


def _get_tennis_coverage_detail(team_name: str) -> dict:
    try:
        with get_db() as conn:
            sport_repo = SportRepo(conn)
            team_repo = TeamRepo(conn)
            sport = sport_repo.get_by_name("tennis")
            if not sport:
                return _default_tennis_coverage_detail()

            team = team_repo.resolve(team_name, sport.id)
            if not team:
                return _default_tennis_coverage_detail()

            rows = conn.execute(
                "SELECT stat_key, source FROM team_form WHERE team_id = ? AND sport_id = ?",
                (team.id, sport.id),
            ).fetchall()
    except Exception as exc:
        logger.debug("Failed to inspect tennis coverage for %s: %s", team_name, exc)
        return _default_tennis_coverage_detail()

    return classify_rich_coverage(
        rows,
        _TENNIS_POLICY["required_rich_keys"],
        _TENNIS_ALLOWED_SOURCES,
        baseline_sources=_TENNIS_BASELINE_SOURCES,
    )


def _merge_tennis_coverage_into_result(result: dict, detail: dict) -> None:
    for stat_key in detail.get("stat_keys", []):
        result.setdefault("stats_found", {})[stat_key] = True


def _needs_tennis_rich_completion(result: dict, coverage_detail: dict) -> bool:
    return result.get("sport") == "tennis" and bool(result.get("tennis_missing_rich_keys")) and (
        coverage_detail.get("bucket") in {"baseline_only", "partial"} or bool(result.get("stats_found"))
    )


def _apply_tennis_rich_completion(result: dict, max_fixtures: int = 5) -> dict:
    if result.get("sport") != "tennis":
        return result

    coverage_before = _get_tennis_coverage_detail(result["team"])
    _merge_tennis_coverage_into_result(result, coverage_before)
    _set_result_status(result)

    completion = result.setdefault(
        "tennis_completion",
        {
            "needed": False,
            "attempted": False,
            "success": False,
            "source": _TENNIS_POLICY["canonical_source"],
            "status": "not_needed",
            "fixtures_scanned": 0,
            "matches_persisted": 0,
            "rich_keys_added": [],
            "missing_after": [],
            "error": None,
            "failure_reason": None,
            "baseline_only": coverage_before.get("bucket") == "baseline_only",
        },
    )

    error_text = (result.get("error") or "").lower()
    if "known missing team" in error_text or "missing team name" in error_text:
        completion.update(
            {
                "needed": False,
                "attempted": False,
                "success": False,
                "status": "skipped",
                "error": result.get("error"),
                "missing_after": result.get("tennis_missing_rich_keys", []),
                "baseline_only": coverage_before.get("bucket") == "baseline_only",
            }
        )
        return result

    completion["needed"] = _needs_tennis_rich_completion(result, coverage_before)
    if not completion["needed"]:
        completion["status"] = "not_needed"
        completion["missing_after"] = result.get("tennis_missing_rich_keys", [])
        completion["baseline_only"] = coverage_before.get("bucket") == "baseline_only"
        return result

    existing_rich = set(result.get("tennis_rich_keys_found", []))
    helper_result = complete_tennis_rich_stats(result["team"], result["sport"], max_fixtures=max_fixtures)
    added_rich = [
        key for key in helper_result.get("rich_keys_found", []) if key not in existing_rich
    ]

    completion.update(
        {
            "needed": True,
            "attempted": True,
            "source": helper_result.get("source", _TENNIS_POLICY["canonical_source"]),
            "status": helper_result.get("status", "failed"),
            "fixtures_scanned": helper_result.get("fixtures_scanned", 0),
            "matches_persisted": helper_result.get("matches_persisted", 0),
            "rich_keys_added": added_rich,
            "error": helper_result.get("error"),
            "failure_reason": helper_result.get("failure_reason"),
        }
    )

    if helper_result.get("status") in ("enriched", "partial") and helper_result.get("rich_keys_found"):
        for stat_key in helper_result["rich_keys_found"]:
            result.setdefault("stats_found", {})[stat_key] = True
        helper_source = helper_result.get("source", _TENNIS_POLICY["canonical_source"])
        if result.get("source") and result["source"] != helper_source:
            supplementary_sources = result.setdefault("supplementary_sources", [])
            if helper_source not in supplementary_sources:
                supplementary_sources.append(helper_source)
        else:
            result["source"] = helper_source
        result["error"] = None
    elif helper_result.get("error"):
        errors = [
            message
            for message in [result.get("error"), f"tennis-completion: {helper_result['error']}"]
            if message
        ]
        result["error"] = "; ".join(errors[-2:])

    coverage_after = _get_tennis_coverage_detail(result["team"])
    _merge_tennis_coverage_into_result(result, coverage_after)
    completion["success"] = bool(added_rich)
    completion["baseline_only"] = coverage_after.get("bucket") == "baseline_only"
    _set_result_status(result)
    completion["missing_after"] = result.get("tennis_missing_rich_keys", [])
    return result


def _summarize_enrichment_results(results: list[dict], extra_metrics: dict | None = None) -> dict:
    enriched = sum(1 for r in results if r.get("status") == "enriched")
    partial = sum(1 for r in results if r.get("status") == "partial")
    failed = sum(1 for r in results if r.get("status") == "failed")
    football_eligible = sum(
        1 for r in results if r.get("sport") == "football" and r.get("football_completion", {}).get("needed")
    )
    football_completed_via_flashscore_html = sum(
        1 for r in results if r.get("sport") == "football" and r.get("football_completion", {}).get("success")
    )
    football_still_missing_rich = sum(
        1 for r in results if r.get("sport") == "football" and r.get("football_missing_rich_keys")
    )
    basketball_eligible = sum(
        1 for r in results if r.get("sport") == "basketball" and r.get("basketball_completion", {}).get("needed")
    )
    basketball_completed = sum(
        1 for r in results if r.get("sport") == "basketball" and r.get("basketball_completion", {}).get("success")
    )
    basketball_still_missing = sum(
        1 for r in results if r.get("sport") == "basketball" and r.get("basketball_missing_rich_keys")
    )
    hockey_eligible = sum(
        1 for r in results if r.get("sport") == "hockey" and r.get("hockey_completion", {}).get("needed")
    )
    hockey_completed = sum(
        1 for r in results if r.get("sport") == "hockey" and r.get("hockey_completion", {}).get("success")
    )
    hockey_still_missing = sum(
        1 for r in results if r.get("sport") == "hockey" and r.get("hockey_missing_rich_keys")
    )
    volleyball_eligible = sum(
        1 for r in results if r.get("sport") == "volleyball" and r.get("volleyball_completion", {}).get("needed")
    )
    volleyball_completed = sum(
        1 for r in results if r.get("sport") == "volleyball" and r.get("volleyball_completion", {}).get("success")
    )
    volleyball_still_missing = sum(
        1 for r in results if r.get("sport") == "volleyball" and r.get("volleyball_missing_rich_keys")
    )
    tennis_eligible = sum(
        1 for r in results if r.get("sport") == "tennis" and r.get("tennis_completion", {}).get("needed")
    )
    tennis_completed = sum(
        1 for r in results if r.get("sport") == "tennis" and r.get("tennis_completion", {}).get("success")
    )
    tennis_still_missing = sum(
        1 for r in results if r.get("sport") == "tennis" and r.get("tennis_missing_rich_keys")
    )
    tennis_baseline_only = sum(
        1 for r in results if r.get("sport") == "tennis" and r.get("tennis_completion", {}).get("baseline_only")
    )

    metrics = {
        "enriched": enriched,
        "partial": partial,
        "failed": failed,
        "total": len(results),
        "football_rich_eligible": football_eligible,
        "football_completed_via_flashscore_html": football_completed_via_flashscore_html,
        "football_still_missing_rich": football_still_missing_rich,
        "basketball_rich_eligible": basketball_eligible,
        "basketball_completed": basketball_completed,
        "basketball_still_missing_rich": basketball_still_missing,
        "hockey_rich_eligible": hockey_eligible,
        "hockey_completed": hockey_completed,
        "hockey_still_missing_rich": hockey_still_missing,
        "volleyball_rich_eligible": volleyball_eligible,
        "volleyball_completed": volleyball_completed,
        "volleyball_still_missing_rich": volleyball_still_missing,
        "tennis_rich_eligible": tennis_eligible,
        "tennis_completed": tennis_completed,
        "tennis_still_missing_rich": tennis_still_missing,
        "tennis_baseline_only": tennis_baseline_only,
    }
    if extra_metrics:
        metrics.update(extra_metrics)
    return metrics


def _get_competition_for_team(team_name: str, sport: str) -> str:
    """Try to resolve competition name from DB fixtures for better ESPN league matching."""
    try:
        with get_db() as conn:
            sport_repo = SportRepo(conn)
            team_repo = TeamRepo(conn)
            sport_obj = sport_repo.get_by_name(sport)
            if not sport_obj:
                return ""
            team = team_repo.resolve(team_name, sport_obj.id)
            if not team:
                return ""
            row = conn.execute(
                "SELECT c.name FROM fixtures f "
                "JOIN competitions c ON f.competition_id = c.id "
                "WHERE (f.home_team_id = ? OR f.away_team_id = ?) "
                "ORDER BY f.kickoff DESC LIMIT 1",
                (team.id, team.id),
            ).fetchone()
            return row["name"] if row else ""
    except Exception:
        return ""


def _filter_enrichment_targets(
    entries: list[dict],
    *,
    sport_filter: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    filtered = [
        entry
        for entry in entries
        if entry.get("team") and entry.get("sport") and (not sport_filter or entry.get("sport") == sport_filter)
    ]
    if limit is not None:
        return filtered[:limit]
    return filtered


def _get_existing_team_form_rows(team_name: str, sport: str) -> list[tuple[str, str]]:
    try:
        with get_db() as conn:
            sport_repo = SportRepo(conn)
            team_repo = TeamRepo(conn)
            sport_obj = sport_repo.get_by_name(sport)
            if not sport_obj:
                return []
            team = team_repo.resolve(team_name, sport_obj.id)
            if not team:
                return []
            rows = conn.execute(
                "SELECT stat_key, source FROM team_form WHERE team_id = ? AND sport_id = ?",
                (team.id, sport_obj.id),
            ).fetchall()
            return [(str(row[0] or ""), str(row[1] or "")) for row in rows]
    except Exception:
        return []


def _build_dry_run_preview_result(entry: dict) -> dict:
    team_name = entry.get("team", "")
    sport = entry.get("sport", "")
    rows = _get_existing_team_form_rows(team_name, sport)

    result = {
        "team": team_name,
        "sport": sport,
        "status": "failed",
        "stats_found": {stat_key: True for stat_key, _ in rows if stat_key},
        "source": next((source for _, source in rows if source), None),
        "error": None,
    }
    _set_result_status(result)

    if sport == "football":
        result["football_completion"] = {
            "needed": _needs_football_rich_completion(result),
            "attempted": False,
            "success": False,
            "status": "dry_run",
        }
    elif sport == "basketball":
        result["basketball_completion"] = {
            "needed": _needs_basketball_rich_completion(result),
            "attempted": False,
            "success": False,
            "status": "dry_run",
        }
    elif sport == "tennis":
        coverage_detail = _get_tennis_coverage_detail(team_name)
        _merge_tennis_coverage_into_result(result, coverage_detail)
        _set_result_status(result)
        result["tennis_completion"] = {
            "needed": _needs_tennis_rich_completion(result, coverage_detail),
            "attempted": False,
            "success": False,
            "status": "dry_run",
            "baseline_only": coverage_detail.get("bucket") == "baseline_only",
        }
    elif sport == "hockey":
        coverage_detail = classify_rich_coverage(
            rows,
            _HOCKEY_POLICY["required_rich_keys"],
            _HOCKEY_ALLOWED_SOURCES,
        )
        _merge_hockey_coverage_into_result(result, coverage_detail)
        result["hockey_completion"] = {
            "needed": _needs_hockey_rich_completion(result, coverage_detail),
            "attempted": False,
            "success": False,
            "status": "dry_run",
            "source": _HOCKEY_POLICY["canonical_source"],
        }
    elif sport == "volleyball":
        coverage_detail = classify_rich_coverage(
            rows,
            _VOLLEYBALL_POLICY["required_rich_keys"],
            _VOLLEYBALL_ALLOWED_SOURCES,
        )
        _merge_volleyball_coverage_into_result(result, coverage_detail)
        result["volleyball_completion"] = {
            "needed": _needs_volleyball_rich_completion(result, coverage_detail),
            "attempted": False,
            "success": False,
            "status": "dry_run",
            "source": _VOLLEYBALL_POLICY["canonical_source"],
        }

    return result


def _preview_enrichment_results(entries: list[dict]) -> list[dict]:
    return [_build_dry_run_preview_result(entry) for entry in entries]


# ---------------------------------------------------------------------------
# Core enrichment: uses proper API client fallback chains
# ---------------------------------------------------------------------------

def enrich_team(
    team_name: str,
    sport: str,
    max_retries: int = 2,
    skip_known_missing: bool = False,
    allow_football_rich_completion: bool = True,
    allow_basketball_rich_completion: bool = True,
) -> dict:
    """Fetch and save stats for a single team via API client fallback chains.

    Chain order (per sport): baseline provider chain, with Flashscore last resort only where policy still allows it.
    All saving (cache + DB) is handled by fetch_api_stats._store_in_cache().

    Returns: {
        "team": team_name,
        "sport": sport,
        "status": "enriched" | "partial" | "failed",
        "stats_found": {"corners": 8.5, ...},
        "source": "espn-football" | "api-football" | "api-volleyball" | ...,
        "error": None | "description"
    }
    """
    result = {
        "team": team_name,
        "sport": sport,
        "status": "failed",
        "stats_found": {},
        "source": None,
        "error": None,
    }

    stat_keys = SPORT_STAT_KEYS.get(sport, [])
    if not stat_keys:
        result["error"] = f"No stat keys defined for sport: {sport}"
        return result

    # Check known-missing cache (skip when user explicitly provided shortlist)
    if not skip_known_missing and _is_known_missing(team_name, sport):
        result["error"] = f"Known missing team (cached 404): {team_name}"
        logger.debug(f"Skipping known-missing team: {team_name} ({sport})")
        return result

    # Resolve competition for better league matching (especially ESPN football)
    competition = _get_competition_for_team(team_name, sport)

    # Try each API client in the fallback chain
    chain = FALLBACK_CHAINS.get(sport, [])
    errors = []

    for api_name in chain:
        if _source_is_down(api_name):
            logger.debug(f"Skipping {api_name} for {team_name} — circuit-broken")
            continue

        try:
            client = get_client(api_name, rate_limiter=_rate_limiter)
            if not client.is_available():
                logger.debug(f"{api_name} not available (no API key?)")
                continue
        except (ValueError, Exception) as e:
            logger.debug(f"Cannot create client {api_name}: {e}")
            continue

        try:
            matches = fetch_team_stats(
                client, team_name, sport, last_n=10, competition=competition
            )
        except APIRateLimitError:
            logger.info(f"{api_name} rate limited for {team_name}")
            _record_source_failure(api_name)
            errors.append(f"{api_name}: rate limited")
            continue
        except Exception as e:
            logger.debug(f"{api_name} failed for {team_name}: {e}")
            _record_source_failure(api_name)
            errors.append(f"{api_name}: {e}")
            continue

        if not matches:
            errors.append(f"{api_name}: no matches found")
            continue

        # Check if we actually got stats (not just fixture metadata)
        matches_with_stats = [m for m in matches if getattr(m, "stats", {})]
        if not matches_with_stats:
            errors.append(f"{api_name}: matches found but 0 stat keys")
            continue

        # SUCCESS — save to cache + DB via established infrastructure
        _record_source_success(api_name)
        _store_in_cache(sport, team_name, matches, api_name)

        # Compute what we got
        all_stat_keys = set()
        for m in matches_with_stats:
            all_stat_keys.update(m.stats.keys())

        result["source"] = api_name
        result["stats_found"] = {k: True for k in all_stat_keys}
        _set_result_status(result)

        logger.info(
            f"[{api_name}] Enriched {team_name} ({sport}): "
            f"{len(matches_with_stats)} matches, {len(all_stat_keys)} stat keys"
        )
        break  # Don't return yet — let supplementary enrichment run for hockey

    if sport == "tennis":
        result = _apply_tennis_rich_completion(result)
    elif sport == "football" and allow_football_rich_completion:
        result = _apply_football_rich_completion(result)
    elif sport == "basketball" and allow_basketball_rich_completion:
        result = _apply_basketball_rich_completion(
            result,
            allow_basketball_rich_completion=allow_basketball_rich_completion,
        )
    elif sport == "hockey":
        result = _apply_hockey_rich_completion(result)
    elif sport == "volleyball":
        result = _apply_volleyball_rich_completion(result)
    elif result["stats_found"]:
        _set_result_status(result)

    # Supplementary: MoneyPuck season aggregates for hockey (adds Corsi/Fenwick/xG)
    if sport == "hockey" and result["status"] != "enriched":
        try:
            from bet.api_clients.moneypuck_client import get_team_stats as mp_get_team_stats
            mp_stats = mp_get_team_stats(team_name)
            if mp_stats and mp_stats.get("stats"):
                _save_supplementary_stats(team_name, sport, mp_stats["stats"], "moneypuck")
                _record_hockey_supplementary_source(result, "moneypuck")
                if not result["stats_found"]:
                    result["stats_found"] = mp_stats["stats"]
                else:
                    result["stats_found"].update(mp_stats["stats"])
                _refresh_hockey_coverage_result(result)
                logger.info(f"[moneypuck] Supplemented {team_name}: {len(mp_stats['stats'])} advanced stat keys")
        except Exception as e:
            logger.debug(f"[moneypuck] supplement failed for {team_name}: {e}")

    # Supplementary: ScraperNHL advanced stats for hockey (Corsi/Fenwick/on-ice)
    if sport == "hockey" and result["status"] != "enriched":
        try:
            from bet.api_clients.scrapernhl_wrapper import ScraperNHLClient
            nhl_client = ScraperNHLClient()
            nhl_stats = nhl_client.get_team_advanced_stats(team_name)
            if nhl_stats:
                _save_supplementary_stats(team_name, sport, nhl_stats, "scrapernhl")
                _record_hockey_supplementary_source(result, "scrapernhl")
                if not result["stats_found"]:
                    result["stats_found"] = nhl_stats
                else:
                    result["stats_found"].update(nhl_stats)
                _refresh_hockey_coverage_result(result)
                logger.info(f"[scrapernhl] Supplemented {team_name}: {len(nhl_stats)} advanced stat keys")
        except Exception as e:
            logger.debug(f"[scrapernhl] supplement failed for {team_name}: {e}")

    # If main chain already succeeded, return now (supplementary is done)
    if result["status"] in ("enriched", "partial") and result["source"]:
        return result

    # Last resort: Flashscore via curl_cffi (entity resolution + results page)
    if sport != "volleyball" and not _source_is_down("flashscore.com"):
        for attempt in range(1, max_retries + 1):
            stats, err = _try_flashscore(team_name, sport)
            if stats:
                _record_source_success("flashscore.com")
                result["source"] = "flashscore"
                found_keys = set(stats.keys())
                expected_keys = set(stat_keys)
                if found_keys >= expected_keys:
                    result["status"] = "enriched"
                elif found_keys:
                    result["status"] = "partial"
                else:
                    continue

                flashscore_stats = {k: _safe_avg(v) for k, v in stats.items() if v}
                # Merge flashscore into existing stats (don't overwrite supplementary data)
                if result["stats_found"]:
                    result["stats_found"].update(flashscore_stats)
                else:
                    result["stats_found"] = flashscore_stats
                _save_flashscore_to_db(team_name, sport, stats)
                if sport == "hockey":
                    _refresh_hockey_coverage_result(result)
                else:
                    _set_result_status(result)
                if (
                    sport == "football"
                    and allow_football_rich_completion
                    and not result.get("football_completion", {}).get("attempted")
                ):
                    result = _apply_football_rich_completion(result)
                elif sport == "basketball" and allow_basketball_rich_completion:
                    result = _apply_basketball_rich_completion(
                        result,
                        allow_basketball_rich_completion=allow_basketball_rich_completion,
                    )
                elif sport == "tennis":
                    result = _apply_tennis_rich_completion(result)
                elif sport == "hockey":
                    result = _apply_hockey_rich_completion(result)
                elif sport == "volleyball":
                    result = _apply_volleyball_rich_completion(result)
                logger.info(f"[flashscore] Enriched {team_name} ({sport}): {len(stats)} stat keys")
                return result

            if err:
                errors.append(f"flashscore: {err}")
                # Only network failures trip circuit breaker
                if any(x in err.lower() for x in ("blocked", "403", "429", "timeout")):
                    _record_source_failure("flashscore.com")

    # All sources failed
    result["error"] = "; ".join(errors[-3:]) if errors else "No data from any source"
    _mark_missing(team_name, sport)
    return result


def _save_supplementary_stats(team_name: str, sport: str, stats: dict, source: str) -> None:
    """Save supplementary stats (MoneyPuck, scrapernhl) to DB via team_form."""
    with _db_write_lock:
        try:
            with get_db() as conn:
                sport_repo = SportRepo(conn)
                team_repo = TeamRepo(conn)
                stats_repo = StatsRepo(conn)

                sport_obj = sport_repo.get_by_name(sport)
                if not sport_obj:
                    return

                team = team_repo.find_or_create(team_name, sport_obj.id)
                now_iso = _now_iso()

                for stat_key, value in stats.items():
                    if not isinstance(value, (int, float)):
                        continue
                    val = float(value)
                    if math.isnan(val) or math.isinf(val):
                        continue
                    # Season aggregates → single-value arrays
                    form = TeamForm(
                        id=None,
                        team_id=team.id,
                        sport_id=sport_obj.id,
                        stat_key=stat_key,
                        l10_values=[val],
                        l5_values=[val],
                        l10_avg=val,
                        l5_avg=val,
                        h2h_values=[],
                        h2h_opponent_id=None,
                        trend="stable",
                        updated_at=now_iso,
                        source=source,
                    )
                    stats_repo.save_team_form(form)
                conn.commit()
        except Exception as e:
            logger.debug(f"Failed to save {source} stats for {team_name}: {e}")

def _save_flashscore_to_db(team_name: str, sport: str, stats: dict) -> None:
    """Save Flashscore raw stat arrays to DB (fallback path only)."""
    with _db_write_lock:
        try:
            with get_db() as conn:
                sport_repo = SportRepo(conn)
                team_repo = TeamRepo(conn)
                stats_repo = StatsRepo(conn)

                sport_obj = sport_repo.get_by_name(sport)
                if not sport_obj:
                    return

                team = team_repo.find_or_create(team_name, sport_obj.id)

                for stat_key, values in stats.items():
                    # Range validation
                    ranges = SPORT_VALUE_RANGES.get(sport, {})
                    bounds = ranges.get(stat_key)
                    if bounds:
                        lo, hi = bounds
                        values = [v for v in values if lo <= v <= hi]
                        if not values:
                            continue

                    l10 = values[:10]
                    l5 = values[:5] if len(values) >= 5 else values
                    l10_avg = _safe_avg(l10)
                    l5_avg = _safe_avg(l5)

                    # Trend
                    trend = "stable"
                    if l10_avg and l5_avg:
                        diff = l5_avg - l10_avg
                        if abs(diff) >= 0.3:
                            trend = "rising" if diff > 0 else "falling"

                    form = TeamForm(
                        id=None,
                        team_id=team.id,
                        sport_id=sport_obj.id,
                        stat_key=stat_key,
                        l10_values=l10,
                        l5_values=l5,
                        l10_avg=l10_avg,
                        l5_avg=l5_avg,
                        h2h_values=[],
                        h2h_opponent_id=None,
                        trend=trend,
                        updated_at=_now_iso(),
                        source="flashscore",
                    )
                    stats_repo.save_team_form(form)

                conn.commit()
                logger.info("Saved Flashscore stats to DB: %s (%s)", team_name, sport)
        except Exception as exc:
            logger.error("Flashscore DB save failed for %s: %s", team_name, exc)


# ---------------------------------------------------------------------------
# H2H enrichment
# ---------------------------------------------------------------------------

def enrich_h2h(team_a: str, team_b: str, sport: str) -> dict:
    """Fetch H2H stats between two teams via API client fallback chains.

    Returns: {
        "team_a": ..., "team_b": ...,
        "status": "enriched" | "failed",
        "meetings_found": 5,
        "source": "espn-football",
        "error": None | "description"
    }
    """
    result = {
        "team_a": team_a,
        "team_b": team_b,
        "sport": sport,
        "status": "failed",
        "meetings_found": 0,
        "source": None,
        "error": None,
    }

    competition = _get_competition_for_team(team_a, sport)
    chain = FALLBACK_CHAINS.get(sport, [])

    for api_name in chain:
        if _source_is_down(api_name):
            continue

        try:
            client = get_client(api_name, rate_limiter=_rate_limiter)
            if not client.is_available():
                continue
        except Exception:
            continue

        try:
            h2h_matches = fetch_h2h_stats(
                client, team_a, team_b, sport, last_n=10, competition=competition
            )
        except Exception as e:
            logger.debug(f"{api_name} H2H failed: {e}")
            continue

        if not h2h_matches:
            continue

        # Save H2H data
        _record_source_success(api_name)
        _store_in_cache(sport, team_a, [], api_name, opponent=team_b, h2h_matches=h2h_matches)

        result["status"] = "enriched"
        result["meetings_found"] = len(h2h_matches)
        result["source"] = api_name
        logger.info(f"[{api_name}] H2H {team_a} vs {team_b}: {len(h2h_matches)} meetings")
        return result

    # Flashscore H2H fallback
    try:
        entity_type_a, slug_a, id_a = _get_flashscore_entity(team_a, sport)
        entity_type_b, slug_b, id_b = _get_flashscore_entity(team_b, sport)

        if slug_a and id_a and slug_b and id_b:
            import curl_cffi.requests as _cffi_req
            from flashscore_enricher import _FS_HEADERS, _FS_IMPERSONATE

            url_a = f"https://www.flashscore.com/{entity_type_a}/{slug_a}/{id_a}/results/"
            time.sleep(1.5)
            resp = _cffi_req.get(url_a, impersonate=_FS_IMPERSONATE, headers=_FS_HEADERS, timeout=15)
            if resp.status_code == 200 and len(resp.text) > 500:
                from flashscore_enricher import _parse_flashscore_stats
                stats = _parse_flashscore_stats(resp.text, sport)
                if stats:
                    _save_h2h_to_db(team_a, team_b, sport, stats)
                    result["status"] = "enriched"
                    result["source"] = "flashscore"
                    result["meetings_found"] = max(len(v) for v in stats.values()) if stats else 0
                    return result
    except Exception as e:
        logger.debug(f"Flashscore H2H fallback failed: {e}")

    result["error"] = "No H2H data from any source"
    return result


def _save_h2h_to_db(team_a: str, team_b: str, sport: str, stats: dict) -> None:
    """Save H2H stats to DB."""
    with _db_write_lock:
        try:
            with get_db() as conn:
                sport_repo = SportRepo(conn)
                team_repo = TeamRepo(conn)
                stats_repo = StatsRepo(conn)

                sport_obj = sport_repo.get_by_name(sport)
                if not sport_obj:
                    return

                t_a = team_repo.find_or_create(team_a, sport_obj.id)
                t_b = team_repo.find_or_create(team_b, sport_obj.id)

                for stat_key, values in stats.items():
                    form = TeamForm(
                        id=None,
                        team_id=t_a.id,
                        sport_id=sport_obj.id,
                        stat_key=stat_key,
                        l10_values=[],
                        l5_values=[],
                        l10_avg=None,
                        l5_avg=None,
                        h2h_values=values[:10],
                        h2h_opponent_id=t_b.id,
                        trend="stable",
                        updated_at=_now_iso(),
                        source="flashscore-h2h",
                    )
                    stats_repo.save_team_form(form)

                conn.commit()
                logger.info("Saved H2H to DB: %s vs %s (%s)", team_a, team_b, sport)
        except Exception as exc:
            logger.error("H2H DB save failed: %s", exc)


# ---------------------------------------------------------------------------
# Batch enrichment
# ---------------------------------------------------------------------------

def batch_enrich(
    teams: list[dict],
    max_workers: int = 4,
    skip_known_missing: bool = False,
    allow_basketball_rich_completion: bool = True,
) -> list[dict]:
    """Enrich multiple teams in parallel.

    Input: [{"team": "FC Barcelona", "sport": "football"}]
    Returns: list of enrich_team results
    """
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for entry in teams:
            team_name = entry.get("team", "")
            sport = entry.get("sport", "")
            if not team_name or not sport:
                results.append({
                    "team": team_name, "sport": sport,
                    "status": "failed", "stats_found": {},
                    "source": None, "error": "Missing team name or sport",
                })
                continue
            fut = executor.submit(
                enrich_team,
                team_name,
                sport,
                skip_known_missing=skip_known_missing,
                allow_football_rich_completion=False if sport == "football" else True,
                allow_basketball_rich_completion=allow_basketball_rich_completion,
            )
            futures[fut] = entry

        for fut in concurrent.futures.as_completed(futures):
            try:
                res = fut.result()
                if res.get("sport") == "football":
                    res = _apply_football_rich_completion(res)
                results.append(res)
            except Exception as exc:
                entry = futures[fut]
                results.append({
                    "team": entry.get("team", ""), "sport": entry.get("sport", ""),
                    "status": "failed", "stats_found": {},
                    "source": None, "error": str(exc),
                })

    return results


# ---------------------------------------------------------------------------
# Auto-detect missing teams from shortlist / DB fixtures
# ---------------------------------------------------------------------------

def _detect_missing_from_shortlist(date_str: str, shortlist_override: str | None = None) -> list[dict]:
    """Scan shortlist for candidates with missing stats cache.
    
    When shortlist_override is provided, reads ONLY from that file (targeted enrichment).
    Uses cache-file-only check when shortlist_override is used (bypasses stale DB data).
    Otherwise falls back to DB fixtures (broad enrichment — legacy behavior).
    """
    # If explicit shortlist provided, use it directly — do NOT load all fixtures from DB
    force_cache_check = False  # When True, skip DB team_form check and use cache files only
    shortlist_path = None
    if shortlist_override:
        shortlist_path = Path(shortlist_override)
        if shortlist_path.exists():
            force_cache_check = True  # Explicit shortlist = always use fresh cache check
            logger.info(f"[shortlist] Using explicit shortlist: {shortlist_path}")
        else:
            logger.warning(f"[shortlist] Override not found: {shortlist_path}, falling back to DB")
            shortlist_path = None

    if shortlist_path is None:
        # DB-first: load fixtures from DB (R2) — broad mode
        teams_from_db = []
        try:
            from db_data_loader import load_fixtures_from_db
            fixtures = load_fixtures_from_db(date_str)
            if fixtures:
                seen = set()
                for f in fixtures:
                    for team_key in ("home_team", "away_team"):
                        team_name = f.get(team_key, "")
                        sport = f.get("sport", "")
                        if team_name and sport and (team_name, sport) not in seen:
                            seen.add((team_name, sport))
                            teams_from_db.append({"team": team_name, "sport": sport})
                if teams_from_db:
                    logger.info(f"[DB] Loaded {len(teams_from_db)} teams from {len(fixtures)} fixtures")
        except Exception as exc:
            logger.debug(f"DB fixture load failed: {exc}")

        if teams_from_db:
            # Filter to teams missing stats (check DB team_form first, cache file as fallback)
            missing = []
            try:
                with get_db() as conn:
                    for entry in teams_from_db:
                        team_name = entry["team"]
                        sport = entry["sport"]
                        # Check DB team_form for existing stats
                        sport_row = conn.execute(
                            "SELECT id FROM sports WHERE name = ?", (sport,)
                        ).fetchone()
                        if not sport_row:
                            missing.append(entry)
                            continue
                        team_row = conn.execute(
                            "SELECT id FROM teams WHERE sport_id = ? AND (name = ? OR aliases LIKE ?)",
                            (sport_row["id"], team_name, f'%{team_name}%'),
                        ).fetchone()
                        if not team_row:
                            missing.append(entry)
                            continue
                        # Check if team has at least 2 stat keys in team_form
                        form_count = conn.execute(
                            "SELECT COUNT(DISTINCT stat_key) as cnt FROM team_form "
                            "WHERE team_id = ? AND sport_id = ?",
                            (team_row["id"], sport_row["id"]),
                        ).fetchone()
                        if not form_count or form_count["cnt"] < 2:
                            missing.append(entry)
            except Exception as exc:
                logger.debug(f"DB team_form check failed, falling back to cache: {exc}")
                # Fallback: check cache file existence
                missing = []
                for entry in teams_from_db:
                    slug = _slugify(entry["team"])
                    cache_path = CACHE_DIR / entry["sport"] / f"{slug}.json"
                    if not cache_path.exists():
                        missing.append(entry)

            logger.info(f"[DB] {len(missing)}/{len(teams_from_db)} teams need enrichment")
            return missing

        # JSON fallback — try standard shortlist path
        shortlist_path = DATA_DIR / f"{date_str}_s2_shortlist.json"
    if not shortlist_path.exists():
        shortlist_path = DATA_DIR / f"{date_str.replace('-', '')}_s2_shortlist.json"
    if not shortlist_path.exists():
        logger.warning("Shortlist not found: %s", shortlist_path)
        return []

    try:
        data = json.loads(shortlist_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to read shortlist: %s", exc)
        return []

    candidates = data.get("candidates", [])
    missing = []

    for c in candidates:
        sport = c.get("sport", "")
        if not SPORT_STAT_KEYS.get(sport):
            continue
        for team_field in ("home_team", "away_team", "home", "away", "team_a", "team_b"):
            team_name = c.get(team_field, "")
            if not team_name:
                continue
            missing.append({"team": team_name, "sport": sport})

    # Deduplicate
    seen = set()
    deduped = []
    for entry in missing:
        key = (entry["team"], entry["sport"])
        if key not in seen:
            seen.add(key)
            deduped.append(entry)

    # Filter to teams actually missing stats (DB-first, cache fallback)
    truly_missing = []
    if force_cache_check:
        # Explicit shortlist mode: use cache file existence only (avoids stale DB data)
        for entry in deduped:
            slug = _slugify(entry["team"])
            cache_path = CACHE_DIR / entry["sport"] / f"{slug}.json"
            if not cache_path.exists():
                truly_missing.append(entry)
    else:
        try:
            with get_db() as conn:
                for entry in deduped:
                    team_name = entry["team"]
                    sport = entry["sport"]
                    sport_row = conn.execute(
                        "SELECT id FROM sports WHERE name = ?", (sport,)
                    ).fetchone()
                    if not sport_row:
                        truly_missing.append(entry)
                        continue
                    team_row = conn.execute(
                        "SELECT id FROM teams WHERE sport_id = ? AND (name = ? OR aliases LIKE ?)",
                        (sport_row["id"], team_name, f'%{team_name}%'),
                    ).fetchone()
                    if not team_row:
                        truly_missing.append(entry)
                        continue
                    form_count = conn.execute(
                        "SELECT COUNT(DISTINCT stat_key) as cnt FROM team_form "
                        "WHERE team_id = ? AND sport_id = ?",
                        (team_row["id"], sport_row["id"]),
                    ).fetchone()
                    if not form_count or form_count["cnt"] < 2:
                        truly_missing.append(entry)
        except Exception as exc:
            logger.debug(f"DB check failed, using cache fallback: {exc}")
            truly_missing = []
            for entry in deduped:
                slug = _slugify(entry["team"])
                cache_path = CACHE_DIR / entry["sport"] / f"{slug}.json"
                if not cache_path.exists():
                    truly_missing.append(entry)

    return truly_missing


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    from agent_output import AgentOutput

    parser = argparse.ArgumentParser(description="Self-healing data enrichment agent")
    parser.add_argument("--team", help="Single team name to enrich")
    parser.add_argument("--sport", help="Sport for --team mode")
    parser.add_argument("--batch", help="Path to JSON file with teams to enrich")
    parser.add_argument("--date", help="Auto-detect missing teams from shortlist (YYYY-MM-DD)")
    parser.add_argument("--h2h", nargs=2, metavar=("TEAM_A", "TEAM_B"), help="Fetch H2H stats")
    parser.add_argument("--workers", type=int, default=4, help="Max parallel workers")
    parser.add_argument("--limit", type=int, help="Limit teams processed in --date mode after optional sport filtering")
    parser.add_argument("--dry-run", action="store_true", help="Inspect filtered enrichment targets and emit AGENT_SUMMARY without writing data")
    parser.add_argument("--news", action="store_true", default=False,
                        help="Run Gemini news enrichment after stats enrichment")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    parser.add_argument("--stop-on-error", action="store_true", help="Stop on first critical error")
    parser.add_argument("--all", action="store_true",
                        help="Enrich ALL teams in DB (not just shortlist). Default: shortlist only.")
    parser.add_argument("--shortlist", help="Explicit shortlist JSON path to use for --date mode")
    args = parser.parse_args()

    out = AgentOutput("s2_enrich", verbose=args.verbose, stop_on_error=args.stop_on_error)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if args.team:
        if not args.sport:
            out.error("--sport required with --team", recoverable=False)
            out.summary(verdict="FAILED", metrics={"error": "--sport required with --team"})
            sys.exit(1)
        result = enrich_team(args.team, args.sport)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        out.summary(
            verdict="OK" if result.get("status") == "enriched" else "PARTIAL",
            metrics={"team": args.team, "sport": args.sport, "status": result.get("status", "?")},
        )

    elif args.h2h:
        if not args.sport:
            out.error("--sport required with --h2h", recoverable=False)
            out.summary(verdict="FAILED", metrics={"error": "--sport required with --h2h"})
            sys.exit(1)
        result = enrich_h2h(args.h2h[0], args.h2h[1], args.sport)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        out.summary(verdict="OK", metrics={"h2h": f"{args.h2h[0]} vs {args.h2h[1]}", "sport": args.sport})

    elif args.batch:
        batch_path = Path(args.batch)
        if not batch_path.exists():
            out.error(f"Batch file not found: {batch_path}", recoverable=False)
            out.summary(verdict="FAILED", metrics={"error": f"Batch file not found: {batch_path}"})
            sys.exit(1)
        try:
            teams = json.loads(batch_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            out.error(f"Failed to read batch file: {exc}", recoverable=False)
            out.summary(verdict="FAILED", metrics={"error": str(exc)})
            sys.exit(1)
        results = batch_enrich(teams, max_workers=args.workers)
        print(json.dumps(results, indent=2, ensure_ascii=False))
        summary_metrics = _summarize_enrichment_results(results)
        out.summary(
            verdict="OK" if summary_metrics["enriched"] > 0 else "PARTIAL",
            metrics=summary_metrics,
        )

    elif args.date:
        # Input contract pre-check
        _contract = AgentOutput.validate_input_contract("s2_5_enrich", args.date)
        if _contract["status"] != "OK":
            for _w in _contract.get("warnings", []):
                out.warning(f"Input contract: {_w}")
            for _m in _contract.get("missing", []):
                out.warning(f"Missing input: {_m}")

        if args.all:
            # --all: Enrich ALL teams from DB (not just shortlist)
            out.info("Mode: --all (enriching ALL teams in DB, not just shortlist)")
            try:
                from bet.db.connection import get_db
                with get_db() as db:
                    rows = db.execute(
                        "SELECT t.name, s.name as sport FROM teams t "
                        "JOIN sports s ON t.sport_id = s.id"
                    ).fetchall()
                    missing = [{"team": r["name"], "sport": r["sport"]} for r in rows]
                    out.info(f"Found {len(missing)} total teams in DB")
            except Exception as e:
                out.error(f"Failed to load all teams: {e}", recoverable=False)
                out.summary(verdict="FAILED", metrics={"error": str(e)})
                sys.exit(1)
        else:
            # Default: shortlist-only enrichment (fast, targeted)
            missing = _detect_missing_from_shortlist(args.date, shortlist_override=args.shortlist)
        missing = _filter_enrichment_targets(missing, sport_filter=args.sport, limit=args.limit)
        if not missing:
            out.summary(verdict="OK", metrics={"missing": 0, "message": f"No missing teams for {args.date}"})
            sys.exit(0)

        if args.verbose:
            out.event("missing_detected", count=len(missing))
        else:
            print(f"Found {len(missing)} teams with missing stats", file=sys.stderr)

        if args.dry_run:
            results = _preview_enrichment_results(missing)
            print(json.dumps(results, indent=2, ensure_ascii=False))
            summary_metrics = _summarize_enrichment_results(
                results,
                extra_metrics={
                    "dry_run_mode": 1,
                    "dry_run_candidates": len(results),
                },
            )
            out.summary(verdict="OK", metrics=summary_metrics)
            sys.exit(0)

        results = batch_enrich(missing, max_workers=args.workers, skip_known_missing=bool(args.shortlist))
        print(json.dumps(results, indent=2, ensure_ascii=False))

        # Gemini news enrichment (feature flag --news)
        news_count = 0
        if args.news:
            try:
                from gemini_news_enrichment import batch_enrich_news, save_news_to_db
                shortlist_path = DATA_DIR / f"{args.date}_s2_shortlist.json"
                if shortlist_path.exists():
                    sl = json.loads(shortlist_path.read_text(encoding="utf-8"))
                    news_candidates = []
                    seen = set()
                    for c in (sl.get("candidates", sl) if isinstance(sl, dict) else sl):
                        for team_key in ["home_team", "away_team"]:
                            team = c.get(team_key, "")
                            sport = c.get("sport", "football")
                            key = f"{sport}|{team}"
                            if team and key not in seen:
                                seen.add(key)
                                news_candidates.append({"team": team, "sport": sport})
                    if news_candidates:
                        print(f"[enrich] Gemini news enrichment for {len(news_candidates)} teams...")
                        news_results = batch_enrich_news(news_candidates, args.date, max_workers=3)
                        news_count = save_news_to_db(news_results, args.date)
                        print(f"[enrich] Gemini news: {news_count} teams saved to team_news table")
                else:
                    print("[enrich] Shortlist not found — skipping news enrichment")
            except ImportError:
                print("[enrich] gemini_news_enrichment not available — skipping")
            except Exception as e:
                print(f"[enrich] Gemini news enrichment failed (non-fatal): {e}")

        summary_metrics = _summarize_enrichment_results(results, extra_metrics={"news_enriched": news_count})
        out.summary(
            verdict="OK" if summary_metrics["enriched"] > 0 else "PARTIAL",
            metrics=summary_metrics,
        )

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
