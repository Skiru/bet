from __future__ import annotations
import pytest
import dataclasses
from datetime import UTC, datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any
from collections.abc import Mapping
from types import MappingProxyType

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
    EnrichmentAdapter,
    OperationSubject,
    OperationRequest,
    SubjectRole,
    TerminalClass,
    PlannedOperation,
    EnrichmentPlan,
    AttemptResult,
    CapabilityResolution,
    ProviderIdentitySet
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
    attempt_identity,
    selection_epoch_identity
)
from bet.enrichment.kernel.errors import ErrorCode, normalize_error_code
from bet.integration.source_result import SourceResultStatus, normalize_source_result_status

# 1. codec / canonical serialization tests
class SampleEnum(StrEnum):
    VAL1 = "value1"
    VAL2 = "value2"

@dataclasses.dataclass(frozen=True, slots=True)
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

    # Non-frozen dataclass
    @dataclasses.dataclass
    class NonFrozenDC:
        val: int
    with pytest.raises(TypeError):
        to_primitive(NonFrozenDC(val=1))

    # Primitive subclasses
    class MyInt(int): pass
    with pytest.raises(TypeError):
        to_primitive(MyInt(5))

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

    # Invalid UTF-8 bytes
    with pytest.raises(ValueError, match="Invalid UTF-8 bytes"):
        loads_strict(b"\xff\xff")

def test_canonical_json_and_sha256_vectors():
    # Exact literal expected bytes and SHA-256 checks
    payload = {"z": "hello", "a": Decimal("10.200")}
    expected_bytes = b'{"a":"10.2","z":"hello"}'
    expected_sha = "cd4c078724cc9a3b31704ec1bfa4ebd35067d9f1ff4cb8fffca4a5ab63a6af5b"
    assert canonical_json_bytes(payload) == expected_bytes
    assert canonical_json_text(payload) == '{"a":"10.2","z":"hello"}'
    assert canonical_sha256(payload) == expected_sha

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
@dataclasses.dataclass(frozen=True, slots=True)
class DummyDTO:
    value: str

class DummyCodec:
    @property
    def capability_key(self) -> str:
        return "dummy"
    @property
    def schema_version(self) -> int:
        return 1
    @property
    def dto_type(self) -> type[DummyDTO]:
        return DummyDTO
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

    # snapshot
    snap = registry.snapshot()
    assert isinstance(snap, MappingProxyType)
    with pytest.raises(TypeError):
        snap[("dummy", 2)] = codec # type: ignore[index]

    # freeze is idempotent
    registry.freeze()
    assert registry.frozen
    registry.freeze()
    assert registry.frozen

    # register after freeze rejected
    with pytest.raises(CodecRegistryFrozenError):
        registry.register(codec)

    # lookup
    assert registry.get("dummy", 1) is codec

    # unknown codec error
    with pytest.raises(UnknownPayloadCodecError):
        registry.get("unknown", 1)

def test_payload_codec_registry_rejections():
    registry = PayloadCodecRegistry()

    # Reject mutable dataclass
    @dataclasses.dataclass
    class MutableDTO:
        value: str
    class MutableCodec:
        capability_key = "mutable"
        schema_version = 1
        dto_type = MutableDTO
    with pytest.raises(InvalidPayloadCodecError):
        registry.register(MutableCodec())

    # Reject non-dataclass without __immutable__ marker
    class OrdinaryDTO:
        def __init__(self, value: str):
            self.value = value
    class OrdinaryCodec:
        capability_key = "ordinary"
        schema_version = 1
        dto_type = OrdinaryDTO
    with pytest.raises(InvalidPayloadCodecError):
        registry.register(OrdinaryCodec())

    # Reject mutable metadata on codec
    class MutableMetadataCodec:
        def __init__(self):
            self._key = "mutmetadata"
        @property
        def capability_key(self) -> str:
            return self._key
        @capability_key.setter
        def capability_key(self, value: str) -> None:
            self._key = value
        @property
        def schema_version(self) -> int:
            return 1
        @property
        def dto_type(self) -> type[DummyDTO]:
            return DummyDTO
    with pytest.raises(InvalidPayloadCodecError):
        registry.register(MutableMetadataCodec())

# 4. SIGNED-DOC-1 Verification
def test_signed_document_verification():
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

    # Extra fields rejection
    with pytest.raises(SignedDocumentError):
        verify_signature(public_key_b64, {**envelope, "extra": 123}, "governance_decision")

    # Missing fields rejection
    envelope_missing = dict(envelope)
    del envelope_missing["signature_b64"]
    with pytest.raises(SignedDocumentError):
        verify_signature(public_key_b64, envelope_missing, "governance_decision")

    # Type schema_version rejection
    with pytest.raises(SignedDocumentError):
        verify_signature(public_key_b64, {**envelope, "schema_version": "1"}, "governance_decision")

    # Positive integer schema_version rejection
    with pytest.raises(SignedDocumentError):
        verify_signature(public_key_b64, {**envelope, "schema_version": 0}, "governance_decision")

    # Non-bool schema_version check
    with pytest.raises(SignedDocumentError):
        verify_signature(public_key_b64, {**envelope, "schema_version": True}, "governance_decision")

    # Malformed key ID
    with pytest.raises(SignedDocumentError):
        verify_signature(public_key_b64, {**envelope, "key_id": ""}, "governance_decision")

    # Uppercase payload hash
    with pytest.raises(SignedDocumentError):
        verify_signature(public_key_b64, {**envelope, "payload_hash": envelope["payload_hash"].upper()}, "governance_decision")

    # Non-canonical Base64 signature
    non_canonical_signature = signature_b64[:-4] + "A==="
    with pytest.raises(SignedDocumentError):
        verify_signature(public_key_b64, {**envelope, "signature_b64": non_canonical_signature}, "governance_decision")

    # Validity interval checks
    payload = {
        "valid_from": "2026-01-01T00:00:00.000000Z",
        "valid_to": "2026-01-02T00:00:00.000000Z"
    }
    # Inclusive lower (exact match) is valid
    now = datetime(2026, 1, 1, 0, 0, 0, 0, tzinfo=timezone.utc)
    verify_validity_interval(payload, now)

    # Exclusive upper (exact match) raises outside interval
    now_upper = datetime(2026, 1, 2, 0, 0, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(SignedDocumentError):
        verify_validity_interval(payload, now_upper)

    # Naive clock raises error
    with pytest.raises(SignedDocumentError):
        verify_validity_interval(payload, datetime(2026, 1, 1, 12, 0, 0))

# 5. Digest Profiles
def test_digest_profiles():
    # Verify exact keyword-only signatures and validations
    h_sha = "0000000000000000000000000000000000000000000000000000000000000000"
    code_hash = runtime_code_digest(
        git_commit_sha=h_sha,
        git_tree_sha=h_sha,
        dirty=False,
        wheel_sha256=h_sha,
        lock_sha256=h_sha,
        bundle_root_sha256=h_sha,
        package_version="1.0.0"
    )
    assert len(code_hash) == 64

    # dirty=True rejection
    with pytest.raises(ValueError):
        runtime_code_digest(
            git_commit_sha=h_sha,
            git_tree_sha=h_sha,
            dirty=True,
            wheel_sha256=h_sha,
            lock_sha256=h_sha,
            bundle_root_sha256=h_sha,
            package_version="1.0.0"
        )

    # Unknown keyword rejection
    with pytest.raises(TypeError):
        runtime_code_digest(
            git_commit_sha=h_sha,
            git_tree_sha=h_sha,
            dirty=False,
            wheel_sha256=h_sha,
            lock_sha256=h_sha,
            bundle_root_sha256=h_sha,
            package_version="1.0.0",
            unknown_arg="xxx" # type: ignore[call-arg]
        )

    # selection_epoch_identity testing
    epoch_hash = selection_epoch_identity(
        sport="soccer",
        capability_key="lineups",
        subject={"entity_id": 123},
        quality_profile="high",
        policy_tuple={"rule": "strict"},
        epoch=5
    )
    assert len(epoch_hash) == 64

    # epoch bool-versus-int rejection
    with pytest.raises(TypeError):
        selection_epoch_identity(
            sport="soccer",
            capability_key="lineups",
            subject={"entity_id": 123},
            quality_profile="high",
            policy_tuple={"rule": "strict"},
            epoch=True # type: ignore[arg-type]
        )

# 6. Error Taxonomy
def test_error_taxonomy():
    assert ErrorCode.SUCCESS == "SUCCESS"
    assert ErrorCode.INTERNAL_ERROR == "INTERNAL_ERROR"
    assert normalize_error_code("UNKNOWN_TAXONOMY") == ErrorCode.INTERNAL_ERROR
    assert normalize_error_code("TIMEOUT") == ErrorCode.TIMEOUT

def test_source_result_unsupported_normalization():
    assert normalize_source_result_status("UNSUPPORTED") == SourceResultStatus.NOT_SUPPORTED
    assert normalize_source_result_status(SourceResultStatus.UNSUPPORTED) == SourceResultStatus.NOT_SUPPORTED
