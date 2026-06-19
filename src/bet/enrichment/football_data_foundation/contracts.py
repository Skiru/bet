from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class RawFootballDataBundle:
    provider: str
    source_family: str
    source_class: str
    operation: str
    request_identity: str
    retrieved_at: datetime
    source_library: str
    source_library_version: str
    parser_version: str
    schema_fingerprint: str
    data_fingerprint: str
    row_count: int
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    native_ids: tuple[str, ...] = field(default_factory=tuple)
    native_names: tuple[str, ...] = field(default_factory=tuple)
    raw_payload: Any = None

@dataclass(frozen=True)
class NormalizedFootballDataRecord:
    provider: str
    source_family: str
    source_class: str
    operation: str
    request_identity: str
    normalized_at: datetime
    normalization_version: str
    schema_fingerprint: str
    data_fingerprint: str
    row_count: int
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    native_ids: tuple[str, ...] = field(default_factory=tuple)
    native_names: tuple[str, ...] = field(default_factory=tuple)
    records: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
