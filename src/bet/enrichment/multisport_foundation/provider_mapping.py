from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

TARGET_SPORTS = ("basketball", "volleyball", "hockey", "tennis", "cs2", "dota2", "valorant")

class ProviderMappingStatus(StrEnum):
    MAPPING_READY_FOR_SANITIZED_PROBE = "MAPPING_READY_FOR_SANITIZED_PROBE"
    BLOCKED_NO_CREDENTIALS = "BLOCKED_NO_CREDENTIALS"
    BLOCKED_PROVIDER_TERMS_OR_SCOPE = "BLOCKED_PROVIDER_TERMS_OR_SCOPE"
    BLOCKED_PROVIDER_MAPPING_NOT_FOUND = "BLOCKED_PROVIDER_MAPPING_NOT_FOUND"
    BLOCKED_PROVIDER_ACCESS = "BLOCKED_PROVIDER_ACCESS"

@dataclass(frozen=True)
class ProviderRouteSpec:
    provider_key: str
    sport: str
    route_key: str
    endpoint_family: str
    required_env_keys: tuple[str, ...]
    proof_fields_required: tuple[str, ...]
    forbidden_fields: tuple[str, ...]
    terms_or_access_review_required: bool
    live_call_allowed: bool = False
    production_selectable: bool = False
    betting_decisions_enabled: bool = False

@dataclass(frozen=True)
class ProviderMappingArtifact:
    artifact_id: str
    sport: str
    provider_key: str
    status: str
    route_key: str
    endpoint_family: str
    required_env_keys: tuple[str, ...]
    missing_env_keys: tuple[str, ...]
    proof_fields_required: tuple[str, ...]
    forbidden_fields: tuple[str, ...]
    blocked_reason: str
    live_call_allowed: bool
    production_selectable: bool
    betting_decisions_enabled: bool
    sanitized_probe_only: bool
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)

    def to_jsonable(self) -> dict[str, Any]:
        item = asdict(self)
        for key in ("required_env_keys", "missing_env_keys", "proof_fields_required", "forbidden_fields", "evidence_refs"):
            if key in item:
                item[key] = list(item[key])
        return item

def default_route_specs() -> tuple[ProviderRouteSpec, ...]:
    return (
        ProviderRouteSpec("api-sports-family", "basketball", "api_basketball_games", "games", ("API_BASKETBALL_KEY", "API_SPORTS_KEY"), ("fixture_id", "home_team", "away_team", "start_time"), ("odds", "prediction", "betting"), False),
        ProviderRouteSpec("api-sports-family", "volleyball", "api_volleyball_games", "games", ("API_VOLLEYBALL_KEY", "API_SPORTS_KEY"), ("fixture_id", "home_team", "away_team", "start_time"), ("odds", "prediction", "betting"), False),
        ProviderRouteSpec("api-sports-family", "hockey", "api_hockey_games", "games", ("API_HOCKEY_KEY", "API_SPORTS_KEY"), ("fixture_id", "home_team", "away_team", "start_time"), ("odds", "prediction", "betting"), False),
        ProviderRouteSpec("api-sports-family", "tennis", "api_tennis_fixtures", "fixtures", ("API_TENNIS_KEY", "API_SPORTS_KEY"), ("fixture_id", "player_or_team_a", "player_or_team_b", "start_time"), ("odds", "prediction", "betting"), False),
        ProviderRouteSpec("pandascore", "cs2", "pandascore_cs2_matches", "matches", ("PANDASCORE_TOKEN",), ("match_id", "opponents", "begin_at"), ("odds", "betting"), True),
        ProviderRouteSpec("pandascore", "dota2", "pandascore_dota2_matches", "matches", ("PANDASCORE_TOKEN",), ("match_id", "opponents", "begin_at"), ("odds", "betting"), True),
        ProviderRouteSpec("pandascore", "valorant", "pandascore_valorant_matches", "matches", ("PANDASCORE_TOKEN",), ("match_id", "opponents", "begin_at"), ("odds", "betting"), True),
    )

def _env_present(env: dict[str, str], keys: tuple[str, ...]) -> bool:
    return any(bool(env.get(k)) for k in keys)

def build_mapping_artifact(spec: ProviderRouteSpec, env: dict[str, str]) -> ProviderMappingArtifact:
    if spec.terms_or_access_review_required:
        status = ProviderMappingStatus.BLOCKED_PROVIDER_TERMS_OR_SCOPE
        missing = tuple(k for k in spec.required_env_keys if not env.get(k))
        blocked_reason = "terms_or_access_review_required_before_probe"
    elif not _env_present(env, spec.required_env_keys):
        status = ProviderMappingStatus.BLOCKED_NO_CREDENTIALS
        missing = spec.required_env_keys
        blocked_reason = "no_acceptable_provider_credential_present"
    elif not spec.proof_fields_required:
        status = ProviderMappingStatus.BLOCKED_PROVIDER_MAPPING_NOT_FOUND
        missing = tuple()
        blocked_reason = "route_has_no_minimum_fact_policy"
    else:
        status = ProviderMappingStatus.MAPPING_READY_FOR_SANITIZED_PROBE
        missing = tuple()
        blocked_reason = ""

    return ProviderMappingArtifact(
        artifact_id=f"pass_e:{spec.sport}:{spec.provider_key}:{spec.route_key}",
        sport=spec.sport,
        provider_key=spec.provider_key,
        status=str(status),
        route_key=spec.route_key,
        endpoint_family=spec.endpoint_family,
        required_env_keys=spec.required_env_keys,
        missing_env_keys=missing,
        proof_fields_required=spec.proof_fields_required,
        forbidden_fields=spec.forbidden_fields,
        blocked_reason=blocked_reason,
        live_call_allowed=False,
        production_selectable=False,
        betting_decisions_enabled=False,
        sanitized_probe_only=True,
        evidence_refs=(f"route:{spec.route_key}",),
    )

def build_provider_mapping_plan(env: dict[str, str] | None = None) -> dict[str, Any]:
    env = env or {}
    artifacts = [build_mapping_artifact(spec, env) for spec in default_route_specs()]
    by_sport: dict[str, list[dict[str, Any]]] = {sport: [] for sport in TARGET_SPORTS}
    for artifact in artifacts:
        by_sport[artifact.sport].append(artifact.to_jsonable())
    return {
        "phase_id": "MULTISPORT_PASS_E_PROVIDER_MAPPING_CONTRACTS",
        "target_sports": list(TARGET_SPORTS),
        "live_calls_allowed": False,
        "production_activation": False,
        "betting_decisions": False,
        "provider_mapping_by_sport": by_sport,
    }

def validate_mapping_plan(plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    sports = set(plan.get("target_sports", []))
    if sports != set(TARGET_SPORTS):
        errors.append("target_sports_mismatch")
    if plan.get("live_calls_allowed") is not False:
        errors.append("live_calls_must_be_false")
    if plan.get("production_activation") is not False:
        errors.append("production_activation_must_be_false")
    if plan.get("betting_decisions") is not False:
        errors.append("betting_decisions_must_be_false")
    for sport, items in plan.get("provider_mapping_by_sport", {}).items():
        if sport not in TARGET_SPORTS:
            errors.append(f"unexpected_sport:{sport}")
        for item in items:
            if item.get("production_selectable") is not False:
                errors.append(f"production_selectable_true:{sport}")
            if item.get("betting_decisions_enabled") is not False:
                errors.append(f"betting_decisions_enabled_true:{sport}")
            if item.get("live_call_allowed") is not False:
                errors.append(f"live_call_allowed_true:{sport}")
            if item.get("status") == ProviderMappingStatus.MAPPING_READY_FOR_SANITIZED_PROBE and not item.get("proof_fields_required"):
                errors.append(f"ready_without_proof_fields:{sport}")
    return errors
