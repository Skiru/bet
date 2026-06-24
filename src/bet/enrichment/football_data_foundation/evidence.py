from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AtomicEvidence:
    provider: str
    source: str
    operation: str
    capability: str
    scope: str
    request_identity: str
    retrieved_at: str
    parser_version: str
    normalization_version: str
    schema_fingerprint: str
    raw_fingerprint: str
    normalized_fingerprint: str
    row_count: int
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    cache_hit: bool = False
    pagination_model: str = "UNKNOWN"
    evidence_id: str = ""

    def __post_init__(self) -> None:
        # Compute evidence_id if not provided
        if not self.evidence_id:
            payload = {
                "provider": self.provider,
                "source": self.source,
                "operation": self.operation,
                "capability": self.capability,
                "scope": self.scope,
                "request_identity": self.request_identity,
                "retrieved_at": self.retrieved_at,
                "parser_version": self.parser_version,
                "normalization_version": self.normalization_version,
                "schema_fingerprint": self.schema_fingerprint,
                "raw_fingerprint": self.raw_fingerprint,
                "normalized_fingerprint": self.normalized_fingerprint,
                "row_count": self.row_count,
                "diagnostics": dict(sorted(self.diagnostics.items())),
                "cache_hit": self.cache_hit,
                "pagination_model": self.pagination_model,
            }
            serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
            # Since dataclass is frozen, we set field via object.__setattr__
            object.__setattr__(self, "evidence_id", digest)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "source": self.source,
            "operation": self.operation,
            "capability": self.capability,
            "scope": self.scope,
            "request_identity": self.request_identity,
            "retrieved_at": self.retrieved_at,
            "parser_version": self.parser_version,
            "normalization_version": self.normalization_version,
            "schema_fingerprint": self.schema_fingerprint,
            "raw_fingerprint": self.raw_fingerprint,
            "normalized_fingerprint": self.normalized_fingerprint,
            "row_count": self.row_count,
            "diagnostics": self.diagnostics,
            "cache_hit": self.cache_hit,
            "pagination_model": self.pagination_model,
            "evidence_id": self.evidence_id,
        }
