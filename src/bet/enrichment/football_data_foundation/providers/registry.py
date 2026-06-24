from __future__ import annotations

from bet.enrichment.football_data_foundation.open_data_adapters.adapters import (
    KaggleEuropeanSoccerAdapter,
    OpenFootballAdapter,
    SportDBOpenSourceToolingAdapter,
    StatsBombOpenDataAdapter,
    StatsBombPyBridgeAdapter,
)
from bet.enrichment.football_data_foundation.probes.adapters import all_probe_adapters
from bet.enrichment.football_data_foundation.providers.current import (
    APIFootballDeferredAdapter,
    ESPNAcceptedBaselineAdapter,
    FootballDataOrgAdapter,
    HighlightlyAdapter,
    SportDBFootballAdapter,
    TheSportsDBMetadataAdapter,
)
from bet.enrichment.football_data_foundation.soccerdata_replay.replay import all_soccerdata_adapters


def get_registered_football_adapters():
    return (
        ESPNAcceptedBaselineAdapter(),
        HighlightlyAdapter(),
        SportDBFootballAdapter(),
        FootballDataOrgAdapter(),
        APIFootballDeferredAdapter(),
        TheSportsDBMetadataAdapter(),
        StatsBombOpenDataAdapter(),
        StatsBombPyBridgeAdapter(),
        OpenFootballAdapter(),
        KaggleEuropeanSoccerAdapter(),
        SportDBOpenSourceToolingAdapter(),
        *all_soccerdata_adapters(),
        *all_probe_adapters(),
    )


def list_source_descriptors():
    return tuple(adapter.source_descriptor() for adapter in get_registered_football_adapters())


def get_adapter(source_key: str):
    for adapter in get_registered_football_adapters():
        if adapter.source_descriptor().source_key == source_key:
            return adapter
    raise KeyError(source_key)
