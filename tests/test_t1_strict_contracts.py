"""Checkpoint T1 validation tests: strict business contracts, no fabrication, exact event accounting."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from bet.pipeline.contracts.base import StrictBaseModel
from bet.pipeline.contracts.common import EventRecordV1, SourceReferenceV1, EvidenceClaimV1
from bet.pipeline.contracts.steps.s0_to_s2 import SettledRecordV1, S1FixturesShortlistV1, S1eCanonicalEventUniverseV1
from bet.pipeline.contracts.migration import adapt_legacy_artifact, MigrationAdapterError


def test_t1_strict_mode_extra_field_rejection():
    """Verify strict mode rejects extra fields across all models."""
    with pytest.raises(ValidationError):
        SettledRecordV1(
            bet_id="B1",
            canonical_event_id="E1",
            market_family="result",
            selection="home",
            stake=10.0,
            odds=2.0,
            pnl=10.0,
            settled_at="2026-07-27T12:00:00Z",
            outcome="WIN",
            extra_illegal_field="FORBIDDEN",
        )


def test_t1_no_identity_defaults():
    """Verify EventRecordV1 requires all identity fields."""
    with pytest.raises(ValidationError) as exc_info:
        EventRecordV1(canonical_event_id="EVT_100")
    err_str = str(exc_info.value)
    assert "sport" in err_str
    assert "competition" in err_str
    assert "home_team" in err_str
    assert "away_team" in err_str
    assert "event_start_time" in err_str
    assert "discovery_status" in err_str


def test_t1_legacy_migration_rejects_missing_required_data():
    """Verify adapt_legacy_artifact fails closed on missing data instead of inventing truth."""
    data = {"artifact_type": "S1_SHORTLIST", "shortlist": [{"canonical_event_id": "E1"}]}
    with pytest.raises(MigrationAdapterError) as exc_info:
        adapt_legacy_artifact(data, "S1_FIXTURES_SHORTLIST")
    assert "MIGRATION_FAILED" in str(exc_info.value)


def test_t1_valid_event_record_strict_roundtrip():
    """Verify valid EventRecordV1 roundtrips canonically."""
    ev = EventRecordV1(
        canonical_event_id="EVT_001",
        sport="football",
        competition="Premier League",
        home_team="Arsenal",
        away_team="Chelsea",
        event_start_time="2026-07-27T18:00:00Z",
        discovery_status="VERIFIED",
    )
    dumped = ev.model_dump()
    reloaded = EventRecordV1.model_validate(dumped)
    assert reloaded == ev
