from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bet.integration.evidence import EvidenceRef


class SourceResultStatus(StrEnum):
    SUCCESS = "SUCCESS"
    VALID_EMPTY = "VALID_EMPTY"
    NOT_FOUND = "NOT_FOUND"
    NOT_PUBLISHED_YET = "NOT_PUBLISHED_YET"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    AMBIGUOUS = "AMBIGUOUS"
    PLAN_RESTRICTED = "PLAN_RESTRICTED"
    LICENSE_BLOCKED = "LICENSE_BLOCKED"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    BLOCKED = "BLOCKED"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"
    UPSTREAM_ERROR = "UPSTREAM_ERROR"
    PARSE_ERROR = "PARSE_ERROR"
    SCHEMA_ERROR = "SCHEMA_ERROR"
    EVIDENCE_ERROR = "EVIDENCE_ERROR"
    PARTIAL = "PARTIAL"
    TIMEOUT = "TIMEOUT"
    STALE = "STALE"
    TEMPORAL_UNSAFE = "TEMPORAL_UNSAFE"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class SourceOperationResult[T]:
    status: SourceResultStatus
    value: T | None = None
    provider: str = ""
    operation: str = ""
    request_identity: str = ""
    evidence_refs: tuple[EvidenceRef, ...] = field(default_factory=tuple)
    bundle_id: str = ""
    retrieved_at: datetime | None = None
    provider_updated_at: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    http_status: int | None = None
    error_code: str = ""
    retry_after_seconds: float | None = None
    retry_count: int = 0
    quota_metadata: Mapping[str, Any] = field(default_factory=dict)
    parser_diagnostics: Mapping[str, Any] = field(default_factory=dict)
    schema_fingerprint: str = ""
    parser_version: str = ""
    normalization_version: str = ""
    retryable: bool = False  # Keep for backward compatibility


def normalize_source_result_status(
    status: SourceResultStatus | str,
) -> SourceResultStatus:
    if status == SourceResultStatus.UNSUPPORTED or status == "UNSUPPORTED":
        return SourceResultStatus.NOT_SUPPORTED
    if isinstance(status, SourceResultStatus):
        return status
    try:
        return SourceResultStatus(status)
    except ValueError:
        raise ValueError(f"Unknown SourceResultStatus value: {status}")
