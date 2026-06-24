from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Protocol

from .errors import (
    CredentialsMissingError,
    EvidenceKernelError,
    FusionNotAllowedError,
    FreshnessViolation,
    IdentityMappingViolation,
    PayloadPolicyViolation,
    ProofLevelViolation,
    ProviderCapabilityError,
)


class ProofLevel(StrEnum):
    REAL_ACCEPTED_ARTIFACT_PROOF = "REAL_ACCEPTED_ARTIFACT_PROOF"
    REAL_LOCAL_OPEN_DATA_PROOF = "REAL_LOCAL_OPEN_DATA_PROOF"
    REAL_DEPENDENCY_REPLAY_PROOF = "REAL_DEPENDENCY_REPLAY_PROOF"
    REAL_LIVE_API_PROOF = "REAL_LIVE_API_PROOF"
    SYNTHETIC_CONTRACT_PROOF = "SYNTHETIC_CONTRACT_PROOF"
    DOCS_CAPABILITY_ONLY = "DOCS_CAPABILITY_ONLY"
    NO_PROOF = "NO_PROOF"


class SourceRole(StrEnum):
    CURRENT_LIVE = "CURRENT_LIVE"
    CURRENT_LIVE_BENCHMARK = "CURRENT_LIVE_BENCHMARK"
    CURRENT_LIVE_OR_RECENT_DETAILED_SHADOW = "CURRENT_LIVE_OR_RECENT_DETAILED_SHADOW"
    CURRENT_REFERENCE = "CURRENT_REFERENCE"
    HISTORICAL_DEEP = "HISTORICAL_DEEP"
    REFERENCE_IDENTITY = "REFERENCE_IDENTITY"
    REFERENCE_METADATA_SHADOW = "REFERENCE_METADATA_SHADOW"
    DEPENDENCY_REPLAY = "DEPENDENCY_REPLAY"
    OPTIONAL_LIBRARY_BRIDGE = "OPTIONAL_LIBRARY_BRIDGE"
    EXPERIMENTAL_PROBE = "EXPERIMENTAL_PROBE"
    LATER_PROVIDER_CANDIDATE = "LATER_PROVIDER_CANDIDATE"
    REJECTED_OR_DEFERRED = "REJECTED_OR_DEFERRED"


class FactType(StrEnum):
    FIXTURE_IDENTITY = "FIXTURE_IDENTITY"
    MATCH_STATUS = "MATCH_STATUS"
    SCORE = "SCORE"
    STANDINGS = "STANDINGS"
    TEAM_FORM = "TEAM_FORM"
    HISTORICAL_FORM_H2H = "HISTORICAL_FORM_H2H"
    PLAYER_AVAILABILITY = "PLAYER_AVAILABILITY"
    LINEUP = "LINEUP"
    MATCH_EVENT = "MATCH_EVENT"
    MATCH_STATISTIC = "MATCH_STATISTIC"
    XG = "XG"
    SHOT = "SHOT"
    THREE_SIXTY_FRAME = "THREE_SIXTY_FRAME"
    ODDS_REFERENCE = "ODDS_REFERENCE"
    TEAM_RATING = "TEAM_RATING"
    PLAYER_DATA_CONTEXT = "PLAYER_DATA_CONTEXT"
    HIGHLIGHT = "HIGHLIGHT"
    PREDICTION_REFERENCE = "PREDICTION_REFERENCE"
    HISTORICAL_PRIOR = "HISTORICAL_PRIOR"
    REFERENCE_SCHEDULE = "REFERENCE_SCHEDULE"
    REFERENCE_RESULT = "REFERENCE_RESULT"
    METADATA = "METADATA"


KEBAB_CASE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA256_HEX = re.compile(r"^[a-fA-F0-9]{64}$")
RAW_KEYS = {"raw", "payload", "raw_payload", "response_body", "html", "json_raw", "raw_json", "raw_html"}


def sanitized_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _assert_json_serializable_without_datetime(value: Mapping[str, Any]) -> None:
    def reject(obj: Any) -> Any:
        if isinstance(obj, datetime):
            raise TypeError("datetime must be an ISO string inside claim_value")
        raise TypeError(f"not JSON serializable: {type(obj)!r}")

    json.dumps(value, sort_keys=True, default=reject)


def _contains_forbidden_raw_key(value: Mapping[str, Any]) -> bool:
    def walk(obj: Any) -> bool:
        if isinstance(obj, Mapping):
            for key, nested in obj.items():
                if str(key).lower() in RAW_KEYS:
                    return True
                if walk(nested):
                    return True
        elif isinstance(obj, (tuple, list)):
            return any(walk(item) for item in obj)
        return False

    return walk(value)


@dataclass(frozen=True)
class SourceDescriptor:
    source_key: str
    display_name: str
    role: SourceRole
    requires_credentials: bool
    supports_live: bool
    supports_historical: bool
    supports_reference: bool
    supports_replay: bool
    allowed_proof_levels: tuple[ProofLevel, ...]
    forbidden_fact_types: tuple[FactType, ...] = ()
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not KEBAB_CASE.match(self.source_key):
            raise ProviderCapabilityError("source_key must be non-empty lowercase kebab-case")
        if self.role in {
            SourceRole.CURRENT_LIVE,
            SourceRole.CURRENT_LIVE_BENCHMARK,
            SourceRole.CURRENT_LIVE_OR_RECENT_DETAILED_SHADOW,
        } and not self.supports_live:
            raise ProviderCapabilityError("current/live roles must support live")
        if self.role is SourceRole.HISTORICAL_DEEP and self.supports_live:
            raise ProviderCapabilityError("HISTORICAL_DEEP source cannot support live truth")
        if self.role is SourceRole.REFERENCE_IDENTITY:
            forbidden_deep = {
                FactType.XG,
                FactType.SHOT,
                FactType.THREE_SIXTY_FRAME,
                FactType.MATCH_STATISTIC,
                FactType.LINEUP,
            }
            if not forbidden_deep.issubset(set(self.forbidden_fact_types)):
                raise ProviderCapabilityError("REFERENCE_IDENTITY source must forbid detailed/stat event fact types")
        if self.role is SourceRole.EXPERIMENTAL_PROBE and ProofLevel.REAL_LIVE_API_PROOF in self.allowed_proof_levels:
            raise ProviderCapabilityError("EXPERIMENTAL_PROBE cannot allow REAL_LIVE_API_PROOF")
        if self.role is SourceRole.LATER_PROVIDER_CANDIDATE and ProofLevel.REAL_LIVE_API_PROOF in self.allowed_proof_levels:
            raise ProviderCapabilityError("later provider candidate cannot allow live proof before its own certification phase")


@dataclass(frozen=True)
class ProviderIdentity:
    source_key: str
    provider_fixture_id: str | None = None
    provider_competition_id: str | None = None
    provider_season_id: str | None = None
    provider_home_team_id: str | None = None
    provider_away_team_id: str | None = None
    provider_player_ids: tuple[str, ...] = ()
    normalized_home_name: str | None = None
    normalized_away_name: str | None = None
    identity_confidence: float | None = None
    identity_warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not KEBAB_CASE.match(self.source_key):
            raise IdentityMappingViolation("identity source_key must be kebab-case")
        if self.identity_confidence is not None and not 0 <= self.identity_confidence <= 1:
            raise IdentityMappingViolation("identity confidence must be 0..1")
        if self.provider_home_team_id and self.provider_home_team_id == self.provider_away_team_id:
            raise IdentityMappingViolation("home and away provider IDs cannot be identical")

    @property
    def complete_fixture_identity(self) -> bool:
        return bool(
            self.provider_fixture_id
            and self.provider_home_team_id
            and self.provider_away_team_id
            and self.normalized_home_name
            and self.normalized_away_name
        )


@dataclass(frozen=True)
class EvidenceFreshness:
    observed_at: datetime
    source_reported_at: datetime | None = None
    valid_from: datetime | None = None
    stale_after: datetime | None = None
    is_current_truth_allowed: bool = False
    freshness_reason: str = ""

    def __post_init__(self) -> None:
        for name in ("observed_at", "source_reported_at", "valid_from", "stale_after"):
            value = getattr(self, name)
            if value is not None and value.tzinfo is None:
                raise FreshnessViolation(f"{name} must be timezone-aware")
        if self.observed_at.tzinfo is not UTC:
            object.__setattr__(self, "observed_at", self.observed_at.astimezone(UTC))
        if self.stale_after is not None and self.stale_after <= self.observed_at:
            raise FreshnessViolation("stale_after must be after observed_at")


@dataclass(frozen=True)
class PayloadPolicy:
    raw_payload_stored: bool = False
    raw_payload_git_allowed: bool = False
    sanitized_sample_allowed: bool = True
    payload_hash: str | None = None
    payload_byte_count: int | None = None
    payload_record_count: int | None = None

    def __post_init__(self) -> None:
        if self.raw_payload_git_allowed:
            raise PayloadPolicyViolation("raw payloads are never allowed in Git")
        if self.raw_payload_stored and not self.payload_hash:
            raise PayloadPolicyViolation("raw_payload_stored requires payload_hash")
        if self.payload_hash and not SHA256_HEX.match(self.payload_hash):
            raise PayloadPolicyViolation("payload_hash must be sha256 hex")
        if self.payload_byte_count is not None and self.payload_byte_count < 0:
            raise PayloadPolicyViolation("payload_byte_count cannot be negative")
        if self.payload_record_count is not None and self.payload_record_count < 0:
            raise PayloadPolicyViolation("payload_record_count cannot be negative")


@dataclass(frozen=True)
class EvidenceClaim:
    source: SourceDescriptor
    proof_level: ProofLevel
    fact_type: FactType
    identity: ProviderIdentity
    freshness: EvidenceFreshness
    payload_policy: PayloadPolicy
    claim_value: Mapping[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.proof_level not in self.source.allowed_proof_levels:
            raise ProofLevelViolation(f"proof level {self.proof_level} is not allowed for {self.source.source_key}")
        if self.fact_type in set(self.source.forbidden_fact_types):
            raise ProviderCapabilityError(f"{self.source.source_key} cannot emit {self.fact_type}")
        if self.identity.source_key != self.source.source_key:
            raise IdentityMappingViolation("claim identity source_key must match claim source")
        if not 0 <= self.confidence <= 1:
            raise ProofLevelViolation("claim confidence must be 0..1")
        if self.proof_level is ProofLevel.SYNTHETIC_CONTRACT_PROOF:
            if self.claim_value or self.confidence > 0:
                raise ProofLevelViolation("synthetic contract proof cannot carry value or confidence")
        if self.proof_level is ProofLevel.DOCS_CAPABILITY_ONLY and self.claim_value:
            raise ProofLevelViolation("docs-only proof cannot carry claim_value")
        if self.proof_level is ProofLevel.NO_PROOF and not self.errors:
            raise ProofLevelViolation("NO_PROOF requires explicit errors")
        if self.source.role in {
            SourceRole.HISTORICAL_DEEP,
            SourceRole.REFERENCE_IDENTITY,
            SourceRole.REFERENCE_METADATA_SHADOW,
            SourceRole.DEPENDENCY_REPLAY,
            SourceRole.OPTIONAL_LIBRARY_BRIDGE,
            SourceRole.EXPERIMENTAL_PROBE,
            SourceRole.LATER_PROVIDER_CANDIDATE,
            SourceRole.REJECTED_OR_DEFERRED,
        } and self.freshness.is_current_truth_allowed:
            raise FreshnessViolation(f"{self.source.role} cannot be current live truth")
        if _contains_forbidden_raw_key(self.claim_value):
            raise PayloadPolicyViolation("claim_value contains forbidden raw payload key")
        _assert_json_serializable_without_datetime(self.claim_value)

    @property
    def selectable_for_production(self) -> bool:
        return False

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "source_key": self.source.source_key,
            "source_role": self.source.role.value,
            "proof_level": self.proof_level.value,
            "fact_type": self.fact_type.value,
            "claim_value": dict(self.claim_value),
            "confidence": self.confidence,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "selectable_for_production": False,
        }


@dataclass(frozen=True)
class EvidenceClaimBatch:
    batch_id: str
    source_key: str
    adapter_name: str
    adapter_version: str
    generated_at: datetime
    claims: tuple[EvidenceClaim, ...]
    batch_warnings: tuple[str, ...] = ()
    batch_errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None:
            raise FreshnessViolation("batch generated_at must be timezone-aware")
        for claim in self.claims:
            if claim.source.source_key != self.source_key:
                raise ProviderCapabilityError("all claims in a batch must share source_key")

    @staticmethod
    def deterministic_id(source_key: str, adapter_version: str, claims: tuple[EvidenceClaim, ...]) -> str:
        serial = json.dumps([c.to_public_dict() for c in claims], sort_keys=True)
        return hashlib.sha256(f"{source_key}:{adapter_version}:{serial}".encode()).hexdigest()[:16]

    def summary_counts(self) -> dict[str, dict[str, int]]:
        proof: dict[str, int] = {}
        fact: dict[str, int] = {}
        for claim in self.claims:
            proof[claim.proof_level.value] = proof.get(claim.proof_level.value, 0) + 1
            fact[claim.fact_type.value] = fact.get(claim.fact_type.value, 0) + 1
        return {"proof_level": proof, "fact_type": fact}

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "source_key": self.source_key,
            "adapter_name": self.adapter_name,
            "adapter_version": self.adapter_version,
            "generated_at": self.generated_at.isoformat(),
            "claims": [claim.to_public_dict() for claim in self.claims],
            "summary_counts": self.summary_counts(),
            "selectable_for_production": False,
        }


class FootballEvidenceAdapter(Protocol):
    def source_descriptor(self) -> SourceDescriptor: ...
    def adapter_name(self) -> str: ...
    def adapter_version(self) -> str: ...
    def capabilities(self) -> Mapping[str, Any]: ...
    def build_contract_probe(self) -> EvidenceClaimBatch: ...
    def normalize_replay_fixture(self, input_path: Path) -> EvidenceClaimBatch: ...
    def fetch_shadow_live(self, query: Mapping[str, Any]) -> EvidenceClaimBatch: ...
