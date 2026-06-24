from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from bet.enrichment.football_data_foundation.kernel import (
    CredentialsMissingError,
    EvidenceClaim,
    EvidenceClaimBatch,
    EvidenceFreshness,
    FactType,
    PayloadPolicy,
    ProofLevel,
    ProviderCapabilityError,
    ProviderIdentity,
    sanitized_hash,
)


def now_utc() -> datetime:
    return datetime.now(UTC)


def identity(source_key: str, fixture_id: str | None = None) -> ProviderIdentity:
    return ProviderIdentity(
        source_key=source_key,
        provider_fixture_id=fixture_id,
        provider_home_team_id="home-1" if fixture_id else None,
        provider_away_team_id="away-1" if fixture_id else None,
        normalized_home_name="Home FC" if fixture_id else None,
        normalized_away_name="Away FC" if fixture_id else None,
        identity_confidence=0.9 if fixture_id else None,
    )


def synthetic_batch(adapter: Any, fact_type: FactType, note: str = "contract probe only") -> EvidenceClaimBatch:
    source = adapter.source_descriptor()
    claim = EvidenceClaim(
        source=source,
        proof_level=ProofLevel.SYNTHETIC_CONTRACT_PROOF,
        fact_type=fact_type,
        identity=ProviderIdentity(source_key=source.source_key),
        freshness=EvidenceFreshness(observed_at=now_utc(), is_current_truth_allowed=False, freshness_reason=note),
        payload_policy=PayloadPolicy(),
        claim_value={},
        confidence=0.0,
        warnings=(note,),
    )
    return EvidenceClaimBatch(
        EvidenceClaimBatch.deterministic_id(source.source_key, adapter.adapter_version(), (claim,)),
        source.source_key,
        adapter.adapter_name(),
        adapter.adapter_version(),
        now_utc(),
        (claim,),
    )


def docs_only_batch(adapter: Any, fact_type: FactType, error: str | None = None) -> EvidenceClaimBatch:
    source = adapter.source_descriptor()
    proof = ProofLevel.NO_PROOF if error else ProofLevel.DOCS_CAPABILITY_ONLY
    claim = EvidenceClaim(
        source=source,
        proof_level=proof,
        fact_type=fact_type,
        identity=ProviderIdentity(source_key=source.source_key),
        freshness=EvidenceFreshness(observed_at=now_utc(), is_current_truth_allowed=False, freshness_reason="docs/capability only"),
        payload_policy=PayloadPolicy(),
        claim_value={},
        confidence=0.0,
        warnings=("not implementation-ready",) if not error else (),
        errors=(error,) if error else (),
    )
    return EvidenceClaimBatch(
        EvidenceClaimBatch.deterministic_id(source.source_key, adapter.adapter_version(), (claim,)),
        source.source_key,
        adapter.adapter_name(),
        adapter.adapter_version(),
        now_utc(),
        (claim,),
    )


def replay_claim(
    adapter: Any,
    fact_type: FactType,
    claim_value: Mapping[str, Any],
    fixture_id: str | None = "fixture-1",
    proof_level: ProofLevel = ProofLevel.REAL_DEPENDENCY_REPLAY_PROOF,
    confidence: float = 0.65,
    freshness_reason: str = "sanitized replay only",
) -> EvidenceClaimBatch:
    source = adapter.source_descriptor()
    payload_hash = sanitized_hash(claim_value)
    claim = EvidenceClaim(
        source=source,
        proof_level=proof_level,
        fact_type=fact_type,
        identity=identity(source.source_key, fixture_id),
        freshness=EvidenceFreshness(
            observed_at=now_utc(),
            stale_after=now_utc() + timedelta(hours=1),
            is_current_truth_allowed=False,
            freshness_reason=freshness_reason,
        ),
        payload_policy=PayloadPolicy(payload_hash=payload_hash, payload_byte_count=len(json.dumps(claim_value)), payload_record_count=1),
        claim_value=dict(claim_value),
        confidence=confidence,
    )
    return EvidenceClaimBatch(
        EvidenceClaimBatch.deterministic_id(source.source_key, adapter.adapter_version(), (claim,)),
        source.source_key,
        adapter.adapter_name(),
        adapter.adapter_version(),
        now_utc(),
        (claim,),
    )


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def require_env(name: str) -> None:
    if not os.getenv(name):
        raise CredentialsMissingError(f"{name} is required for live shadow fetch")
