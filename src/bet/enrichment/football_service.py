# ruff: noqa: E501, I001, W291, W293, F401, F841, UP015, UP017

import json
import hashlib
import yaml
from dataclasses import dataclass
from datetime import datetime, timezone, UTC
from typing import Any, Protocol, get_type_hints, get_origin, get_args, Union
from enum import StrEnum, Enum
from pathlib import Path
import sqlite3

from bet.db.repositories import FixtureRepo, TeamRepo, FixtureCapabilityRepo, FootballSnapshotReader
from bet.db.observation_models import create_observation, create_projection
from bet.enrichment.football_snapshot import (
    CapabilityOutcome,
    FootballEnrichmentSnapshot,
    to_dict,
    from_dict,
    canonical_hash,
    canonical_json_bytes,
    parse_datetime,
)
from bet.enrichment.models import (
    NormalizedParticipant,
    NormalizedTeamMatch,
    NormalizedMetricSet,
    NormalizedStandingTable,
    NormalizedStandingRow,
)
from bet.integration.source_result import SourceOperationResult, SourceResultStatus
from bet.integration.evidence import namespaced_source_refs, write_source_operation_bundle
from bet.api_clients.espn import ESPNClient
from bet.api_clients.api_football import APIFootballClient
from bet.api_clients.football_data_org import FootballDataOrgClient
from bet.api_clients.rate_limiter import RateLimiter


# ---------------------------------------------------------------------------
# Provider States and Registry
# ---------------------------------------------------------------------------

class ProviderState(StrEnum):
    CANDIDATE = "CANDIDATE"
    QUALIFIED_SHADOW = "QUALIFIED_SHADOW"
    PRODUCTION_ALLOWED = "PRODUCTION_ALLOWED"
    CREDENTIAL_UNAVAILABLE = "CREDENTIAL_UNAVAILABLE"
    GOVERNANCE_BLOCKED = "GOVERNANCE_BLOCKED"
    REJECTED = "REJECTED"


PROVIDER_REGISTRY = {
    "espn": ProviderState.QUALIFIED_SHADOW,
    "api-football": ProviderState.CANDIDATE,
    "football-data": ProviderState.CANDIDATE,
    "sportdb": ProviderState.CANDIDATE,
    "highlightly": ProviderState.CANDIDATE,
    "understat": ProviderState.CANDIDATE,
    "thesportsdb": ProviderState.CANDIDATE,
}


# ---------------------------------------------------------------------------
# Configuration Loader and Validator
# ---------------------------------------------------------------------------

def parse_enrichment_mode() -> str:
    import os
    raw_mode = os.environ.get("FOOTBALL_ENRICHMENT_MODE", "off")
    mode = raw_mode.strip().lower()
    if mode not in ("off", "shadow", "canary", "on"):
        raise ValueError(f"Invalid FOOTBALL_ENRICHMENT_MODE: '{raw_mode}'")
    if mode in ("canary", "on"):
        raise PermissionError(f"FOOTBALL_ENRICHMENT_MODE '{mode}' is explicitly unauthorized in this phase")
    return mode


VALID_PROVIDER_CAPABILITY_STATUSES: set[str] = {
    "CERTIFIED_SELECTABLE",
    "CERTIFIED_SHADOW",
    "PLAN_RESTRICTED_CURRENT",
    "HISTORICAL_ONLY",
    "REFERENCE_ONLY",
    "SEPARATE_PIPELINE",
    "RESEARCH_ONLY",
    "REJECTED_WITH_REASON",
    "NOT_IMPLEMENTED",
    "NOT_TESTED",
}

LEGACY_SELECTABLE_CLASSIFICATIONS: set[str] = {
    "PRODUCTION_PRIMARY",
    "PRODUCTION_FALLBACK",
    "SHADOW",
}
LEGACY_SELECTABLE_STATUSES: set[str] = {"QUALIFIED", "NARROW_SCOPE_ONLY"}
BROWSER_TRANSPORT_TYPES: set[str] = {"browser_scraper", "dom_scraper"}
ROUTE_NAME_FROM_CAPABILITY: dict[str, str] = {
    "current_recent_form": "current_form",
    "h2h_head_to_head": "historical_form_h2h",
    "standings_competition_context": "standings",
    "fixture_team_statistics": "detailed_metrics",
}
ESPN_TO_FOOTBALL_DATA_COMPETITION: dict[str, str] = {
    "eng.1": "PL",
}


def _mode_matches(entry_mode: Any, requested_mode: str) -> bool:
    normalized = str(entry_mode or "shadow")
    if requested_mode == "off":
        return normalized in {"off", "shadow"}
    return normalized == requested_mode


def _season_matches(entry_season: Any, requested_season: str) -> bool:
    normalized = str(entry_season or requested_season or "current")
    return normalized in {requested_season, "*"}


def _scope_covers(proven_scope: str, requested_scope: str) -> bool:
    if not proven_scope or not requested_scope:
        return False
    if proven_scope == requested_scope:
        return True
    if proven_scope == "football:*" and requested_scope.startswith("football:"):
        return True
    return False


def _scope_specificity(scope: str) -> int:
    return 0 if scope == "football:*" else 1


def _is_selectable_matrix_entry(entry: dict[str, Any]) -> bool:
    selectable = entry.get("selectable_as_projection")
    if isinstance(selectable, bool):
        return (
            selectable is True
            and entry.get("evidence_replay") is True
            and entry.get("status") == "CERTIFIED_SELECTABLE"
        )
    return (
        entry.get("classification") in LEGACY_SELECTABLE_CLASSIFICATIONS
        and entry.get("status") in LEGACY_SELECTABLE_STATUSES
        and entry.get("evidence_replay") is True
    )


def _normalize_route_entries(route_info: dict[str, Any]) -> list[dict[str, Any]]:
    normalized_routes: list[dict[str, Any]] = []

    def parse_bucket_list(routes_list: list[Any], bucket_name: str) -> None:
        for route in routes_list:
            if not isinstance(route, dict) or not route.get("provider"):
                continue
            normalized_routes.append(
                {
                    "provider": route["provider"],
                    "competition_scope": str(route.get("competition_scope") or "football:*"),
                    "season_scope": str(route.get("season_scope") or "current"),
                    "mode": str(route.get("mode") or "shadow"),
                    "selectable_status": str(route.get("selectable_status") or ""),
                    "bucket": bucket_name,
                }
            )

    # 1. Check explicit buckets
    if "production_routes" in route_info and isinstance(route_info["production_routes"], list):
        parse_bucket_list(route_info["production_routes"], "production")
    if "candidate_routes" in route_info and isinstance(route_info["candidate_routes"], list):
        parse_bucket_list(route_info["candidate_routes"], "candidate")
    if "shadow_routes" in route_info and isinstance(route_info["shadow_routes"], list):
        parse_bucket_list(route_info["shadow_routes"], "shadow")

    # 2. Check legacy routes list (treated as production-compatible)
    if not normalized_routes and "routes" in route_info and isinstance(route_info["routes"], list):
        parse_bucket_list(route_info["routes"], "production")

    # 3. Check legacy precedence list (treated as production-compatible)
    if not normalized_routes and "precedence" in route_info and isinstance(route_info["precedence"], list):
        for provider in route_info["precedence"]:
            if isinstance(provider, str) and provider:
                normalized_routes.append(
                    {
                        "provider": provider,
                        "competition_scope": "football:*",
                        "season_scope": "current",
                        "mode": "shadow",
                        "selectable_status": "",
                        "bucket": "production",
                    }
                )

    return normalized_routes


def _route_identity_tuple(
    route_name: str,
    route_entry: dict[str, Any],
) -> tuple[str, str, str, str, str, str, str]:
    return (
        route_name,
        str(route_entry.get("bucket") or ""),
        str(route_entry.get("provider") or ""),
        str(route_entry.get("competition_scope") or "football:*"),
        str(route_entry.get("season_scope") or "current"),
        str(route_entry.get("mode") or "shadow"),
        str(route_entry.get("selectable_status") or ""),
    )


def _find_matching_matrix_entry(
    matrix: dict[str, Any],
    *,
    provider: str,
    route_name: str,
    competition_scope: str,
    season_scope: str,
    mode: str,
) -> dict[str, Any] | None:
    provider_entry = (matrix.get("providers") or {}).get(provider)
    if not isinstance(provider_entry, dict):
        return None

    capability_entries = ((provider_entry.get("capabilities") or {}).get(route_name)) or []
    best_match: dict[str, Any] | None = None
    best_score: tuple[int, int] = (-1, -1)
    for entry in capability_entries:
        if not isinstance(entry, dict):
            continue
        if not _mode_matches(entry.get("mode"), mode):
            continue
        if not _season_matches(entry.get("season_scope"), season_scope):
            continue
        entry_scope = str(entry.get("competition_scope") or "football:*")
        if not _scope_covers(entry_scope, competition_scope):
            continue
        score = (1 if entry_scope == competition_scope else 0, _scope_specificity(entry_scope))
        if best_match is None or score > best_score:
            best_match = entry
            best_score = score
    return best_match


def load_provider_capability_matrix(config_dir: Path | str = "config") -> dict[str, Any]:
    config_dir = Path(config_dir)
    with open(config_dir / "provider_capability_matrix.json", "r", encoding="utf-8") as f:
        matrix = json.load(f)
    providers = matrix.get("providers")
    if not isinstance(providers, dict) or not providers:
        raise ValueError("Provider capability matrix must define non-empty providers")

    for provider_name, provider_entry in providers.items():
        if not isinstance(provider_entry, dict):
            raise ValueError(f"Provider entry must be an object: {provider_name}")
        transport_type = str(provider_entry.get("transport_type") or "unknown")
        capabilities = provider_entry.get("capabilities") or {}
        if not isinstance(capabilities, dict):
            raise ValueError(f"Provider capabilities must be a mapping: {provider_name}")
        seen_tuples: set[tuple[str, str, str, str]] = set()
        for capability_name, capability_entries in capabilities.items():
            if not isinstance(capability_entries, list):
                raise ValueError(f"Capability entries must be a list: {provider_name}/{capability_name}")
            for entry in capability_entries:
                if not isinstance(entry, dict):
                    raise ValueError(f"Capability entry must be an object: {provider_name}/{capability_name}")
                status = str(entry.get("status") or "")
                selectable = entry.get("selectable_as_projection")
                if status and status not in VALID_PROVIDER_CAPABILITY_STATUSES and status not in LEGACY_SELECTABLE_STATUSES:
                    raise ValueError(f"Unsupported status for {provider_name}/{capability_name}: {status}")
                if selectable is None:
                    if status in VALID_PROVIDER_CAPABILITY_STATUSES:
                        raise ValueError(
                            f"Capability entry missing selectable_as_projection: {provider_name}/{capability_name}"
                        )
                elif not isinstance(selectable, bool):
                    raise ValueError(
                        f"selectable_as_projection must be boolean: {provider_name}/{capability_name}"
                    )
                if selectable is True and status != "CERTIFIED_SELECTABLE":
                    raise ValueError(
                        f"Only CERTIFIED_SELECTABLE entries may be selectable: {provider_name}/{capability_name}"
                    )
                if selectable is True and not bool(entry.get("evidence_replay")):
                    raise ValueError(
                        f"Selectable entry requires evidence_replay=true: {provider_name}/{capability_name}"
                    )
                if selectable is True and transport_type in BROWSER_TRANSPORT_TYPES:
                    raise ValueError(
                        f"Browser/DOM transport cannot be production-selectable: {provider_name}/{capability_name}"
                    )
                tuple_key = (
                    capability_name,
                    str(entry.get("competition_scope") or "football:*"),
                    str(entry.get("season_scope") or "current"),
                    str(entry.get("mode") or "shadow"),
                )
                if tuple_key in seen_tuples:
                    raise ValueError(
                        f"Duplicate capability scope tuple in matrix: {provider_name}/{capability_name}/{tuple_key[1]}/{tuple_key[2]}/{tuple_key[3]}"
                    )
                seen_tuples.add(tuple_key)
    return matrix


def _resolve_route_qualification(
    matrix: dict[str, Any],
    *,
    provider: str,
    route_name: str,
    mode: str,
    competition_scope: str = "football:*",
    season_scope: str = "current",
    require_selectable: bool = False,
) -> dict[str, Any] | None:
    entry = _find_matching_matrix_entry(
        matrix,
        provider=provider,
        route_name=route_name,
        competition_scope=competition_scope,
        season_scope=season_scope,
        mode=mode,
    )
    if entry is None:
        return None
    if require_selectable:
        provider_entry = (matrix.get("providers") or {}).get(provider) or {}
        transport_type = str(provider_entry.get("transport_type") or "unknown")
        if not _is_selectable_matrix_entry(entry):
            return None
        if transport_type in BROWSER_TRANSPORT_TYPES:
            return None
    return entry


def get_route_candidates(
    config: dict[str, Any],
    route_name: str,
    requested_competition_scope: str,
    *,
    season_scope: str = "current",
    mode: str | None = None,
    selectable_only: bool = False,
) -> list[dict[str, Any]]:
    requested_mode = mode or parse_enrichment_mode()
    route_info = (config.get("routing") or {}).get(route_name) or {}
    matrix = config.get("provider_capability_matrix") or {}
    candidates: list[dict[str, Any]] = []
    for route_entry in _normalize_route_entries(route_info):
        if selectable_only and route_entry.get("bucket") != "production":
            continue
        route_scope = str(route_entry.get("competition_scope") or "football:*")
        if not _scope_covers(route_scope, requested_competition_scope):
            continue
        entry_mode = str(route_entry.get("mode") or requested_mode)
        entry = _resolve_route_qualification(
            matrix,
            provider=route_entry["provider"],
            route_name=route_name,
            mode=entry_mode,
            competition_scope=requested_competition_scope,
            season_scope=season_scope,
            require_selectable=selectable_only,
        )
        if entry is None:
            continue
        if selectable_only and not _is_selectable_matrix_entry(entry):
            continue
        candidates.append({**route_entry, "matrix_entry": entry})
    return candidates


def select_route_provider(
    config: dict[str, Any],
    route_name: str,
    requested_competition_scope: str,
    *,
    season_scope: str = "current",
    mode: str | None = None,
) -> dict[str, Any] | None:
    candidates = get_route_candidates(
        config,
        route_name,
        requested_competition_scope,
        season_scope=season_scope,
        mode=mode,
        selectable_only=True,
    )
    return candidates[0] if candidates else None


def require_production_route(
    config: dict[str, Any],
    route_name: str,
    requested_competition_scope: str,
    *,
    season_scope: str = "current",
    mode: str | None = None,
) -> dict[str, Any]:
    route = select_route_provider(
        config,
        route_name,
        requested_competition_scope,
        season_scope=season_scope,
        mode=mode,
    )
    if route is None:
        raise ValueError(
            f"No CERTIFIED_SELECTABLE route for {route_name} scope={requested_competition_scope} season={season_scope}"
        )
    return route


def load_and_validate_config(config_dir: Path | str = "config") -> dict[str, Any]:
    config_dir = Path(config_dir)
    mode = parse_enrichment_mode()
    
    # Load capabilities
    with open(config_dir / "football_capabilities.yaml", "r") as f:
        caps_data = yaml.safe_load(f) or {}
    capabilities = caps_data.get("capabilities", {})
    
    # Load freshness
    with open(config_dir / "football_freshness.yaml", "r") as f:
        fresh_data = yaml.safe_load(f) or {}
    freshness = fresh_data.get("freshness", {})
    
    # Load routing
    with open(config_dir / "football_routing.yaml", "r") as f:
        routing_data = yaml.safe_load(f) or {}
    routing = routing_data.get("routing", {})

    provider_capability_matrix = load_provider_capability_matrix(config_dir)
    
    # Load metrics
    with open(config_dir / "football_metrics.yaml", "r") as f:
        metrics_data = yaml.safe_load(f) or {}
    metrics = metrics_data.get("metrics", {})
    
    # Validation rules:
    # 1. Reject unknown capability names in routing
    # 2. Validate freshness values (must be positive integers)
    for k, v in freshness.items():
        if not isinstance(v, int) or v <= 0:
            raise ValueError(f"Invalid freshness value for {k}: {v}")
            
    # 3. Validate routing
    for route_name, route_info in routing.items():
        normalized_routes = _normalize_route_entries(route_info or {})
        seen_route_identities: set[tuple[str, str, str, str, str, str, str]] = set()
        for route_entry in normalized_routes:
            route_identity = _route_identity_tuple(route_name, route_entry)
            if route_identity in seen_route_identities:
                raise ValueError(
                    "Duplicate route identity in route "
                    f"{route_name}: {route_identity}"
                )
            seen_route_identities.add(route_identity)

        for route_entry in normalized_routes:
            provider = route_entry["provider"]
            if provider not in provider_capability_matrix["providers"]:
                raise ValueError(f"Unknown provider in route {route_name}: {provider}")

            competition_scope = route_entry["competition_scope"]
            season_scope = route_entry["season_scope"]
            route_mode = route_entry["mode"]

            # Find exact match in matrix
            provider_entry = provider_capability_matrix["providers"][provider]
            capability_entries = (provider_entry.get("capabilities") or {}).get(route_name) or []

            exact_match = None
            for entry in capability_entries:
                if (
                    str(entry.get("competition_scope") or "football:*") == competition_scope
                    and str(entry.get("season_scope") or "current") == season_scope
                    and str(entry.get("mode") or "shadow") == route_mode
                ):
                    exact_match = entry
                    break

            if exact_match is None:
                raise ValueError(
                    f"Route {route_name}/{provider} has no exact matrix tuple for scope={competition_scope} season={season_scope} mode={route_mode}"
                )

            selectable_status = route_entry.get("selectable_status")
            matrix_status = str(exact_match.get("status") or "")
            if selectable_status and selectable_status != matrix_status:
                raise ValueError(
                    f"Route {route_name}/{provider} selectable_status={selectable_status} disagrees with matrix status={matrix_status}"
                )

            if route_entry.get("bucket") == "production":
                if (
                    matrix_status != "CERTIFIED_SELECTABLE"
                    or exact_match.get("selectable_as_projection") is not True
                    or exact_match.get("evidence_replay") is not True
                ):
                    raise ValueError(
                        f"Production route {route_name}/{provider} exact matrix tuple is not CERTIFIED_SELECTABLE with selectable_as_projection=true and evidence_replay=true"
                    )
                
    # Compute policy_config_hash from canonicalized contents of the configuration actually used for the run
    canonical_config = {
        "capabilities": capabilities,
        "freshness": freshness,
        "routing": routing,
        "metrics": metrics,
        "provider_capability_matrix": provider_capability_matrix,
    }
    config_json = json.dumps(canonical_config, sort_keys=True, separators=(",", ":"))
    policy_config_hash = hashlib.sha256(config_json.encode("utf-8")).hexdigest()
    
    return {
        "capabilities": capabilities,
        "freshness": freshness,
        "routing": routing,
        "metrics": metrics,
        "provider_capability_matrix": provider_capability_matrix,
        "policy_config_hash": policy_config_hash,
    }


# ---------------------------------------------------------------------------
# Football Capability-Adapter Protocol and Implementations
# ---------------------------------------------------------------------------

class FootballCapabilityAdapter(Protocol):
    @property
    def provider(self) -> str:
        ...

    def fetch_capability(
        self,
        capability: str,
        canonical_fixture_id: int,
        analysis_cutoff_at: datetime,
        **kwargs
    ) -> SourceOperationResult[Any]:
        ...


class ESPNFootballAdapter:
    def __init__(self, client: ESPNClient):
        self.client = client
        self.provider_name = "espn"

    @property
    def provider(self) -> str:
        return self.provider_name

    def fetch_capability(
        self,
        capability: str,
        canonical_fixture_id: int,
        analysis_cutoff_at: datetime,
        **kwargs
    ) -> SourceOperationResult[Any]:
        if capability == "current_recent_form":
            team_id = kwargs.get("team_id")
            native_team_id = kwargs.get("native_team_id")
            target_event_id = kwargs.get("native_fixture_id")
            
            if not native_team_id:
                return SourceOperationResult(SourceResultStatus.NOT_FOUND, error_code="native_team_id_missing")
                
            last_fixtures_res = self.client.get_team_last_fixtures_result(
                native_team_id,
                last_n=5,
                analysis_cutoff_at=analysis_cutoff_at.isoformat(),
                exclude_event_ids={target_event_id} if target_event_id else None
            )
            
            if last_fixtures_res.status is not SourceResultStatus.SUCCESS:
                return SourceOperationResult(
                    status=last_fixtures_res.status,
                    http_status=last_fixtures_res.http_status,
                    error_code=last_fixtures_res.error_code,
                    evidence_refs=last_fixtures_res.evidence_refs,
                )
                
            last_fixtures = last_fixtures_res.value or []
            if not last_fixtures:
                return SourceOperationResult(
                    status=SourceResultStatus.VALID_EMPTY,
                    value=[],
                    evidence_refs=last_fixtures_res.evidence_refs,
                )
                
            matches = []
            evidence_refs = list(last_fixtures_res.evidence_refs)
            
            for fix_data in last_fixtures:
                fix_id = str(fix_data.get("id", ""))
                if not fix_id:
                    continue
                    
                stats_res = self.client.get_fixture_stats_result(fix_id)
                evidence_refs.extend(stats_res.evidence_refs)
                
                if stats_res.status is not SourceResultStatus.SUCCESS or not stats_res.value:
                    continue
                    
                for ms in stats_res.value:
                    home_id = getattr(ms, "home_participant_id", "")
                    away_id = getattr(ms, "away_participant_id", "")
                    
                    if str(native_team_id) not in (str(home_id), str(away_id)):
                        continue
                        
                    is_home = str(native_team_id) == str(home_id)
                    opp_id = away_id if is_home else home_id
                    goals_val = ms.stats.get("goals", {}).get("home" if is_home else "away", 0)
                    
                    match_dto = NormalizedTeamMatch(
                        canonical_fixture_id=None,
                        native_fixture_id=fix_id,
                        provider="espn",
                        source_timestamp=analysis_cutoff_at,
                        team_canonical_id=team_id,
                        team_native_id=str(native_team_id),
                        opponent_canonical_id=None,
                        opponent_native_id=str(opp_id),
                        kickoff_at=parse_datetime(fix_data.get("date")),
                        metrics=NormalizedMetricSet(
                            provider="espn",
                            source_timestamp=analysis_cutoff_at,
                            values={"goals": goals_val}
                        )
                    )
                    matches.append(match_dto)
                    
            if not evidence_refs:
                return SourceOperationResult(SourceResultStatus.EVIDENCE_ERROR, error_code="no_evidence_refs")
                
            source_refs = namespaced_source_refs("espn-football", [target_event_id] if target_event_id else [])
            bundle_id, _ = write_source_operation_bundle(
                registered_source_key="espn-football",
                operation_name="current_recent_form",
                request_identity=f"GET /teams/{native_team_id}/schedule",
                parser_version="espn-v1",
                source_event_refs=source_refs,
                evidence_refs=evidence_refs,
            )
            
            return SourceOperationResult(
                status=SourceResultStatus.SUCCESS,
                value=matches,
                provider="espn",
                operation="current_recent_form",
                request_identity=f"GET /teams/{native_team_id}/schedule",
                evidence_refs=tuple(evidence_refs),
                bundle_id=bundle_id,
                retrieved_at=datetime.now(timezone.utc),
            )

        elif capability == "h2h_head_to_head":
            team1_id = kwargs.get("team1_id")
            team2_id = kwargs.get("team2_id")
            native_team1_id = kwargs.get("native_team1_id")
            native_team2_id = kwargs.get("native_team2_id")
            target_event_id = kwargs.get("native_fixture_id")
            
            if not native_team1_id or not native_team2_id:
                return SourceOperationResult(SourceResultStatus.NOT_FOUND, error_code="native_team_ids_missing")
                
            h2h_res = self.client.get_h2h_result(
                native_team1_id,
                native_team2_id,
                analysis_cutoff_at=analysis_cutoff_at.isoformat(),
                exclude_event_ids={target_event_id} if target_event_id else None,
                last_n=5
            )
            
            if h2h_res.status is not SourceResultStatus.SUCCESS:
                return SourceOperationResult(
                    status=h2h_res.status,
                    http_status=h2h_res.http_status,
                    error_code=h2h_res.error_code,
                    evidence_refs=h2h_res.evidence_refs,
                )
                
            meetings = h2h_res.value or []
            if not meetings:
                return SourceOperationResult(
                    status=SourceResultStatus.VALID_EMPTY,
                    value=[],
                    evidence_refs=h2h_res.evidence_refs,
                )
                
            matches = []
            evidence_refs = list(h2h_res.evidence_refs)
            
            for meeting in meetings:
                fix_id = meeting.get("event_id")
                home_id = meeting.get("home_participant_id")
                away_id = meeting.get("away_participant_id")
                score = meeting.get("score", "")
                
                home_goals = 0
                away_goals = 0
                if "-" in score:
                    try:
                        home_goals, away_goals = map(int, score.split("-"))
                    except ValueError:
                        pass
                        
                match_dto = NormalizedTeamMatch(
                    canonical_fixture_id=None,
                    native_fixture_id=fix_id,
                    provider="espn",
                    source_timestamp=analysis_cutoff_at,
                    team_canonical_id=team1_id if str(home_id) == str(native_team1_id) else team2_id,
                    team_native_id=str(home_id),
                    opponent_canonical_id=team2_id if str(home_id) == str(native_team1_id) else team1_id,
                    opponent_native_id=str(away_id),
                    kickoff_at=parse_datetime(meeting.get("date")),
                    metrics=NormalizedMetricSet(
                        provider="espn",
                        source_timestamp=analysis_cutoff_at,
                        values={"goals": home_goals if str(home_id) == str(native_team1_id) else away_goals}
                    )
                )
                matches.append(match_dto)
                
            if not evidence_refs:
                return SourceOperationResult(SourceResultStatus.EVIDENCE_ERROR, error_code="no_evidence_refs")
                
            source_refs = namespaced_source_refs("espn-football", [target_event_id] if target_event_id else [])
            bundle_id, _ = write_source_operation_bundle(
                registered_source_key="espn-football",
                operation_name="h2h_head_to_head",
                request_identity=f"GET /teams/{native_team1_id}/schedule",
                parser_version="espn-v1",
                source_event_refs=source_refs,
                evidence_refs=evidence_refs,
            )
            
            return SourceOperationResult(
                status=SourceResultStatus.SUCCESS,
                value=matches,
                provider="espn",
                operation="h2h_head_to_head",
                request_identity=f"GET /teams/{native_team1_id}/schedule",
                evidence_refs=tuple(evidence_refs),
                bundle_id=bundle_id,
                retrieved_at=datetime.now(timezone.utc),
            )

        elif capability == "standings_competition_context":
            competition_id = kwargs.get("competition_id")
            native_competition_id = kwargs.get("native_competition_id")
            
            standings_res = self.client.get_standings_result()
            
            if standings_res.status is not SourceResultStatus.SUCCESS:
                return SourceOperationResult(
                    status=standings_res.status,
                    http_status=standings_res.http_status,
                    error_code=standings_res.error_code,
                    evidence_refs=standings_res.evidence_refs,
                )
                
            raw_rows = standings_res.value or []
            if not raw_rows:
                return SourceOperationResult(
                    status=SourceResultStatus.VALID_EMPTY,
                    value=None,
                    evidence_refs=standings_res.evidence_refs,
                )
                
            rows = []
            for r in raw_rows:
                row_dto = NormalizedStandingRow(
                    team_canonical_id=None,
                    team_native_id=str(r.get("team_id")),
                    rank=int(r.get("rank") or 0),
                    points=int(r.get("points") or 0),
                    played=int(r.get("played") or 0),
                    wins=int(r.get("wins") or 0),
                    draws=int(r.get("draws") or 0),
                    losses=int(r.get("losses") or 0),
                    goals_for=int(r.get("goals_for") or 0),
                    goals_against=int(r.get("goals_against") or 0),
                    goal_diff=int(r.get("goal_diff") or 0),
                    form=str(r.get("form") or "")
                )
                rows.append(row_dto)
                
            table_dto = NormalizedStandingTable(
                competition_canonical_id=competition_id,
                competition_native_id=str(native_competition_id),
                provider="espn",
                source_timestamp=analysis_cutoff_at,
                rows=tuple(rows)
            )
            
            if not standings_res.evidence_refs:
                return SourceOperationResult(SourceResultStatus.EVIDENCE_ERROR, error_code="no_evidence_refs")
                
            bundle_id, _ = write_source_operation_bundle(
                registered_source_key="espn-football",
                operation_name="standings_competition_context",
                request_identity="GET /standings",
                parser_version="espn-v1",
                source_event_refs=[],
                evidence_refs=list(standings_res.evidence_refs),
            )
            
            return SourceOperationResult(
                status=SourceResultStatus.SUCCESS,
                value=table_dto,
                provider="espn",
                operation="standings_competition_context",
                request_identity="GET /standings",
                evidence_refs=standings_res.evidence_refs,
                bundle_id=bundle_id,
                retrieved_at=datetime.now(timezone.utc),
            )

        elif capability == "fixture_team_statistics":
            native_fixture_id = kwargs.get("native_fixture_id")
            
            if not native_fixture_id:
                return SourceOperationResult(SourceResultStatus.NOT_FOUND, error_code="native_fixture_id_missing")
                
            stats_res = self.client.get_fixture_stats_result(native_fixture_id)
            
            if stats_res.status is not SourceResultStatus.SUCCESS:
                return SourceOperationResult(
                    status=stats_res.status,
                    http_status=stats_res.http_status,
                    error_code=stats_res.error_code,
                    evidence_refs=stats_res.evidence_refs,
                )
                
            raw_stats = stats_res.value or []
            if not raw_stats:
                return SourceOperationResult(
                    status=SourceResultStatus.VALID_EMPTY,
                    value=None,
                    evidence_refs=stats_res.evidence_refs,
                )
                
            ms = raw_stats[0]
            metric_set = NormalizedMetricSet(
                provider="espn",
                source_timestamp=analysis_cutoff_at,
                values=ms.stats
            )
            
            if not stats_res.evidence_refs:
                return SourceOperationResult(SourceResultStatus.EVIDENCE_ERROR, error_code="no_evidence_refs")
                
            bundle_id, _ = write_source_operation_bundle(
                registered_source_key="espn-football",
                operation_name="fixture_team_statistics",
                request_identity=f"GET /summary?event={native_fixture_id}",
                parser_version="espn-v1",
                source_event_refs=namespaced_source_refs("espn-football", [native_fixture_id]),
                evidence_refs=list(stats_res.evidence_refs),
            )
            
            return SourceOperationResult(
                status=SourceResultStatus.SUCCESS,
                value=metric_set,
                provider="espn",
                operation="fixture_team_statistics",
                request_identity=f"GET /summary?event={native_fixture_id}",
                evidence_refs=stats_res.evidence_refs,
                bundle_id=bundle_id,
                retrieved_at=datetime.now(timezone.utc),
            )

        return SourceOperationResult(
            status=SourceResultStatus.NOT_SUPPORTED,
            error_code="capability_not_supported",
        )


class APIFootballCandidateAdapter:
    def __init__(self, client: APIFootballClient):
        self.client = client
        self.provider_name = "api-football"

    @property
    def provider(self) -> str:
        return self.provider_name

    def fetch_capability(
        self,
        capability: str,
        canonical_fixture_id: int,
        analysis_cutoff_at: datetime,
        **kwargs
    ) -> SourceOperationResult[Any]:
        native_fixture_id = kwargs.get("native_fixture_id")
        if capability == "fixture_team_statistics":
            if not native_fixture_id:
                return SourceOperationResult(SourceResultStatus.NOT_FOUND, error_code="native_fixture_id_missing")
            res = self.client.get_fixture_stats_result(native_fixture_id)
            return res
        return SourceOperationResult(SourceResultStatus.NOT_SUPPORTED, error_code="capability_not_supported")


class FootballDataStandingsAdapter:
    def __init__(self, client: FootballDataOrgClient):
        self.client = client
        self.provider_name = "football-data"

    @property
    def provider(self) -> str:
        return self.provider_name

    def fetch_capability(
        self,
        capability: str,
        canonical_fixture_id: int,
        analysis_cutoff_at: datetime,
        **kwargs,
    ) -> SourceOperationResult[Any]:
        if capability != "standings_competition_context":
            return SourceOperationResult(SourceResultStatus.NOT_SUPPORTED, error_code="capability_not_supported")

        competition_id = kwargs.get("competition_id")
        native_competition_id = str(kwargs.get("native_competition_id") or "").strip()
        provider_competition_id = ESPN_TO_FOOTBALL_DATA_COMPETITION.get(
            native_competition_id,
            native_competition_id,
        )
        if not provider_competition_id:
            return SourceOperationResult(SourceResultStatus.NOT_FOUND, error_code="native_competition_id_missing")

        standings_res = self.client.get_standings_result(provider_competition_id)
        if standings_res.status is not SourceResultStatus.SUCCESS:
            return SourceOperationResult(
                status=standings_res.status,
                http_status=standings_res.http_status,
                error_code=standings_res.error_code,
                evidence_refs=standings_res.evidence_refs,
                bundle_id=standings_res.bundle_id,
            )

        raw_tables = standings_res.value or []
        if not raw_tables:
            return SourceOperationResult(
                status=SourceResultStatus.VALID_EMPTY,
                value=None,
                evidence_refs=standings_res.evidence_refs,
                bundle_id=standings_res.bundle_id,
            )

        first_table = raw_tables[0] if isinstance(raw_tables[0], dict) else {}
        raw_rows = first_table.get("table", []) if isinstance(first_table, dict) else []
        if not raw_rows:
            return SourceOperationResult(
                status=SourceResultStatus.VALID_EMPTY,
                value=None,
                evidence_refs=standings_res.evidence_refs,
                bundle_id=standings_res.bundle_id,
            )

        rows: list[NormalizedStandingRow] = []
        for row in raw_rows:
            team = row.get("team", {}) if isinstance(row, dict) else {}
            rows.append(
                NormalizedStandingRow(
                    team_canonical_id=None,
                    team_native_id=str(team.get("id", "")),
                    rank=int(row.get("position") or 0),
                    points=int(row.get("points") or 0),
                    played=int(row.get("playedGames") or 0),
                    wins=int(row.get("won") or 0),
                    draws=int(row.get("draw") or 0),
                    losses=int(row.get("lost") or 0),
                    goals_for=int(row.get("goalsFor") or 0),
                    goals_against=int(row.get("goalsAgainst") or 0),
                    goal_diff=int(row.get("goalDifference") or 0),
                    form=str(row.get("form") or ""),
                )
            )

        table = NormalizedStandingTable(
            competition_canonical_id=competition_id,
            competition_native_id=provider_competition_id,
            provider="football-data",
            source_timestamp=analysis_cutoff_at,
            rows=tuple(rows),
        )
        return SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=table,
            provider="football-data",
            operation="standings_competition_context",
            request_identity=f"GET /competitions/{provider_competition_id}/standings",
            evidence_refs=standings_res.evidence_refs,
            bundle_id=standings_res.bundle_id,
            retrieved_at=datetime.now(timezone.utc),
        )


class FootballAdapterRegistry:
    def __init__(self):
        self._adapters = {}

    def register(self, provider: str, adapter: FootballCapabilityAdapter) -> None:
        self._adapters[provider] = adapter

    def get(self, provider: str) -> FootballCapabilityAdapter | None:
        return self._adapters.get(provider)


# ---------------------------------------------------------------------------
# Executable Candidate Registry and Probe Runner
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CandidateRecord:
    """
    Inventory and probe metadata only.
    This record is strictly for tracking candidate capabilities and probe eligibility.
    It has absolutely no production routing or selection implication.
    Production routing is governed solely by the provider capability matrix and routing configuration.
    """
    provider_key: str
    implementation_state: str
    credential_requirement: bool
    governance_state: str
    provenance_family: str
    supported_capabilities: tuple[str, ...]
    replay_capabilities: tuple[str, ...]
    live_probe_eligibility: bool
    reason_when_blocked: str = ""


CANDIDATE_REGISTRY: dict[str, CandidateRecord] = {
    "espn": CandidateRecord(
        provider_key="espn",
        implementation_state="PRODUCTION_READY",
        credential_requirement=False,
        governance_state="QUALIFIED_SHADOW",
        provenance_family="espn-football",
        supported_capabilities=("current_recent_form", "h2h_head_to_head", "standings_competition_context", "fixture_team_statistics"),
        replay_capabilities=("current_recent_form", "h2h_head_to_head", "standings_competition_context", "fixture_team_statistics"),
        live_probe_eligibility=True,
    ),
    "api-football": CandidateRecord(
        provider_key="api-football",
        implementation_state="LIVE_PARTIAL",
        credential_requirement=True,
        governance_state="CANDIDATE",
        provenance_family="api-football",
        supported_capabilities=("current_recent_form", "h2h_head_to_head", "standings_competition_context", "fixture_team_statistics"),
        replay_capabilities=("current_recent_form", "h2h_head_to_head", "standings_competition_context", "fixture_team_statistics"),
        live_probe_eligibility=True,
    ),
    "football-data": CandidateRecord(
        provider_key="football-data",
        implementation_state="IMPLEMENTED_UNVERIFIED",
        credential_requirement=True,
        governance_state="CANDIDATE",
        provenance_family="football-data-org",
        supported_capabilities=("current_discovery", "standings_competition_context"),
        replay_capabilities=(),
        live_probe_eligibility=False,
        reason_when_blocked="unverified_implementation",
    ),
    "thesportsdb": CandidateRecord(
        provider_key="thesportsdb",
        implementation_state="IMPLEMENTED_UNVERIFIED",
        credential_requirement=True,
        governance_state="CANDIDATE",
        provenance_family="thesportsdb",
        supported_capabilities=("current_recent_form", "h2h_head_to_head"),
        replay_capabilities=(),
        live_probe_eligibility=False,
        reason_when_blocked="unverified_implementation",
    ),
    "sportdb": CandidateRecord(
        provider_key="sportdb",
        implementation_state="NOT_IMPLEMENTED",
        credential_requirement=False,
        governance_state="STRATEGIC_P2E",
        provenance_family="sportdb",
        supported_capabilities=(),
        replay_capabilities=(),
        live_probe_eligibility=False,
        reason_when_blocked="no_implementation",
    ),
    "highlightly": CandidateRecord(
        provider_key="highlightly",
        implementation_state="IMPLEMENTED_SCOPE_LIMITED",
        credential_requirement=True,
        governance_state="CANDIDATE",
        provenance_family="highlightly",
        supported_capabilities=("current_recent_form", "h2h_head_to_head", "fixture_team_statistics"),
        replay_capabilities=("current_recent_form", "h2h_head_to_head", "fixture_team_statistics"),
        live_probe_eligibility=True,
    ),
    "understat": CandidateRecord(
        provider_key="understat",
        implementation_state="IMPLEMENTED_UNVERIFIED",
        credential_requirement=False,
        governance_state="CANDIDATE",
        provenance_family="understat",
        supported_capabilities=("advanced_xg",),
        replay_capabilities=(),
        live_probe_eligibility=False,
        reason_when_blocked="narrow_scope",
    ),
}


class ProbeRunner:
    def __init__(
        self,
        allow_live: bool = False,
        provider_budgets: dict[str, int] | None = None,
        global_budget: int = 10,
    ):
        self.allow_live = allow_live
        self.provider_budgets = provider_budgets or {"espn": 5, "api-football": 5}
        self.global_budget = global_budget
        self.call_ledger: list[dict[str, Any]] = []

    def run_probe(
        self,
        provider: str,
        operation: str,
        **kwargs
    ) -> SourceOperationResult[Any]:
        if provider not in CANDIDATE_REGISTRY:
            raise ValueError(f"Provider {provider} not found in candidate registry")
            
        record = CANDIDATE_REGISTRY[provider]
        
        # 1. if operation is not in record.supported_capabilities, block as not supported
        if operation not in record.supported_capabilities:
            return SourceOperationResult(
                status=SourceResultStatus.NOT_SUPPORTED,
                error_code="capability_not_supported",
            )
            
        # 2. live_probe_eligibility must gate only live probing, not offline replay
        if self.allow_live:
            if not record.live_probe_eligibility:
                return SourceOperationResult(
                    status=SourceResultStatus.BLOCKED,
                    error_code="probe_blocked",
                    parser_diagnostics={"reason": record.reason_when_blocked or "not_eligible"}
                )
        else:
            # 3. when allow_live=False, enforce capability-scoped replay via record.replay_capabilities and retained evidence requirements
            if operation not in record.replay_capabilities:
                return SourceOperationResult(
                    status=SourceResultStatus.BLOCKED,
                    error_code="probe_blocked",
                    parser_diagnostics={"reason": record.reason_when_blocked or "not_eligible"}
                )

        provider_calls = len([c for c in self.call_ledger if c["provider"] == provider])
        if provider_calls >= self.provider_budgets.get(provider, 0):
            return SourceOperationResult(SourceResultStatus.RATE_LIMITED, error_code="provider_budget_exceeded")
            
        if len(self.call_ledger) >= self.global_budget:
            return SourceOperationResult(SourceResultStatus.RATE_LIMITED, error_code="global_budget_exceeded")
            
        if not self.allow_live:
            bundle_id = kwargs.get("bundle_id")
            adapter = kwargs.get("adapter")
            if bundle_id and adapter:
                try:
                    canonical_fixture_id = kwargs.get("canonical_fixture_id", 0)
                    analysis_cutoff_at = kwargs.get("analysis_cutoff_at") or datetime.now(UTC)
                    res = adapter.fetch_capability(
                        operation,
                        canonical_fixture_id,
                        analysis_cutoff_at,
                        **kwargs
                    )
                    self.call_ledger.append({
                        "provider": provider,
                        "operation": operation,
                        "mode": "offline_replay",
                        "timestamp": datetime.now(UTC).isoformat(),
                    })
                    return res
                except Exception as e:
                    return SourceOperationResult(
                        status=SourceResultStatus.EVIDENCE_ERROR,
                        error_code="replay_failed",
                        parser_diagnostics={"error": str(e)}
                    )
            else:
                return SourceOperationResult(
                    status=SourceResultStatus.BLOCKED,
                    error_code="RETAINED_EVIDENCE_REQUIRED",
                )
            
        raise PermissionError("External network calls are blocked by default. Live mode is unused in this session.")


# ---------------------------------------------------------------------------
# Football Enrichment Service
# ---------------------------------------------------------------------------

def verify_evidence_bundle(bundle_id: str) -> bool:
    if not bundle_id or bundle_id == "test_bundle_id":
        return False
    try:
        from bet.integration.evidence import load_bundle_manifest
        manifest = load_bundle_manifest(bundle_id)
        # Check for dummy object_sha256
        for entry in manifest.get("entries", []):
            if entry.object_sha256 in ("abc", "test_sha256", ""):
                return False
        return True
    except Exception:
        return False


def get_most_informative_status(results: list[SourceOperationResult]) -> str:
    if not results:
        return "NOT_SUPPORTED"
    # Define status priority (lower index = more informative)
    priority = [
        "VALID_EMPTY",
        "NOT_PUBLISHED_YET",
        "PLAN_RESTRICTED",
        "RATE_LIMITED",
        "TIMEOUT",
        "UPSTREAM_ERROR",
        "PARSE_ERROR",
        "SCHEMA_ERROR",
        "EVIDENCE_ERROR",
        "AMBIGUOUS",
        "PARTIAL",
        "NOT_FOUND",
        "NOT_SUPPORTED",
    ]
    # Find the result with the highest priority status
    best_status = "NOT_SUPPORTED"
    best_idx = len(priority)
    for r in results:
        status_str = r.status.value if isinstance(r.status, Enum) else str(r.status)
        if status_str in priority:
            idx = priority.index(status_str)
            if idx < best_idx:
                best_idx = idx
                best_status = status_str
        else:
            # If it's some other status, use it if we don't have anything better
            if best_idx == len(priority):
                best_status = status_str
    return best_status


def _is_capability_outcome_satisfied(status: str) -> bool:
    return status in {"SUCCESS", "VALID_EMPTY"}


def _derive_snapshot_state(capability_outcomes: list[CapabilityOutcome]) -> str:
    required = [outcome for outcome in capability_outcomes if outcome.required]
    if required and all(outcome.satisfied for outcome in required):
        return "COMPLETE"
    if any(outcome.satisfied for outcome in required):
        return "DEGRADED"
    return "BLOCKED"


class FootballEnrichmentService:
    def __init__(self, adapter_registry: FootballAdapterRegistry | None = None):
        self.adapter_registry = adapter_registry or FootballAdapterRegistry()

    def enrich_fixture(
        self,
        canonical_fixture_id: int,
        analysis_cutoff_at: datetime,
        *,
        force_refresh: bool = False,
    ) -> FootballEnrichmentSnapshot:
        """Enrich a football fixture and publish an atomic immutable snapshot."""
        from bet.db.connection import get_db
        
        # Validate mode
        try:
            mode = parse_enrichment_mode()
        except Exception as e:
            raise RuntimeError(f"Configuration error: {e}") from e

        if analysis_cutoff_at.tzinfo is None:
            analysis_cutoff_at = analysis_cutoff_at.replace(tzinfo=UTC)
        else:
            analysis_cutoff_at = analysis_cutoff_at.astimezone(UTC)

        # Load and validate config
        config = load_and_validate_config()
        policy_config_hash = config["policy_config_hash"]

        # Compute run identity
        base_identity = hashlib.sha256(
            f"football|{canonical_fixture_id}|{analysis_cutoff_at.isoformat()}|{policy_config_hash}".encode()
        ).hexdigest()
        
        if force_refresh:
            run_identity = f"{base_identity}_ref_{int(datetime.now(UTC).timestamp())}"
        else:
            run_identity = base_identity

        # Idempotency check
        if not force_refresh:
            with get_db() as conn:
                existing_run = conn.execute(
                    "SELECT id FROM sports_enrichment_run WHERE run_identity = ? AND status = 'COMPLETE'",
                    (run_identity,)
                ).fetchone()
                if existing_run:
                    reader = FootballSnapshotReader(conn)
                    snap = reader.get_snapshot(canonical_fixture_id)
                    if snap:
                        return snap

        # STAGE 1: Prepare (in a short DB transaction)
        with get_db() as conn:
            fixture_repo = FixtureRepo(conn)
            team_repo = TeamRepo(conn)

            # 1. Resolve fixture and teams
            fixture = fixture_repo.get_by_id(canonical_fixture_id)
            if not fixture:
                raise ValueError(f"Fixture {canonical_fixture_id} not found")

            home_team = team_repo.get_by_id(fixture.home_team_id)
            away_team = team_repo.get_by_id(fixture.away_team_id)
            if not home_team or not away_team:
                raise ValueError(f"Teams for fixture {canonical_fixture_id} not found")

            # Fetch native IDs from fixture_sources
            espn_fixture_row = conn.execute(
                "SELECT external_id FROM fixture_sources WHERE fixture_id = ? AND source = 'espn-football'",
                (canonical_fixture_id,)
            ).fetchone()
            native_fixture_id = espn_fixture_row["external_id"] if espn_fixture_row else ""

            espn_home_row = conn.execute(
                "SELECT provider_entity_id FROM source_entity_reference WHERE canonical_entity_id = (SELECT id FROM sports_entity WHERE domain_entity_id = ? AND domain_table = 'teams') AND provider = 'espn-football'",
                (fixture.home_team_id,)
            ).fetchone()
            native_home_id = espn_home_row["provider_entity_id"] if espn_home_row else ""

            espn_away_row = conn.execute(
                "SELECT provider_entity_id FROM source_entity_reference WHERE canonical_entity_id = (SELECT id FROM sports_entity WHERE domain_entity_id = ? AND domain_table = 'teams') AND provider = 'espn-football'",
                (fixture.away_team_id,)
            ).fetchone()
            native_away_id = espn_away_row["provider_entity_id"] if espn_away_row else ""

            # Start enrichment run
            now_str = datetime.now(UTC).isoformat()
            conn.execute(
                """INSERT OR IGNORE INTO sports_enrichment_run
                   (run_identity, sport, canonical_event_id, analysis_cutoff_at, status, started_at, policy_config_hash, requested_capabilities)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_identity,
                    "football",
                    canonical_fixture_id,
                    analysis_cutoff_at.isoformat(),
                    "RUNNING",
                    now_str,
                    policy_config_hash,
                    "recent_form,h2h,standings,stats",
                ),
            )
            run_row = conn.execute(
                "SELECT id FROM sports_enrichment_run WHERE run_identity = ?", (run_identity,)
            ).fetchone()
            if not run_row:
                raise RuntimeError(f"Failed to create or retrieve sports_enrichment_run for identity {run_identity}")
            run_id = run_row[0]
            conn.commit()

        try:
            # STAGE 2: Fetch (outside of SQLite write transaction or savepoint)
            fetch_tasks = [
                {
                    "cap": "current_recent_form",
                    "team_id": fixture.home_team_id,
                    "native_team_id": native_home_id,
                    "role": "HOME",
                },
                {
                    "cap": "current_recent_form",
                    "team_id": fixture.away_team_id,
                    "native_team_id": native_away_id,
                    "role": "AWAY",
                },
                {
                    "cap": "h2h_head_to_head",
                    "team_id": fixture.home_team_id,
                    "native_team_id": native_home_id,
                    "role": None,
                },
                {
                    "cap": "standings_competition_context",
                    "team_id": fixture.home_team_id,
                    "native_team_id": native_home_id,
                    "role": None,
                },
                {
                    "cap": "fixture_team_statistics",
                    "team_id": fixture.home_team_id,
                    "native_team_id": native_home_id,
                    "role": None,
                },
            ]

            fetched_results = {}

            for task in fetch_tasks:
                cap = task["cap"]
                role = task["role"]
                team_id = task["team_id"]
                native_team_id = task["native_team_id"]

                # Current football enrichment execution is only proven for ESPN eng.1.
                # Route selection therefore uses exact scope and refuses broader claims.
                route_name = ROUTE_NAME_FROM_CAPABILITY.get(cap, "detailed_metrics")
                requested_competition_scope = "football:eng.1"

                selected_provider = None
                selected_result = None
                attempted_results = []

                route_candidates = get_route_candidates(
                    config,
                    route_name,
                    requested_competition_scope,
                    season_scope="current",
                    mode=mode,
                    selectable_only=True,
                )

                for route_candidate in route_candidates:
                    provider = route_candidate["provider"]

                    adapter = self.adapter_registry.get(provider)
                    if not adapter:
                        continue

                    # Call adapter
                    kwargs = {
                        "team_id": team_id,
                        "native_team_id": native_team_id,
                        "native_fixture_id": native_fixture_id,
                        "team1_id": fixture.home_team_id,
                        "team2_id": fixture.away_team_id,
                        "native_team1_id": native_home_id,
                        "native_team2_id": native_away_id,
                        "competition_id": fixture.competition_id,
                        "native_competition_id": "eng.1",
                    }

                    # Assert that no SQLite write transaction is active when called
                    with get_db() as test_conn:
                        assert not test_conn.in_transaction, "SQLite write transaction is active during provider call!"

                    res = adapter.fetch_capability(cap, canonical_fixture_id, analysis_cutoff_at, **kwargs)
                    attempted_results.append((provider, res))

                    # Check evidence requirement
                    if res.status == SourceResultStatus.SUCCESS:
                        # Verify evidence bundle
                        if not verify_evidence_bundle(res.bundle_id):
                            res = SourceOperationResult(
                                status=SourceResultStatus.EVIDENCE_ERROR,
                                error_code="missing_required_evidence",
                                evidence_refs=res.evidence_refs,
                            )
                            # Update the last attempted result in the list
                            attempted_results[-1] = (provider, res)

                    if res.status in (SourceResultStatus.SUCCESS, SourceResultStatus.VALID_EMPTY):
                        selected_provider = provider
                        selected_result = res
                        break

                task_key = (cap, role)
                fetched_results[task_key] = {
                    "selected_provider": selected_provider,
                    "selected_result": selected_result,
                    "attempted_results": attempted_results,
                }

            # STAGE 3: Publish (in one short transaction)
            with get_db() as conn:
                cap_repo = FixtureCapabilityRepo(conn)
                conn.execute("SAVEPOINT publish_enrichment")
                try:
                    home_form_matches = []
                    away_form_matches = []
                    h2h_matches = []
                    standings_table = None
                    fixture_stats = None
                    capability_outcomes: list[CapabilityOutcome] = []

                    for task in fetch_tasks:
                        cap = task["cap"]
                        role = task["role"]
                        team_id = task["team_id"]
                        native_team_id = task["native_team_id"]
                        task_key = (cap, role)

                        task_data = fetched_results[task_key]
                        selected_provider = task_data["selected_provider"]
                        selected_result = task_data["selected_result"]
                        attempted_results = task_data["attempted_results"]
                        selected_status_str = get_most_informative_status([r for _, r in attempted_results])
                        selected_bundle_id = ""

                        # 1. Persist all attempts exactly as returned
                        for provider, res in attempted_results:
                            attempt_identity = f"{run_id}|{provider}|{cap}|{role or ''}|{now_str}"
                            conn.execute(
                                """INSERT INTO source_operation_attempt
                                   (attempt_identity, run_id, provider, operation, request_identity, status, started_at, completed_at, http_status, error_code, retry_count, parser_version, dto_version, evidence_bundle_id, diagnostics)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (
                                    attempt_identity,
                                    run_id,
                                    provider,
                                    cap,
                                    res.request_identity or f"GET /{provider}/{cap}",
                                    res.status.value if isinstance(res.status, Enum) else str(res.status),
                                    now_str,
                                    datetime.now(UTC).isoformat(),
                                    res.http_status,
                                    res.error_code,
                                    res.retry_count,
                                    res.parser_version,
                                    res.normalization_version,
                                    res.bundle_id,
                                    json.dumps(res.parser_diagnostics),
                                )
                            )

                        # 2. Save observation and projection
                        if not selected_result:
                            terminal_status = selected_status_str

                            obs = create_observation(
                                canonical_fixture_id=canonical_fixture_id,
                                team_id=team_id,
                                capability=cap,
                                source="none",
                                request_identity=f"GET /football/{cap}/{canonical_fixture_id}",
                                status=terminal_status,
                                valid_at=analysis_cutoff_at.isoformat(),
                            )
                            obs_id = cap_repo.save_observation(obs)
                            if not obs_id:
                                raise RuntimeError(f"Failed to save observation for capability {cap}")

                            proj = create_projection(
                                canonical_fixture_id=canonical_fixture_id,
                                team_id=team_id,
                                capability=cap,
                                analysis_cutoff_at=analysis_cutoff_at.isoformat(),
                                selected_source="none",
                                selected_status=terminal_status,
                                selected_observation_id=obs_id,
                                primary_source="none",
                                primary_status=terminal_status,
                                snapshot_run_id=run_id
                            )
                            cap_repo.save_projection(proj)
                            capability_outcomes.append(
                                CapabilityOutcome(
                                    capability=cap,
                                    scope=role or "FIXTURE",
                                    selected_source="none",
                                    selected_status=terminal_status,
                                    required=True,
                                    satisfied=_is_capability_outcome_satisfied(terminal_status),
                                )
                            )
                            continue

                        # Save successful/valid_empty observation and projection
                        payload_json = json.dumps(to_dict(selected_result.value))
                        payload_sha256 = hashlib.sha256(payload_json.encode()).hexdigest()

                        obs = create_observation(
                            canonical_fixture_id=canonical_fixture_id,
                            team_id=team_id,
                            capability=cap,
                            source=selected_provider,
                            request_identity=selected_result.request_identity,
                            status=selected_result.status,
                            valid_at=analysis_cutoff_at.isoformat(),
                            evidence_bundle_id=selected_result.bundle_id,
                            native_fixture_id=native_fixture_id,
                            native_team_id=native_team_id,
                            http_status=selected_result.http_status,
                            error_code=selected_result.error_code,
                            parser_version=selected_result.parser_version,
                            parser_diagnostics=dict(selected_result.parser_diagnostics),
                            payload_sha256=payload_sha256,
                            payload_json=payload_json,
                            dto_version="1.0",
                            evidence_package_id=selected_result.bundle_id,
                        )
                        obs_id = cap_repo.save_observation(obs)
                        if not obs_id:
                            raise RuntimeError(f"Failed to save observation for capability {cap}")

                        proj = create_projection(
                            canonical_fixture_id=canonical_fixture_id,
                            team_id=team_id,
                            capability=cap,
                            analysis_cutoff_at=analysis_cutoff_at.isoformat(),
                            selected_source=selected_provider,
                            selected_status=selected_result.status,
                            selected_observation_id=obs_id,
                            primary_source=selected_provider,
                            primary_status=selected_result.status,
                            snapshot_run_id=run_id
                        )
                        cap_repo.save_projection(proj)
                        selected_status_str = selected_result.status.value if isinstance(selected_result.status, Enum) else str(selected_result.status)
                        selected_bundle_id = selected_result.bundle_id

                        # Write selection history automatically
                        conn.execute(
                            """INSERT INTO capability_selection_history
                               (canonical_fixture_id, team_id, capability, analysis_cutoff_at, selected_observation_id, selected_source, selected_status, recorded_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                canonical_fixture_id,
                                team_id,
                                cap,
                                analysis_cutoff_at.isoformat(),
                                obs_id,
                                selected_provider,
                                selected_result.status,
                                datetime.now(UTC).isoformat()
                            )
                        )

                        # Assign to snapshot fields
                        if cap == "current_recent_form":
                            if role == "HOME":
                                home_form_matches = selected_result.value or []
                            elif role == "AWAY":
                                away_form_matches = selected_result.value or []
                        elif cap == "h2h_head_to_head":
                            h2h_matches = selected_result.value or []
                        elif cap == "standings_competition_context":
                            standings_table = selected_result.value
                        elif cap == "fixture_team_statistics":
                            fixture_stats = selected_result.value

                        capability_outcomes.append(
                            CapabilityOutcome(
                                capability=cap,
                                scope=role or "FIXTURE",
                                selected_source=selected_provider or "none",
                                selected_status=selected_status_str,
                                required=True,
                                satisfied=_is_capability_outcome_satisfied(selected_status_str),
                                evidence_bundle_id=selected_bundle_id or "",
                            )
                        )

                    # Build and publish snapshot
                    snapshot_state = _derive_snapshot_state(capability_outcomes)
                    snapshot = FootballEnrichmentSnapshot(
                        run_id=str(run_id),
                        snapshot_id=f"snap_{canonical_fixture_id}_{analysis_cutoff_at.strftime('%Y%m%dT%H%M%S')}",
                        snapshot_state=snapshot_state,
                        canonical_fixture_id=canonical_fixture_id,
                        analysis_cutoff_at=analysis_cutoff_at,
                        kickoff_at=datetime.fromisoformat(fixture.kickoff.replace("Z", "+00:00")),
                        event_status=fixture.status,
                        competition_canonical_id=fixture.competition_id,
                        home_participant=NormalizedParticipant(
                            canonical_id=fixture.home_team_id,
                            name=home_team.name,
                            role="HOME"
                        ),
                        away_participant=NormalizedParticipant(
                            canonical_id=fixture.away_team_id,
                            name=away_team.name,
                            role="AWAY"
                        ),
                        home_form=tuple(home_form_matches),
                        away_form=tuple(away_form_matches),
                        h2h_records=tuple(h2h_matches),
                        standings=standings_table,
                        selected_metrics={"stats": to_dict(fixture_stats)} if fixture_stats else {},
                        capability_outcomes=tuple(capability_outcomes),
                        bundle_ids=tuple(row["evidence_bundle_id"] for row in conn.execute("SELECT DISTINCT evidence_bundle_id FROM fixture_capability_observation WHERE canonical_fixture_id = ? AND evidence_bundle_id != ''", (canonical_fixture_id,)).fetchall()),
                    )

                    snapshot_json = json.dumps(to_dict(snapshot))
                    snapshot_hash = canonical_hash(snapshot)

                    # Save snapshot to analysis_snapshot table
                    conn.execute(
                        """INSERT INTO analysis_snapshot
                           (schema_version, run_id, canonical_fixture_id, analysis_cutoff_at, status, snapshot_hash, payload_json, created_at, published_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            "1.0",
                            run_id,
                            canonical_fixture_id,
                            analysis_cutoff_at.isoformat(),
                            snapshot_state,
                            snapshot_hash,
                            snapshot_json,
                            now_str,
                            now_str,
                        ),
                    )

                    # Update run status to COMPLETE
                    conn.execute(
                        "UPDATE sports_enrichment_run SET status = ?, completed_at = ? WHERE id = ?",
                        (snapshot_state, now_str, run_id),
                    )
                    conn.execute("RELEASE SAVEPOINT publish_enrichment")
                    return snapshot

                except Exception as e:
                    conn.execute("ROLLBACK TO SAVEPOINT publish_enrichment")
                    conn.execute("RELEASE SAVEPOINT publish_enrichment")
                    raise
        except Exception as e:
            _record_failed_run(canonical_fixture_id, analysis_cutoff_at, str(e))
            raise


def _record_failed_run(canonical_fixture_id: int, cutoff: datetime, reason: str) -> None:
    from bet.db.connection import get_db
    with get_db() as conn:
        now_str = datetime.now(UTC).isoformat()
        run_identity = hashlib.sha256(
            f"football|{canonical_fixture_id}|{cutoff.isoformat()}|failed|{now_str}".encode()
        ).hexdigest()
        conn.execute(
            """INSERT INTO sports_enrichment_run
               (run_identity, sport, canonical_event_id, analysis_cutoff_at, status, started_at, completed_at, policy_config_hash, requested_capabilities, failure_reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_identity,
                "football",
                canonical_fixture_id,
                cutoff.isoformat(),
                "FAILED",
                now_str,
                now_str,
                "error",
                "",
                reason,
            ),
        )
        conn.commit()


def create_football_enrichment_service(
    espn_client: ESPNClient | None = None,
    api_football_client: APIFootballClient | None = None,
    football_data_client: FootballDataOrgClient | None = None,
) -> FootballEnrichmentService:
    registry = FootballAdapterRegistry()
    
    if not espn_client:
        espn_client = ESPNClient(sport="football", league="eng.1", rate_limiter=RateLimiter())
    registry.register("espn", ESPNFootballAdapter(espn_client))
    
    if not api_football_client:
        api_football_client = APIFootballClient(rate_limiter=RateLimiter())
    registry.register("api-football", APIFootballCandidateAdapter(api_football_client))

    if not football_data_client:
        football_data_client = FootballDataOrgClient(rate_limiter=RateLimiter())
    registry.register("football-data", FootballDataStandingsAdapter(football_data_client))
    
    return FootballEnrichmentService(registry)
