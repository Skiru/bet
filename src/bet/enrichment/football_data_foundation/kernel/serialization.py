from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Mapping

from .contracts import (
    EvidenceClaim,
    EvidenceClaimBatch,
    EvidenceFreshness,
    FactType,
    PayloadPolicy,
    ProofLevel,
    ProviderIdentity,
    SourceDescriptor,
    SourceRole,
)


def serialize_batch(batch: EvidenceClaimBatch) -> str:
    """Serializes an EvidenceClaimBatch to a JSON string."""
    return json.dumps(batch.to_public_dict(), indent=2)


def deserialize_batch(
    data_str: str,
    source_descriptors: Mapping[str, SourceDescriptor],
) -> EvidenceClaimBatch:
    """Deserializes an EvidenceClaimBatch JSON string back to objects.
    
    Requires a mapping of source_key to SourceDescriptor because descriptors are referenced.
    """
    data = json.loads(data_str)
    source_key = data["source_key"]
    descriptor = source_descriptors.get(source_key)
    if not descriptor:
        raise ValueError(f"Unknown source_key: {source_key}")

    claims = []
    for c_data in data["claims"]:
        identity = ProviderIdentity(source_key=source_key)
        freshness = EvidenceFreshness(
            observed_at=datetime.fromisoformat(data["generated_at"]),
            is_current_truth_allowed=False,
        )
        policy = PayloadPolicy()
        
        claim = EvidenceClaim(
            source=descriptor,
            proof_level=ProofLevel(c_data["proof_level"]),
            fact_type=FactType(c_data["fact_type"]),
            identity=identity,
            freshness=freshness,
            payload_policy=policy,
            claim_value=c_data["claim_value"],
            confidence=c_data["confidence"],
            warnings=tuple(c_data["warnings"]),
            errors=tuple(c_data["errors"]),
        )
        claims.append(claim)

    return EvidenceClaimBatch(
        batch_id=data["batch_id"],
        source_key=source_key,
        adapter_name=data["adapter_name"],
        adapter_version=data["adapter_version"],
        generated_at=datetime.fromisoformat(data["generated_at"]),
        claims=tuple(claims),
    )
