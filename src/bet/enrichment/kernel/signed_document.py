from __future__ import annotations
import base64
import hashlib
import secrets
from collections.abc import Mapping
from datetime import datetime, timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
from bet.enrichment.kernel.codec import canonical_json_bytes

PROFILE = "BET-SIGNED-DOC-1"
DOMAIN = b"BET-SIGNED-DOC-1\x00"
_UTC_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

class SignedDocumentError(ValueError): pass

def unsigned_object(envelope: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(envelope, Mapping):
        raise SignedDocumentError("envelope must be a Mapping")
    for f in ("document_type", "schema_version", "profile", "payload"):
        if f not in envelope:
            raise SignedDocumentError(f"Missing field {f} in envelope")
    return {
        "document_type": envelope["document_type"],
        "schema_version": envelope["schema_version"],
        "profile": envelope["profile"],
        "payload": envelope["payload"],
    }

def compute_payload_hash(envelope: Mapping[str, object]) -> str:
    try:
        unsigned = unsigned_object(envelope)
        return hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest()
    except Exception as exc:
        if isinstance(exc, SignedDocumentError):
            raise
        raise SignedDocumentError("Failed to compute payload hash") from exc

def signature_message(document_type: str, payload_hash: str) -> bytes:
    if type(document_type) is not str or not document_type or not document_type.isascii():
        raise SignedDocumentError("document_type must be a non-empty ASCII string")
    if type(payload_hash) is not str or len(payload_hash) != 64 or not all(c in "0123456789abcdef" for c in payload_hash):
        raise SignedDocumentError("payload_hash must be lowercase 64-hex SHA-256")
    try:
        digest = bytes.fromhex(payload_hash)
    except ValueError as exc:
        raise SignedDocumentError("payload_hash is not valid hex") from exc
    return DOMAIN + document_type.encode("ascii") + b"\x00" + digest

def decode_canonical_b64(value: str, expected_len: int) -> bytes:
    if type(value) is not str:
        raise SignedDocumentError("Base64 value must be a string")
    try:
        raw = base64.b64decode(value, validate=True)
    except Exception as exc:
        raise SignedDocumentError("Invalid Base64 format") from exc
    if len(raw) != expected_len or base64.b64encode(raw).decode("ascii") != value:
        raise SignedDocumentError("Non-canonical Base64 encoding or incorrect length")
    return raw

def verify_signature(public_key_b64: str, envelope: Mapping[str, object], expected_type: str) -> None:
    if not isinstance(envelope, Mapping):
        raise SignedDocumentError("envelope must be a Mapping")

    expected_fields = {"document_type", "schema_version", "profile", "payload", "payload_hash", "key_id", "signature_b64"}
    if set(envelope.keys()) != expected_fields:
        raise SignedDocumentError("envelope must contain exactly the 7 expected fields and no others")

    dt = envelope["document_type"]
    if type(dt) is not str or not dt or not dt.isascii():
        raise SignedDocumentError("document_type must be a non-empty ASCII string")
    if dt != expected_type:
        raise SignedDocumentError("document_type mismatch")

    sv = envelope["schema_version"]
    if type(sv) is not int or isinstance(sv, bool) or sv <= 0:
        raise SignedDocumentError("schema_version must be a positive integer")

    profile = envelope["profile"]
    if type(profile) is not str or profile != PROFILE:
        raise SignedDocumentError("profile must be BET-SIGNED-DOC-1")

    payload = envelope["payload"]
    if not isinstance(payload, Mapping):
        raise SignedDocumentError("payload must be a Mapping")
    for k in payload.keys():
        if type(k) is not str:
            raise SignedDocumentError("payload keys must be exact str")

    claimed_hash = envelope["payload_hash"]
    if type(claimed_hash) is not str or len(claimed_hash) != 64 or not all(c in "0123456789abcdef" for c in claimed_hash):
        raise SignedDocumentError("payload_hash must be lowercase 64-hex SHA-256")

    key_id = envelope["key_id"]
    if type(key_id) is not str or not key_id:
        raise SignedDocumentError("key_id must be a non-empty string")

    actual_hash = compute_payload_hash(envelope)
    if not secrets.compare_digest(actual_hash, claimed_hash):
        raise SignedDocumentError("payload_hash mismatch")

    public_key = decode_canonical_b64(public_key_b64, 32)
    signature = decode_canonical_b64(envelope["signature_b64"], 64)

    try:
        msg = signature_message(expected_type, actual_hash)
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, msg)
    except Exception as exc:
        raise SignedDocumentError("Signature verification failed") from exc

def envelope_hash(envelope: Mapping[str, object]) -> str:
    if not isinstance(envelope, Mapping):
        raise SignedDocumentError("envelope must be a Mapping")
    try:
        return hashlib.sha256(canonical_json_bytes(envelope)).hexdigest()
    except Exception as exc:
        raise SignedDocumentError("failed to compute envelope hash") from exc

def parse_canonical_utc(value: str) -> datetime:
    if type(value) is not str:
        raise SignedDocumentError("timestamp must be a string")
    try:
        parsed = datetime.strptime(value, _UTC_FORMAT).replace(tzinfo=timezone.utc)
    except Exception as exc:
        raise SignedDocumentError("timestamp format must be canonical UTC YYYY-MM-DDTHH:MM:SS.ffffffZ") from exc
    if parsed.strftime(_UTC_FORMAT) != value:
        raise SignedDocumentError("timestamp must be canonical UTC YYYY-MM-DDTHH:MM:SS.ffffffZ")
    return parsed

def verify_validity_interval(payload: Mapping[str, object], now: datetime) -> None:
    if not isinstance(payload, Mapping):
        raise SignedDocumentError("payload must be a Mapping")
    if "valid_from" not in payload or "valid_to" not in payload:
        raise SignedDocumentError("payload missing valid_from or valid_to")
    start = parse_canonical_utc(payload["valid_from"])
    end = parse_canonical_utc(payload["valid_to"])
    if end <= start:
        raise SignedDocumentError("invalid interval: valid_to must be > valid_from")
    if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
        raise SignedDocumentError("now must be a timezone-aware datetime")
    current = now.astimezone(timezone.utc)
    if current < start or current >= end:
        raise SignedDocumentError("current time is outside validity interval (inclusive lower, exclusive upper)")
