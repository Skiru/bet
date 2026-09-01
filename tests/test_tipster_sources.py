from __future__ import annotations

from bet.tipsters.source_contracts import TIPSTER_SITES, TIPSTER_SOURCE_CONTRACTS
from bet.tipster_registry import TIPSTER_SOURCE_REGISTRY


def test_tipster_source_contracts_cover_required_sites():
    assert [contract.name for contract in TIPSTER_SOURCE_CONTRACTS] == [
        "ZawodTyper",
        "Typersi",
        "Sportsgambler",
        "PicksWise",
        "BetIdeas",
        "Feedinco",
        "BettingClosed",
    ]


def test_zawodtyper_contract_is_xhr_first():
    zawodtyper = next(contract for contract in TIPSTER_SOURCE_CONTRACTS if contract.name == "ZawodTyper")
    assert zawodtyper.transport == "playwright_xhr"
    assert zawodtyper.timeout_seconds == 30
    assert zawodtyper.wait_after_load_ms == 3000


def test_site_configs_match_contracts():
    by_name = {site["name"]: site for site in TIPSTER_SITES}
    for contract in TIPSTER_SOURCE_CONTRACTS:
        config = by_name[contract.name]
        assert config["parser"] == contract.parser
        assert config["language"] == contract.language
        assert tuple(config["sports"]) == contract.sports


def test_registry_uses_contract_backed_active_sources():
    football_sources = TIPSTER_SOURCE_REGISTRY["football"]["active_sources"]
    assert football_sources == [contract.name for contract in TIPSTER_SOURCE_CONTRACTS if "football" in contract.sports]
