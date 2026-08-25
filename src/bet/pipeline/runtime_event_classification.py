"""Fail-closed event classification and exact selection accounting."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Any

from bet.pipeline.event_runtime_contract import (
    CanonicalEventStatus,
    ProviderRequestStatus,
    betting_day_utc_bounds,
    parse_utc_timestamp,
)


class RuntimeEventDecision(StrEnum):
    ANALYZE_FROM_S2 = "ANALYZE_FROM_S2"
    ALREADY_VALID_COMPLETE = "ALREADY_VALID_COMPLETE"
    LIVE = "LIVE"
    FINISHED = "FINISHED"
    POSTPONED = "POSTPONED"
    CANCELLED = "CANCELLED"
    ABANDONED = "ABANDONED"
    SUSPENDED = "SUSPENDED"
    WALKOVER = "WALKOVER"
    AWARDED_TERMINAL = "AWARDED_TERMINAL"
    TIME_EXPIRED_UNCONFIRMED = "TIME_EXPIRED_UNCONFIRMED"
    INSUFFICIENT_LEAD = "INSUFFICIENT_LEAD"
    PROVIDER_RECHECK_REQUIRED = "PROVIDER_RECHECK_REQUIRED"
    IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
    NO_VALID_IDENTITY = "NO_VALID_IDENTITY"


@dataclass(frozen=True)
class RuntimeEventInput:
    canonical_event_id: str
    fixture_id: int | None
    betting_date: date
    canonical_kickoff_utc: datetime
    participant_identity_sha256: str
    provider_event_ids: dict[str, str]
    current_plan_attempts: list[dict[str, Any]]
    reusable_complete: bool


@dataclass(frozen=True)
class RuntimeClassificationResult:
    decision: RuntimeEventDecision
    reason: str
    canonical_status: CanonicalEventStatus
    observed_kickoff_utc: datetime | None
    input_fingerprint: str


def resolve_current_plan_observations(
    attempts: Iterable[dict[str, Any]], run_id: str
) -> dict[str, dict[str, Any]]:
    """Resolve one current PLAN attempt per provider without preferring success."""
    current: dict[str, dict[str, Any]] = {}
    for attempt in attempts:
        if attempt.get("run_id") != run_id or attempt.get("phase") != "PLAN":
            continue
        provider = str(attempt.get("provider") or "")
        if not provider:
            continue
        key = (
            int(attempt.get("attempt_number") or 0),
            str(attempt.get("attempted_at_utc") or ""),
            int(attempt.get("id") or 0),
        )
        previous = current.get(provider)
        previous_key = (
            (
                int(previous.get("attempt_number") or 0),
                str(previous.get("attempted_at_utc") or ""),
                int(previous.get("id") or 0),
            )
            if previous
            else None
        )
        if previous_key is None or key > previous_key:
            current[provider] = attempt
    return current


def _fingerprint(event: RuntimeEventInput, attempts: list[dict[str, Any]]) -> str:
    payload = {
        "canonical_event_id": event.canonical_event_id,
        "fixture_id": event.fixture_id,
        "canonical_kickoff_utc": parse_utc_timestamp(
            event.canonical_kickoff_utc
        ).isoformat(),
        "participant_identity_sha256": event.participant_identity_sha256,
        "provider_event_ids": event.provider_event_ids,
        "observations": [
            {
                "provider": a.get("provider"),
                "provider_event_id": a.get("provider_event_id"),
                "request_status": a.get("request_status"),
                "canonical_event_status": a.get("canonical_event_status"),
                "observed_kickoff_utc": a.get("observed_kickoff_utc"),
                "participant_identity_sha256": a.get("participant_identity_sha256"),
                "observation_envelope_sha256": a.get("observation_envelope_sha256"),
            }
            for a in sorted(
                attempts,
                key=lambda item: (str(item.get("provider")), int(item.get("id") or 0)),
            )
        ],
        "contract_version": "runtime-event-classification-v1",
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class RuntimeEventClassifier:
    """Pure classifier. It does not access DB, filesystem, network, env, or clock."""

    _TERMINAL = {
        CanonicalEventStatus.LIVE: RuntimeEventDecision.LIVE,
        CanonicalEventStatus.FINISHED: RuntimeEventDecision.FINISHED,
        CanonicalEventStatus.POSTPONED: RuntimeEventDecision.POSTPONED,
        CanonicalEventStatus.CANCELLED: RuntimeEventDecision.CANCELLED,
        CanonicalEventStatus.ABANDONED: RuntimeEventDecision.ABANDONED,
        CanonicalEventStatus.SUSPENDED: RuntimeEventDecision.SUSPENDED,
        CanonicalEventStatus.WALKOVER: RuntimeEventDecision.WALKOVER,
        CanonicalEventStatus.AWARDED_TERMINAL: RuntimeEventDecision.AWARDED_TERMINAL,
    }

    def classify(
        self,
        event: RuntimeEventInput,
        runtime_now_utc: datetime,
        minimum_lead: timedelta,
    ) -> RuntimeClassificationResult:
        now = parse_utc_timestamp(runtime_now_utc)
        event_kickoff = parse_utc_timestamp(event.canonical_kickoff_utc)
        attempts = list(event.current_plan_attempts)
        fingerprint = _fingerprint(event, attempts)

        if not event.canonical_event_id or not event.participant_identity_sha256:
            return RuntimeClassificationResult(
                RuntimeEventDecision.NO_VALID_IDENTITY,
                "Incomplete canonical identity",
                CanonicalEventStatus.UNKNOWN,
                None,
                fingerprint,
            )

        start, end = betting_day_utc_bounds(event.betting_date)
        if not start <= event_kickoff < end:
            return RuntimeClassificationResult(
                RuntimeEventDecision.NO_VALID_IDENTITY,
                "Event is outside Warsaw betting day",
                CanonicalEventStatus.UNKNOWN,
                None,
                fingerprint,
            )

        if not attempts:
            return RuntimeClassificationResult(
                RuntimeEventDecision.PROVIDER_RECHECK_REQUIRED,
                "Missing current PLAN observation",
                CanonicalEventStatus.UNKNOWN,
                None,
                fingerprint,
            )

        successes: list[tuple[dict[str, Any], CanonicalEventStatus, datetime]] = []
        for attempt in attempts:
            try:
                request_status = ProviderRequestStatus(
                    str(attempt.get("request_status"))
                )
            except ValueError:
                return RuntimeClassificationResult(
                    RuntimeEventDecision.PROVIDER_RECHECK_REQUIRED,
                    "Invalid provider request status",
                    CanonicalEventStatus.UNKNOWN,
                    None,
                    fingerprint,
                )
            if request_status is ProviderRequestStatus.IDENTITY_CONFLICT:
                return RuntimeClassificationResult(
                    RuntimeEventDecision.IDENTITY_CONFLICT,
                    "Provider identity conflict",
                    CanonicalEventStatus.UNKNOWN,
                    None,
                    fingerprint,
                )
            if request_status is not ProviderRequestStatus.SUCCESS:
                return RuntimeClassificationResult(
                    RuntimeEventDecision.PROVIDER_RECHECK_REQUIRED,
                    f"Provider attempt is {request_status.value}",
                    CanonicalEventStatus.UNKNOWN,
                    None,
                    fingerprint,
                )
            if not attempt.get("evidence_valid"):
                return RuntimeClassificationResult(
                    RuntimeEventDecision.PROVIDER_RECHECK_REQUIRED,
                    "Provider evidence is not valid",
                    CanonicalEventStatus.UNKNOWN,
                    None,
                    fingerprint,
                )
            provider = str(attempt.get("provider") or "")
            expected_provider_id = event.provider_event_ids.get(provider)
            if (
                not expected_provider_id
                or str(attempt.get("provider_event_id") or "") != expected_provider_id
            ):
                return RuntimeClassificationResult(
                    RuntimeEventDecision.IDENTITY_CONFLICT,
                    "Provider event identity mismatch",
                    CanonicalEventStatus.UNKNOWN,
                    None,
                    fingerprint,
                )
            if (
                attempt.get("participant_identity_sha256")
                != event.participant_identity_sha256
            ):
                return RuntimeClassificationResult(
                    RuntimeEventDecision.IDENTITY_CONFLICT,
                    "Participant identity mismatch",
                    CanonicalEventStatus.UNKNOWN,
                    None,
                    fingerprint,
                )
            try:
                status = CanonicalEventStatus(
                    str(attempt.get("canonical_event_status"))
                )
                kickoff = parse_utc_timestamp(attempt["observed_kickoff_utc"])
            except (ValueError, KeyError, TypeError):
                return RuntimeClassificationResult(
                    RuntimeEventDecision.PROVIDER_RECHECK_REQUIRED,
                    "Incomplete canonical provider observation",
                    CanonicalEventStatus.UNKNOWN,
                    None,
                    fingerprint,
                )
            successes.append((attempt, status, kickoff))

        statuses = {status for _, status, _ in successes}
        kickoffs = [kickoff for _, _, kickoff in successes]
        if len(statuses) != 1 or (max(kickoffs) - min(kickoffs)) > timedelta(minutes=5):
            return RuntimeClassificationResult(
                RuntimeEventDecision.PROVIDER_RECHECK_REQUIRED,
                "Current providers disagree",
                CanonicalEventStatus.UNKNOWN,
                None,
                fingerprint,
            )

        status = successes[0][1]
        kickoff = successes[0][2]
        terminal = self._TERMINAL.get(status)
        if terminal:
            return RuntimeClassificationResult(
                terminal,
                f"Provider canonical status is {status.value}",
                status,
                kickoff,
                fingerprint,
            )
        if status is not CanonicalEventStatus.SCHEDULED:
            return RuntimeClassificationResult(
                RuntimeEventDecision.PROVIDER_RECHECK_REQUIRED,
                "Provider status is not confirmed scheduled",
                status,
                kickoff,
                fingerprint,
            )
        if kickoff <= now:
            return RuntimeClassificationResult(
                RuntimeEventDecision.TIME_EXPIRED_UNCONFIRMED,
                "Scheduled status is stale after kickoff",
                status,
                kickoff,
                fingerprint,
            )
        if kickoff <= now + minimum_lead:
            return RuntimeClassificationResult(
                RuntimeEventDecision.INSUFFICIENT_LEAD,
                "Minimum lead time not met",
                status,
                kickoff,
                fingerprint,
            )
        decision = (
            RuntimeEventDecision.ALREADY_VALID_COMPLETE
            if event.reusable_complete
            else RuntimeEventDecision.ANALYZE_FROM_S2
        )
        return RuntimeClassificationResult(
            decision, "Safe current provider observation", status, kickoff, fingerprint
        )


def persist_runtime_event_decisions(
    conn: sqlite3.Connection,
    run_id: str,
    betting_date: str,
    decisions: list[dict[str, Any]],
) -> dict[str, int]:
    """Atomically replace one run's selection with exactly one row per event."""
    ids = [str(item.get("canonical_event_id") or "") for item in decisions]
    if any(not event_id for event_id in ids):
        raise ValueError("MISSING_CANONICAL_EVENT_ID")
    if len(set(ids)) != len(ids):
        raise ValueError("DUPLICATE_CANONICAL_EVENT_ID")

    counts = {decision.value: 0 for decision in RuntimeEventDecision}
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "DELETE FROM pipeline_runtime_event_selection WHERE run_id = ?", (run_id,)
        )
        for item in decisions:
            decision = item["decision"]
            decision_value = (
                decision.value
                if isinstance(decision, RuntimeEventDecision)
                else str(decision)
            )
            counts[decision_value] += 1
            conn.execute(
                """INSERT INTO pipeline_runtime_event_selection (
                    run_id, canonical_event_id, fixture_id, betting_date, decision,
                    resume_action, observed_status, observed_kickoff,
                    observation_timestamp_utc, provider, provider_event_id,
                    source_evidence_sha256, previous_analysis_status,
                    previous_analysis_sha256, previous_gate_status,
                    previous_gate_sha256, input_fingerprint, reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    str(item["canonical_event_id"]),
                    item.get("fixture_id"),
                    betting_date,
                    decision_value,
                    "ANALYZE"
                    if decision_value == RuntimeEventDecision.ANALYZE_FROM_S2.value
                    else "SKIP",
                    item.get("observed_status", ""),
                    item.get("observed_kickoff", ""),
                    item.get(
                        "observation_timestamp_utc",
                        datetime.now().astimezone().isoformat(),
                    ),
                    item.get("provider", ""),
                    item.get("provider_event_id", ""),
                    item.get("source_evidence_sha256", ""),
                    item.get("previous_analysis_status", "NONE"),
                    item.get("previous_analysis_sha256", ""),
                    item.get("previous_gate_status", "NONE"),
                    item.get("previous_gate_sha256", ""),
                    item.get("input_fingerprint", ""),
                    item.get("reason", ""),
                    item.get("created_at", datetime.now().astimezone().isoformat()),
                ),
            )
        stored = conn.execute(
            "SELECT COUNT(*) FROM pipeline_runtime_event_selection WHERE run_id = ?",
            (run_id,),
        ).fetchone()[0]
        if stored != len(decisions):
            raise RuntimeError("SELECTION_ACCOUNTING_MISMATCH")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return counts
