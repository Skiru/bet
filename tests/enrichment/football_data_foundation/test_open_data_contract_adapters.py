from pathlib import Path

import pytest

from bet.enrichment.football_data_foundation.kernel.contracts import FactType, ProofLevel, ProviderCapabilityError, SourceRole
from bet.enrichment.football_data_foundation.providers.registry import get_adapter

FIX = Path(__file__).parent.parent.parent / "fixtures/enrichment/football_data_foundation/pass1"


def test_open_data_adapters():
    statsbomb = get_adapter("statsbomb-open-data").normalize_replay_fixture(FIX / "open_data/statsbomb")
    assert statsbomb.claims[0].proof_level is ProofLevel.REAL_LOCAL_OPEN_DATA_PROOF
    assert statsbomb.claims[0].source.role is SourceRole.HISTORICAL_DEEP
    assert statsbomb.claims[0].claim_value["shot_count"] == 2
    assert statsbomb.claims[0].claim_value["xg_sum"] == 0.6

    openfootball = get_adapter("openfootball").normalize_replay_fixture(FIX / "openfootball_minimal.txt")
    assert openfootball.claims[0].fact_type is FactType.REFERENCE_RESULT
    assert openfootball.claims[0].proof_level is ProofLevel.REAL_LOCAL_OPEN_DATA_PROOF
    assert openfootball.claims[0].source.role is SourceRole.REFERENCE_IDENTITY

    kaggle = get_adapter("kaggle-european-soccer").normalize_replay_fixture(FIX / "kaggle_european_soccer_minimal.csv")
    assert kaggle.claims[0].claim_value["temporal_decay_required"] is True
    assert kaggle.claims[0].proof_level is ProofLevel.REAL_LOCAL_OPEN_DATA_PROOF
    assert kaggle.claims[0].source.role is SourceRole.HISTORICAL_DEEP


def test_statsbombpy_bridge_is_docs_only():
    adapter = get_adapter("statsbombpy")
    assert adapter.source_descriptor().role is SourceRole.OPTIONAL_LIBRARY_BRIDGE
    with pytest.raises(ProviderCapabilityError):
        adapter.normalize_replay_fixture(FIX / "open_data/statsbomb")


def test_sportdb_tooling_is_docs_only():
    adapter = get_adapter("sportdb-open-source-tooling")
    assert adapter.source_descriptor().role is SourceRole.OPTIONAL_LIBRARY_BRIDGE
    with pytest.raises(ProviderCapabilityError):
        adapter.normalize_replay_fixture(FIX / "openfootball_minimal.txt")
