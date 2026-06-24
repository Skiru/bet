from bet.enrichment.football_data_foundation.worldcup_20260624_live_shadow.contracts import (
    FixtureSpec,
    ProviderCaptureEnvelope,
    LiveFixtureShadowSnapshot,
    LiveShadowRunSummary
)

def test_fixture_spec_contract() -> None:
    f = FixtureSpec(
        slug="worldcup2026-switzerland-canada",
        home_team="Switzerland",
        away_team="Canada",
        group="B",
        kickoff_utc_or_unknown="2026-06-24T21:00:00Z",
        official_context_status="PREFLIGHT_VERIFIED"
    )
    data = f.to_dict()
    assert data["slug"] == "worldcup2026-switzerland-canada"
    assert data["home_team"] == "Switzerland"
    assert data["away_team"] == "Canada"
    assert data["group"] == "B"


def test_provider_capture_envelope_contract() -> None:
    env = ProviderCaptureEnvelope(
        fixture_slug="worldcup2026-switzerland-canada",
        provider="sportdb",
        request_purpose="sportdb_detail",
        source_url="http://api.sportdb.dev",
        status="FETCHED",
        status_code=200,
        body={"test": "ok"},
        body_sha256="fake_sha",
        captured_at_utc="2026-06-24T12:00:00Z"
    )
    data = env.to_dict()
    assert data["provider"] == "sportdb"
    assert data["status"] == "FETCHED"
    assert data["body_sha256"] == "fake_sha"


def test_live_fixture_shadow_snapshot_contract() -> None:
    snap = LiveFixtureShadowSnapshot(
        fixture_slug="worldcup2026-switzerland-canada",
        provider_ids={"sportdb": "123"},
        provider_fact_counts={"sportdb": 5},
        score={"home": 2, "away": 1},
        status="FINISHED",
        kickoff="2026-06-24T21:00:00Z",
        conflicts=[],
        source_files=["cache/sportdb/worldcup2026-switzerland-canada.json"],
        activation_candidate_status="ACTIVATION_CANDIDATE_SHADOW_ONLY"
    )
    data = snap.to_dict()
    assert data["fixture_slug"] == "worldcup2026-switzerland-canada"
    assert data["production_selectable"] is False
    assert data["manual_authorization_required"] is True
    assert data["betting_decisions_allowed"] is False
