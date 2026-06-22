import pytest

from bet.enrichment.football_data_foundation.kernel.contracts import FactType, SourceRole
from bet.enrichment.football_data_foundation.providers.registry import (
    get_adapter,
    get_registered_football_adapters,
    list_source_descriptors,
)


def test_catalog_contains_every_required_source():
    keys = {d.source_key for d in list_source_descriptors()}
    expected = {
        "espn-accepted-baseline",
        "highlightly",
        "sportdb",
        "football-data-org",
        "api-football",
        "thesportsdb",
        "statsbomb-open-data",
        "statsbombpy",
        "openfootball",
        "kaggle-european-soccer",
        "sportdb-open-source-tooling",
        "soccerdata-clubelo",
        "soccerdata-espn",
        "soccerdata-fbref",
        "soccerdata-fivethirtyeight",
        "soccerdata-matchhistory",
        "soccerdata-sofascore",
        "soccerdata-sofifa",
        "soccerdata-understat",
        "soccerdata-whoscored",
        "fotmob-probe",
        "sofascore-rich-probe",
        "scraperfc-sofascore-bridge",
    }
    assert expected.issubset(keys)


def test_no_duplicate_source_keys():
    keys = [d.source_key for d in list_source_descriptors()]
    assert len(keys) == len(set(keys))


def test_sourcedata_espn_is_not_baseline_espn():
    assert get_adapter("soccerdata-espn").source_descriptor().source_key != "espn-accepted-baseline"


def test_contract_probes_have_no_real_values():
    for adapter in get_registered_football_adapters():
        batch = adapter.build_contract_probe()
        for c in batch.claims:
            assert c.claim_value == {}
            assert c.confidence == 0.0
            assert not c.selectable_for_production


def test_registry_is_shadow_only():
    # Registry is shadow-only and all claims selectable_for_production is always False
    for adapter in get_registered_football_adapters():
        batch = adapter.build_contract_probe()
        for c in batch.claims:
            assert c.selectable_for_production is False
