from __future__ import annotations

import json
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from bet.enrichment.football_data_foundation.kernel.contracts import (
    EvidenceClaim,
    SourceDescriptor,
    ProviderIdentity,
    EvidenceFreshness,
    PayloadPolicy,
    ProofLevel,
    SourceRole,
    FactType,
)

FORBIDDEN_RAW_KEYS = {"raw_payload", "response_body", "json_raw", "raw_json", "html", "raw_html"}


def _validate_no_forbidden_keys(data: Any) -> None:
    if isinstance(data, dict):
        for k, v in data.items():
            if str(k).lower() in FORBIDDEN_RAW_KEYS:
                raise ValueError(f"Forbidden raw payload key found: {k}")
            if k == "selectable_for_production" and v is True:
                raise ValueError("selectable_for_production=True is strictly forbidden")
            _validate_no_forbidden_keys(v)
    elif isinstance(data, list):
        for item in data:
            _validate_no_forbidden_keys(item)


def load_fixture_context_fixture(path: Path | str) -> tuple[EvidenceClaim, ...]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Fixture file not found: {p}")

    text = p.read_text(encoding="utf-8")
    data = json.loads(text)

    # Check forbidden keys/values
    _validate_no_forbidden_keys(data)

    claims: list[EvidenceClaim] = []
    claims_list = data.get("claims", [])
    if not isinstance(claims_list, list):
        raise ValueError("Root key 'claims' must be a list")

    for idx, cdata in enumerate(claims_list):
        # Parse SourceDescriptor
        sdata = cdata.get("source")
        if not sdata:
            raise ValueError(f"Claim at index {idx} is missing 'source'")
        
        allowed_proofs = tuple(
            [ProofLevel(p) for p in sdata.get("allowed_proof_levels", [])]
        )
        forbidden_facts = tuple(
            [FactType(f) for f in sdata.get("forbidden_fact_types", [])]
        )

        source = SourceDescriptor(
            source_key=sdata["source_key"],
            display_name=sdata["display_name"],
            role=SourceRole(sdata["role"]),
            requires_credentials=sdata.get("requires_credentials", False),
            supports_live=sdata.get("supports_live", False),
            supports_historical=sdata.get("supports_historical", False),
            supports_reference=sdata.get("supports_reference", False),
            supports_replay=sdata.get("supports_replay", False),
            allowed_proof_levels=allowed_proofs,
            forbidden_fact_types=forbidden_facts,
            notes=tuple(sdata.get("notes", [])),
        )

        # Parse ProviderIdentity
        idata = cdata.get("identity", {})
        identity = ProviderIdentity(
            source_key=idata.get("source_key", source.source_key),
            provider_fixture_id=idata.get("provider_fixture_id"),
            provider_competition_id=idata.get("provider_competition_id"),
            provider_season_id=idata.get("provider_season_id"),
            provider_home_team_id=idata.get("provider_home_team_id"),
            provider_away_team_id=idata.get("provider_away_team_id"),
            provider_player_ids=tuple(idata.get("provider_player_ids", [])),
            normalized_home_name=idata.get("normalized_home_name"),
            normalized_away_name=idata.get("normalized_away_name"),
            identity_confidence=idata.get("identity_confidence"),
            identity_warnings=tuple(idata.get("identity_warnings", [])),
        )

        # Parse EvidenceFreshness
        fdata = cdata.get("freshness", {})
        observed_at_str = fdata.get("observed_at")
        if not observed_at_str:
            raise ValueError(f"Claim at index {idx} is missing observed_at in freshness")
        
        observed_at = datetime.fromisoformat(observed_at_str.replace("Z", "+00:00"))
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=UTC)

        reported_str = fdata.get("source_reported_at")
        reported_at = (
            datetime.fromisoformat(reported_str.replace("Z", "+00:00"))
            if reported_str
            else None
        )

        valid_str = fdata.get("valid_from")
        valid_from = (
            datetime.fromisoformat(valid_str.replace("Z", "+00:00"))
            if valid_str
            else None
        )

        stale_str = fdata.get("stale_after")
        stale_after = (
            datetime.fromisoformat(stale_str.replace("Z", "+00:00"))
            if stale_str
            else None
        )

        freshness = EvidenceFreshness(
            observed_at=observed_at,
            source_reported_at=reported_at,
            valid_from=valid_from,
            stale_after=stale_after,
            is_current_truth_allowed=fdata.get("is_current_truth_allowed", False),
            freshness_reason=fdata.get("freshness_reason", ""),
        )

        # Parse PayloadPolicy
        pdata = cdata.get("payload_policy", {})
        payload_policy = PayloadPolicy(
            raw_payload_stored=pdata.get("raw_payload_stored", False),
            raw_payload_git_allowed=pdata.get("raw_payload_git_allowed", False),
            sanitized_sample_allowed=pdata.get("sanitized_sample_allowed", True),
            payload_hash=pdata.get("payload_hash"),
            payload_byte_count=pdata.get("payload_byte_count"),
            payload_record_count=pdata.get("payload_record_count"),
        )

        claim = EvidenceClaim(
            source=source,
            proof_level=ProofLevel(cdata["proof_level"]),
            fact_type=FactType(cdata["fact_type"]),
            identity=identity,
            freshness=freshness,
            payload_policy=payload_policy,
            claim_value=cdata.get("claim_value", {}),
            confidence=cdata.get("confidence", 0.0),
            warnings=tuple(cdata.get("warnings", [])),
            errors=tuple(cdata.get("errors", [])),
        )
        claims.append(claim)

    return tuple(claims)
