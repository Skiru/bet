import pytest
from bet.enrichment.football_data_foundation.live_response_corpus_capture.contracts import (
    ProviderResponseEnvelope,
    LiveCorpusManifest,
    Provider,
    CaptureStatus,
)


def test_provider_response_envelope_valid():
    env = ProviderResponseEnvelope(
        provider=Provider.SPORTDB.value,
        status=CaptureStatus.FETCHED.value,
        fixture_slug="england-italy-2026-06-23",
        source_url="http://example.com",
        captured_at_utc="2026-06-23T12:00:00Z",
        status_code=200,
        body={"foo": "bar"},
        body_sha256="abc123sha",
    )
    env.validate()
    d = env.to_dict()
    assert d["provider"] == "sportdb"
    assert d["status"] == "FETCHED"
    assert d["raw_headers_stored"] is False
    assert d["secrets_stored"] is False
    assert d["selectable_for_production"] is False


def test_provider_response_envelope_invalid_headers():
    env = ProviderResponseEnvelope(
        provider="sportdb",
        status="FETCHED",
        fixture_slug="slug",
        source_url=None,
        captured_at_utc="2026",
        raw_headers_stored=True,
    )
    with pytest.raises(ValueError, match="raw_headers_stored"):
        env.validate()


def test_provider_response_envelope_invalid_secrets():
    env = ProviderResponseEnvelope(
        provider="sportdb",
        status="FETCHED",
        fixture_slug="slug",
        source_url=None,
        captured_at_utc="2026",
        secrets_stored=True,
    )
    with pytest.raises(ValueError, match="secrets_stored"):
        env.validate()


def test_provider_response_envelope_invalid_production():
    env = ProviderResponseEnvelope(
        provider="sportdb",
        status="FETCHED",
        fixture_slug="slug",
        source_url=None,
        captured_at_utc="2026",
        selectable_for_production=True,
    )
    with pytest.raises(ValueError, match="selectable_for_production"):
        env.validate()


def test_live_corpus_manifest_valid():
    manifest = LiveCorpusManifest(
        run_id="run-123",
        run_started_at_utc="2026-06-23T12:00:00Z",
        target_date_utc="2026-06-23",
        fixture_count=1,
        provider_count=5,
        fetched_count=1,
        skipped_count=4,
        failed_count=0,
        credentials_present={"sportdb": True},
        files_written=["path/to/env.json"],
    )
    manifest.validate()
    d = manifest.to_dict()
    assert d["run_id"] == "run-123"
    assert d["selectable_for_production"] is False


def test_live_corpus_manifest_invalid_production():
    manifest = LiveCorpusManifest(
        run_id="run-123",
        run_started_at_utc="2026-06-23T12:00:00Z",
        target_date_utc="2026-06-23",
        fixture_count=1,
        provider_count=5,
        fetched_count=1,
        skipped_count=4,
        failed_count=0,
        credentials_present={"sportdb": True},
        files_written=["path/to/env.json"],
        selectable_for_production=True,
    )
    with pytest.raises(ValueError, match="selectable_for_production"):
        manifest.validate()
