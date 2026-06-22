from pathlib import Path

import pytest

from bet.enrichment.football_data_foundation.kernel.contracts import (
    CredentialsMissingError,
    FactType,
    ProofLevel,
    ProviderCapabilityError,
    SourceRole,
)
from bet.enrichment.football_data_foundation.providers.registry import get_adapter

FIX = Path(__file__).parent.parent.parent / "fixtures/enrichment/football_data_foundation/pass1"


def test_espn_accepted_baseline_replay_is_accepted_artifact():
    batch = get_adapter("espn-accepted-baseline").normalize_replay_fixture(FIX / "providers/espn_accepted_baseline.json")
    claim = batch.claims[0]
    assert claim.proof_level is ProofLevel.REAL_ACCEPTED_ARTIFACT_PROOF
    assert claim.source.role is SourceRole.CURRENT_LIVE_BENCHMARK


def test_current_provider_replay_adapters():
    cases = [
        ("highlightly", "providers/highlightly_sanitized_stats.json", FactType.MATCH_STATISTIC),
        ("sportdb", "providers/sportdb_sanitized_live_match.json", FactType.MATCH_STATUS),
        ("football-data-org", "providers/football_data_org_sanitized_standings.json", FactType.STANDINGS),
        ("thesportsdb", "providers/thesportsdb_metadata.json", FactType.METADATA),
    ]
    for source_key, rel, fact in cases:
        batch = get_adapter(source_key).normalize_replay_fixture(FIX / rel)
        assert batch.claims[0].fact_type is fact
        assert batch.claims[0].proof_level is ProofLevel.REAL_DEPENDENCY_REPLAY_PROOF


def test_highlightly_is_current_detailed_shadow():
    d = get_adapter("highlightly").source_descriptor()
    assert d.role is SourceRole.CURRENT_LIVE_OR_RECENT_DETAILED_SHADOW
    assert d.requires_credentials
    assert FactType.THREE_SIXTY_FRAME in d.forbidden_fact_types


def test_api_football_is_deferred_not_live_enabled_for_pass1():
    adapter = get_adapter("api-football")
    assert adapter.source_descriptor().role is SourceRole.LATER_PROVIDER_CANDIDATE
    with pytest.raises(ProviderCapabilityError):
        adapter.fetch_shadow_live({})
    with pytest.raises(ProviderCapabilityError):
        adapter.normalize_replay_fixture(FIX / "providers/highlightly_sanitized_stats.json")


def test_live_credentials_missing_fail_closed(monkeypatch):
    for source_key, env_name in [("sportdb", "SPORTDB_API_KEY"), ("football-data-org", "FOOTBALL_DATA_API_KEY"), ("highlightly", "HIGHLIGHTLY_API_KEY")]:
        monkeypatch.delenv(env_name, raising=False)
        with pytest.raises(CredentialsMissingError):
            get_adapter(source_key).fetch_shadow_live({})


def test_football_data_org_forbids_detailed():
    d = get_adapter("football-data-org").source_descriptor()
    for fact in [FactType.XG, FactType.SHOT, FactType.THREE_SIXTY_FRAME, FactType.MATCH_EVENT, FactType.PLAYER_DATA_CONTEXT]:
        assert fact in d.forbidden_fact_types


def test_thesportsdb_metadata_only():
    d = get_adapter("thesportsdb").source_descriptor()
    assert d.role is SourceRole.REFERENCE_METADATA_SHADOW
    for fact in [FactType.XG, FactType.SHOT, FactType.THREE_SIXTY_FRAME, FactType.MATCH_STATISTIC]:
        assert fact in d.forbidden_fact_types
