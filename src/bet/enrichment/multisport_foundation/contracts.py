from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SportKey(str, Enum):
    BASKETBALL = "basketball"
    VOLLEYBALL = "volleyball"
    HOCKEY = "hockey"
    TENNIS = "tennis"
    CS2 = "cs2"
    DOTA2 = "dota2"
    VALORANT = "valorant"


class ProviderRole(str, Enum):
    CURRENT_LIVE = "current_live"
    CURRENT_REFERENCE = "current_reference"
    HISTORICAL_REFERENCE = "historical_reference"
    ESPORTS_LIVE = "esports_live"
    ESPORTS_REFERENCE = "esports_reference"
    DEFERRED_BY_ACCESS = "deferred_by_access"


class ProofLevel(str, Enum):
    REAL_LIVE_HTTP_PROOF = "real_live_http_proof"
    REAL_REPLAY_CORPUS_PROOF = "real_replay_corpus_proof"
    REAL_OPEN_DATA_PROOF = "real_open_data_proof"
    DOCS_CAPABILITY_ONLY = "docs_capability_only"
    BLOCKED_ACCESS_PROOF = "blocked_access_proof"
    NO_PROOF = "no_proof"


class OutcomeStatus(str, Enum):
    SOURCE_BOUND_SHADOW_READY = "SOURCE_BOUND_SHADOW_READY"
    ACTIVATION_CANDIDATE_SHADOW_ONLY = "ACTIVATION_CANDIDATE_SHADOW_ONLY"
    REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT = (
        "REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT"
    )
    BLOCKED_PROVIDER_ACCESS = "BLOCKED_PROVIDER_ACCESS"
    BLOCKED_NO_CREDENTIALS = "BLOCKED_NO_CREDENTIALS"
    BLOCKED_NO_REAL_PROVIDER_ACCESS = "BLOCKED_NO_REAL_PROVIDER_ACCESS"


class PassKind(str, Enum):
    KERNEL_PROFILES = "MS-A_KERNEL_PROFILES"
    PROVIDER_CORPUS_SHADOW = "MS-B_PROVIDER_CORPUS_SHADOW"
    ACTIVATION_LIVE_OBSERVATION = "MS-C_ACTIVATION_LIVE_OBSERVATION"
    FINAL_MERGE_GATE = "MS-D_FINAL_MERGE_GATE"


@dataclass(frozen=True)
class FactRequirement:
    name: str
    required_for_shadow_ready: bool
    unknown_allowed: bool
    description: str

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "required_for_shadow_ready": self.required_for_shadow_ready,
            "unknown_allowed": self.unknown_allowed,
            "description": self.description,
        }


@dataclass(frozen=True)
class SportProfile:
    sport: SportKey
    identity_keys: tuple[str, ...]
    fixture_terms: tuple[str, ...]
    minimum_real_mapped_providers: int
    required_facts: tuple[FactRequirement, ...]
    provider_candidates: tuple[str, ...]
    blocked_is_valid_outcome: bool = True

    def to_json(self) -> dict[str, Any]:
        return {
            "sport": self.sport.value,
            "identity_keys": list(self.identity_keys),
            "fixture_terms": list(self.fixture_terms),
            "minimum_real_mapped_providers": self.minimum_real_mapped_providers,
            "required_facts": [item.to_json() for item in self.required_facts],
            "provider_candidates": list(self.provider_candidates),
            "blocked_is_valid_outcome": self.blocked_is_valid_outcome,
        }


@dataclass(frozen=True)
class ProviderProfile:
    key: str
    roles: tuple[ProviderRole, ...]
    sports_supported: tuple[SportKey, ...]
    credential_env_names: tuple[str, ...]
    max_rps: float | None
    docs_url: str
    allowed_proof_levels: tuple[ProofLevel, ...]
    notes: str

    def supports(self, sport: SportKey) -> bool:
        return sport in self.sports_supported

    def to_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "roles": [role.value for role in self.roles],
            "sports_supported": [sport.value for sport in self.sports_supported],
            "credential_env_names": list(self.credential_env_names),
            "max_rps": self.max_rps,
            "docs_url": self.docs_url,
            "allowed_proof_levels": [level.value for level in self.allowed_proof_levels],
            "notes": self.notes,
        }


@dataclass(frozen=True)
class PassDefinition:
    pass_kind: PassKind
    objective: str
    allowed_paths: tuple[str, ...]
    forbidden_paths: tuple[str, ...]
    required_gates: tuple[str, ...]
    success_statuses: tuple[OutcomeStatus, ...]
    agent_must_not: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "pass_kind": self.pass_kind.value,
            "objective": self.objective,
            "allowed_paths": list(self.allowed_paths),
            "forbidden_paths": list(self.forbidden_paths),
            "required_gates": list(self.required_gates),
            "success_statuses": [status.value for status in self.success_statuses],
            "agent_must_not": list(self.agent_must_not),
        }


@dataclass
class MultisportPlan:
    profiles: dict[SportKey, SportProfile]
    providers: dict[str, ProviderProfile]
    passes: tuple[PassDefinition, ...]
    global_guardrails: tuple[str, ...]
    generated_reports: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "profiles": {
                sport.value: profile.to_json()
                for sport, profile in sorted(self.profiles.items(), key=lambda item: item[0].value)
            },
            "providers": {
                key: provider.to_json()
                for key, provider in sorted(self.providers.items(), key=lambda item: item[0])
            },
            "passes": [item.to_json() for item in self.passes],
            "global_guardrails": list(self.global_guardrails),
            "generated_reports": self.generated_reports,
        }
