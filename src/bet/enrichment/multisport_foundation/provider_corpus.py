from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

SECRET_KEY_RE = re.compile(r"(authorization|cookie|token|api[_-]?key|x-api|x-rapidapi|secret)", re.IGNORECASE)
SECRET_VALUE_RE = re.compile(r"(bearer\s+[A-Za-z0-9._-]+|sk-[A-Za-z0-9._-]+|[A-Za-z0-9_=-]{32,})", re.IGNORECASE)

@dataclass(frozen=True)
class ProviderCorpusRecord:
    corpus_id: str
    source_key: str
    sport: str
    proof_level: str
    status: str
    endpoint_family: str
    captured_at_utc: str
    sanitized_request: dict[str, Any]
    sanitized_response_envelope: dict[str, Any]
    participant_evidence: tuple[str, ...]
    mapping_notes: str

    def to_json(self) -> dict[str, Any]:
        return {
            "corpus_id": self.corpus_id,
            "source_key": self.source_key,
            "sport": self.sport,
            "proof_level": self.proof_level,
            "status": self.status,
            "endpoint_family": self.endpoint_family,
            "captured_at_utc": self.captured_at_utc,
            "sanitized_request": self.sanitized_request,
            "sanitized_response_envelope": self.sanitized_response_envelope,
            "participant_evidence": list(self.participant_evidence),
            "mapping_notes": self.mapping_notes,
        }


def sanitize_headers(headers: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in headers.items():
        if SECRET_KEY_RE.search(key):
            sanitized[key] = "<redacted>"
        else:
            text = str(value)
            sanitized[key] = SECRET_VALUE_RE.sub("<redacted>", text)
    return sanitized


def stable_corpus_id(source_key: str, sport: str, endpoint_family: str, envelope: dict[str, Any]) -> str:
    seed = json.dumps({"source_key": source_key, "sport": sport, "endpoint_family": endpoint_family, "envelope": envelope}, sort_keys=True)
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def build_blocked_corpus_record(source_key: str, sport: str, status: str, endpoint_family: str, reason: str, proof_level: str = "blocked_access_proof") -> ProviderCorpusRecord:
    envelope = {"blocked_reason": reason, "real_provider_data": False}
    return ProviderCorpusRecord(
        corpus_id=stable_corpus_id(source_key, sport, endpoint_family, envelope),
        source_key=source_key,
        sport=sport,
        proof_level=proof_level,
        status=status,
        endpoint_family=endpoint_family,
        captured_at_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        sanitized_request={"headers": {}, "params": {}},
        sanitized_response_envelope=envelope,
        participant_evidence=(),
        mapping_notes=reason,
    )


def contains_raw_secret(payload: object) -> bool:
    blob = json.dumps(payload, sort_keys=True, default=str)
    if SECRET_VALUE_RE.search(blob):
        return True
    lowered = blob.lower()
    return any(term in lowered and "<redacted>" not in lowered for term in ("authorization", "cookie", "x-api", "x-rapidapi", "bearer "))
