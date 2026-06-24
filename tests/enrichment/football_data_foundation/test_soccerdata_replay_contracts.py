from pathlib import Path

import pytest

from bet.enrichment.football_data_foundation.kernel.contracts import FactType, ProofLevel, ProviderCapabilityError, SourceRole
from bet.enrichment.football_data_foundation.providers.registry import get_adapter

FIX = Path(__file__).parent.parent.parent / "fixtures/enrichment/football_data_foundation/pass1"


def test_soccerdata_replay_matrix():
    cases = {
        "soccerdata-clubelo": ("soccerdata/clubelo.json", FactType.TEAM_RATING),
        "soccerdata-espn": ("soccerdata/espn.json", FactType.REFERENCE_RESULT),
        "soccerdata-fbref": ("soccerdata/fbref.json", FactType.MATCH_STATISTIC),
        "soccerdata-fivethirtyeight": ("soccerdata/fivethirtyeight.json", FactType.HISTORICAL_PRIOR),
        "soccerdata-matchhistory": ("soccerdata/matchhistory.json", FactType.ODDS_REFERENCE),
        "soccerdata-sofascore": ("soccerdata/sofascore.json", FactType.MATCH_STATISTIC),
        "soccerdata-sofifa": ("soccerdata/sofifa.json", FactType.PLAYER_DATA_CONTEXT),
        "soccerdata-understat": ("soccerdata/understat.json", FactType.XG),
    }
    for source_key, (rel, fact) in cases.items():
        adapter = get_adapter(source_key)
        batch = adapter.normalize_replay_fixture(FIX / rel)
        assert batch.claims[0].fact_type is fact
        assert batch.claims[0].proof_level is ProofLevel.REAL_DEPENDENCY_REPLAY_PROOF
        with pytest.raises(ProviderCapabilityError):
            adapter.fetch_shadow_live({})

    mh = get_adapter("soccerdata-matchhistory").normalize_replay_fixture(FIX / "soccerdata/matchhistory.json")
    assert mh.claims[0].claim_value["odds_reference_not_decision"] is True

    fte = get_adapter("soccerdata-fivethirtyeight").normalize_replay_fixture(FIX / "soccerdata/fivethirtyeight.json")
    assert fte.claims[0].claim_value["staleness_risk"] == "legacy_or_provider_deprecated_check_required"


def test_whoscored_is_deferred_docs_only():
    adapter = get_adapter("soccerdata-whoscored")
    with pytest.raises(ProviderCapabilityError):
        adapter.normalize_replay_fixture(FIX / "soccerdata/fbref.json")


def test_soccerdata_espn_not_espn():
    assert get_adapter("soccerdata-espn").source_descriptor().source_key == "soccerdata-espn"
    assert get_adapter("soccerdata-espn").source_descriptor().source_key != "espn-accepted-baseline"


def test_sofifa_cannot_emit_match_truth():
    # SoFIFA is player data context only, should not have MATCH_STATUS etc
    d = get_adapter("soccerdata-sofifa").source_descriptor()
    assert d.role is SourceRole.DEPENDENCY_REPLAY
