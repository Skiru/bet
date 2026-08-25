"""Service for provider observation evidence envelopes, atomic file I/O, and verification (C3)."""

from __future__ import annotations

import json
import hashlib
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from bet.pipeline.event_runtime_contract import (
    ProviderRequestStatus,
    CanonicalEventStatus,
    sha256_file,
    verify_evidence_file,
)


def write_observation_evidence_envelope(
    payload: dict[str, Any],
    target_dir: Path | str,
) -> tuple[str, str]:
    """Write observation envelope atomically to disk and calculate SHA256 of final bytes.
    
    Returns (final_file_path_str, sha256_hex).
    """
    target_p = Path(target_dir).resolve()
    target_p.mkdir(parents=True, exist_ok=True)

    run_id = str(payload.get("run_id") or "run_unknown")
    phase = str(payload.get("phase") or "PLAN")
    event_id = str(payload.get("canonical_event_id") or "evt_unknown")
    provider = str(payload.get("provider") or "provider_unknown")
    attempt = int(payload.get("attempt_number") or 1)

    filename = f"obs_{run_id}_{phase}_{event_id}_{provider}_att{attempt}.json"
    final_path = target_p / filename

    # Sanitize payload for envelope JSON serialization
    sanitized_payload = {
        "schema_version": payload.get("schema_version", "v1"),
        "run_id": run_id,
        "phase": phase,
        "attempt_number": attempt,
        "canonical_event_id": event_id,
        "fixture_id": payload.get("fixture_id"),
        "provider": provider,
        "provider_event_id": payload.get("provider_event_id"),
        "attempted_at_utc": payload.get("attempted_at_utc"),
        "request_status": str(payload.get("request_status")),
        "raw_provider_status": payload.get("raw_provider_status"),
        "canonical_event_status": str(payload.get("canonical_event_status")),
        "raw_observed_kickoff": payload.get("raw_observed_kickoff"),
        "observed_kickoff_utc": payload.get("observed_kickoff_utc"),
        "observed_home_name": payload.get("observed_home_name"),
        "observed_away_name": payload.get("observed_away_name"),
        "participant_identity_sha256": payload.get("participant_identity_sha256"),
        "competition_identity_sha256": payload.get("competition_identity_sha256"),
        "upstream_evidence_bundle_id": payload.get("upstream_evidence_bundle_id"),
        "upstream_evidence_refs": payload.get("upstream_evidence_refs"),
        "error_code": payload.get("error_code"),
        "error_detail": payload.get("error_detail"),
    }

    json_bytes = json.dumps(sanitized_payload, sort_keys=True, ensure_ascii=False, indent=2).encode("utf-8")

    # Atomic write via temporary file
    temp_fd, temp_path_str = tempfile.mkstemp(dir=target_p, prefix="tmp_obs_")
    try:
        with os.fdopen(temp_fd, "wb") as f:
            f.write(json_bytes)
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_path_str, final_path)
    except Exception as exc:
        if os.path.exists(temp_path_str):
            try:
                os.remove(temp_path_str)
            except OSError:
                pass
        raise exc

    # Calculate SHA256 from final written bytes
    final_sha256 = sha256_file(final_path)
    return str(final_path), final_sha256


def validate_persisted_provider_observation(
    db_record: dict[str, Any],
    evidence_path: Path | str | None = None,
    expected_sha256: str | None = None,
    allowed_root: Path | str | None = None,
) -> tuple[bool, str]:
    """Validate persisted observation record against disk evidence envelope."""
    ev_path = evidence_path or db_record.get("evidence_path")
    exp_sha = expected_sha256 or db_record.get("observation_envelope_sha256") or db_record.get("raw_evidence_sha256")

    if not ev_path:
        return False, "MISSING_EVIDENCE: Evidence path is missing or null"

    p = Path(ev_path).resolve()
    if not p.exists() or not p.is_file():
        return False, f"MISSING_EVIDENCE: Evidence file does not exist: {p}"

    # Path traversal check if allowed_root supplied
    if allowed_root:
        root_p = Path(allowed_root).resolve()
        try:
            p.relative_to(root_p)
        except ValueError:
            return False, f"PATH_TRAVERSAL_BLOCKED: Path {p} escapes allowed root {root_p}"

    if not exp_sha:
        return False, "MISSING_EVIDENCE_HASH: Expected SHA256 is null or empty"

    # Verify SHA256 match
    is_valid_hash, hash_msg = verify_evidence_file(p, exp_sha)
    if not is_valid_hash:
        return False, hash_msg

    # Read and parse envelope JSON
    try:
        envelope_data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"INVALID_ENVELOPE_JSON: Could not parse JSON envelope: {exc}"

    # Verify key fields match DB record
    for field in ("run_id", "phase", "canonical_event_id", "provider", "request_status"):
        if field in db_record and field in envelope_data:
            db_val = str(db_record[field])
            env_val = str(envelope_data[field])
            if db_val != env_val:
                return False, f"ENVELOPE_MISMATCH: Field {field} mismatch (db='{db_val}', envelope='{env_val}')"

    return True, "OBSERVATION_VERIFIED"


def persist_provider_observation_with_evidence(
    conn: sqlite3.Connection,
    payload: dict[str, Any],
    target_dir: Path | str,
) -> int:
    """Write evidence file atomically and insert observation record into DB with compensating cleanup on failure."""
    from bet.db.repositories import ProviderObservationAttemptRepository

    repo = ProviderObservationAttemptRepository(conn)
    evidence_path_str, final_sha256 = write_observation_evidence_envelope(payload, target_dir)

    payload_copy = dict(payload)
    payload_copy["evidence_path"] = evidence_path_str
    payload_copy["observation_envelope_sha256"] = final_sha256

    try:
        attempt_id = repo.insert_attempt(
            run_id=payload_copy["run_id"],
            phase=payload_copy["phase"],
            attempt_number=payload_copy.get("attempt_number", 1),
            canonical_event_id=payload_copy["canonical_event_id"],
            fixture_id=payload_copy.get("fixture_id"),
            provider=payload_copy["provider"],
            provider_event_id=payload_copy.get("provider_event_id"),
            attempted_at_utc=payload_copy["attempted_at_utc"],
            request_status=payload_copy["request_status"],
            raw_provider_status=payload_copy.get("raw_provider_status"),
            canonical_event_status=payload_copy["canonical_event_status"],
            raw_observed_kickoff=payload_copy.get("raw_observed_kickoff"),
            observed_kickoff_utc=payload_copy.get("observed_kickoff_utc"),
            observed_home_name=payload_copy.get("observed_home_name"),
            observed_away_name=payload_copy.get("observed_away_name"),
            participant_identity_sha256=payload_copy.get("participant_identity_sha256"),
            competition_identity_sha256=payload_copy.get("competition_identity_sha256"),
            upstream_evidence_bundle_id=payload_copy.get("upstream_evidence_bundle_id"),
            upstream_evidence_refs_json=json.dumps(payload_copy.get("upstream_evidence_refs")) if payload_copy.get("upstream_evidence_refs") else None,
            observation_envelope_sha256=final_sha256,
            evidence_path=evidence_path_str,
            error_code=payload_copy.get("error_code"),
            error_detail=payload_copy.get("error_detail"),
        )
        return attempt_id
    except Exception as exc:
        # Compensating cleanup: remove created evidence file if DB insert fails
        if os.path.exists(evidence_path_str):
            try:
                os.remove(evidence_path_str)
            except OSError:
                pass
        raise exc
