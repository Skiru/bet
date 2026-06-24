from datetime import UTC, datetime, timedelta

import pytest

from bet.enrichment.football_data_foundation.kernel.contracts import (
    EvidenceClaim,
    EvidenceClaimBatch,
    EvidenceFreshness,
    FactType,
    PayloadPolicy,
    PayloadPolicyViolation,
    ProofLevel,
    ProofLevelViolation,
    ProviderCapabilityError,
    ProviderIdentity,
    SourceDescriptor,
    SourceRole,
)


def descriptor(role=SourceRole.CURRENT_LIVE, source_key="test-source"):
    return SourceDescriptor(
        source_key=source_key,
        display_name="Test Source",
        role=role,
        requires_credentials=False,
        supports_live=role in {SourceRole.CURRENT_LIVE, SourceRole.CURRENT_LIVE_BENCHMARK, SourceRole.CURRENT_LIVE_OR_RECENT_DETAILED_SHADOW, SourceRole.CURRENT_REFERENCE},
        supports_historical=True,
        supports_reference=True,
        supports_replay=True,
        allowed_proof_levels=(ProofLevel.SYNTHETIC_CONTRACT_PROOF, ProofLevel.REAL_DEPENDENCY_REPLAY_PROOF, ProofLevel.DOCS_CAPABILITY_ONLY, ProofLevel.NO_PROOF),
        forbidden_fact_types=(),
    )


def claim(source=None, proof=ProofLevel.REAL_DEPENDENCY_REPLAY_PROOF, value=None, confidence=0.5):
    source = source or descriptor()
    return EvidenceClaim(
        source=source,
        proof_level=proof,
        fact_type=FactType.MATCH_STATUS,
        identity=ProviderIdentity(source.source_key),
        freshness=EvidenceFreshness(datetime.now(UTC), stale_after=datetime.now(UTC) + timedelta(minutes=1), is_current_truth_allowed=False, freshness_reason="test"),
        payload_policy=PayloadPolicy(payload_hash="a" * 64),
        claim_value=value or {"status": "ok"},
        confidence=confidence,
        errors=("no proof",) if proof is ProofLevel.NO_PROOF else (),
    )


def test_source_key_must_be_kebab_case():
    with pytest.raises(ProviderCapabilityError):
        descriptor(source_key="Bad_Source")


def test_reference_identity_must_forbid_deep_fact_types():
    with pytest.raises(ProviderCapabilityError):
        SourceDescriptor("openfootball", "OpenFootball", SourceRole.REFERENCE_IDENTITY, False, False, True, True, True, (ProofLevel.SYNTHETIC_CONTRACT_PROOF,), ())


def test_historical_deep_cannot_support_live():
    with pytest.raises(ProviderCapabilityError):
        SourceDescriptor("hist", "Hist", SourceRole.HISTORICAL_DEEP, False, True, True, True, True, (ProofLevel.SYNTHETIC_CONTRACT_PROOF,), ())


def test_synthetic_cannot_carry_value_or_confidence():
    with pytest.raises(ProofLevelViolation):
        claim(proof=ProofLevel.SYNTHETIC_CONTRACT_PROOF, value={"fake": 1}, confidence=0.1)


def test_docs_only_cannot_carry_value():
    with pytest.raises(ProofLevelViolation):
        claim(proof=ProofLevel.DOCS_CAPABILITY_ONLY, value={"doc": True}, confidence=0.0)


def test_no_proof_requires_errors():
    source = descriptor()
    with pytest.raises(ProofLevelViolation):
        EvidenceClaim(source, ProofLevel.NO_PROOF, FactType.MATCH_STATUS, ProviderIdentity(source.source_key), EvidenceFreshness(datetime.now(UTC)), PayloadPolicy(), {}, 0.0)


def test_raw_payload_keys_are_rejected_nested():
    with pytest.raises(PayloadPolicyViolation):
        claim(value={"nested": {"response_body": "nope"}})


def test_datetime_in_claim_value_rejected():
    with pytest.raises(TypeError):
        claim(value={"when": datetime.now(UTC)})


def test_batch_requires_single_source():
    a = claim(source=descriptor(source_key="source-a"))
    b = claim(source=descriptor(source_key="source-b"))
    with pytest.raises(ProviderCapabilityError):
        EvidenceClaimBatch("id", "source-a", "Adapter", "v", datetime.now(UTC), (a, b))


def test_raw_payload_git_never_allowed():
    with pytest.raises(PayloadPolicyViolation):
        PayloadPolicy(raw_payload_git_allowed=True)
