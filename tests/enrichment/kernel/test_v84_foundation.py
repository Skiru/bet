from __future__ import annotations
import pytest
from datetime import UTC, datetime, timezone
from decimal import Decimal
from enum import StrEnum
from dataclasses import dataclass
from typing import Any

from bet.enrichment.kernel.codec import (
    to_primitive,
    canonical_json_bytes,
    canonical_json_text,
    canonical_sha256,
    loads_strict,
    DuplicateKeyError,
    NonFiniteJsonNumberError,
    StrictJsonTypeError,
    CanonicalTypeError
)
from bet.enrichment.kernel.contracts import (
    RunLifecycle,
    AttemptLifecycle,
    RunReservation,
    ProjectionVersion,
    PlannedTransportCall,
    EnrichmentAdapter
)
from bet.enrichment.kernel.payload_codec import (
    PayloadCodec,
    PayloadCodecRegistry,
    DuplicateCodecRegistrationError,
    CodecRegistryFrozenError,
    UnknownPayloadCodecError,
    InvalidPayloadCodecError
)
from bet.enrichment.kernel.signed_document import (
    verify_signature,
    unsigned_object,
    compute_payload_hash,
    signature_message,
    decode_canonical_b64,
    envelope_hash,
    parse_canonical_utc,
    verify_validity_interval,
    SignedDocumentError
)
from bet.enrichment.kernel.digests import (
    runtime_code_digest,
    runtime_environment_digest,
    request_identity,
    operation_identity,
    attempt_identity
)
from bet.enrichment.kernel.errors import ErrorCode, normalize_error_code
from bet.integration.source_result import SourceResultStatus, normalize_source_result_status

# 1. codec / canonical serialization tests
class SampleEnum(StrEnum):
    VAL1 = "value1"
    VAL2 = "value2"

@dataclass(frozen=True, slots=True)
class SampleFrozenDataclass:
    id_val: int
    name: str

def test_to_primitive_success():
    assert to_primitive(None) is None
    assert to_primitive(True) is True
    assert to_primitive(False) is False
    assert to_primitive(123) == 123
    assert to_primitive("abc") == "abc"
    assert to_primitive(SampleEnum.VAL1) == "value1"

    # Decimals
    assert to_primitive(Decimal("1.2300")) == "1.23"
    assert to_primitive(Decimal("10.0")) == "10"
    assert to_primitive(Decimal("-0.0")) == "0"
    assert to_primitive(Decimal("0")) == "0"

    # aware datetime
    dt = datetime(2026, 6, 16, 12, 0, 0, 123456, tzinfo=timezone.utc)
    assert to_primitive(dt) == "2026-06-16T12:00:00.123456Z"

    # frozen dataclass
    dc = SampleFrozenDataclass(id_val=42, name="test")
    assert to_primitive(dc) == {"id_val": 42, "name": "test"}

    # mappings
    assert to_primitive({"b": 2, "a": 1}) == {"a": 1, "b": 2}

def test_to_primitive_rejections():
    # Float and subclasses
    with pytest.raises(TypeError):
        to_primitive(1.23)

    # class objects
    with pytest.raises(TypeError):
        to_primitive(SampleFrozenDataclass)

    # naive datetime
    with pytest.raises(ValueError):
        to_primitive(datetime.now())

    # bytes/bytearray
    with pytest.raises(TypeError):
        to_primitive(b"hello")

    # set/frozenset
    with pytest.raises(TypeError):
        to_primitive({1, 2})

def test_loads_strict():
    # Duplicate keys
    with pytest.raises(DuplicateKeyError):
        loads_strict('{"a": 1, "a": 2}')

    # Non-finite numbers
    with pytest.raises(NonFiniteJsonNumberError):
        loads_strict('{"val": NaN}')

    # Unpaired Unicode surrogates
    with pytest.raises(ValueError, match="Unpaired Unicode surrogate"):
        loads_strict('{"val": "\\ud800"}')

# 2. Typed API Behavior
def test_typed_contracts_dataclasses():
    # Check slots and frozen
    assert RunReservation.__slots__ is not None
    assert ProjectionVersion.__slots__ is not None
    assert PlannedTransportCall.__slots__ is not None

    reservation = RunReservation(
        semantic_base_identity="base",
        refresh_token="token",
        request_identity="req",
        sport="soccer",
        target_event_entity_id=1,
        analysis_cutoff_at=datetime.now(UTC),
        selection_epoch=0,
        plan_hash="plan",
        contract_hash="contract",
        metric_contract_hash="metric",
        policy_config_hash="policy",
        routing_revision_hash="route",
        execution_mode="mode",
        runtime_code_digest="code",
        runtime_environment_digest="env",
        owner="owner",
        lease_expires_at=datetime.now(UTC)
    )
    with pytest.raises(Exception):
        reservation.sport = "basketball"

# 3. PayloadCodecRegistry Behavior
@dataclass
class DummyDTO:
    value: str

class DummyCodec:
    capability_key = "dummy"
    schema_version = 1
    dto_type = DummyDTO
    def encode(self, value):
        return {"value": value.value}
    def decode(self, payload):
        return DummyDTO(value=payload["value"])

def test_payload_codec_registry():
    registry = PayloadCodecRegistry()
    assert not registry.frozen

    codec = DummyCodec()
    registry.register(codec)

    # ID list
    assert registry.identities() == (("dummy", 1),)

    # freeze
    registry.freeze()
    assert registry.frozen

    # duplicate check
    with pytest.raises(CodecRegistryFrozenError):
        registry.register(codec)

    # lookup
    assert registry.get("dummy", 1) is codec

    # unknown codec error
    with pytest.raises(UnknownPayloadCodecError):
        registry.get("unknown", 1)

# 4. SIGNED-DOC-1 Verification
def test_signed_document_verification():
    # Verified using project vectors
    public_key_b64 = "fWrzJpDQ1FBYYgcW0Rv17C6vFL849l/YfQhh6ZIS0dM="
    signature_b64 = "IhqYg7qh3XL+ng+ADCUqo0F6VcAGLCvGGfarGB0olmQBrgBHMVOiwrpd4mPvZlNGcxmN6oc8e3oc09ihybhKDw=="
    envelope = {
        "document_type": "governance_decision",
        "schema_version": 1,
        "profile": "BET-SIGNED-DOC-1",
        "payload": {
            "decision_id": "vector-1",
            "issued_at": "2026-01-01T00:00:00.000000Z"
        },
        "payload_hash": "eac970397194f9f048c9fe917f1289994aa1dc8bd9d0fb9f51e481c3c224f371",
        "key_id": "dummy_key",
        "signature_b64": signature_b64
    }

    # verify_signature should not raise
    verify_signature(public_key_b64, envelope, "governance_decision")

    # Tamper check
    tampered_envelope = dict(envelope)
    tampered_envelope["payload_hash"] = "eac970397194f9f048c9fe917f1289994aa1dc8bd9d0fb9f51e481c3c224f372"
    with pytest.raises(SignedDocumentError):
        verify_signature(public_key_b64, tampered_envelope, "governance_decision")

# 5. Digest Profiles
def test_digest_profiles():
    code_h1 = runtime_code_digest(version="1.0", dirty=False)
    code_h2 = runtime_code_digest(version="1.0", dirty=True)
    assert code_h1 != code_h2

    env_h1 = runtime_environment_digest({"os": "linux", "python": "3.12"})
    env_h2 = runtime_environment_digest({"os": "darwin", "python": "3.12"})
    assert env_h1 != env_h2

    req_h1 = request_identity({"sport": "soccer", "cutoff": "2026-01-01"})
    req_h2 = request_identity({"sport": "basketball", "cutoff": "2026-01-01"})
    assert req_h1 != req_h2

    attempt_h1 = attempt_identity("op1", 0)
    attempt_h2 = attempt_identity("op1", 1)
    assert attempt_h1 != attempt_h2

# 6. Error Taxonomy
def test_error_taxonomy():
    assert ErrorCode.SUCCESS == "SUCCESS"
    assert ErrorCode.INTERNAL_ERROR == "INTERNAL_ERROR"
    assert normalize_error_code("UNKNOWN_TAXONOMY") == ErrorCode.INTERNAL_ERROR
    assert normalize_error_code("TIMEOUT") == ErrorCode.TIMEOUT

def test_source_result_unsupported_normalization():
    assert normalize_source_result_status("UNSUPPORTED") == SourceResultStatus.NOT_SUPPORTED
    assert normalize_source_result_status(SourceResultStatus.UNSUPPORTED) == SourceResultStatus.NOT_SUPPORTED
