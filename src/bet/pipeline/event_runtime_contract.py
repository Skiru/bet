"""Single Runtime Event Contract for BET V5/V8.

Nondeterministic side-effects (clock, HTTP, DB connection, subprocess) are isolated outside this module.
All time inputs must be explicit.
"""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, UTC
from enum import Enum, StrEnum
from pathlib import Path
from zoneinfo import ZoneInfo

from bet.utils.common import normalize_for_matching


# Exceptions
class NaiveDatetimeError(ValueError):
    """Raised when a naive datetime (lacking tzinfo) is passed."""


class InvalidEvidenceError(ValueError):
    """Raised when evidence file or hash is invalid."""


class IncompleteObservationError(ValueError):
    """Raised when a SUCCESS observation lacks mandatory fields."""


# Enums
class CanonicalEventStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    LIVE = "LIVE"
    FINISHED = "FINISHED"
    POSTPONED = "POSTPONED"
    CANCELLED = "CANCELLED"
    ABANDONED = "ABANDONED"
    SUSPENDED = "SUSPENDED"
    WALKOVER = "WALKOVER"
    AWARDED_TERMINAL = "AWARDED_TERMINAL"
    UNKNOWN = "UNKNOWN"


class ProviderRequestStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    UNSUPPORTED = "UNSUPPORTED"
    IDENTITY_MISSING = "IDENTITY_MISSING"
    IDENTITY_CONFLICT = "IDENTITY_CONFLICT"


# Time Utilities
def parse_utc_timestamp(val: datetime | str) -> datetime:
    """Parse a datetime or ISO string as an explicit UTC datetime.
    
    Raises NaiveDatetimeError if naive.
    """
    if isinstance(val, str):
        # Support trailing Z or ISO offset
        s = val.strip()
        if s.endswith("Z") or s.endswith("z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
    elif isinstance(val, datetime):
        dt = val
    else:
        raise TypeError(f"Expected datetime or str, got {type(val)}")

    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise NaiveDatetimeError("NAIVE_DATETIME_REJECTED: Naive datetime without timezone information is prohibited")

    return dt.astimezone(UTC)


def betting_day_utc_bounds(
    betting_date: date,
    timezone_name: str = "Europe/Warsaw",
) -> tuple[datetime, datetime]:
    """Calculate [start_utc, end_utc) bounds for a calendar betting day in local timezone."""
    tz = ZoneInfo(timezone_name)
    local_start = datetime.combine(betting_date, time.min, tzinfo=tz)
    local_end = datetime.combine(betting_date + timedelta(days=1), time.min, tzinfo=tz)

    start_utc = local_start.astimezone(UTC)
    end_utc = local_end.astimezone(UTC)

    return start_utc, end_utc


# Status Normalization
_SCHEDULED_RAW = {
    "pending", "ns", "sched", "scheduled", "confirmed",
    "status_scheduled", "status_not_started", "timed",
}

_LIVE_RAW = {
    "live", "in_play", "in_progress", "status_in_progress",
    "1h", "ht", "2h", "et", "bt", "p", "q1", "q2", "q3", "q4", "ot",
}

_FINISHED_RAW = {
    "finished", "final", "status_final", "ft", "aet", "pen", "aot", "ended", "ap", "awt",
}

_POSTPONED_RAW = {
    "post", "pst", "postp", "postponed", "status_postponed",
}

_CANCELLED_RAW = {
    "canc", "cancelled", "canceled", "status_canceled", "abd",
}

_ABANDONED_RAW = {
    "abandoned", "int", "interrupted",
}

_SUSPENDED_RAW = {
    "susp", "suspended",
}

_AWARDED_RAW = {
    "awd", "awarded", "awarded_terminal",
}

_WALKOVER_RAW = {
    "wo", "walkover", "retired", "status_retired",
}


def normalize_provider_status(
    raw_status: str | None,
    *,
    provider: str = "",
    observed_kickoff_utc: datetime | str | None = None,
    observed_at_utc: datetime | str | None = None,
    minimum_lead: timedelta = timedelta(minutes=0),
) -> CanonicalEventStatus:
    """Normalize raw provider status to CanonicalEventStatus."""
    if not raw_status:
        return CanonicalEventStatus.UNKNOWN

    norm = raw_status.strip().lower()

    if norm in _SCHEDULED_RAW:
        if observed_kickoff_utc is not None and observed_at_utc is not None:
            kickoff_dt = parse_utc_timestamp(observed_kickoff_utc)
            observed_dt = parse_utc_timestamp(observed_at_utc)
            if kickoff_dt > (observed_dt + minimum_lead):
                return CanonicalEventStatus.SCHEDULED
            else:
                return CanonicalEventStatus.UNKNOWN
        elif observed_kickoff_utc is not None and observed_at_utc is None:
            # If observed_at_utc is omitted, we require kickoff to be provided
            return CanonicalEventStatus.SCHEDULED
        return CanonicalEventStatus.SCHEDULED

    if norm in _LIVE_RAW:
        return CanonicalEventStatus.LIVE

    if norm in _FINISHED_RAW:
        return CanonicalEventStatus.FINISHED

    if norm in _POSTPONED_RAW:
        return CanonicalEventStatus.POSTPONED

    if norm in _CANCELLED_RAW:
        return CanonicalEventStatus.CANCELLED

    if norm in _ABANDONED_RAW:
        return CanonicalEventStatus.ABANDONED

    if norm in _SUSPENDED_RAW:
        return CanonicalEventStatus.SUSPENDED

    if norm in _AWARDED_RAW:
        return CanonicalEventStatus.AWARDED_TERMINAL

    if norm in _WALKOVER_RAW:
        return CanonicalEventStatus.WALKOVER

    return CanonicalEventStatus.UNKNOWN


def is_status_allowed_for_plan(status: CanonicalEventStatus) -> bool:
    """Check if canonical status is eligible for initial plan selection."""
    return status == CanonicalEventStatus.SCHEDULED


def is_status_allowed_for_continuation(status: CanonicalEventStatus) -> bool:
    """Check if canonical status is eligible for continuation selection."""
    return status == CanonicalEventStatus.SCHEDULED


# Participant Identity
@dataclass(frozen=True)
class ParticipantIdentity:
    home_raw: str
    away_raw: str
    home_normalized: str
    away_normalized: str
    identity_sha256: str


def build_participant_identity(home_raw: str, away_raw: str) -> ParticipantIdentity:
    """Build normalized participant identity preserving home/away order."""
    home_norm = normalize_for_matching(home_raw)
    away_norm = normalize_for_matching(away_raw)

    canonical_data = [home_norm, away_norm]
    sha = hashlib.sha256(json.dumps(canonical_data, ensure_ascii=False).encode("utf-8")).hexdigest()

    return ParticipantIdentity(
        home_raw=home_raw,
        away_raw=away_raw,
        home_normalized=home_norm,
        away_normalized=away_norm,
        identity_sha256=sha,
    )


# Evidence Validation
def sha256_file(path: Path | str) -> str:
    """Calculate SHA256 hex digest of file bytes."""
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise InvalidEvidenceError(f"Evidence file missing or not a file: {p}")

    hasher = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_evidence_file(path: Path | str, expected_sha256: str) -> tuple[bool, str]:
    """Verify that file exists and matches expected SHA256."""
    try:
        actual_hash = sha256_file(path)
        if actual_hash.lower() == expected_sha256.lower():
            return True, "EVIDENCE_VERIFIED"
        return False, f"SHA256_MISMATCH: expected {expected_sha256}, got {actual_hash}"
    except Exception as exc:
        return False, f"EVIDENCE_ERROR: {exc}"


def verify_evidence_envelope(record: dict) -> tuple[bool, str]:
    """Verify evidence envelope dict containing evidence_path and raw_evidence_sha256."""
    ev_path = record.get("evidence_path")
    expected_sha = record.get("raw_evidence_sha256") or record.get("expected_artifact_sha256")
    if not ev_path or not expected_sha:
        return False, "MISSING_EVIDENCE_PATH_OR_HASH"

    return verify_evidence_file(ev_path, expected_sha)


# Observation Model & Record Builder
@dataclass
class ProviderObservationRecord:
    canonical_event_id: str
    fixture_id: int | None
    provider: str
    provider_event_id: str | None
    attempted_at_utc: str
    request_status: ProviderRequestStatus
    raw_provider_status: str | None
    canonical_event_status: CanonicalEventStatus
    raw_observed_kickoff: str | None
    observed_kickoff_utc: str | None
    observed_home_name: str | None
    observed_away_name: str | None
    participant_identity_sha256: str | None
    competition_identity_sha256: str | None
    upstream_evidence_bundle_id: str | None = None
    upstream_evidence_refs_json: str | None = None
    observation_envelope_sha256: str | None = None
    evidence_path: str | None = None
    error_code: str | None = None
    error_detail: str | None = None


def build_provider_observation_record(
    db_row: dict,
    provider_response: dict,
    attempted_at_utc: datetime | None = None,
    provider_name: str = "api_football",
) -> ProviderObservationRecord:
    """Build ProviderObservationRecord using provider-observed fields rather than DB fields."""
    if attempted_at_utc is None:
        attempted_at_dt = datetime.now(UTC)
    else:
        attempted_at_dt = parse_utc_timestamp(attempted_at_utc)

    raw_status = provider_response.get("status") or provider_response.get("raw_status")
    raw_kickoff = provider_response.get("kickoff") or provider_response.get("raw_kickoff")
    
    observed_kickoff_dt = None
    if raw_kickoff:
        try:
            observed_kickoff_dt = parse_utc_timestamp(raw_kickoff)
        except Exception:
            observed_kickoff_dt = None

    canonical_status = normalize_provider_status(
        raw_status,
        provider=provider_name,
        observed_kickoff_utc=observed_kickoff_dt,
        observed_at_utc=attempted_at_dt,
    )

    home_name = provider_response.get("home") or provider_response.get("home_team")
    away_name = provider_response.get("away") or provider_response.get("away_team")

    part_sha = None
    if home_name and away_name:
        part_id = build_participant_identity(home_name, away_name)
        part_sha = part_id.identity_sha256

    provider_evt_id = provider_response.get("provider_event_id") or provider_response.get("external_id")

    return ProviderObservationRecord(
        canonical_event_id=str(db_row.get("canonical_event_id") or db_row.get("fixture_id") or ""),
        fixture_id=db_row.get("fixture_id"),
        provider=provider_name,
        provider_event_id=provider_evt_id,
        attempted_at_utc=attempted_at_dt.isoformat(),
        request_status=ProviderRequestStatus.SUCCESS,
        raw_provider_status=raw_status,
        canonical_event_status=canonical_status,
        raw_observed_kickoff=raw_kickoff,
        observed_kickoff_utc=observed_kickoff_dt.isoformat() if observed_kickoff_dt else None,
        observed_home_name=home_name,
        observed_away_name=away_name,
        participant_identity_sha256=part_sha,
        competition_identity_sha256=provider_response.get("competition_identity_sha256"),
        upstream_evidence_bundle_id=provider_response.get("upstream_evidence_bundle_id"),
        upstream_evidence_refs_json=json.dumps(provider_response.get("upstream_refs")) if provider_response.get("upstream_refs") else None,
        observation_envelope_sha256=provider_response.get("observation_envelope_sha256"),
        evidence_path=provider_response.get("evidence_path"),
    )


def validate_provider_observation(obs: ProviderObservationRecord | dict) -> tuple[bool, str]:
    """Validate completeness and correctness of a provider observation record."""
    if isinstance(obs, ProviderObservationRecord):
        req_status = obs.request_status
        p_event_id = obs.provider_event_id
        c_status = obs.canonical_event_status
        obs_at = obs.attempted_at_utc
        part_sha = obs.participant_identity_sha256
        ev_sha = obs.observation_envelope_sha256
    else:
        req_status = obs.get("request_status")
        p_event_id = obs.get("provider_event_id")
        c_status = obs.get("canonical_event_status")
        obs_at = obs.get("attempted_at_utc")
        part_sha = obs.get("participant_identity_sha256")
        ev_sha = obs.get("observation_envelope_sha256")

    if req_status == ProviderRequestStatus.SUCCESS:
        if not p_event_id:
            return False, "INCOMPLETE_OBSERVATION: Missing provider_event_id"
        if not c_status:
            return False, "INCOMPLETE_OBSERVATION: Missing canonical_event_status"
        if not obs_at:
            return False, "INCOMPLETE_OBSERVATION: Missing attempted_at_utc"
        if not part_sha:
            return False, "INCOMPLETE_OBSERVATION: Missing participant_identity_sha256"

    return True, "OBSERVATION_VALID"


# Event Classification
@dataclass(frozen=True)
class EventEligibilityResult:
    is_eligible: bool
    routing_status: str
    reason: str


def classify_event_eligibility(
    raw_provider_status: str | None = None,
    canonical_status: CanonicalEventStatus | str = CanonicalEventStatus.UNKNOWN,
    observed_kickoff: datetime | str | None = None,
    observed_at: datetime | str | None = None,
    provider_request_status: ProviderRequestStatus | str = ProviderRequestStatus.SUCCESS,
    minimum_lead: timedelta = timedelta(minutes=0),
) -> EventEligibilityResult:
    """Classify event eligibility for ANALYZE_FROM_S2."""
    if isinstance(provider_request_status, str):
        try:
            req_status = ProviderRequestStatus(provider_request_status)
        except ValueError:
            req_status = ProviderRequestStatus.FAILED
    else:
        req_status = provider_request_status

    if req_status == ProviderRequestStatus.FAILED:
        return EventEligibilityResult(
            is_eligible=False,
            routing_status="PROVIDER_RECHECK_REQUIRED",
            reason="Provider request failed",
        )

    if req_status == ProviderRequestStatus.UNSUPPORTED:
        return EventEligibilityResult(
            is_eligible=False,
            routing_status="PROVIDER_UNSUPPORTED",
            reason="Provider unsupported for event lookup",
        )

    if req_status in (ProviderRequestStatus.IDENTITY_MISSING, ProviderRequestStatus.IDENTITY_CONFLICT):
        return EventEligibilityResult(
            is_eligible=False,
            routing_status="IDENTITY_CONFLICT",
            reason=f"Provider identity status: {req_status}",
        )

    if isinstance(canonical_status, str):
        if raw_provider_status and canonical_status in (CanonicalEventStatus.UNKNOWN, "UNKNOWN"):
            c_status = normalize_provider_status(raw_provider_status)
        else:
            try:
                c_status = CanonicalEventStatus(canonical_status)
            except ValueError:
                c_status = CanonicalEventStatus.UNKNOWN
    else:
        c_status = canonical_status

    if raw_provider_status:
        norm_raw = normalize_provider_status(
            raw_provider_status,
            observed_kickoff_utc=observed_kickoff,
            observed_at_utc=observed_at,
            minimum_lead=minimum_lead,
        )
        if norm_raw != CanonicalEventStatus.SCHEDULED:
            c_status = norm_raw

    if c_status != CanonicalEventStatus.SCHEDULED:
        return EventEligibilityResult(
            is_eligible=False,
            routing_status="EXCLUDED_TERMINAL_OR_NON_SCHEDULED",
            reason=f"Status {c_status} is not SCHEDULED",
        )

    if observed_kickoff is not None:
        try:
            kickoff_dt = parse_utc_timestamp(observed_kickoff)
            ref_dt = parse_utc_timestamp(observed_at) if observed_at is not None else datetime.now(UTC)
            if kickoff_dt <= (ref_dt + minimum_lead):
                return EventEligibilityResult(
                    is_eligible=False,
                    routing_status="TIME_EXPIRED_UNCONFIRMED",
                    reason="Kickoff time has passed or lead time is insufficient",
                )
        except Exception:
            pass

    return EventEligibilityResult(
        is_eligible=True,
        routing_status="ANALYZE_FROM_S2",
        reason="Current confirmed pre-match event eligible for analysis",
    )


# Provider Revalidation Registry
class ProviderEventRevalidationRegistry:
    """Registry for exact provider event revalidation."""

    @staticmethod
    def timestamps_equal(ts1: str | datetime, ts2: str | datetime) -> bool:
        """Check if two ISO timestamps represent the exact same instant."""
        try:
            dt1 = parse_utc_timestamp(ts1)
            dt2 = parse_utc_timestamp(ts2)
            return dt1 == dt2
        except Exception:
            return False

    def revalidate_exact(
        self,
        target_provider: str,
        target_event_id: str,
        available_events: list[dict],
    ) -> dict | None:
        """Exact lookup by provider and provider event ID."""
        for evt in available_events:
            p = evt.get("provider") or evt.get("source")
            pid = evt.get("provider_event_id") or evt.get("external_id")
            if p == target_provider and pid == target_event_id:
                return evt
        return None


# Input Fingerprint
def compute_runtime_input_fingerprint(payload: dict) -> str:
    """Compute deterministic SHA256 fingerprint of input dictionary."""
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# Work Reuse
def is_stage_work_reusable(
    *,
    db_record: dict | None,
    expected_input_fingerprint: str,
    artifact_path: Path | str | None,
    receipt_path: Path | str | None,
) -> tuple[bool, str]:
    """Check if existing stage work can be safely reused."""
    if not db_record:
        return False, "NO_DB_RECORD"

    status = db_record.get("status")
    if status not in ("PASS", "COMPLETED"):
        return False, f"STATUS_NOT_PASS: {status}"

    actual_fp = db_record.get("input_fingerprint")
    if actual_fp != expected_input_fingerprint:
        return False, f"FINGERPRINT_MISMATCH: expected {expected_input_fingerprint}, got {actual_fp}"

    if artifact_path is None:
        return False, "MISSING_OUTPUT_ARTIFACT"

    art_p = Path(artifact_path)
    if not art_p.exists() or not art_p.is_file():
        return False, "ARTIFACT_NOT_FOUND"

    if receipt_path is None:
        return False, "MISSING_RECEIPT"

    rec_p = Path(receipt_path)
    if not rec_p.exists() or not rec_p.is_file():
        return False, "RECEIPT_NOT_FOUND"

    expected_art_hash = db_record.get("expected_artifact_sha256")
    if expected_art_hash:
        actual_art_hash = sha256_file(art_p)
        if actual_art_hash.lower() != expected_art_hash.lower():
            return False, f"ARTIFACT_SHA256_MISMATCH: expected {expected_art_hash}, got {actual_art_hash}"

    return True, "REUSE_VALID"


# Selection Scope
@dataclass
class RuntimeSelectionScope:
    selection_run_id: str
    allowed_fixture_ids: set[int]
    selection_hash: str

    def is_allowed(self, fixture_id: int) -> bool:
        return fixture_id in self.allowed_fixture_ids

    def apply_to_sql(self, sql: str) -> str:
        """Wrap or constrain SQL query to allowed fixture IDs."""
        if not self.allowed_fixture_ids:
            return f"SELECT * FROM ({sql}) WHERE 1=0"
        placeholders = ",".join("?" for _ in self.allowed_fixture_ids)
        return f"SELECT * FROM ({sql}) WHERE id IN ({placeholders})"

    @property
    def query_params(self) -> tuple:
        return tuple(sorted(list(self.allowed_fixture_ids)))
