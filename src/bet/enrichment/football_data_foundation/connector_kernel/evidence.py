from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Mapping
from bet.enrichment.football_data_foundation.evidence import AtomicEvidence
from bet.enrichment.football_data_foundation.fingerprints import compute_schema_fingerprint, compute_data_fingerprint

class EvidencePackager:
    def create_package(
        self,
        provider: str,
        source_family: str,
        source_class: str,
        operation: str,
        capability: str,
        scope: str,
        request_identity: str,
        raw_payload: Any,
        normalized_records: list[Mapping[str, Any]],
        cache_hit: bool = False,
        pagination_model: str = "UNKNOWN",
        diagnostics: Mapping[str, Any] | None = None
    ) -> AtomicEvidence:
        retrieved_at = datetime.now(timezone.utc).isoformat()
        
        schema_fingerprint = compute_schema_fingerprint(raw_payload)
        raw_fingerprint = compute_data_fingerprint(raw_payload)
        normalized_fingerprint = compute_data_fingerprint(normalized_records)
        
        return AtomicEvidence(
            provider=provider,
            source=f"{source_family}:{source_class}",
            operation=operation,
            capability=capability,
            scope=scope,
            request_identity=request_identity,
            retrieved_at=retrieved_at,
            parser_version="football_foundation_v1",
            normalization_version="football_foundation_v1",
            schema_fingerprint=schema_fingerprint,
            raw_fingerprint=raw_fingerprint,
            normalized_fingerprint=normalized_fingerprint,
            row_count=len(normalized_records),
            diagnostics=diagnostics or {},
            cache_hit=cache_hit,
            pagination_model=pagination_model
        )
