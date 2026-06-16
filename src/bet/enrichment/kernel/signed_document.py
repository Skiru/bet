from __future__ import annotations
import base64, hashlib, secrets
from collections.abc import Mapping
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from bet.enrichment.kernel.codec import canonical_json_bytes

PROFILE = "BET-SIGNED-DOC-1"
DOMAIN = b"BET-SIGNED-DOC-1\x00"

class SignedDocumentError(ValueError): pass

def unsigned_object(envelope: Mapping[str, object]) -> dict[str, object]:
    return {
        "document_type": envelope["document_type"],
        "schema_version": envelope["schema_version"],
        "profile": envelope["profile"],
        "payload": envelope["payload"],
    }

def compute_payload_hash(envelope: Mapping[str, object]) -> str:
    return hashlib.sha256(canonical_json_bytes(unsigned_object(envelope))).hexdigest()

def signature_message(document_type: str, payload_hash: str) -> bytes:
    if type(document_type) is not str or not document_type.isascii() or not document_type:
        raise SignedDocumentError("document_type")
    if type(payload_hash) is not str or len(payload_hash) != 64:
        raise SignedDocumentError("payload_hash")
    try: digest = bytes.fromhex(payload_hash)
    except ValueError as exc: raise SignedDocumentError("payload_hash") from exc
    return DOMAIN + document_type.encode("ascii") + b"\x00" + digest

def decode_canonical_b64(value: str, expected_len: int) -> bytes:
    if type(value) is not str: raise SignedDocumentError("base64 type")
    try: raw = base64.b64decode(value, validate=True)
    except Exception as exc: raise SignedDocumentError("base64") from exc
    if len(raw) != expected_len or base64.b64encode(raw).decode("ascii") != value:
        raise SignedDocumentError("base64 canonical/length")
    return raw

def verify_signature(public_key_b64: str, envelope: Mapping[str, object], expected_type: str) -> None:
    if envelope.get("profile") != PROFILE or envelope.get("document_type") != expected_type:
        raise SignedDocumentError("profile/type")
    actual = compute_payload_hash(envelope)
    claimed = envelope.get("payload_hash")
    if type(claimed) is not str or not secrets.compare_digest(actual, claimed):
        raise SignedDocumentError("hash")
    public_key = decode_canonical_b64(public_key_b64, 32)
    signature = decode_canonical_b64(str(envelope.get("signature_b64")), 64)
    Ed25519PublicKey.from_public_bytes(public_key).verify(signature, signature_message(expected_type, actual))

def envelope_hash(envelope: Mapping[str, object]) -> str:
    return hashlib.sha256(canonical_json_bytes(envelope)).hexdigest()

from datetime import datetime, timezone
_UTC_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
def parse_canonical_utc(value: str) -> datetime:
    if type(value) is not str: raise SignedDocumentError("timestamp type")
    try: parsed=datetime.strptime(value,_UTC_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError as exc: raise SignedDocumentError("timestamp") from exc
    if parsed.strftime(_UTC_FORMAT)!=value: raise SignedDocumentError("timestamp canonical")
    return parsed
def verify_validity_interval(payload: Mapping[str, object], now: datetime) -> None:
    start=parse_canonical_utc(str(payload["valid_from"])); end=parse_canonical_utc(str(payload["valid_to"]))
    if end<=start: raise SignedDocumentError("invalid interval")
    if now.tzinfo is None or now.utcoffset() is None: raise SignedDocumentError("naive clock")
    current=now.astimezone(timezone.utc)
    if current<start or current>=end: raise SignedDocumentError("outside interval")
