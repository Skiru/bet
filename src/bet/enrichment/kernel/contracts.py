from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Generic, Protocol, TypeVar

from bet.integration.source_result import SourceOperationResult, SourceResultStatus
from src.bet.enrichment.kernel.codec import canonical_sha256, to_primitive

P = TypeVar("P")
T = TypeVar("T")


class SubjectRole(StrEnum):
    EVENT = "EVENT"
    HOME = "HOME"
    AWAY = "AWAY"
    SIDE_A = "SIDE_A"
    SIDE_B = "SIDE_B"
    TEAM = "TEAM"
    ATHLETE = "ATHLETE"
    COMPETITION = "COMPETITION"
    SEASON = "SEASON"
    VENUE = "VENUE"
    OFFICIAL = "OFFICIAL"


@dataclass(frozen=True, slots=True)
class OperationSubject:
    entity_id: int
    role: SubjectRole

    def __post_init__(self):
        if not isinstance(self.entity_id, int) or isinstance(self.entity_id, bool) or self.entity_id <= 0:
            raise ValueError("entity_id must be a positive integer")


@dataclass(frozen=True, slots=True)
class OperationRequest(Generic[P]):
    sport: str
    capability_key: str
    target_event_entity_id: int
    subject: OperationSubject
    provider: str
    provider_event_id: str | None
    provider_subject_id: str | None
    provider_related_subject_ids: Mapping[str, str]
    provider_competition_id: str | None
    provider_season_id: str | None
    analysis_cutoff_at: datetime
    parameters: P
    contract_version: str
    dto_version: str

    def __post_init__(self):
        if not isinstance(self.target_event_entity_id, int) or isinstance(self.target_event_entity_id, bool) or self.target_event_entity_id <= 0:
            raise ValueError("target_event_entity_id must be a positive integer")
        if self.analysis_cutoff_at.tzinfo is None:
            raise ValueError("analysis_cutoff_at must be timezone-aware")

        for field_name in ["sport", "capability_key", "provider", "contract_version", "dto_version"]:
            field_value = getattr(self, field_name)
            if not field_value or not str(field_value).strip():
                raise ValueError(f"{field_name} cannot be empty")

        for k, v in self.provider_related_subject_ids.items():
            if not k or not k.strip() or not v or not v.strip():
                raise ValueError("provider_related_subject_ids keys and values cannot be empty")

        # Defensive copy of provider_related_subject_ids
        object.__setattr__(self, 'provider_related_subject_ids', dict(sorted(self.provider_related_subject_ids.items())))


    def logical_identity(self) -> str:
        # Canonicalize analysis_cutoff_at to UTC
        canonical_cutoff = self.analysis_cutoff_at.astimezone(UTC)

        # Create a dictionary of semantic fields for hashing
        semantic_fields = {
            "sport": self.sport,
            "capability_key": self.capability_key,
            "target_event_entity_id": self.target_event_entity_id,
            "subject": to_primitive(self.subject),
            "provider": self.provider,
            "provider_event_id": self.provider_event_id,
            "provider_subject_id": self.provider_subject_id,
            "provider_related_subject_ids": self.provider_related_subject_ids, # already sorted in __post_init__
            "provider_competition_id": self.provider_competition_id,
            "provider_season_id": self.provider_season_id,
            "analysis_cutoff_at": canonical_cutoff,
            "parameters": to_primitive(self.parameters),
            "contract_version": self.contract_version,
            "dto_version": self.dto_version,
        }
        return canonical_sha256(semantic_fields)


class EnrichmentAdapter(Protocol):
    @property
    def provider(self) -> str: ...

    @property
    def provenance_family(self) -> str: ...

    def execute(
        self,
        request: OperationRequest[object],
    ) -> SourceOperationResult[object]: ...


@dataclass(frozen=True, slots=True)
class PlannedTransportCall:
    provider: str
    operation: str
    sanitized_request_identity: str
    worst_case_http_calls: int

    def __post_init__(self):
        if not isinstance(self.worst_case_http_calls, int) or isinstance(self.worst_case_http_calls, bool) or self.worst_case_http_calls < 0:
            raise ValueError("worst_case_http_calls must be a non-negative integer")
        for field_name in ["provider", "operation", "sanitized_request_identity"]:
            field_value = getattr(self, field_name)
            if not field_value or not str(field_value).strip():
                raise ValueError(f"{field_name} cannot be empty")


class ProbeableEnrichmentAdapter(EnrichmentAdapter, Protocol):
    def preview_transport(
        self,
        request: OperationRequest[object],
    ) -> tuple[PlannedTransportCall, ...]: ...


@dataclass(frozen=True, slots=True)
class RouteCandidate:
    provider: str
    provenance_family: str
    ordinal: int

    def __post_init__(self):
        if not isinstance(self.ordinal, int) or isinstance(self.ordinal, bool) or self.ordinal < 0:
            raise ValueError("ordinal must be a non-negative integer")
        for field_name in ["provider", "provenance_family"]:
            field_value = getattr(self, field_name)
            if not field_value or not str(field_value).strip():
                raise ValueError(f"{field_name} cannot be empty")


class TerminalClass(StrEnum):
    PARTIAL = "PARTIAL"
    VALID_EMPTY = "VALID_EMPTY"
    TEMPORAL = "TEMPORAL"
    SEMANTIC = "SEMANTIC"
    OPERATIONAL = "OPERATIONAL"


DEFAULT_TERMINAL_PRECEDENCE = (
    TerminalClass.PARTIAL,
    TerminalClass.VALID_EMPTY,
    TerminalClass.TEMPORAL,
    TerminalClass.SEMANTIC,
    TerminalClass.OPERATIONAL,
)

AVAILABILITY_TERMINAL_PRECEDENCE = (
    TerminalClass.PARTIAL,
    TerminalClass.VALID_EMPTY,
    TerminalClass.SEMANTIC,
    TerminalClass.TEMPORAL,
    TerminalClass.OPERATIONAL,
)


@dataclass(frozen=True, slots=True)
class PlannedOperation(Generic[P]):
    capability_key: str
    subject: OperationSubject
    parameters: P
    route: tuple[RouteCandidate, ...]
    freshness_seconds: int | None
    required: bool
    terminal_precedence: tuple[TerminalClass, ...] = DEFAULT_TERMINAL_PRECEDENCE

    def __post_init__(self):
        if not self.capability_key or not self.capability_key.strip():
            raise ValueError("capability_key cannot be empty")
        if not self.route:
            raise ValueError("route cannot be empty")

        seen_ordinals = set()
        seen_providers = set()
        for i, candidate in enumerate(self.route):
            if candidate.ordinal != i:
                raise ValueError("route ordinals must be contiguous starting from 0")
            if candidate.ordinal in seen_ordinals:
                raise ValueError(f"duplicate ordinal {candidate.ordinal} in route")
            if candidate.provider in seen_providers:
                raise ValueError(f"duplicate provider {candidate.provider} in route")
            seen_ordinals.add(candidate.ordinal)
            seen_providers.add(candidate.provider)

        if self.freshness_seconds is not None:
            if not isinstance(self.freshness_seconds, int) or isinstance(self.freshness_seconds, bool) or self.freshness_seconds <= 0:
                raise ValueError("freshness_seconds must be a positive integer or None")

        if not self.terminal_precedence:
            raise ValueError("terminal_precedence cannot be empty")
        if len(self.terminal_precedence) != len(set(self.terminal_precedence)):
            raise ValueError("terminal_precedence cannot have duplicate entries")


@dataclass(frozen=True, slots=True)
class EnrichmentPlan:
    sport: str
    target_event_entity_id: int
    analysis_cutoff_at: datetime
    operations: tuple[PlannedOperation[object], ...]
    contract_hash: str
    metric_contract_hash: str
    policy_config_hash: str
    selection_epoch: int

    def __post_init__(self):
        if not isinstance(self.target_event_entity_id, int) or isinstance(self.target_event_entity_id, bool) or self.target_event_entity_id <= 0:
            raise ValueError("target_event_entity_id must be a positive integer")
        if self.analysis_cutoff_at.tzinfo is None:
            raise ValueError("analysis_cutoff_at must be timezone-aware")

        for field_name in ["sport", "contract_hash", "metric_contract_hash", "policy_config_hash"]:
            field_value = getattr(self, field_name)
            if not field_value or not str(field_value).strip():
                raise ValueError(f"{field_name} cannot be empty")

        if not self.operations:
            raise ValueError("operations cannot be empty")

        if not isinstance(self.selection_epoch, int) or isinstance(self.selection_epoch, bool) or self.selection_epoch < 0:
            raise ValueError("selection_epoch must be a non-negative integer")

        seen_operations = set()
        for op in self.operations:
            op_identity = (op.capability_key, op.subject.entity_id, op.subject.role)
            if op_identity in seen_operations:
                raise ValueError(f"duplicate operation identity: {op_identity}")
            seen_operations.add(op_identity)


    def plan_hash(self) -> str:
        # Canonicalize analysis_cutoff_at to UTC
        canonical_cutoff = self.analysis_cutoff_at.astimezone(UTC)

        semantic_fields = {
            "sport": self.sport,
            "target_event_entity_id": self.target_event_entity_id,
            "analysis_cutoff_at": canonical_cutoff,
            "operations": to_primitive(self.operations),
            "contract_hash": self.contract_hash,
            "metric_contract_hash": self.metric_contract_hash,
            "policy_config_hash": self.policy_config_hash,
            "selection_epoch": self.selection_epoch,
        }
        return canonical_sha256(semantic_fields)


@dataclass(frozen=True, slots=True)
class AttemptResult:
    capability_key: str
    subject: OperationSubject
    provider: str
    provenance_family: str
    ordinal: int
    logical_request_identity: str
    result: SourceOperationResult[object]

    def __post_init__(self):
        if not isinstance(self.ordinal, int) or isinstance(self.ordinal, bool) or self.ordinal < 0:
            raise ValueError("ordinal must be a non-negative integer")
        for field_name in ["capability_key", "provider", "provenance_family", "logical_request_identity"]:
            field_value = getattr(self, field_name)
            if not field_value or not str(field_value).strip():
                raise ValueError(f"{field_name} cannot be empty")


@dataclass(frozen=True, slots=True)
class CapabilityResolution:
    capability_key: str
    subject: OperationSubject
    attempts: tuple[AttemptResult, ...]
    selected_attempt_index: int | None
    terminal_status: SourceResultStatus

    def __post_init__(self):
        if not self.attempts:
            raise ValueError("attempts cannot be empty")
        if self.selected_attempt_index is not None:
            if not isinstance(self.selected_attempt_index, int) or isinstance(self.selected_attempt_index, bool) or not (0 <= self.selected_attempt_index < len(self.attempts)):
                raise ValueError("selected_attempt_index must be a valid index or None")


@dataclass(frozen=True, slots=True)
class ProviderIdentitySet:
    provider: str
    event_id: str | None
    competition_id: str | None
    season_id: str | None
    participant_ids: Mapping[int, str]
    venue_id: str | None = None
    official_id: str | None = None

    def __post_init__(self):
        if not self.provider or not self.provider.strip():
            raise ValueError("provider cannot be empty")

        for k, v in self.participant_ids.items():
            if not isinstance(k, int) or isinstance(k, bool) or k <= 0:
                raise ValueError("participant_ids keys must be positive integers")
            if not v or not v.strip():
                raise ValueError("participant_ids values cannot be empty strings")

        # Defensive copy of participant_ids
        object.__setattr__(self, 'participant_ids', dict(self.participant_ids))


class QualifiedIdentityResolver(Protocol):
    def resolve(
        self,
        *,
        provider: str,
        target_event_entity_id: int,
        subjects: tuple[OperationSubject, ...],
        valid_at: datetime,
    ) -> ProviderIdentitySet: ...
