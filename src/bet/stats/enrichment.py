# ruff: noqa: E501, I001, W291, W293

"""Incremental stat enrichment — fetch team stats only when stale/missing.

API clients first, scraping fallback. Updates team_form table with
computed L10/L5 averages and trend.

For football: reads from fixture-scoped projections when available,
falls back to global team_form cache only for non-football sports.
"""

import hashlib
import json
import logging
from datetime import UTC, datetime

from bet.api_clients.base_client import SourceOperationResult, SourceResultStatus
from bet.api_clients.espn import (
    ESPN_PARSER_VERSION,
    get_espn_league_for_competition,
)
from bet.db.observation_models import create_observation, create_projection
from bet.db.models import Fixture, TeamForm
from bet.db.repositories import (
    FixtureCapabilityRepo,
    SourceHealthRepo,
    SportRepo,
    StatsRepo,
    TeamRepo,
    TeamSourceAliasRepo,
)
from bet.enrichment.capability_router import (
    Capability,
    CapabilityResolution,
    create_observation_from_result,
    should_fallback,
)
from bet.integration.evidence import canonical_json_bytes, namespaced_source_refs, write_bundle_manifest
from bet.stats.market_ranking import SPORT_STAT_KEYS

logger = logging.getLogger(__name__)


def get_fixture_scoped_form_snapshot(
    db_conn,
    canonical_fixture_id: int,
    team_id: int,
    analysis_cutoff_at: str,
    stat_key: str,
) -> dict | None:
    """Read fixture-scoped form snapshot for downstream analysis.
    
    Returns None if no projection exists (caller should fall back to global team_form).
    Returns dict with:
    - l10_values: list[float] or None
    - l5_values: list[float] or None
    - l10_avg: float or None
    - l5_avg: float or None
    - trend: str
    - source: str
    - status: str
    - evidence_bundle_id: str
    - observation_id: int or None
    - native_ids: dict
    - staleness: bool (always False for projections)
    - primary_source: str
    - primary_status: str
    - fallback_reason: str
    
    This function reads from fixture_capability_projection, NOT from team_form.
    The global team_form table remains a latest cache only.
    """
    repo = FixtureCapabilityRepo(db_conn)
    
    # Map stat_key to capability
    capability = Capability.CURRENT_RECENT_FORM
    
    snapshot = repo.get_snapshot_for_analysis(
        canonical_fixture_id=canonical_fixture_id,
        team_id=team_id,
        capability=capability.value,
        analysis_cutoff_at=analysis_cutoff_at,
    )
    
    if snapshot["status"] == "NOT_FOUND":
        return None

    payload = snapshot.get("payload") or {}
    stat_payload = ((payload.get("stats") or {}).get(stat_key)) if isinstance(payload, dict) else None
    if not isinstance(stat_payload, dict):
        return {
            **snapshot,
            "stat_key": stat_key,
            "value": "UNKNOWN",
            "l10_values": None,
            "l5_values": None,
            "l10_avg": None,
            "l5_avg": None,
            "trend": "UNKNOWN",
        }

    return {
        **snapshot,
        "stat_key": stat_key,
        "value": stat_payload,
        "l10_values": stat_payload.get("l10_values"),
        "l5_values": stat_payload.get("l5_values"),
        "l10_avg": stat_payload.get("l10_avg"),
        "l5_avg": stat_payload.get("l5_avg"),
        "trend": stat_payload.get("trend", "UNKNOWN"),
    }


def _payload_sha256(payload: dict | list | None) -> str:
    if payload is None:
        return ""
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _persist_capability_result(
    *,
    db_conn,
    canonical_fixture_id: int,
    team_id: int,
    capability: Capability,
    analysis_cutoff_at: str,
    source: str,
    result: SourceOperationResult,
    normalized_value: dict | None,
    native_ids: dict[str, str] | None,
    parser_version: str,
) -> int:
    request_identity = ""
    if result.evidence_refs:
        request_identity = str(getattr(result.evidence_refs[0], "request_identity", "") or "")
    if not request_identity:
        request_identity = f"{source}:{capability.value}:{canonical_fixture_id}:{team_id}:{analysis_cutoff_at}"
    obs = create_observation(
        canonical_fixture_id=canonical_fixture_id,
        team_id=team_id,
        capability=capability.value,
        source=source,
        request_identity=request_identity,
        status=result.status.value,
        valid_at=analysis_cutoff_at,
        evidence_bundle_id=result.bundle_id or "",
        native_fixture_id=(native_ids or {}).get("fixture_id", ""),
        native_team_id=(native_ids or {}).get("team_id", ""),
        http_status=result.http_status,
        error_code=result.error_code,
        retryable=result.retryable,
        parser_version=parser_version,
        parser_diagnostics=result.parser_diagnostics,
        payload_sha256=_payload_sha256(normalized_value),
        payload_json=json.dumps(normalized_value, sort_keys=True) if normalized_value is not None else "",
    )
    repo = FixtureCapabilityRepo(db_conn)
    return repo.save_observation(obs)


def _resolve_football_recent_form(
    *,
    team,
    stat_keys: list[str],
    db_conn,
    fixture_context: dict,
) -> CapabilityResolution:
    fixture_id = int(fixture_context["fixture_id"])
    analysis_cutoff_at = str(fixture_context["kickoff"])
    repo = FixtureCapabilityRepo(db_conn)
    existing = repo.get_snapshot_for_analysis(
        canonical_fixture_id=fixture_id,
        team_id=team.id,
        capability=Capability.CURRENT_RECENT_FORM.value,
        analysis_cutoff_at=analysis_cutoff_at,
    )
    resolution = CapabilityResolution(
        capability=Capability.CURRENT_RECENT_FORM,
        canonical_fixture_id=fixture_id,
        team_id=team.id,
        analysis_cutoff_at=analysis_cutoff_at,
    )
    if existing["status"] == SourceResultStatus.SUCCESS.value and existing.get("payload"):
        resolution.select_result(
            source=existing["source"],
            status=SourceResultStatus.SUCCESS,
            value=existing["payload"],
            bundle_id=existing["evidence_bundle_id"],
        )
        return resolution

    primary = _try_espn_fetch(
        team,
        "football",
        stat_keys,
        db_conn,
        fixture_contexts=[fixture_context],
    )
    primary_payload = primary.value.get("payload") if isinstance(primary.value, dict) else None
    primary_ids = primary.value.get("native_ids") if isinstance(primary.value, dict) else None
    resolution.add_observation(
        create_observation_from_result(
            "espn-football",
            primary,
            native_ids=primary_ids,
            parser_version=ESPN_PARSER_VERSION,
        )
    )
    primary_observation_id = _persist_capability_result(
        db_conn=db_conn,
        canonical_fixture_id=fixture_id,
        team_id=team.id,
        capability=Capability.CURRENT_RECENT_FORM,
        analysis_cutoff_at=analysis_cutoff_at,
        source="espn-football",
        result=primary,
        normalized_value=primary_payload,
        native_ids=primary_ids,
        parser_version=ESPN_PARSER_VERSION,
    )
    selected_source = "espn-football"
    selected_status = primary.status
    selected_payload = primary_payload
    selected_bundle_id = primary.bundle_id or ""
    selected_observation_id = primary_observation_id
    fallback_reason = ""

    if should_fallback(Capability.CURRENT_RECENT_FORM, primary.status):
        fallback = _try_api_sports_fetch(
            team,
            "football",
            stat_keys,
            db_conn,
            fixture_contexts=[fixture_context],
        )
        fallback_payload = fallback.value.get("payload") if isinstance(fallback.value, dict) else None
        fallback_ids = fallback.value.get("native_ids") if isinstance(fallback.value, dict) else None
        resolution.add_observation(
            create_observation_from_result(
                "api-football",
                fallback,
                native_ids=fallback_ids,
                parser_version="api-football-team-form-v1",
            )
        )
        fallback_observation_id = _persist_capability_result(
            db_conn=db_conn,
            canonical_fixture_id=fixture_id,
            team_id=team.id,
            capability=Capability.CURRENT_RECENT_FORM,
            analysis_cutoff_at=analysis_cutoff_at,
            source="api-football",
            result=fallback,
            normalized_value=fallback_payload,
            native_ids=fallback_ids,
            parser_version="api-football-team-form-v1",
        )
        if fallback.status is SourceResultStatus.SUCCESS and fallback_payload:
            selected_source = "api-football"
            selected_status = fallback.status
            selected_payload = fallback_payload
            selected_bundle_id = fallback.bundle_id or ""
            selected_observation_id = fallback_observation_id
            fallback_reason = f"primary_{primary.status.value.lower()}"

    resolution.select_result(
        source=selected_source,
        status=selected_status,
        value=selected_payload,
        bundle_id=selected_bundle_id,
        fallback_reason=fallback_reason,
    )
    projection = create_projection(
        canonical_fixture_id=fixture_id,
        team_id=team.id,
        capability=Capability.CURRENT_RECENT_FORM.value,
        analysis_cutoff_at=analysis_cutoff_at,
        selected_source=selected_source,
        selected_status=selected_status.value,
        selected_observation_id=selected_observation_id,
        primary_source="espn-football",
        primary_status=primary.status.value,
        fallback_reason=fallback_reason,
    )
    repo.save_projection(projection)
    return resolution


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
    team_contexts: dict[tuple[int, int], list[dict]] = {}
    for fix in fixtures:
        home_key = (fix.home_team_id, fix.sport_id)
        away_key = (fix.away_team_id, fix.sport_id)
        team_sport_pairs.add(home_key)
        team_sport_pairs.add(away_key)
        shared_context = {
            "fixture_id": fix.id,
            "fixture_external_id": fix.external_id,
            "kickoff": fix.kickoff,
            "competition_id": fix.competition_id,
            "home_team_id": fix.home_team_id,
            "away_team_id": fix.away_team_id,
        }
        team_contexts.setdefault(home_key, []).append({**shared_context, "team_side": "home"})
        team_contexts.setdefault(away_key, []).append({**shared_context, "team_side": "away"})

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
            team,
            sport_obj.name,
            stat_keys,
            db_conn,
            playwright_pool,
            fixture_contexts=team_contexts.get((team.id, sport_id), []),
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
    team, sport: str, stat_keys: list[str], db_conn, pool, fixture_contexts: list[dict] | None = None
) -> bool:
    """Fetch and store stats for a single team. Returns True if data was fetched.
    
    For football: checks fixture-scoped projections first, only fetches if no
    projection exists for the given fixture+cutoff.
    """
    stats_repo = StatsRepo(db_conn)
    sport_repo = SportRepo(db_conn)
    sport_obj = sport_repo.get_by_name(sport)
    if not sport_obj:
        return False

    fetched = False

    if sport == "football" and fixture_contexts:
        fixture_context = _select_single_fixture_context(fixture_contexts)
        if fixture_context:
            resolution = _resolve_football_recent_form(
                team=team,
                stat_keys=stat_keys,
                db_conn=db_conn,
                fixture_context=fixture_context,
            )
            return resolution.selected_status is SourceResultStatus.SUCCESS and bool(resolution.selected_value)

    # Try API — run synchronously to avoid SQLite threading issues
    # (sqlite3 connections cannot be shared across threads)
    api_result = _try_api_fetch(team, sport, stat_keys, db_conn, fixture_contexts=fixture_contexts)

    if api_result.status is SourceResultStatus.SUCCESS and api_result.value:
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
            updated_at=datetime.now(UTC).isoformat(),
            source="computed",
        )
        stats_repo.save_team_form(team_form)
        fetched = True

    return fetched


def _try_api_fetch(
    team,
    sport: str,
    stat_keys: list[str],
    db_conn,
    fixture_contexts: list[dict] | None = None,
) -> SourceOperationResult[dict]:
    """Try to fetch stats from sport-specific API client.

    Strategy: ESPN first (free, unlimited), then API-Sports as fallback.
    Fetches the team's last 10 fixtures with stats from the API,
    aggregates per-stat values, and saves directly to team_form.
    Checks match_stats table first to avoid redundant API calls.
    """
    if sport == "football" and _has_multiple_fixture_contexts(fixture_contexts or []):
        logger.debug("Skipping %s due to ambiguous multi-fixture cutoff context", team.name)
        return SourceOperationResult(SourceResultStatus.AMBIGUOUS, error_code="fixture_context_ambiguous")

    # Try ESPN first (free, unlimited)
    espn_result = _try_espn_fetch(
        team,
        sport,
        stat_keys,
        db_conn,
        fixture_contexts=fixture_contexts,
    )
    if espn_result.status is SourceResultStatus.SUCCESS and espn_result.value:
        return espn_result

    if sport == "football" and espn_result.status in {
        SourceResultStatus.SUCCESS,
        SourceResultStatus.NOT_FOUND,
        SourceResultStatus.AMBIGUOUS,
        SourceResultStatus.NOT_PUBLISHED_YET,
        SourceResultStatus.NOT_SUPPORTED,
        SourceResultStatus.PARSE_ERROR,
        SourceResultStatus.SCHEMA_ERROR,
        SourceResultStatus.PLAN_RESTRICTED,
    }:
        return espn_result

    # Fall back to API-Sports
    api_sports_result = _try_api_sports_fetch(
        team,
        sport,
        stat_keys,
        db_conn,
        fixture_contexts=fixture_contexts,
    )
    return api_sports_result


def _try_espn_fetch(
    team,
    sport: str,
    stat_keys: list[str],
    db_conn,
    fixture_contexts: list[dict] | None = None,
) -> SourceOperationResult[dict]:
    """Try ESPN as primary stat source. Returns typed success/failure result."""
    from bet.api_clients import API_ESPN
    from bet.api_clients.espn import (
        ESPN_LEAGUES,
        ESPNClient,
        get_espn_league_for_competition,
    )

    espn_client_name = API_ESPN.get(sport)
    if not espn_client_name:
        return SourceOperationResult(SourceResultStatus.NOT_SUPPORTED, error_code="espn_client_not_registered")

    try:
        from bet.api_clients import RateLimiter

        # For football, we need an exact fixture context for cutoff-safe identity.
        league = None
        fixture_identity = None
        if sport == "football":
            fixture_context = _select_single_fixture_context(fixture_contexts or [])
            if not fixture_context:
                return SourceOperationResult(SourceResultStatus.NOT_FOUND, error_code="fixture_context_missing")
            row = _get_fixture_identity_row(db_conn, fixture_context.get("fixture_id"))
            if row:
                league = get_espn_league_for_competition(row["competition_name"])
            if not league:
                return SourceOperationResult(SourceResultStatus.NOT_SUPPORTED, error_code="competition_not_supported_by_espn")
        else:
            # Non-football: use default league
            leagues = ESPN_LEAGUES.get(sport, [])
            league = leagues[0] if leagues else None
            if not league:
                return SourceOperationResult(SourceResultStatus.NOT_SUPPORTED, error_code="sport_not_supported_by_espn")

        rate_limiter = RateLimiter()
        client = ESPNClient(sport=sport, league=league, rate_limiter=rate_limiter)
        if not client.is_available():
            return SourceOperationResult(SourceResultStatus.AUTHENTICATION_ERROR, error_code="client_unavailable")

        evidence_refs = []

        if sport == "football":
            fixture_identity = _resolve_espn_fixture_identity(
                client=client,
                db_conn=db_conn,
                fixture_context=fixture_context,
            )
            if fixture_identity.status is not SourceResultStatus.SUCCESS or not fixture_identity.value:
                return SourceOperationResult(
                    status=fixture_identity.status,
                    http_status=fixture_identity.http_status,
                    retryable=fixture_identity.retryable,
                    error_code=fixture_identity.error_code,
                    retry_after_seconds=fixture_identity.retry_after_seconds,
                    evidence_refs=fixture_identity.evidence_refs,
                )
            evidence_refs.extend(fixture_identity.evidence_refs)
            identity_value = fixture_identity.value
            api_team_id = identity_value["team_provider_ids"].get(team.id)
            if not api_team_id:
                return SourceOperationResult(SourceResultStatus.SCHEMA_ERROR, error_code="provider_team_id_missing", evidence_refs=evidence_refs)
            last_fixtures_result = client.get_team_last_fixtures_result(
                api_team_id,
                last_n=10,
                analysis_cutoff_at=identity_value["target_start_at"],
                exclude_event_ids={identity_value["target_source_event_id"]},
            )
        else:
            api_team_id = client.resolve_team_id(team.name)
            if not api_team_id:
                return SourceOperationResult(SourceResultStatus.NOT_FOUND, error_code="team_id_not_found")
            last_fixtures_result = client.get_team_last_fixtures_result(api_team_id, last_n=10)

        evidence_refs.extend(last_fixtures_result.evidence_refs)
        if last_fixtures_result.status is not SourceResultStatus.SUCCESS:
            return SourceOperationResult(
                status=last_fixtures_result.status,
                http_status=last_fixtures_result.http_status,
                retryable=last_fixtures_result.retryable,
                error_code=last_fixtures_result.error_code,
                retry_after_seconds=last_fixtures_result.retry_after_seconds,
                evidence_refs=evidence_refs,
            )

        last_fixtures = last_fixtures_result.value or []
        if not last_fixtures:
            return SourceOperationResult(SourceResultStatus.SUCCESS, value={}, evidence_refs=evidence_refs)

        stat_values: dict[str, list[float]] = {k: [] for k in stat_keys}
        source_event_ids: list[str] = []

        for fix_data in last_fixtures:
            fix_id = str(fix_data.get("id", ""))
            if not fix_id:
                continue

            source_event_ids.append(fix_id)

            fix_stats_result = client.get_fixture_stats_result(fix_id)
            evidence_refs.extend(fix_stats_result.evidence_refs)
            if fix_stats_result.status is not SourceResultStatus.SUCCESS:
                continue
            fix_stats = fix_stats_result.value or []
            if not fix_stats:
                continue
            for ms in fix_stats:
                team_side = None
                if sport == "football":
                    team_side = _select_espn_stat_side(str(api_team_id), ms)
                    if team_side is None:
                        logger.debug(
                            "Skipping ESPN stat for %s fixture=%s due to provider-side mismatch home=%s away=%s requested=%s",
                            team.name,
                            fix_id,
                            getattr(ms, "home_participant_id", ""),
                            getattr(ms, "away_participant_id", ""),
                            api_team_id,
                        )
                        continue
                for stat_key, sides in ms.stats.items():
                    if stat_key not in stat_keys:
                        continue
                    if team_side == "home":
                        val = sides.get("home")
                    elif team_side == "away":
                        val = sides.get("away")
                    elif _is_home_team(team.name, ms.home_team_name):
                        val = sides.get("home")
                    else:
                        val = sides.get("away")
                    if isinstance(val, (int, float)):
                        stat_values[stat_key].append(float(val))

        if not any(stat_values.values()):
            return SourceOperationResult(SourceResultStatus.SUCCESS, value={}, evidence_refs=evidence_refs)

        stats_repo = StatsRepo(db_conn)
        sport_repo = SportRepo(db_conn)
        sport_obj = sport_repo.get_by_name(sport)
        now = datetime.now(UTC).isoformat()
        all_source_event_ids = source_event_ids[:]
        if sport == "football":
            all_source_event_ids.append(identity_value["target_source_event_id"])
        source_refs = namespaced_source_refs(client.api_name, all_source_event_ids)
        evidence_hash, _ = write_bundle_manifest(
            registered_source_key=client.api_name,
            projection_name="team_form",
            canonical_fixture_id=int(fixture_context["fixture_id"]) if sport == "football" and fixture_context.get("fixture_id") is not None else 0,
            parser_version=ESPN_PARSER_VERSION,
            source_event_refs=source_refs,
            evidence_refs=evidence_refs,
        )

        normalized_stats = {}
        for stat_key, values in stat_values.items():
            if not values:
                continue
            form = compute_form(values)
            l5_values = values[:5] if len(values) >= 5 else values
            normalized_stats[stat_key] = {
                "l10_values": values[:10],
                "l5_values": l5_values,
                "l10_avg": form["l10_avg"],
                "l5_avg": form["l5_avg"],
                "trend": form["trend"],
            }
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
                source_event_ids=source_refs,
                evidence_hash=evidence_hash,
            )
            stats_repo.save_team_form(team_form)

        _record_source_success(db_conn, f"espn-{sport}")
        return SourceOperationResult(
            SourceResultStatus.SUCCESS,
            value={
                "payload": {
                    "team_id": team.id,
                    "source": client.api_name,
                    "source_event_ids": source_refs,
                    "stats": normalized_stats,
                },
                "native_ids": {
                    "fixture_id": identity_value["target_source_event_id"],
                    "team_id": str(api_team_id),
                },
            },
            evidence_refs=evidence_refs,
            bundle_id=evidence_hash,
        )

    except Exception as exc:
        logger.debug("ESPN fetch failed for %s/%s: %s", sport, team.name, exc)
        return SourceOperationResult(SourceResultStatus.TRANSPORT_ERROR, retryable=False, error_code="unexpected_exception")


def _try_api_sports_fetch(
    team,
    sport: str,
    stat_keys: list[str],
    db_conn,
    fixture_contexts: list[dict] | None = None,
) -> SourceOperationResult[dict]:
    """Try API-Sports as fallback stat source using exact source crosswalks."""
    from bet.api_clients import API_SPORTS

    client_name = API_SPORTS.get(sport)
    if not client_name:
        return SourceOperationResult(SourceResultStatus.NOT_SUPPORTED, error_code="client_not_registered")

    try:
        from bet.api_clients import get_client
        client = get_client(client_name)
        if not client.is_available():
            return SourceOperationResult(SourceResultStatus.AUTHENTICATION_ERROR, error_code="client_unavailable")

        fixture_context = _select_single_fixture_context(fixture_contexts or [])
        if not fixture_context:
            status = (
                SourceResultStatus.AMBIGUOUS
                if _has_multiple_fixture_contexts(fixture_contexts or [])
                else SourceResultStatus.NOT_FOUND
            )
            return SourceOperationResult(status, error_code="fixture_context_missing")

        fixture_identity = _resolve_api_sports_fixture_identity(
            client=client,
            db_conn=db_conn,
            fixture_context=fixture_context,
        )
        if fixture_identity.status is not SourceResultStatus.SUCCESS or not fixture_identity.value:
            return fixture_identity

        identity_value = fixture_identity.value
        evidence_refs = fixture_identity.evidence_refs[:]
        api_team_id = identity_value["team_provider_ids"].get(team.id)
        if not api_team_id:
            return SourceOperationResult(
                SourceResultStatus.SCHEMA_ERROR,
                error_code="provider_team_id_missing",
                evidence_refs=evidence_refs,
            )

        last_fixtures_result = client.get_team_last_fixtures_result(
            api_team_id,
            last_n=10,
            analysis_cutoff_at=identity_value["target_start_at"],
            exclude_event_ids={identity_value["target_source_event_id"]},
            season_id=identity_value.get("season_id"),
            competition_id=identity_value.get("competition_id"),
        )
        evidence_refs.extend(last_fixtures_result.evidence_refs)
        if last_fixtures_result.status is not SourceResultStatus.SUCCESS:
            return SourceOperationResult(
                status=last_fixtures_result.status,
                http_status=last_fixtures_result.http_status,
                retryable=last_fixtures_result.retryable,
                error_code=last_fixtures_result.error_code,
                retry_after_seconds=last_fixtures_result.retry_after_seconds,
                evidence_refs=evidence_refs,
            )

        last_fixtures = last_fixtures_result.value or []
        if not last_fixtures:
            return SourceOperationResult(SourceResultStatus.SUCCESS, value={}, evidence_refs=evidence_refs)

        stat_values: dict[str, list[float]] = {k: [] for k in stat_keys}
        source_event_ids: list[str] = []

        for fix_data in last_fixtures:
            fix_id = str(fix_data.get("id", ""))
            if not fix_id:
                continue

            source_event_ids.append(fix_id)
            fix_stats_result = client.get_fixture_stats_result(
                fix_id,
                home_participant_id=str(fix_data.get("home_participant_id", "") or ""),
                away_participant_id=str(fix_data.get("away_participant_id", "") or ""),
            )
            evidence_refs.extend(fix_stats_result.evidence_refs)
            if fix_stats_result.status is not SourceResultStatus.SUCCESS:
                continue
            fix_stats = fix_stats_result.value or []
            for ms in fix_stats:
                team_side = _select_provider_stat_side(str(api_team_id), ms)
                if team_side is None:
                    continue
                for stat_key, sides in ms.stats.items():
                    if stat_key not in stat_keys:
                        continue
                    val = sides.get(team_side)
                    if isinstance(val, (int, float)):
                        stat_values[stat_key].append(float(val))

        if not any(stat_values.values()):
            return SourceOperationResult(SourceResultStatus.SUCCESS, value={}, evidence_refs=evidence_refs)

        stats_repo = StatsRepo(db_conn)
        sport_repo = SportRepo(db_conn)
        sport_obj = sport_repo.get_by_name(sport)
        now = datetime.now(UTC).isoformat()

        source_refs = namespaced_source_refs(
            client.api_name,
            [*source_event_ids, identity_value["target_source_event_id"]],
        )
        evidence_hash, _ = write_bundle_manifest(
            registered_source_key=client.api_name,
            projection_name="team_form",
            canonical_fixture_id=int(fixture_context["fixture_id"]),
            parser_version=f"{client.api_name}-team-form-v1",
            source_event_refs=source_refs,
            evidence_refs=evidence_refs,
        )

        normalized_stats = {}
        for stat_key, values in stat_values.items():
            if not values:
                continue
            form = compute_form(values)
            l5_values = values[:5] if len(values) >= 5 else values
            normalized_stats[stat_key] = {
                "l10_values": values[:10],
                "l5_values": l5_values,
                "l10_avg": form["l10_avg"],
                "l5_avg": form["l5_avg"],
                "trend": form["trend"],
            }
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
                source_event_ids=source_refs,
                evidence_hash=evidence_hash,
            )
            stats_repo.save_team_form(team_form)

        _record_source_success(db_conn, client_name)
        return SourceOperationResult(
            SourceResultStatus.SUCCESS,
            value={
                "payload": {
                    "team_id": team.id,
                    "source": client.api_name,
                    "source_event_ids": source_refs,
                    "stats": normalized_stats,
                },
                "native_ids": {
                    "fixture_id": identity_value["target_source_event_id"],
                    "team_id": str(api_team_id),
                },
            },
            evidence_refs=evidence_refs,
            bundle_id=evidence_hash,
        )

    except Exception as exc:
        logger.debug("API fetch failed for %s/%s: %s", sport, team.name, exc)
        return SourceOperationResult(SourceResultStatus.TRANSPORT_ERROR, retryable=False, error_code="unexpected_exception")


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


def _has_multiple_fixture_contexts(fixture_contexts: list[dict]) -> bool:
    if not fixture_contexts:
        return False
    unique_contexts = {
        (
            ctx.get("fixture_id"),
            ctx.get("fixture_external_id") or "",
            ctx.get("kickoff") or "",
        )
        for ctx in fixture_contexts
        if ctx.get("fixture_id") is not None
    }
    return len(unique_contexts) > 1


def _select_single_fixture_context(fixture_contexts: list[dict]) -> dict | None:
    if not fixture_contexts or _has_multiple_fixture_contexts(fixture_contexts):
        return None
    return fixture_contexts[0]


def _parse_snapshot_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _get_fixture_identity_row(db_conn, fixture_id: int | None):
    if fixture_id is None:
        return None
    return db_conn.execute(
        "SELECT f.id AS fixture_id, f.external_id, f.kickoff, f.sport_id, "
        "f.home_team_id, f.away_team_id, ht.name AS home_team_name, at.name AS away_team_name, "
        "COALESCE(c.name, '') AS competition_name "
        "FROM fixtures f "
        "JOIN teams ht ON ht.id = f.home_team_id "
        "JOIN teams at ON at.id = f.away_team_id "
        "LEFT JOIN competitions c ON c.id = f.competition_id "
        "WHERE f.id = ?",
        (fixture_id,),
    ).fetchone()


def _team_name_matches_expected(team, source_name: str) -> bool:
    from bet.utils import normalize_team_name

    source = (source_name or "").strip()
    if not source:
        return False
    source_norm = normalize_team_name(source)
    for candidate in [team.name, *(team.aliases or [])]:
        candidate_value = (candidate or "").strip()
        if not candidate_value:
            continue
        if candidate_value.casefold() == source.casefold():
            return True
        if normalize_team_name(candidate_value) == source_norm:
            return True
    return False


def _get_fixture_source_event_ids(db_conn, fixture_id: int | None, source: str) -> list[str]:
    if fixture_id is None:
        return []
    rows = db_conn.execute(
        "SELECT external_id FROM fixture_sources WHERE fixture_id = ? AND source = ?",
        (fixture_id, source),
    ).fetchall()
    distinct_ids = {
        str((row["external_id"] if hasattr(row, "keys") else row[0]) or "").strip()
        for row in rows
        if str((row["external_id"] if hasattr(row, "keys") else row[0]) or "").strip()
    }
    return sorted(distinct_ids)


def _resolve_espn_fixture_identity(*, client, db_conn, fixture_context: dict) -> SourceOperationResult[dict]:
    source_event_ids = _get_fixture_source_event_ids(
        db_conn,
        fixture_context.get("fixture_id"),
        client.api_name,
    )
    if not source_event_ids:
        return SourceOperationResult(SourceResultStatus.NOT_FOUND, error_code="fixture_source_mapping_missing")
    if len(source_event_ids) > 1:
        return SourceOperationResult(SourceResultStatus.AMBIGUOUS, error_code="fixture_source_mapping_ambiguous")

    row = _get_fixture_identity_row(db_conn, fixture_context.get("fixture_id"))
    if not row:
        return SourceOperationResult(SourceResultStatus.NOT_FOUND, error_code="fixture_identity_row_missing")

    target_source_event_id = source_event_ids[0]
    target_start_at = str(row["kickoff"] or "").strip()
    if not target_source_event_id or not target_start_at:
        return SourceOperationResult(SourceResultStatus.SCHEMA_ERROR, error_code="fixture_identity_missing_target_fields")

    target_start_dt = _parse_snapshot_datetime(target_start_at)
    if target_start_dt is None:
        return SourceOperationResult(SourceResultStatus.SCHEMA_ERROR, error_code="fixture_identity_invalid_kickoff")

    target_date = target_start_at[:10]
    source_fixture_result = client.get_event_fixture_result(target_date, target_source_event_id)
    if source_fixture_result.status is not SourceResultStatus.SUCCESS or source_fixture_result.value is None:
        return SourceOperationResult(
            status=source_fixture_result.status,
            http_status=source_fixture_result.http_status,
            retryable=source_fixture_result.retryable,
            error_code=source_fixture_result.error_code,
            retry_after_seconds=source_fixture_result.retry_after_seconds,
            evidence_refs=source_fixture_result.evidence_refs,
        )
    source_fixture = source_fixture_result.value
    if str(source_fixture.external_id).strip() != target_source_event_id:
        return SourceOperationResult(SourceResultStatus.SCHEMA_ERROR, error_code="crosswalk_event_id_mismatch", evidence_refs=source_fixture_result.evidence_refs)

    source_start_dt = _parse_snapshot_datetime(source_fixture.kickoff)
    if source_start_dt is None or source_start_dt != target_start_dt:
        return SourceOperationResult(SourceResultStatus.SCHEMA_ERROR, error_code="crosswalk_kickoff_mismatch", evidence_refs=source_fixture_result.evidence_refs)
    if not source_fixture.home_participant_id or not source_fixture.away_participant_id:
        return SourceOperationResult(SourceResultStatus.SCHEMA_ERROR, error_code="crosswalk_participant_ids_missing", evidence_refs=source_fixture_result.evidence_refs)
    if source_fixture.home_participant_id == source_fixture.away_participant_id:
        return SourceOperationResult(SourceResultStatus.SCHEMA_ERROR, error_code="crosswalk_participant_ids_duplicated", evidence_refs=source_fixture_result.evidence_refs)
    if get_espn_league_for_competition(row["competition_name"] or "") != client.league:
        return SourceOperationResult(SourceResultStatus.SCHEMA_ERROR, error_code="crosswalk_competition_mismatch", evidence_refs=source_fixture_result.evidence_refs)

    team_repo = TeamRepo(db_conn)
    home_team = team_repo.get_by_id(row["home_team_id"])
    away_team = team_repo.get_by_id(row["away_team_id"])
    if not home_team or not away_team:
        return SourceOperationResult(SourceResultStatus.NOT_FOUND, error_code="canonical_teams_missing", evidence_refs=source_fixture_result.evidence_refs)

    if not _team_name_matches_expected(home_team, source_fixture.home_team_name):
        return SourceOperationResult(SourceResultStatus.SCHEMA_ERROR, error_code="crosswalk_home_name_diagnostic_mismatch", evidence_refs=source_fixture_result.evidence_refs)
    if not _team_name_matches_expected(away_team, source_fixture.away_team_name):
        return SourceOperationResult(SourceResultStatus.SCHEMA_ERROR, error_code="crosswalk_away_name_diagnostic_mismatch", evidence_refs=source_fixture_result.evidence_refs)

    competition_hint = row["competition_name"] or ""
    alias_repo = TeamSourceAliasRepo(db_conn)
    cached_home_id = alias_repo.get_verified_provider_team_id(home_team.id, client.api_name, competition_hint)
    cached_away_id = alias_repo.get_verified_provider_team_id(away_team.id, client.api_name, competition_hint)
    if cached_home_id and cached_home_id != source_fixture.home_participant_id:
        return SourceOperationResult(SourceResultStatus.SCHEMA_ERROR, error_code="crosswalk_home_alias_conflict", evidence_refs=source_fixture_result.evidence_refs)
    if cached_away_id and cached_away_id != source_fixture.away_participant_id:
        return SourceOperationResult(SourceResultStatus.SCHEMA_ERROR, error_code="crosswalk_away_alias_conflict", evidence_refs=source_fixture_result.evidence_refs)

    alias_repo.upsert_alias(
        team_id=home_team.id,
        sport_id=row["sport_id"],
        source=client.api_name,
        provider_team_name=source_fixture.home_team_name,
        provider_team_id=source_fixture.home_participant_id,
        provider_competition_hint=competition_hint,
        confidence=1.0,
        status="verified",
    )
    alias_repo.upsert_alias(
        team_id=away_team.id,
        sport_id=row["sport_id"],
        source=client.api_name,
        provider_team_name=source_fixture.away_team_name,
        provider_team_id=source_fixture.away_participant_id,
        provider_competition_hint=competition_hint,
        confidence=1.0,
        status="verified",
    )

    return SourceOperationResult(
        SourceResultStatus.SUCCESS,
        value={
            "target_source_event_id": target_source_event_id,
            "target_start_at": source_fixture.kickoff,
            "team_provider_ids": {
                home_team.id: source_fixture.home_participant_id,
                away_team.id: source_fixture.away_participant_id,
            },
        },
        evidence_refs=source_fixture_result.evidence_refs,
    )


def _select_espn_stat_side(provider_team_id: str, match_stats) -> str | None:
    requested_id = str(provider_team_id or "").strip()
    home_id = str(getattr(match_stats, "home_participant_id", "") or "").strip()
    away_id = str(getattr(match_stats, "away_participant_id", "") or "").strip()
    if not requested_id or not home_id or not away_id:
        return None
    home_match = requested_id == home_id
    away_match = requested_id == away_id
    if home_match == away_match:
        return None
    return "home" if home_match else "away"


def _select_provider_stat_side(provider_team_id: str, match_stats) -> str | None:
    return _select_espn_stat_side(provider_team_id, match_stats)


def _resolve_api_sports_fixture_identity(*, client, db_conn, fixture_context: dict) -> SourceOperationResult[dict]:
    source_event_ids = _get_fixture_source_event_ids(
        db_conn,
        fixture_context.get("fixture_id"),
        client.api_name,
    )
    if not source_event_ids:
        return SourceOperationResult(SourceResultStatus.NOT_FOUND, error_code="fixture_source_mapping_missing")
    if len(source_event_ids) > 1:
        return SourceOperationResult(SourceResultStatus.AMBIGUOUS, error_code="fixture_source_mapping_ambiguous")

    row = _get_fixture_identity_row(db_conn, fixture_context.get("fixture_id"))
    if not row:
        return SourceOperationResult(SourceResultStatus.NOT_FOUND, error_code="fixture_identity_row_missing")

    target_source_event_id = source_event_ids[0]
    target_start_at = str(row["kickoff"] or "").strip()
    if not target_source_event_id or not target_start_at:
        return SourceOperationResult(SourceResultStatus.SCHEMA_ERROR, error_code="fixture_identity_missing_target_fields")

    target_start_dt = _parse_snapshot_datetime(target_start_at)
    if target_start_dt is None:
        return SourceOperationResult(SourceResultStatus.SCHEMA_ERROR, error_code="fixture_identity_invalid_kickoff")

    source_fixture_result = client.get_event_fixture_result(target_start_at[:10], target_source_event_id)
    if source_fixture_result.status is not SourceResultStatus.SUCCESS or source_fixture_result.value is None:
        return SourceOperationResult(
            status=source_fixture_result.status,
            http_status=source_fixture_result.http_status,
            retryable=source_fixture_result.retryable,
            error_code=source_fixture_result.error_code,
            retry_after_seconds=source_fixture_result.retry_after_seconds,
            evidence_refs=source_fixture_result.evidence_refs,
        )
    source_fixture = source_fixture_result.value
    if str(source_fixture.external_id).strip() != target_source_event_id:
        return SourceOperationResult(SourceResultStatus.SCHEMA_ERROR, error_code="crosswalk_event_id_mismatch", evidence_refs=source_fixture_result.evidence_refs)
    source_start_dt = _parse_snapshot_datetime(source_fixture.kickoff)
    if source_start_dt is None or source_start_dt != target_start_dt:
        return SourceOperationResult(SourceResultStatus.SCHEMA_ERROR, error_code="crosswalk_kickoff_mismatch", evidence_refs=source_fixture_result.evidence_refs)
    if not source_fixture.home_participant_id or not source_fixture.away_participant_id:
        return SourceOperationResult(SourceResultStatus.SCHEMA_ERROR, error_code="crosswalk_participant_ids_missing", evidence_refs=source_fixture_result.evidence_refs)
    if source_fixture.home_participant_id == source_fixture.away_participant_id:
        return SourceOperationResult(SourceResultStatus.SCHEMA_ERROR, error_code="crosswalk_participant_ids_duplicated", evidence_refs=source_fixture_result.evidence_refs)

    team_repo = TeamRepo(db_conn)
    home_team = team_repo.get_by_id(row["home_team_id"])
    away_team = team_repo.get_by_id(row["away_team_id"])
    if not home_team or not away_team:
        return SourceOperationResult(SourceResultStatus.NOT_FOUND, error_code="canonical_teams_missing", evidence_refs=source_fixture_result.evidence_refs)
    if not _team_name_matches_expected(home_team, source_fixture.home_team_name):
        return SourceOperationResult(SourceResultStatus.SCHEMA_ERROR, error_code="crosswalk_home_name_diagnostic_mismatch", evidence_refs=source_fixture_result.evidence_refs)
    if not _team_name_matches_expected(away_team, source_fixture.away_team_name):
        return SourceOperationResult(SourceResultStatus.SCHEMA_ERROR, error_code="crosswalk_away_name_diagnostic_mismatch", evidence_refs=source_fixture_result.evidence_refs)

    competition_hint = row["competition_name"] or ""
    alias_repo = TeamSourceAliasRepo(db_conn)
    cached_home_id = alias_repo.get_verified_provider_team_id(home_team.id, client.api_name, competition_hint)
    cached_away_id = alias_repo.get_verified_provider_team_id(away_team.id, client.api_name, competition_hint)
    if cached_home_id and cached_home_id != source_fixture.home_participant_id:
        return SourceOperationResult(SourceResultStatus.SCHEMA_ERROR, error_code="crosswalk_home_alias_conflict", evidence_refs=source_fixture_result.evidence_refs)
    if cached_away_id and cached_away_id != source_fixture.away_participant_id:
        return SourceOperationResult(SourceResultStatus.SCHEMA_ERROR, error_code="crosswalk_away_alias_conflict", evidence_refs=source_fixture_result.evidence_refs)

    alias_repo.upsert_alias(
        team_id=home_team.id,
        sport_id=row["sport_id"],
        source=client.api_name,
        provider_team_name=source_fixture.home_team_name,
        provider_team_id=source_fixture.home_participant_id,
        provider_competition_hint=competition_hint,
        confidence=1.0,
        status="verified",
    )
    alias_repo.upsert_alias(
        team_id=away_team.id,
        sport_id=row["sport_id"],
        source=client.api_name,
        provider_team_name=source_fixture.away_team_name,
        provider_team_id=source_fixture.away_participant_id,
        provider_competition_hint=competition_hint,
        confidence=1.0,
        status="verified",
    )

    return SourceOperationResult(
        SourceResultStatus.SUCCESS,
        value={
            "target_source_event_id": target_source_event_id,
            "target_start_at": source_fixture.kickoff,
            "competition_id": source_fixture.competition_id,
            "season_id": source_fixture.season_id,
            "team_provider_ids": {
                home_team.id: source_fixture.home_participant_id,
                away_team.id: source_fixture.away_participant_id,
            },
        },
        evidence_refs=source_fixture_result.evidence_refs,
    )


def _is_home_team(team_name: str, home_team_name: str) -> bool:
    """Check if team_name matches home team via equality or containment."""
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


def _upsert_fixture_source_mapping(
    db_conn,
    *,
    fixture_id: int,
    source: str,
    external_id: str,
    confidence: float,
    raw_data: dict,
) -> None:
    db_conn.execute(
        """INSERT INTO fixture_sources (fixture_id, source, external_id, confidence, raw_data, fetched_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(fixture_id, source) DO UPDATE SET
             external_id = excluded.external_id,
             confidence = excluded.confidence,
             raw_data = excluded.raw_data,
             fetched_at = excluded.fetched_at""",
        (
            fixture_id,
            source,
            external_id,
            confidence,
            json.dumps(raw_data, sort_keys=True),
            datetime.now(UTC).isoformat(),
        ),
    )


def _match_cross_provider_candidate(db_conn, fixture_row, candidates: list) -> list:
    from bet.utils import normalize_team_name

    expected_competition = str(fixture_row["competition_name"] or "")
    expected_league = get_espn_league_for_competition(expected_competition)
    expected_names = {
        normalize_team_name(str(fixture_row["home_team_name"] or "")),
        normalize_team_name(str(fixture_row["away_team_name"] or "")),
    }
    target_dt = _parse_snapshot_datetime(str(fixture_row["kickoff"] or ""))
    if target_dt is None:
        return []

    matched = []
    for candidate in candidates:
        candidate_league = get_espn_league_for_competition(candidate.competition_name or "")
        if expected_league and candidate_league != expected_league:
            continue
        candidate_dt = _parse_snapshot_datetime(candidate.kickoff)
        if candidate_dt is None:
            continue
        if abs((candidate_dt - target_dt).total_seconds()) > 600:
            continue
        candidate_names = {
            normalize_team_name(candidate.home_team_name or ""),
            normalize_team_name(candidate.away_team_name or ""),
        }
        if candidate_names != expected_names:
            continue
        matched.append(candidate)
    return matched


def _resolve_cross_provider_identity(
    db_conn,
    canonical_fixture_id: int,
    analysis_cutoff_at: str,
) -> CapabilityResolution:
    from bet.api_clients.espn import ESPNClient, RateLimiter

    row = _get_fixture_identity_row(db_conn, canonical_fixture_id)
    if not row:
        resolution = CapabilityResolution(
            capability=Capability.CROSS_PROVIDER_IDENTITY,
            canonical_fixture_id=canonical_fixture_id,
            analysis_cutoff_at=analysis_cutoff_at,
        )
        resolution.select_result("cross-provider", SourceResultStatus.NOT_FOUND)
        return resolution

    team_id = int(row["home_team_id"])
    resolution = CapabilityResolution(
        capability=Capability.CROSS_PROVIDER_IDENTITY,
        canonical_fixture_id=canonical_fixture_id,
        team_id=team_id,
        analysis_cutoff_at=analysis_cutoff_at,
    )
    repo = FixtureCapabilityRepo(db_conn)
    existing = repo.get_snapshot_for_analysis(
        canonical_fixture_id=canonical_fixture_id,
        team_id=team_id,
        capability=Capability.CROSS_PROVIDER_IDENTITY.value,
        analysis_cutoff_at=analysis_cutoff_at,
    )
    if existing["status"] == SourceResultStatus.SUCCESS.value and existing.get("payload"):
        resolution.select_result(
            source=existing["source"],
            status=SourceResultStatus.SUCCESS,
            value=existing["payload"],
            bundle_id=existing["evidence_bundle_id"],
        )
        return resolution

    api_source_row = db_conn.execute(
        "SELECT external_id, raw_data FROM fixture_sources WHERE fixture_id = ? AND source = ?",
        (canonical_fixture_id, "api-football"),
    ).fetchone()
    api_payload = json.loads(api_source_row["raw_data"] or "{}") if api_source_row else {}

    league = get_espn_league_for_competition(str(row["competition_name"] or ""))
    if not league:
        result = SourceOperationResult(
            SourceResultStatus.NOT_SUPPORTED,
            error_code="competition_not_supported_by_espn",
        )
        obs_id = _persist_capability_result(
            db_conn=db_conn,
            canonical_fixture_id=canonical_fixture_id,
            team_id=team_id,
            capability=Capability.CROSS_PROVIDER_IDENTITY,
            analysis_cutoff_at=analysis_cutoff_at,
            source="cross-provider",
            result=result,
            normalized_value=None,
            native_ids=None,
            parser_version=ESPN_PARSER_VERSION,
        )
        repo.save_projection(
            create_projection(
                canonical_fixture_id=canonical_fixture_id,
                team_id=team_id,
                capability=Capability.CROSS_PROVIDER_IDENTITY.value,
                analysis_cutoff_at=analysis_cutoff_at,
                selected_source="cross-provider",
                selected_status=result.status.value,
                selected_observation_id=obs_id,
                primary_source="espn-football",
                primary_status=result.status.value,
            )
        )
        resolution.select_result("cross-provider", result.status)
        return resolution

    client = ESPNClient(sport="football", league=league, rate_limiter=RateLimiter())
    espn_result = client.get_fixtures_result(str(row["kickoff"] or "")[:10])
    resolution.add_observation(
        create_observation_from_result(
            "espn-football",
            espn_result,
            parser_version=ESPN_PARSER_VERSION,
        )
    )
    if espn_result.status is not SourceResultStatus.SUCCESS or not espn_result.value:
        obs_id = _persist_capability_result(
            db_conn=db_conn,
            canonical_fixture_id=canonical_fixture_id,
            team_id=team_id,
            capability=Capability.CROSS_PROVIDER_IDENTITY,
            analysis_cutoff_at=analysis_cutoff_at,
            source="cross-provider",
            result=espn_result,
            normalized_value=None,
            native_ids=None,
            parser_version=ESPN_PARSER_VERSION,
        )
        repo.save_projection(
            create_projection(
                canonical_fixture_id=canonical_fixture_id,
                team_id=team_id,
                capability=Capability.CROSS_PROVIDER_IDENTITY.value,
                analysis_cutoff_at=analysis_cutoff_at,
                selected_source="cross-provider",
                selected_status=espn_result.status.value,
                selected_observation_id=obs_id,
                primary_source="espn-football",
                primary_status=espn_result.status.value,
            )
        )
        resolution.select_result("cross-provider", espn_result.status)
        return resolution

    candidates = _match_cross_provider_candidate(db_conn, row, espn_result.value)
    if len(candidates) != 1:
        status = SourceResultStatus.AMBIGUOUS if len(candidates) > 1 else SourceResultStatus.NOT_FOUND
        result = SourceOperationResult(
            status,
            http_status=espn_result.http_status,
            error_code="cross_provider_candidate_ambiguous" if len(candidates) > 1 else "cross_provider_candidate_not_found",
            evidence_refs=espn_result.evidence_refs,
        )
        obs_id = _persist_capability_result(
            db_conn=db_conn,
            canonical_fixture_id=canonical_fixture_id,
            team_id=team_id,
            capability=Capability.CROSS_PROVIDER_IDENTITY,
            analysis_cutoff_at=analysis_cutoff_at,
            source="cross-provider",
            result=result,
            normalized_value=None,
            native_ids=None,
            parser_version=ESPN_PARSER_VERSION,
        )
        repo.save_projection(
            create_projection(
                canonical_fixture_id=canonical_fixture_id,
                team_id=team_id,
                capability=Capability.CROSS_PROVIDER_IDENTITY.value,
                analysis_cutoff_at=analysis_cutoff_at,
                selected_source="cross-provider",
                selected_status=result.status.value,
                selected_observation_id=obs_id,
                primary_source="espn-football",
                primary_status=result.status.value,
            )
        )
        resolution.select_result("cross-provider", result.status)
        return resolution

    candidate = candidates[0]
    bundle_id, _ = write_bundle_manifest(
        registered_source_key=client.api_name,
        projection_name="cross_provider_identity",
        canonical_fixture_id=canonical_fixture_id,
        parser_version=ESPN_PARSER_VERSION,
        source_event_refs=namespaced_source_refs(client.api_name, [candidate.external_id]),
        evidence_refs=espn_result.evidence_refs,
    )
    raw_data = {
        "provider_participant_ids": {
            "home": candidate.home_participant_id,
            "away": candidate.away_participant_id,
        },
        "competition_name": candidate.competition_name,
        "kickoff": candidate.kickoff,
        "evidence_bundle_id": bundle_id,
    }
    _upsert_fixture_source_mapping(
        db_conn,
        fixture_id=canonical_fixture_id,
        source=client.api_name,
        external_id=candidate.external_id,
        confidence=1.0,
        raw_data=raw_data,
    )

    alias_repo = TeamSourceAliasRepo(db_conn)
    competition_hint = str(row["competition_name"] or "")
    alias_repo.upsert_alias(
        team_id=int(row["home_team_id"]),
        sport_id=int(row["sport_id"]),
        source=client.api_name,
        provider_team_name=candidate.home_team_name,
        provider_team_id=candidate.home_participant_id,
        provider_competition_hint=competition_hint,
        confidence=1.0,
        status="verified",
    )
    alias_repo.upsert_alias(
        team_id=int(row["away_team_id"]),
        sport_id=int(row["sport_id"]),
        source=client.api_name,
        provider_team_name=candidate.away_team_name,
        provider_team_id=candidate.away_participant_id,
        provider_competition_hint=competition_hint,
        confidence=1.0,
        status="verified",
    )

    payload = {
        "canonical": {
            "fixture_id": canonical_fixture_id,
            "competition_name": competition_hint,
            "kickoff": str(row["kickoff"]),
            "home_team_id": int(row["home_team_id"]),
            "away_team_id": int(row["away_team_id"]),
        },
        "api_football": {
            "fixture_id": api_source_row["external_id"] if api_source_row else "",
            "team_ids": (api_payload.get("provider_participant_ids") or {}),
            "evidence_bundle_id": api_payload.get("evidence_bundle_id", ""),
        },
        "espn": {
            "fixture_id": candidate.external_id,
            "team_ids": {
                "home": candidate.home_participant_id,
                "away": candidate.away_participant_id,
            },
            "evidence_bundle_id": bundle_id,
            "kickoff": candidate.kickoff,
        },
    }
    selected = SourceOperationResult(
        SourceResultStatus.SUCCESS,
        value=payload,
        http_status=espn_result.http_status,
        evidence_refs=espn_result.evidence_refs,
        bundle_id=bundle_id,
    )
    obs_id = _persist_capability_result(
        db_conn=db_conn,
        canonical_fixture_id=canonical_fixture_id,
        team_id=team_id,
        capability=Capability.CROSS_PROVIDER_IDENTITY,
        analysis_cutoff_at=analysis_cutoff_at,
        source="cross-provider",
        result=selected,
        normalized_value=payload,
        native_ids={"fixture_id": candidate.external_id, "team_id": candidate.home_participant_id},
        parser_version=ESPN_PARSER_VERSION,
    )
    repo.save_projection(
        create_projection(
            canonical_fixture_id=canonical_fixture_id,
            team_id=team_id,
            capability=Capability.CROSS_PROVIDER_IDENTITY.value,
            analysis_cutoff_at=analysis_cutoff_at,
            selected_source="cross-provider",
            selected_status=SourceResultStatus.SUCCESS.value,
            selected_observation_id=obs_id,
            primary_source="espn-football",
            primary_status=SourceResultStatus.SUCCESS.value,
        )
    )
    resolution.select_result(
        source="cross-provider",
        status=SourceResultStatus.SUCCESS,
        value=payload,
        bundle_id=bundle_id,
    )
    return resolution


def _resolve_standings_for_fixture(
    db_conn,
    canonical_fixture_id: int,
    team_id: int,
    analysis_cutoff_at: str,
) -> SourceOperationResult[dict]:
    from bet.api_clients.espn import ESPNClient, RateLimiter

    row = _get_fixture_identity_row(db_conn, canonical_fixture_id)
    if not row:
        return SourceOperationResult(SourceResultStatus.NOT_FOUND, error_code="fixture_identity_row_missing")
    league = get_espn_league_for_competition(str(row["competition_name"] or ""))
    if not league:
        return SourceOperationResult(SourceResultStatus.NOT_SUPPORTED, error_code="competition_not_supported_by_espn")

    client = ESPNClient(sport="football", league=league, rate_limiter=RateLimiter())
    result = client.get_standings_result()
    alias_repo = TeamSourceAliasRepo(db_conn)
    source_event_ids = _get_fixture_source_event_ids(db_conn, canonical_fixture_id, client.api_name)
    provider_team_id = alias_repo.get_verified_provider_team_id(team_id, client.api_name, str(row["competition_name"] or "")) or ""
    standings = result.value or []
    selected_row = next((entry for entry in standings if str(entry.get("team_id", "")) == str(provider_team_id)), None)
    payload = {
        "competition_name": str(row["competition_name"] or ""),
        "league": league,
        "canonical_fixture_id": canonical_fixture_id,
        "team_id": team_id,
        "provider_team_id": str(provider_team_id),
        "selected_team": selected_row,
        "standings": standings,
    } if result.status is SourceResultStatus.SUCCESS else None

    obs_id = _persist_capability_result(
        db_conn=db_conn,
        canonical_fixture_id=canonical_fixture_id,
        team_id=team_id,
        capability=Capability.STANDINGS_COMPETITION_CONTEXT,
        analysis_cutoff_at=analysis_cutoff_at,
        source=client.api_name,
        result=result,
        normalized_value=payload,
        native_ids={"fixture_id": source_event_ids[0] if source_event_ids else "", "team_id": str(provider_team_id)},
        parser_version=ESPN_PARSER_VERSION,
    )
    FixtureCapabilityRepo(db_conn).save_projection(
        create_projection(
            canonical_fixture_id=canonical_fixture_id,
            team_id=team_id,
            capability=Capability.STANDINGS_COMPETITION_CONTEXT.value,
            analysis_cutoff_at=analysis_cutoff_at,
            selected_source=client.api_name,
            selected_status=result.status.value,
            selected_observation_id=obs_id,
            primary_source=client.api_name,
            primary_status=result.status.value,
        )
    )
    return SourceOperationResult(
        result.status,
        value=payload,
        http_status=result.http_status,
        evidence_refs=result.evidence_refs,
        bundle_id=result.bundle_id,
        error_code=result.error_code,
    )


def _resolve_h2h_for_fixture(
    db_conn,
    canonical_fixture_id: int,
    analysis_cutoff_at: str,
) -> SourceOperationResult[dict]:
    from bet.api_clients.espn import ESPNClient, RateLimiter

    row = _get_fixture_identity_row(db_conn, canonical_fixture_id)
    if not row:
        return SourceOperationResult(SourceResultStatus.NOT_FOUND, error_code="fixture_identity_row_missing")
    league = get_espn_league_for_competition(str(row["competition_name"] or ""))
    if not league:
        return SourceOperationResult(SourceResultStatus.NOT_SUPPORTED, error_code="competition_not_supported_by_espn")
    alias_repo = TeamSourceAliasRepo(db_conn)
    competition_hint = str(row["competition_name"] or "")
    home_provider_id = alias_repo.get_verified_provider_team_id(int(row["home_team_id"]), "espn-football", competition_hint)
    away_provider_id = alias_repo.get_verified_provider_team_id(int(row["away_team_id"]), "espn-football", competition_hint)
    event_ids: list[str] = _get_fixture_source_event_ids(db_conn, canonical_fixture_id, "espn-football")
    if not home_provider_id or not away_provider_id or len(event_ids) != 1:
        result = SourceOperationResult(SourceResultStatus.NOT_FOUND, error_code="cross_provider_identity_missing")
    else:
        client = ESPNClient(sport="football", league=league, rate_limiter=RateLimiter())
        result = client.get_h2h_result(
            str(home_provider_id),
            str(away_provider_id),
            analysis_cutoff_at=analysis_cutoff_at,
            exclude_event_ids={event_ids[0]},
            last_n=10,
        )

    payload = result.value if result.status is SourceResultStatus.SUCCESS else None
    obs_id = _persist_capability_result(
        db_conn=db_conn,
        canonical_fixture_id=canonical_fixture_id,
        team_id=int(row["home_team_id"]),
        capability=Capability.H2H_HEAD_TO_HEAD,
        analysis_cutoff_at=analysis_cutoff_at,
        source="espn-football",
        result=result,
        normalized_value=payload,
        native_ids={"fixture_id": event_ids[0] if event_ids else "", "team_id": str(home_provider_id or "")},
        parser_version=ESPN_PARSER_VERSION,
    )
    FixtureCapabilityRepo(db_conn).save_projection(
        create_projection(
            canonical_fixture_id=canonical_fixture_id,
            team_id=int(row["home_team_id"]),
            capability=Capability.H2H_HEAD_TO_HEAD.value,
            analysis_cutoff_at=analysis_cutoff_at,
            selected_source="espn-football",
            selected_status=result.status.value,
            selected_observation_id=obs_id,
            primary_source="espn-football",
            primary_status=result.status.value,
        )
    )
    return result if result.status is not SourceResultStatus.SUCCESS else SourceOperationResult(
        result.status,
        value=payload,
        http_status=result.http_status,
        evidence_refs=result.evidence_refs,
        bundle_id=result.bundle_id,
        parser_diagnostics=getattr(result, "parser_diagnostics", {}),
    )


def _resolve_fixture_statistics_for_fixture(
    db_conn,
    canonical_fixture_id: int,
    analysis_cutoff_at: str,
) -> SourceOperationResult[dict]:
    from bet.api_clients.espn import ESPNClient, RateLimiter

    row = _get_fixture_identity_row(db_conn, canonical_fixture_id)
    if not row:
        return SourceOperationResult(SourceResultStatus.NOT_FOUND, error_code="fixture_identity_row_missing")
    league = get_espn_league_for_competition(str(row["competition_name"] or ""))
    event_ids: list[str] = _get_fixture_source_event_ids(db_conn, canonical_fixture_id, "espn-football")
    if not league or len(event_ids) != 1:
        result = SourceOperationResult(SourceResultStatus.NOT_FOUND, error_code="espn_fixture_mapping_missing")
    else:
        client = ESPNClient(sport="football", league=league, rate_limiter=RateLimiter())
        result = client.get_fixture_stats_result(event_ids[0])
        if result.status is SourceResultStatus.SUCCESS and not result.value:
            result = SourceOperationResult(
                SourceResultStatus.NOT_PUBLISHED_YET,
                http_status=result.http_status,
                error_code="fixture_stats_not_published",
                evidence_refs=result.evidence_refs,
                bundle_id=result.bundle_id,
            )

    payload = None
    if result.status is SourceResultStatus.SUCCESS and result.value:
        stats = result.value[0]
        payload = {
            "fixture_id": canonical_fixture_id,
            "source_fixture_id": event_ids[0] if event_ids else "",
            "home_team_name": stats.home_team_name,
            "away_team_name": stats.away_team_name,
            "stats": stats.stats,
        }
    obs_id = _persist_capability_result(
        db_conn=db_conn,
        canonical_fixture_id=canonical_fixture_id,
        team_id=int(row["home_team_id"]),
        capability=Capability.FIXTURE_TEAM_STATISTICS,
        analysis_cutoff_at=analysis_cutoff_at,
        source="espn-football",
        result=result,
        normalized_value=payload,
        native_ids={"fixture_id": event_ids[0] if event_ids else "", "team_id": ""},
        parser_version=ESPN_PARSER_VERSION,
    )
    FixtureCapabilityRepo(db_conn).save_projection(
        create_projection(
            canonical_fixture_id=canonical_fixture_id,
            team_id=int(row["home_team_id"]),
            capability=Capability.FIXTURE_TEAM_STATISTICS.value,
            analysis_cutoff_at=analysis_cutoff_at,
            selected_source="espn-football",
            selected_status=result.status.value,
            selected_observation_id=obs_id,
            primary_source="espn-football",
            primary_status=result.status.value,
        )
    )
    return result if payload is None else SourceOperationResult(
        result.status,
        value=payload,
        http_status=result.http_status,
        evidence_refs=result.evidence_refs,
        bundle_id=result.bundle_id,
    )


def enrich_standings(
    db_conn,
    analysis_cutoff_at: str,
    canonical_fixture_id: int | None = None,
    team_id: int | None = None,
    sport: str | None = None,
    competition_name: str | None = None,
) -> SourceOperationResult[dict]:
    """Resolve standings for a concrete fixture/team scope.

    Accepts the new fixture/team contract and a narrow compatibility fallback for
    older football callsites that still pass competition_name.
    """
    if canonical_fixture_id is None or team_id is None:
        if sport not in {None, "football"} or not competition_name:
            return SourceOperationResult(
                SourceResultStatus.NOT_SUPPORTED,
                error_code="standings_scope_missing",
            )
        row = db_conn.execute(
            """SELECT f.id, f.home_team_id
               FROM fixtures f
               JOIN competitions c ON c.id = f.competition_id
               WHERE c.name = ? AND f.kickoff = ?
               ORDER BY f.id ASC
               LIMIT 1""",
            (competition_name, analysis_cutoff_at),
        ).fetchone()
        if not row:
            return SourceOperationResult(
                SourceResultStatus.NOT_FOUND,
                error_code="standings_fixture_scope_not_found",
            )
        canonical_fixture_id = int(row["id"] if hasattr(row, "keys") else row[0])
        team_id = int(row["home_team_id"] if hasattr(row, "keys") else row[1])
    return _resolve_standings_for_fixture(
        db_conn=db_conn,
        canonical_fixture_id=canonical_fixture_id,
        team_id=team_id,
        analysis_cutoff_at=analysis_cutoff_at,
    )


def get_standings_snapshot(
    db_conn,
    analysis_cutoff_at: str,
    canonical_fixture_id: int | None = None,
    team_id: int | None = None,
    competition_name: str | None = None,
) -> dict | None:
    """Get standings snapshot for downstream analysis using fixture/team scope."""
    if canonical_fixture_id is None or team_id is None:
        if not competition_name:
            return None
        row = db_conn.execute(
            """SELECT f.id, f.home_team_id
               FROM fixtures f
               JOIN competitions c ON c.id = f.competition_id
               WHERE c.name = ? AND f.kickoff = ?
               ORDER BY f.id ASC
               LIMIT 1""",
            (competition_name, analysis_cutoff_at),
        ).fetchone()
        if not row:
            return None
        canonical_fixture_id = int(row["id"] if hasattr(row, "keys") else row[0])
        team_id = int(row["home_team_id"] if hasattr(row, "keys") else row[1])
    cap_repo = FixtureCapabilityRepo(db_conn)

    snapshot = cap_repo.get_snapshot_for_analysis(
        canonical_fixture_id=canonical_fixture_id,
        team_id=team_id,
        capability=Capability.STANDINGS_COMPETITION_CONTEXT.value,
        analysis_cutoff_at=analysis_cutoff_at,
    )

    if snapshot["status"] == "NOT_FOUND":
        return None

    return snapshot


def build_football_fixture_snapshot(
    db_conn,
    canonical_fixture_id: int,
    analysis_cutoff_at: str | None = None,
) -> dict:
    """Build the real football downstream snapshot through typed capability routing."""
    row = _get_fixture_identity_row(db_conn, canonical_fixture_id)
    if not row:
        raise ValueError(f"Fixture {canonical_fixture_id} not found")
    cutoff = analysis_cutoff_at or str(row["kickoff"])
    fixture_context = {
        "fixture_id": canonical_fixture_id,
        "kickoff": cutoff,
        "competition_name": row["competition_name"],
    }
    team_repo = TeamRepo(db_conn)
    home_team = team_repo.get_by_id(int(row["home_team_id"]))
    away_team = team_repo.get_by_id(int(row["away_team_id"]))
    if not home_team or not away_team:
        raise ValueError(f"Fixture {canonical_fixture_id} teams missing")

    cross_provider = _resolve_cross_provider_identity(db_conn, canonical_fixture_id, cutoff)
    stat_keys = SPORT_STAT_KEYS.get("football", [])
    home_form = _resolve_football_recent_form(
        team=home_team,
        stat_keys=stat_keys,
        db_conn=db_conn,
        fixture_context=fixture_context,
    )
    away_form = _resolve_football_recent_form(
        team=away_team,
        stat_keys=stat_keys,
        db_conn=db_conn,
        fixture_context=fixture_context,
    )
    home_standings = _resolve_standings_for_fixture(db_conn, canonical_fixture_id, home_team.id, cutoff)
    away_standings = _resolve_standings_for_fixture(db_conn, canonical_fixture_id, away_team.id, cutoff)
    h2h = _resolve_h2h_for_fixture(db_conn, canonical_fixture_id, cutoff)
    fixture_stats = _resolve_fixture_statistics_for_fixture(db_conn, canonical_fixture_id, cutoff)

    repo = FixtureCapabilityRepo(db_conn)
    home_form_snapshot = repo.get_snapshot_for_analysis(canonical_fixture_id, home_team.id, Capability.CURRENT_RECENT_FORM.value, cutoff)
    away_form_snapshot = repo.get_snapshot_for_analysis(canonical_fixture_id, away_team.id, Capability.CURRENT_RECENT_FORM.value, cutoff)
    home_standings_snapshot = repo.get_snapshot_for_analysis(canonical_fixture_id, home_team.id, Capability.STANDINGS_COMPETITION_CONTEXT.value, cutoff)
    away_standings_snapshot = repo.get_snapshot_for_analysis(canonical_fixture_id, away_team.id, Capability.STANDINGS_COMPETITION_CONTEXT.value, cutoff)
    h2h_snapshot = repo.get_snapshot_for_analysis(canonical_fixture_id, home_team.id, Capability.H2H_HEAD_TO_HEAD.value, cutoff)
    fixture_stats_snapshot = repo.get_snapshot_for_analysis(canonical_fixture_id, home_team.id, Capability.FIXTURE_TEAM_STATISTICS.value, cutoff)
    cross_provider_snapshot = repo.get_snapshot_for_analysis(canonical_fixture_id, home_team.id, Capability.CROSS_PROVIDER_IDENTITY.value, cutoff)

    return {
        "fixture_id": canonical_fixture_id,
        "analysis_cutoff_at": cutoff,
        "competition_name": str(row["competition_name"] or ""),
        "cross_provider_identity": {
            "resolution_status": cross_provider.selected_status.value,
            "payload": cross_provider_snapshot.get("payload"),
        },
        "teams": {
            "home": {
                "team_id": home_team.id,
                "name": home_team.name,
                "recent_form": home_form_snapshot.get("payload"),
                "standings": home_standings_snapshot.get("payload"),
            },
            "away": {
                "team_id": away_team.id,
                "name": away_team.name,
                "recent_form": away_form_snapshot.get("payload"),
                "standings": away_standings_snapshot.get("payload"),
            },
        },
        "h2h": h2h_snapshot.get("payload"),
        "fixture_statistics": fixture_stats_snapshot.get("payload"),
        "capability_statuses": {
            "cross_provider_identity": cross_provider.selected_status.value,
            "current_recent_form_home": home_form.selected_status.value,
            "current_recent_form_away": away_form.selected_status.value,
            "standings_home": home_standings.status.value,
            "standings_away": away_standings.status.value,
            "h2h": h2h.status.value,
            "fixture_statistics": fixture_stats.status.value,
        },
    }
