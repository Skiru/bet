from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
from bet.integration.telemetry_wrapper import TransportResult
from bet.resilience import atomic_write

MANIFEST_SCHEMA_VERSION = "1"
SANITIZATION_POLICY_VERSION = "espn-http-v1"

_SENSITIVE_QUERY_KEYS = {
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "cookie",
    "key",
    "password",
    "session",
    "sessionid",
    "token",
}
_SENSITIVE_JSON_KEYS = {
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "cookie",
    "password",
    "session",
    "sessionid",
    "token",
}


@dataclass(frozen=True)
class EvidenceRef:
    operation: str
    request_identity: str
    media_type: str
    byte_size: int
    object_sha256: str
    source_event_id: str | None = None
    http_status: int | None = None
    captured_at: str | None = None
    cache_hit: bool = False
    retry_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "request_identity": self.request_identity,
            "media_type": self.media_type,
            "byte_size": self.byte_size,
            "object_sha256": self.object_sha256,
            "source_event_id": self.source_event_id,
            "http_status": self.http_status,
            "captured_at": self.captured_at,
            "cache_hit": self.cache_hit,
            "retry_count": self.retry_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceRef:
        return cls(
            operation=str(data["operation"]),
            request_identity=str(data["request_identity"]),
            media_type=str(data["media_type"]),
            byte_size=int(data["byte_size"]),
            object_sha256=str(data["object_sha256"]),
            source_event_id=(str(data["source_event_id"]).strip() or None)
            if data.get("source_event_id") is not None
            else None,
            http_status=int(data["http_status"])
            if data.get("http_status") is not None
            else None,
            captured_at=str(data["captured_at"]) if data.get("captured_at") else None,
            cache_hit=bool(data.get("cache_hit", False)),
            retry_count=int(data.get("retry_count", 0)),
        )


def get_evidence_root(root: Path | str | None = None) -> Path:
    if root is not None:
        return Path(root)
    env_root = os.getenv("BET_EVIDENCE_ROOT", "").strip()
    if env_root:
        return Path(env_root)
    return PROJECT_ROOT / "betting" / "data" / "evidence"


def canonical_json_bytes(data: Any) -> bytes:
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def normalize_request_identity(
    method: str, url: str, params: dict[str, Any] | None = None
) -> str:
    parsed = urlparse(url)
    query_items = list(parse_qsl(parsed.query, keep_blank_values=True))
    if params:
        query_items.extend((str(key), str(value)) for key, value in params.items())
    filtered_items = [
        (key, value)
        for key, value in query_items
        if key.lower() not in _SENSITIVE_QUERY_KEYS
    ]
    query = urlencode(sorted(filtered_items))
    normalized_url = urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, "", query, "")
    )
    return f"{method.upper()} {normalized_url}"


def namespaced_source_refs(source_key: str, event_ids: list[str]) -> list[str]:
    refs = {
        f"{source_key}:{str(event_id).strip()}"
        for event_id in event_ids
        if str(event_id).strip()
    }
    return sorted(refs)


def persist_response_evidence(
    *,
    operation: str,
    url: str,
    params: dict[str, Any] | None,
    response: TransportResult,
    source_event_id: str | None = None,
    evidence_root: Path | str | None = None,
) -> EvidenceRef:
    root = get_evidence_root(evidence_root)
    headers = {str(k).lower(): str(v) for k, v in (response.headers or {}).items()}
    media_type = (
        headers.get("content-type", "application/octet-stream").split(";", 1)[0].strip()
        or "application/octet-stream"
    )
    body = _sanitize_response_bytes(response.body, media_type)
    digest = hashlib.sha256(body).hexdigest()
    object_path = root / "objects" / digest[:2] / digest
    if object_path.exists():
        existing = object_path.read_bytes()
        if hashlib.sha256(existing).hexdigest() != digest:
            raise ValueError(f"Evidence object hash mismatch for {digest}")
    else:
        atomic_write(object_path, body)
    return EvidenceRef(
        operation=operation,
        request_identity=normalize_request_identity("GET", url, params),
        media_type=media_type,
        byte_size=len(body),
        object_sha256=digest,
        source_event_id=(str(source_event_id).strip() or None)
        if source_event_id
        else None,
        http_status=response.status_code,
        captured_at=datetime.now(UTC).isoformat(),
        cache_hit=bool(response.cache_hit),
        retry_count=int(response.retry_count or 0),
    )


def write_bundle_manifest(
    *,
    registered_source_key: str,
    projection_name: str,
    canonical_fixture_id: int,
    parser_version: str,
    source_event_refs: list[str],
    evidence_refs: list[EvidenceRef],
    evidence_root: Path | str | None = None,
) -> tuple[str, Path]:
    root = get_evidence_root(evidence_root)
    identity_entries = []
    seen = set()
    for ref in sorted(
        evidence_refs,
        key=lambda item: (
            item.operation,
            item.request_identity,
            item.source_event_id or "",
            item.media_type,
            item.byte_size,
            item.object_sha256,
        ),
    ):
        entry = {
            "operation": ref.operation,
            "request_identity": ref.request_identity,
            "source_event_id": ref.source_event_id,
            "media_type": ref.media_type,
            "byte_size": ref.byte_size,
            "object_sha256": ref.object_sha256,
        }
        identity_key = tuple(entry.items())
        if identity_key in seen:
            continue
        seen.add(identity_key)
        identity_entries.append(entry)
    identity = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "registered_source_key": registered_source_key,
        "projection_name": projection_name,
        "canonical_fixture_id": canonical_fixture_id,
        "source_event_refs": sorted(dict.fromkeys(source_event_refs)),
        "parser_version": parser_version,
        "sanitization_policy_version": SANITIZATION_POLICY_VERSION,
        "evidence_entries": identity_entries,
    }
    bundle_id = hashlib.sha256(canonical_json_bytes(identity)).hexdigest()
    manifest = {
        "bundle_id": bundle_id,
        "identity": identity,
        "metadata": {
            "created_at": datetime.now(UTC).isoformat(),
            "entries": [ref.to_dict() for ref in evidence_refs],
        },
    }
    manifest_path = root / "bundles" / bundle_id[:2] / f"{bundle_id}.json"
    atomic_write(manifest_path, canonical_json_bytes(manifest))
    return bundle_id, manifest_path


def write_source_operation_bundle(
    *,
    registered_source_key: str,
    operation_name: str,
    request_identity: str,
    parser_version: str,
    source_event_refs: list[str],
    evidence_refs: list[EvidenceRef],
    evidence_root: Path | str | None = None,
) -> tuple[str, Path]:
    root = get_evidence_root(evidence_root)
    identity_entries = []
    seen = set()
    for ref in sorted(
        evidence_refs,
        key=lambda item: (
            item.operation,
            item.request_identity,
            item.source_event_id or "",
            item.media_type,
            item.byte_size,
            item.object_sha256,
        ),
    ):
        entry = {
            "operation": ref.operation,
            "request_identity": ref.request_identity,
            "source_event_id": ref.source_event_id,
            "media_type": ref.media_type,
            "byte_size": ref.byte_size,
            "object_sha256": ref.object_sha256,
        }
        identity_key = tuple(entry.items())
        if identity_key in seen:
            continue
        seen.add(identity_key)
        identity_entries.append(entry)

    identity = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "registered_source_key": registered_source_key,
        "operation_name": operation_name,
        "request_identity": request_identity,
        "source_event_refs": sorted(dict.fromkeys(source_event_refs)),
        "parser_version": parser_version,
        "sanitization_policy_version": SANITIZATION_POLICY_VERSION,
        "evidence_entries": identity_entries,
    }
    bundle_id = hashlib.sha256(canonical_json_bytes(identity)).hexdigest()
    manifest = {
        "bundle_id": bundle_id,
        "identity": identity,
        "metadata": {
            "created_at": datetime.now(UTC).isoformat(),
            "entries": [ref.to_dict() for ref in evidence_refs],
        },
    }
    manifest_path = root / "bundles" / bundle_id[:2] / f"{bundle_id}.json"
    atomic_write(manifest_path, canonical_json_bytes(manifest))
    return bundle_id, manifest_path


def load_bundle_manifest(
    bundle_id: str, evidence_root: Path | str | None = None
) -> dict[str, Any]:
    root = get_evidence_root(evidence_root)
    manifest_path = root / "bundles" / bundle_id[:2] / f"{bundle_id}.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    identity = manifest.get("identity") or {}
    recomputed = hashlib.sha256(canonical_json_bytes(identity)).hexdigest()
    if recomputed != bundle_id:
        raise ValueError(
            f"Evidence bundle hash mismatch: expected {bundle_id}, got {recomputed}"
        )
    entries = [
        EvidenceRef.from_dict(entry)
        for entry in manifest.get("metadata", {}).get("entries", [])
    ]
    for entry in entries:
        body = load_evidence_object_bytes(entry.object_sha256, evidence_root=root)
        if len(body) != entry.byte_size:
            raise ValueError(
                f"Evidence object byte-size mismatch for {entry.object_sha256}"
            )
    return {
        "bundle_id": bundle_id,
        "identity": identity,
        "entries": entries,
        "manifest_path": manifest_path,
    }


def load_evidence_object_bytes(
    object_sha256: str, evidence_root: Path | str | None = None
) -> bytes:
    root = get_evidence_root(evidence_root)
    object_path = root / "objects" / object_sha256[:2] / object_sha256
    body = object_path.read_bytes()
    recomputed = hashlib.sha256(body).hexdigest()
    if recomputed != object_sha256:
        raise ValueError(
            f"Evidence object hash mismatch: expected {object_sha256}, got {recomputed}"
        )
    return body


def build_replay_transport(bundle_id: str, evidence_root: Path | str | None = None):
    manifest = load_bundle_manifest(bundle_id, evidence_root=evidence_root)
    entries = {entry.request_identity: entry for entry in manifest["entries"]}
    root = get_evidence_root(evidence_root)

    def replay_wrap_request(
        provider: str,
        request_fn,
        url: str,
        method: str = "GET",
        scope_id: str = "",
        idempotency_key: str = "",
        **kwargs,
    ):
        request_identity = normalize_request_identity(method, url, kwargs.get("params"))
        entry = entries.get(request_identity)
        if entry is None:
            raise AssertionError(f"Unexpected replay request: {request_identity}")
        body = load_evidence_object_bytes(entry.object_sha256, evidence_root=root)
        return TransportResult(
            success=entry.http_status is not None and 200 <= entry.http_status < 300,
            status_code=entry.http_status,
            headers={"Content-Type": entry.media_type},
            body=body,
            cache_hit=True,
            telemetry={
                "replay": True,
                "request_identity": request_identity,
                "provider": provider,
                "scope_id": scope_id,
            },
        )

    return replay_wrap_request


def _sanitize_response_bytes(body: bytes, media_type: str) -> bytes:
    if not body:
        return b""
    if media_type.endswith("json") or media_type == "application/json":
        try:
            payload = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return body
        return canonical_json_bytes(_sanitize_json_payload(payload))
    return body


def _sanitize_json_payload(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if str(key).lower() in _SENSITIVE_JSON_KEYS:
                cleaned[key] = "REDACTED"
            else:
                cleaned[key] = _sanitize_json_payload(item)
        return cleaned
    if isinstance(value, list):
        return [_sanitize_json_payload(item) for item in value]
    return value
