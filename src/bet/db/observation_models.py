"""Fixture-scoped observation and projection models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class FixtureCapabilityObservation:
    """Immutable observation of a capability from a source.

    Identity: scope + capability + source + request + evidence + cutoff
    """
    id: int | None = None
    canonical_fixture_id: int = 0
    team_id: int = 0
    capability: str = ""
    source: str = ""
    request_identity: str = ""

    # Evidence
    evidence_bundle_id: str = ""
    native_fixture_id: str = ""
    native_team_id: str = ""

    # Status
    status: str = ""
    http_status: int | None = None
    error_code: str = ""
    retryable: bool = False

    # Parser metadata
    parser_version: str = ""
    parser_diagnostics: dict = field(default_factory=dict)

    # Temporal
    observed_at: str = ""
    valid_at: str = ""  # analysis_cutoff_at

    # Payload hash
    payload_sha256: str = ""
    payload_json: str = ""


@dataclass
class FixtureCapabilityProjection:
    """Selected projection for a fixture + team + capability + cutoff.

    This is mutable (can be updated when policy changes) but history is preserved.
    """
    id: int | None = None
    canonical_fixture_id: int = 0
    team_id: int = 0
    capability: str = ""
    analysis_cutoff_at: str = ""

    # Selected result
    selected_source: str = ""
    selected_status: str = ""
    selected_observation_id: int | None = None

    # Fallback metadata
    primary_source: str = ""
    primary_status: str = ""
    fallback_reason: str = ""

    # Timestamps
    created_at: str = ""
    updated_at: str = ""


def create_observation(
    canonical_fixture_id: int,
    team_id: int,
    capability: str,
    source: str,
    request_identity: str,
    status: str,
    valid_at: str,
    evidence_bundle_id: str = "",
    native_fixture_id: str = "",
    native_team_id: str = "",
    http_status: int | None = None,
    error_code: str = "",
    retryable: bool = False,
    parser_version: str = "",
    parser_diagnostics: dict | None = None,
    payload_sha256: str = "",
    payload_json: str = "",
) -> FixtureCapabilityObservation:
    """Create a new fixture-scoped observation."""
    return FixtureCapabilityObservation(
        id=None,
        canonical_fixture_id=canonical_fixture_id,
        team_id=team_id,
        capability=capability,
        source=source,
        request_identity=request_identity,
        evidence_bundle_id=evidence_bundle_id,
        native_fixture_id=native_fixture_id,
        native_team_id=native_team_id,
        status=status,
        http_status=http_status,
        error_code=error_code,
        retryable=retryable,
        parser_version=parser_version,
        parser_diagnostics=parser_diagnostics or {},
        observed_at=datetime.now(UTC).isoformat(),
        valid_at=valid_at,
        payload_sha256=payload_sha256,
        payload_json=payload_json,
    )


def create_projection(
    canonical_fixture_id: int,
    team_id: int,
    capability: str,
    analysis_cutoff_at: str,
    selected_source: str,
    selected_status: str,
    selected_observation_id: int | None = None,
    primary_source: str = "",
    primary_status: str = "",
    fallback_reason: str = "",
) -> FixtureCapabilityProjection:
    """Create a new fixture-scoped projection."""
    now = datetime.now(UTC).isoformat()
    return FixtureCapabilityProjection(
        id=None,
        canonical_fixture_id=canonical_fixture_id,
        team_id=team_id,
        capability=capability,
        analysis_cutoff_at=analysis_cutoff_at,
        selected_source=selected_source,
        selected_status=selected_status,
        selected_observation_id=selected_observation_id,
        primary_source=primary_source,
        primary_status=primary_status,
        fallback_reason=fallback_reason,
        created_at=now,
        updated_at=now,
    )
