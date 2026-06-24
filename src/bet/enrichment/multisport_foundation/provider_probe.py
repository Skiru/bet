from __future__ import annotations

import os
import json
import urllib.request
import urllib.error
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from .provider_mapping import ProviderMappingArtifact, ProviderMappingStatus

class ProviderProbeStatus(StrEnum):
    SANITIZED_PROBE_READY_DRY_RUN = "SANITIZED_PROBE_READY_DRY_RUN"
    SANITIZED_PROBE_BLOCKED_NO_CREDENTIALS = "SANITIZED_PROBE_BLOCKED_NO_CREDENTIALS"
    SANITIZED_PROBE_BLOCKED_PROVIDER_TERMS_OR_SCOPE = "SANITIZED_PROBE_BLOCKED_PROVIDER_TERMS_OR_SCOPE"
    SANITIZED_PROBE_BLOCKED_MAPPING_NOT_READY = "SANITIZED_PROBE_BLOCKED_MAPPING_NOT_READY"
    SANITIZED_PROBE_BLOCKED_PROVIDER_ACCESS = "SANITIZED_PROBE_BLOCKED_PROVIDER_ACCESS"
    SANITIZED_PROBE_RESULT_CAPTURED_SANITIZED = "SANITIZED_PROBE_RESULT_CAPTURED_SANITIZED"

@dataclass(frozen=True)
class ProviderProbePolicy:
    provider_key: str
    sport: str
    route_key: str
    allow_real_network: bool = False
    terms_review_approved: bool = False
    max_requests: int = 1
    timeout_seconds: float = 10.0
    sanitized_probe_only: bool = True
    production_selectable: bool = False
    betting_decisions_enabled: bool = False
    notes: str = ""

    def __post_init__(self) -> None:
        if self.max_requests > 1:
            raise ValueError("max_requests must be <= 1")
        if not self.sanitized_probe_only:
            raise ValueError("sanitized_probe_only must be true")
        if self.production_selectable:
            raise ValueError("production_selectable must always be false")
        if self.betting_decisions_enabled:
            raise ValueError("betting_decisions_enabled must always be false")

@dataclass(frozen=True)
class ProviderProbeArtifact:
    artifact_id: str
    sport: str
    provider_key: str
    route_key: str
    status: str
    source_mapping_status: str
    request_method: str
    request_url_template: str
    sanitized_request_headers: dict[str, str] = field(default_factory=dict)
    sanitized_request_query: dict[str, str] = field(default_factory=dict)
    sanitized_response_envelope: dict[str, Any] = field(default_factory=dict)
    proof_fields_observed: tuple[str, ...] = field(default_factory=tuple)
    missing_proof_fields: tuple[str, ...] = field(default_factory=tuple)
    live_call_made: bool = False
    provider_access_attempted: bool = False
    blocked_reason: str = ""
    production_selectable: bool = False
    betting_decisions_enabled: bool = False
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.production_selectable:
            raise ValueError("production_selectable must be false")
        if self.betting_decisions_enabled:
            raise ValueError("betting_decisions_enabled must be false")
        if self.status != ProviderProbeStatus.SANITIZED_PROBE_RESULT_CAPTURED_SANITIZED:
            if len(self.proof_fields_observed) > 0:
                raise ValueError("proof_fields_observed must be empty unless status is SANITIZED_PROBE_RESULT_CAPTURED_SANITIZED")
        if self.status == ProviderProbeStatus.SANITIZED_PROBE_RESULT_CAPTURED_SANITIZED:
            if not self.live_call_made or not self.provider_access_attempted:
                raise ValueError("SANITIZED_PROBE_RESULT_CAPTURED_SANITIZED requires live_call_made=true and provider_access_attempted=true")

    def to_jsonable(self) -> dict[str, Any]:
        item = asdict(self)
        for key in ("proof_fields_observed", "missing_proof_fields", "evidence_refs"):
            if key in item:
                item[key] = list(item[key])
        return item

def get_url_template(route_key: str) -> str:
    templates = {
        "api_basketball_games": "https://v1.basketball.api-sports.io/games",
        "api_volleyball_games": "https://v1.volleyball.api-sports.io/games",
        "api_hockey_games": "https://v1.hockey.api-sports.io/games",
        "api_tennis_fixtures": "https://v1.tennis.api-sports.io/fixtures",
        "pandascore_cs2_matches": "https://api.pandascore.co/csgo/matches",
        "pandascore_dota2_matches": "https://api.pandascore.co/dota2/matches",
        "pandascore_valorant_matches": "https://api.pandascore.co/valorant/matches",
    }
    return templates.get(route_key, "https://api.example.com")

def get_probe_query_params(route_key: str) -> dict[str, str]:
    if "pandascore" in route_key:
        return {"per_page": "1"}
    else:
        return {"league": "1", "season": "2025"}

def extract_keys_from_json(obj: Any) -> set[str]:
    keys = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(k)
            keys.update(extract_keys_from_json(v))
    elif isinstance(obj, list):
        for item in obj:
            keys.update(extract_keys_from_json(item))
    return keys

def run_provider_probe(
    mapping: ProviderMappingArtifact,
    policy: ProviderProbePolicy,
    env: dict[str, str] | None = None
) -> ProviderProbeArtifact:
    if env is None:
        env = {k: v for k, v in os.environ.items() if v}

    url_template = get_url_template(mapping.route_key)
    query_params = get_probe_query_params(mapping.route_key)

    # Sanitize request headers and query
    if mapping.provider_key == "pandascore":
        sanitized_headers = {"Authorization": "Bearer <redacted>"}
    else:
        sanitized_headers = {"x-apisports-key": "<redacted>"}

    # 1. Check if mapping itself is not ready
    if mapping.status != ProviderMappingStatus.MAPPING_READY_FOR_SANITIZED_PROBE:
        if mapping.status == ProviderMappingStatus.BLOCKED_NO_CREDENTIALS:
            status = ProviderProbeStatus.SANITIZED_PROBE_BLOCKED_NO_CREDENTIALS
            blocked_reason = "missing_source_credentials"
        elif mapping.status == ProviderMappingStatus.BLOCKED_PROVIDER_TERMS_OR_SCOPE:
            status = ProviderProbeStatus.SANITIZED_PROBE_BLOCKED_PROVIDER_TERMS_OR_SCOPE
            blocked_reason = "terms_review_required"
        else:
            status = ProviderProbeStatus.SANITIZED_PROBE_BLOCKED_MAPPING_NOT_READY
            blocked_reason = f"source_mapping_status_not_ready:{mapping.status}"

        return ProviderProbeArtifact(
            artifact_id=f"pass_f:{mapping.sport}:{mapping.provider_key}:{mapping.route_key}",
            sport=mapping.sport,
            provider_key=mapping.provider_key,
            route_key=mapping.route_key,
            status=str(status),
            source_mapping_status=mapping.status,
            request_method="GET",
            request_url_template=url_template,
            sanitized_request_headers=sanitized_headers,
            sanitized_request_query=query_params,
            sanitized_response_envelope={"status": "blocked", "reason": blocked_reason},
            proof_fields_observed=(),
            missing_proof_fields=mapping.proof_fields_required,
            live_call_made=False,
            provider_access_attempted=False,
            blocked_reason=blocked_reason,
            production_selectable=False,
            betting_decisions_enabled=False,
            evidence_refs=(f"probe:{mapping.route_key}",),
        )

    # 2. Mapping is ready. Evaluate real network conditions.
    allow_real_network_env = (env.get("MULTISPORT_PASS_F_ALLOW_REAL_NETWORK") == "1")
    
    # Are credentials present?
    missing_keys = [k for k in mapping.required_env_keys if not env.get(k)]
    credentials_present = len(missing_keys) == 0

    if not credentials_present:
        status = ProviderProbeStatus.SANITIZED_PROBE_BLOCKED_NO_CREDENTIALS
        blocked_reason = "missing_probe_credentials"
        return ProviderProbeArtifact(
            artifact_id=f"pass_f:{mapping.sport}:{mapping.provider_key}:{mapping.route_key}",
            sport=mapping.sport,
            provider_key=mapping.provider_key,
            route_key=mapping.route_key,
            status=str(status),
            source_mapping_status=mapping.status,
            request_method="GET",
            request_url_template=url_template,
            sanitized_request_headers=sanitized_headers,
            sanitized_request_query=query_params,
            sanitized_response_envelope={"status": "blocked", "reason": blocked_reason},
            proof_fields_observed=(),
            missing_proof_fields=mapping.proof_fields_required,
            live_call_made=False,
            provider_access_attempted=False,
            blocked_reason=blocked_reason,
            production_selectable=False,
            betting_decisions_enabled=False,
            evidence_refs=(f"probe:{mapping.route_key}",),
        )

    if not policy.terms_review_approved:
        status = ProviderProbeStatus.SANITIZED_PROBE_BLOCKED_PROVIDER_TERMS_OR_SCOPE
        blocked_reason = "policy_terms_not_approved"
        return ProviderProbeArtifact(
            artifact_id=f"pass_f:{mapping.sport}:{mapping.provider_key}:{mapping.route_key}",
            sport=mapping.sport,
            provider_key=mapping.provider_key,
            route_key=mapping.route_key,
            status=str(status),
            source_mapping_status=mapping.status,
            request_method="GET",
            request_url_template=url_template,
            sanitized_request_headers=sanitized_headers,
            sanitized_request_query=query_params,
            sanitized_response_envelope={"status": "blocked", "reason": blocked_reason},
            proof_fields_observed=(),
            missing_proof_fields=mapping.proof_fields_required,
            live_call_made=False,
            provider_access_attempted=False,
            blocked_reason=blocked_reason,
            production_selectable=False,
            betting_decisions_enabled=False,
            evidence_refs=(f"probe:{mapping.route_key}",),
        )

    # Check remaining gates for live call
    gated_live_allowed = (
        allow_real_network_env and
        policy.allow_real_network and
        policy.max_requests <= 1 and
        policy.sanitized_probe_only
    )

    if not gated_live_allowed:
        # Dry run because real network is not fully allowed/enabled
        status = ProviderProbeStatus.SANITIZED_PROBE_READY_DRY_RUN
        blocked_reason = "real_network_disabled_or_dry_run_policy"
        return ProviderProbeArtifact(
            artifact_id=f"pass_f:{mapping.sport}:{mapping.provider_key}:{mapping.route_key}",
            sport=mapping.sport,
            provider_key=mapping.provider_key,
            route_key=mapping.route_key,
            status=str(status),
            source_mapping_status=mapping.status,
            request_method="GET",
            request_url_template=url_template,
            sanitized_request_headers=sanitized_headers,
            sanitized_request_query=query_params,
            sanitized_response_envelope={"status": "dry_run"},
            proof_fields_observed=(),
            missing_proof_fields=mapping.proof_fields_required,
            live_call_made=False,
            provider_access_attempted=False,
            blocked_reason=blocked_reason,
            production_selectable=False,
            betting_decisions_enabled=False,
            evidence_refs=(f"probe:{mapping.route_key}",),
        )

    # 3. Gated live call is fully authorized!
    # Build query string
    import urllib.parse
    query_str = urllib.parse.urlencode(query_params)
    url_with_query = f"{url_template}?{query_str}"

    # Build real headers
    real_headers = {}
    if mapping.provider_key == "pandascore":
        token = env.get("PANDASCORE_TOKEN", "")
        real_headers["Authorization"] = f"Bearer {token}"
    else:
        # api-sports key
        api_key = ""
        for k in mapping.required_env_keys:
            if env.get(k):
                api_key = env[k]
                break
        real_headers["x-apisports-key"] = api_key

    # Execute request
    req = urllib.request.Request(url_with_query, headers=real_headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=policy.timeout_seconds) as response:
            body = response.read()
            payload = json.loads(body.decode("utf-8"))
            
            # Observe proof fields
            found_keys = extract_keys_from_json(payload)
            proof_fields_observed = tuple(f for f in mapping.proof_fields_required if f in found_keys)
            missing_proof_fields = tuple(f for f in mapping.proof_fields_required if f not in found_keys)

            # Sanitize response
            sanitized_envelope = {
                "status": "success",
                "response_keys_observed": sorted(list(found_keys)),
                "records_count": len(payload) if isinstance(payload, list) else 1
            }

            return ProviderProbeArtifact(
                artifact_id=f"pass_f:{mapping.sport}:{mapping.provider_key}:{mapping.route_key}",
                sport=mapping.sport,
                provider_key=mapping.provider_key,
                route_key=mapping.route_key,
                status=str(ProviderProbeStatus.SANITIZED_PROBE_RESULT_CAPTURED_SANITIZED),
                source_mapping_status=mapping.status,
                request_method="GET",
                request_url_template=url_template,
                sanitized_request_headers=sanitized_headers,
                sanitized_request_query=query_params,
                sanitized_response_envelope=sanitized_envelope,
                proof_fields_observed=proof_fields_observed,
                missing_proof_fields=missing_proof_fields,
                live_call_made=True,
                provider_access_attempted=True,
                blocked_reason="",
                production_selectable=False,
                betting_decisions_enabled=False,
                evidence_refs=(f"probe:{mapping.route_key}",),
            )
    except Exception as err:
        # Map connection/timeout/auth/http errors to SANITIZED_PROBE_BLOCKED_PROVIDER_ACCESS
        status = ProviderProbeStatus.SANITIZED_PROBE_BLOCKED_PROVIDER_ACCESS
        blocked_reason = f"provider_access_failed: {str(err)}"
        return ProviderProbeArtifact(
            artifact_id=f"pass_f:{mapping.sport}:{mapping.provider_key}:{mapping.route_key}",
            sport=mapping.sport,
            provider_key=mapping.provider_key,
            route_key=mapping.route_key,
            status=str(status),
            source_mapping_status=mapping.status,
            request_method="GET",
            request_url_template=url_template,
            sanitized_request_headers=sanitized_headers,
            sanitized_request_query=query_params,
            sanitized_response_envelope={"status": "error", "error_class": err.__class__.__name__},
            proof_fields_observed=(),
            missing_proof_fields=mapping.proof_fields_required,
            live_call_made=True,
            provider_access_attempted=True,
            blocked_reason=blocked_reason,
            production_selectable=False,
            betting_decisions_enabled=False,
            evidence_refs=(f"probe:{mapping.route_key}",),
        )
