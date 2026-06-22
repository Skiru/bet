from pathlib import Path

import pytest

from bet.enrichment.football_data_foundation.kernel.contracts import FactType, ProviderCapabilityError, SourceRole
from bet.enrichment.football_data_foundation.providers.registry import get_adapter

FIX = Path(__file__).parent.parent / "fixtures/enrichment/football_data_foundation/pass1"


def test_probe_contracts():
    for source_key in ["fotmob-probe", "sofascore-rich-probe", "scraperfc-sofascore-bridge"]:
        adapter = get_adapter(source_key)
        d = adapter.source_descriptor()
        assert d.role is SourceRole.EXPERIMENTAL_PROBE
        with pytest.raises(ProviderCapabilityError):
            adapter.fetch_shadow_live({})
        with pytest.raises(ProviderCapabilityError):
            adapter.normalize_replay_fixture(FIX / "soccerdata/fbref.json")

        batch = adapter.build_contract_probe()
        for claim in batch.claims:
            assert claim.selectable_for_production is False
