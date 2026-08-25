from datetime import UTC, date, datetime, timedelta

import pytest

from bet.pipeline.runtime_event_classification import (
    RuntimeEventClassifier,
    RuntimeEventDecision,
    RuntimeEventInput,
    resolve_current_plan_observations,
)

NOW = datetime(2026, 7, 30, 10, 0, tzinfo=UTC)
KICKOFF = datetime(2026, 7, 30, 14, 0, tzinfo=UTC)


def _attempt(status="SUCCESS", canonical="SCHEDULED", **overrides):
    value = {
        "id": 1,
        "run_id": "run-1",
        "phase": "PLAN",
        "attempt_number": 1,
        "canonical_event_id": "event-1",
        "provider": "api_football",
        "provider_event_id": "provider-1",
        "attempted_at_utc": "2026-07-30T09:00:00+00:00",
        "request_status": status,
        "canonical_event_status": canonical,
        "observed_kickoff_utc": KICKOFF.isoformat(),
        "participant_identity_sha256": "participants-1",
        "evidence_valid": status == "SUCCESS",
    }
    value.update(overrides)
    return value


def _event(attempts=None, **overrides):
    value = RuntimeEventInput(
        canonical_event_id="event-1",
        fixture_id=1,
        betting_date=date(2026, 7, 30),
        canonical_kickoff_utc=KICKOFF,
        participant_identity_sha256="participants-1",
        provider_event_ids={"api_football": "provider-1"},
        current_plan_attempts=attempts if attempts is not None else [_attempt()],
        reusable_complete=False,
    )
    return value.__class__(**{**value.__dict__, **overrides})


@pytest.mark.parametrize(
    ("request_status", "expected"),
    [
        pytest.param(
            "FAILED", RuntimeEventDecision.PROVIDER_RECHECK_REQUIRED, id="01-failed"
        ),
        pytest.param(
            "UNSUPPORTED",
            RuntimeEventDecision.PROVIDER_RECHECK_REQUIRED,
            id="02-unsupported",
        ),
        pytest.param(
            "IDENTITY_MISSING",
            RuntimeEventDecision.PROVIDER_RECHECK_REQUIRED,
            id="03-identity-missing",
        ),
        pytest.param(
            "IDENTITY_CONFLICT",
            RuntimeEventDecision.IDENTITY_CONFLICT,
            id="04-identity-conflict",
        ),
    ],
)
def test_provider_gate_rejects_non_success(request_status, expected):
    result = RuntimeEventClassifier().classify(
        _event([_attempt(request_status)]), NOW, timedelta(minutes=15)
    )
    assert result.decision is expected


def test_05_missing_plan_observation_is_rejected():
    result = RuntimeEventClassifier().classify(_event([]), NOW, timedelta(minutes=15))
    assert result.decision is RuntimeEventDecision.PROVIDER_RECHECK_REQUIRED


@pytest.mark.parametrize(
    "attempt",
    [
        pytest.param(_attempt(evidence_valid=False), id="06-missing-evidence"),
        pytest.param(
            _attempt(evidence_valid=False, evidence_error="SHA256_MISMATCH"),
            id="07-tampered-evidence",
        ),
        pytest.param(
            _attempt(evidence_valid=False, evidence_error="ENVELOPE_MISMATCH"),
            id="08-envelope-mismatch",
        ),
        pytest.param(
            _attempt(participant_identity_sha256="other"), id="09-participant-mismatch"
        ),
        pytest.param(_attempt(provider_event_id="other"), id="10-provider-id-mismatch"),
    ],
)
def test_invalid_success_is_rejected(attempt):
    result = RuntimeEventClassifier().classify(
        _event([attempt]), NOW, timedelta(minutes=15)
    )
    assert result.decision in {
        RuntimeEventDecision.PROVIDER_RECHECK_REQUIRED,
        RuntimeEventDecision.IDENTITY_CONFLICT,
    }


def test_11_latest_attempt_wins():
    attempts = [_attempt(), _attempt(status="FAILED", id=2, attempt_number=2)]
    current = resolve_current_plan_observations(attempts, "run-1")
    assert current["api_football"]["request_status"] == "FAILED"


def test_12_continuation_attempt_is_not_used_for_plan():
    current = resolve_current_plan_observations(
        [_attempt(phase="CONTINUATION")], "run-1"
    )
    assert current == {}


def test_13_older_success_does_not_hide_newer_failure():
    attempts = [_attempt(), _attempt(status="FAILED", id=2, attempt_number=2)]
    result = RuntimeEventClassifier().classify(
        _event(list(resolve_current_plan_observations(attempts, "run-1").values())),
        NOW,
        timedelta(minutes=15),
    )
    assert result.decision is RuntimeEventDecision.PROVIDER_RECHECK_REQUIRED


def test_14_conflicting_current_providers_fail_closed():
    attempts = [
        _attempt(),
        _attempt(
            id=2,
            provider="espn",
            provider_event_id="espn-1",
            canonical_event_status="FINISHED",
        ),
    ]
    result = RuntimeEventClassifier().classify(
        _event(
            attempts,
            provider_event_ids={"api_football": "provider-1", "espn": "espn-1"},
        ),
        NOW,
        timedelta(minutes=15),
    )
    assert result.decision is RuntimeEventDecision.PROVIDER_RECHECK_REQUIRED


@pytest.mark.parametrize(
    ("status", "decision"),
    [
        pytest.param(
            "SCHEDULED", RuntimeEventDecision.ANALYZE_FROM_S2, id="15-scheduled"
        ),
        pytest.param("POSTPONED", RuntimeEventDecision.POSTPONED, id="16-postponed"),
        pytest.param(
            "AWARDED_TERMINAL", RuntimeEventDecision.AWARDED_TERMINAL, id="17-awarded"
        ),
        pytest.param("WALKOVER", RuntimeEventDecision.WALKOVER, id="18-walkover"),
        pytest.param("LIVE", RuntimeEventDecision.LIVE, id="19-live"),
        pytest.param("FINISHED", RuntimeEventDecision.FINISHED, id="20-finished"),
        pytest.param("CANCELLED", RuntimeEventDecision.CANCELLED, id="21-cancelled"),
        pytest.param("ABANDONED", RuntimeEventDecision.ABANDONED, id="22-abandoned"),
        pytest.param("SUSPENDED", RuntimeEventDecision.SUSPENDED, id="23-suspended"),
        pytest.param(
            "UNKNOWN", RuntimeEventDecision.PROVIDER_RECHECK_REQUIRED, id="24-unknown"
        ),
    ],
)
def test_canonical_status_drives_decision(status, decision):
    result = RuntimeEventClassifier().classify(
        _event([_attempt(canonical=status)]), NOW, timedelta(minutes=15)
    )
    assert result.decision is decision


def test_25_stale_scheduled_is_time_expired():
    attempt = _attempt(observed_kickoff_utc=(NOW - timedelta(minutes=1)).isoformat())
    result = RuntimeEventClassifier().classify(
        _event([attempt]), NOW, timedelta(minutes=15)
    )
    assert result.decision is RuntimeEventDecision.TIME_EXPIRED_UNCONFIRMED


def test_26_raw_status_cannot_override_canonical_status():
    attempt = _attempt(canonical="UNKNOWN", raw_provider_status="NS")
    result = RuntimeEventClassifier().classify(
        _event([attempt]), NOW, timedelta(minutes=15)
    )
    assert result.decision is RuntimeEventDecision.PROVIDER_RECHECK_REQUIRED


@pytest.mark.parametrize(
    ("kickoff", "betting_date", "expected"),
    [
        pytest.param(
            datetime(2026, 7, 29, 22, 0, tzinfo=UTC),
            date(2026, 7, 30),
            True,
            id="27-warsaw-start",
        ),
        pytest.param(
            datetime(2026, 7, 30, 21, 59, 59, tzinfo=UTC),
            date(2026, 7, 30),
            True,
            id="28-before-end",
        ),
        pytest.param(
            datetime(2026, 7, 30, 22, 0, tzinfo=UTC),
            date(2026, 7, 30),
            False,
            id="29-half-open-end",
        ),
        pytest.param(
            datetime(2026, 7, 29, 23, 0, tzinfo=UTC),
            date(2026, 7, 30),
            True,
            id="30-not-utc-prefix",
        ),
        pytest.param(
            datetime(2026, 7, 29, 22, 0, tzinfo=UTC),
            date(2026, 7, 30),
            True,
            id="31-summer",
        ),
        pytest.param(
            datetime(2026, 1, 14, 23, 0, tzinfo=UTC),
            date(2026, 1, 15),
            True,
            id="32-winter",
        ),
        pytest.param(
            datetime(2026, 3, 28, 23, 0, tzinfo=UTC),
            date(2026, 3, 29),
            True,
            id="33-dst",
        ),
    ],
)
def test_warsaw_day_membership(kickoff, betting_date, expected):
    attempt = _attempt(observed_kickoff_utc=kickoff.isoformat())
    event = _event([attempt], betting_date=betting_date, canonical_kickoff_utc=kickoff)
    result = RuntimeEventClassifier().classify(
        event, kickoff - timedelta(hours=2), timedelta(minutes=15)
    )
    assert (result.decision is RuntimeEventDecision.ANALYZE_FROM_S2) is expected
