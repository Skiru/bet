from __future__ import annotations
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

TARGET_SPORTS = ("basketball", "volleyball", "hockey", "tennis", "cs2", "dota2", "valorant")

class ProviderAuthorizationStatus(StrEnum):
    AUTHORIZED_FOR_SANITIZED_LIVE_PROBE = "AUTHORIZED_FOR_SANITIZED_LIVE_PROBE"
    BLOCKED_NO_CREDENTIALS = "BLOCKED_NO_CREDENTIALS"
    BLOCKED_TERMS_REVIEW_NOT_APPROVED = "BLOCKED_TERMS_REVIEW_NOT_APPROVED"
    BLOCKED_DATA_SCOPE_NOT_APPROVED = "BLOCKED_DATA_SCOPE_NOT_APPROVED"
    BLOCKED_OPERATOR_APPROVAL_MISSING = "BLOCKED_OPERATOR_APPROVAL_MISSING"

@dataclass(frozen=True)
class ProviderAuthorizationSpec:
    sport: str
    provider_key: str
    credential_env_keys: tuple[str, ...]
    terms_approval_env_key: str
    data_scope_approval_env_key: str
    operator_approval_env_key: str
    max_requests: int = 1
    allow_real_network: bool = False
    production_selectable: bool = False
    betting_decisions_enabled: bool = False

    def __post_init__(self) -> None:
        if self.allow_real_network:
            raise ValueError("allow_real_network must always be false in Pass H")
        if self.max_requests > 1:
            raise ValueError("max_requests must be <= 1")
        if self.production_selectable:
            raise ValueError("production_selectable must always be false")
        if self.betting_decisions_enabled:
            raise ValueError("betting_decisions_enabled must always be false")

@dataclass(frozen=True)
class ProviderAuthorizationArtifact:
    artifact_id: str
    sport: str
    provider_key: str
    status: str
    credential_present: bool
    terms_review_approved: bool
    data_scope_approved: bool
    operator_approved: bool
    max_requests: int
    allow_real_network: bool
    next_allowed_phase: str
    blocked_reason: str
    production_selectable: bool
    betting_decisions_enabled: bool
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.allow_real_network:
            raise ValueError("allow_real_network must be false")
        if self.max_requests > 1:
            raise ValueError("max_requests must be <= 1")
        if self.production_selectable:
            raise ValueError("production_selectable must be false")
        if self.betting_decisions_enabled:
            raise ValueError("betting_decisions_enabled must be false")
        if self.status == ProviderAuthorizationStatus.AUTHORIZED_FOR_SANITIZED_LIVE_PROBE:
            if not (self.credential_present and self.terms_review_approved and self.data_scope_approved and self.operator_approved):
                raise ValueError("AUTHORIZED_FOR_SANITIZED_LIVE_PROBE requires all gates to be approved/present")
            if self.next_allowed_phase != "pass_i_authorized_single_flight_probe":
                raise ValueError("AUTHORIZED_FOR_SANITIZED_LIVE_PROBE next_allowed_phase must be pass_i_authorized_single_flight_probe")

    def to_jsonable(self) -> dict[str, Any]:
        item = asdict(self)
        item['evidence_refs'] = list(item['evidence_refs'])
        return item

def default_authorization_specs() -> tuple[ProviderAuthorizationSpec, ...]:
    specs = []
    for sport, keys in (
        ("basketball", ("API_BASKETBALL_KEY", "API_SPORTS_KEY")),
        ("volleyball", ("API_VOLLEYBALL_KEY", "API_SPORTS_KEY")),
        ("hockey", ("API_HOCKEY_KEY", "API_SPORTS_KEY")),
        ("tennis", ("API_TENNIS_KEY", "API_SPORTS_KEY")),
    ):
        specs.append(
            ProviderAuthorizationSpec(
                sport=sport,
                provider_key="api-sports-family",
                credential_env_keys=keys,
                terms_approval_env_key="MULTISPORT_API_SPORTS_TERMS_APPROVED",
                data_scope_approval_env_key="MULTISPORT_API_SPORTS_DATA_SCOPE_APPROVED",
                operator_approval_env_key="MULTISPORT_API_SPORTS_OPERATOR_APPROVED"
            )
        )
    for sport in ("cs2", "dota2", "valorant"):
        specs.append(
            ProviderAuthorizationSpec(
                sport=sport,
                provider_key="pandascore",
                credential_env_keys=("PANDASCORE_TOKEN",),
                terms_approval_env_key="MULTISPORT_PANDASCORE_TERMS_APPROVED",
                data_scope_approval_env_key="MULTISPORT_PANDASCORE_DATA_SCOPE_APPROVED",
                operator_approval_env_key="MULTISPORT_PANDASCORE_OPERATOR_APPROVED"
            )
        )
    return tuple(specs)

def flag_enabled(env: dict[str, str], key: str) -> bool:
    return env.get(key) == "1"

def any_credential_present(env: dict[str, str], keys: tuple[str, ...]) -> bool:
    return any(bool(env.get(k)) for k in keys)

def authorize_probe(spec: ProviderAuthorizationSpec, env: dict[str, str]) -> ProviderAuthorizationArtifact:
    credential_present = any_credential_present(env, spec.credential_env_keys)
    terms_ok = flag_enabled(env, spec.terms_approval_env_key)
    scope_ok = flag_enabled(env, spec.data_scope_approval_env_key)
    operator_ok = flag_enabled(env, spec.operator_approval_env_key)
    
    if not credential_present:
        status = ProviderAuthorizationStatus.BLOCKED_NO_CREDENTIALS
        reason = "credential_presence_missing"
    elif not terms_ok:
        status = ProviderAuthorizationStatus.BLOCKED_TERMS_REVIEW_NOT_APPROVED
        reason = "terms_review_not_approved"
    elif not scope_ok:
        status = ProviderAuthorizationStatus.BLOCKED_DATA_SCOPE_NOT_APPROVED
        reason = "data_scope_not_approved"
    elif not operator_ok:
        status = ProviderAuthorizationStatus.BLOCKED_OPERATOR_APPROVAL_MISSING
        reason = "operator_approval_missing"
    else:
        status = ProviderAuthorizationStatus.AUTHORIZED_FOR_SANITIZED_LIVE_PROBE
        reason = ""
        
    return ProviderAuthorizationArtifact(
        artifact_id=f"pass_h:{spec.sport}:{spec.provider_key}",
        sport=spec.sport,
        provider_key=spec.provider_key,
        status=str(status),
        credential_present=credential_present,
        terms_review_approved=terms_ok,
        data_scope_approved=scope_ok,
        operator_approved=operator_ok,
        max_requests=spec.max_requests,
        allow_real_network=False,
        next_allowed_phase="pass_i_authorized_single_flight_probe" if status == ProviderAuthorizationStatus.AUTHORIZED_FOR_SANITIZED_LIVE_PROBE else "none",
        blocked_reason=reason,
        production_selectable=False,
        betting_decisions_enabled=False,
        evidence_refs=(f"provider:{spec.provider_key}", f"sport:{spec.sport}")
    )

def build_authorization_report(env: dict[str, str] | None = None) -> dict[str, Any]:
    env = env or {}
    artifacts = [authorize_probe(s, env) for s in default_authorization_specs()]
    by_sport = {sport: [] for sport in TARGET_SPORTS}
    for a in artifacts:
        by_sport[a.sport].append(a.to_jsonable())
    status_by_sport = {sport: items[0]['status'] for sport, items in by_sport.items()}
    return {
        "phase_id": "MULTISPORT_PASS_H_PROVIDER_ACCESS_GATE",
        "target_sports": list(TARGET_SPORTS),
        "live_calls_made": False,
        "provider_access_attempted": False,
        "production_activation": False,
        "betting_decisions": False,
        "provider_access_by_sport": by_sport,
        "status_by_sport": status_by_sport,
        "metrics": {
            "total_target_sports": len(TARGET_SPORTS),
            "authorized_for_sanitized_live_probe_count": sum(1 for s in status_by_sport.values() if s == ProviderAuthorizationStatus.AUTHORIZED_FOR_SANITIZED_LIVE_PROBE),
            "blocked_no_credentials_count": sum(1 for s in status_by_sport.values() if s == ProviderAuthorizationStatus.BLOCKED_NO_CREDENTIALS),
            "blocked_terms_review_not_approved_count": sum(1 for s in status_by_sport.values() if s == ProviderAuthorizationStatus.BLOCKED_TERMS_REVIEW_NOT_APPROVED),
            "blocked_data_scope_not_approved_count": sum(1 for s in status_by_sport.values() if s == ProviderAuthorizationStatus.BLOCKED_DATA_SCOPE_NOT_APPROVED),
            "blocked_operator_approval_missing_count": sum(1 for s in status_by_sport.values() if s == ProviderAuthorizationStatus.BLOCKED_OPERATOR_APPROVAL_MISSING)
        }
    }

def validate_authorization_report(report: dict[str, Any]) -> list[str]:
    errors = []
    if set(report.get('target_sports', [])) != set(TARGET_SPORTS):
        errors.append('target_sports_mismatch')
    for k in ('live_calls_made', 'provider_access_attempted', 'production_activation', 'betting_decisions'):
        if report.get(k) is not False:
            errors.append(f'{k}_must_be_false')
    by = report.get('provider_access_by_sport', {})
    if set(by) != set(TARGET_SPORTS):
        errors.append('authorization_sports_mismatch')
    for sport, items in by.items():
        for item in items:
            if item.get('allow_real_network') is not False:
                errors.append(f'allow_real_network_true:{sport}')
            if item.get('max_requests', 99) > 1:
                errors.append(f'max_requests_too_high:{sport}')
            if item.get('production_selectable') is not False:
                errors.append(f'production_selectable_true:{sport}')
            if item.get('betting_decisions_enabled') is not False:
                errors.append(f'betting_decisions_enabled_true:{sport}')
            if item.get('status') == ProviderAuthorizationStatus.AUTHORIZED_FOR_SANITIZED_LIVE_PROBE:
                if not (item.get('credential_present') and item.get('terms_review_approved') and item.get('data_scope_approved') and item.get('operator_approved')):
                    errors.append(f'authorized_without_full_gate:{sport}')
    return errors
