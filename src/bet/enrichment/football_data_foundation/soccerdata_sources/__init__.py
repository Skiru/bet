from __future__ import annotations

from bet.enrichment.football_data_foundation.soccerdata_sources.clubelo import (
    ClubEloConnector,
)
from bet.enrichment.football_data_foundation.soccerdata_sources.espn import (
    ESPNConnector,
)
from bet.enrichment.football_data_foundation.soccerdata_sources.fbref import (
    FBrefConnector,
)
from bet.enrichment.football_data_foundation.soccerdata_sources.fivethirtyeight import (
    FiveThirtyEightConnector,
)
from bet.enrichment.football_data_foundation.soccerdata_sources.matchhistory import (
    MatchHistoryConnector,
)
from bet.enrichment.football_data_foundation.soccerdata_sources.sofascore import (
    SofascoreConnector,
)
from bet.enrichment.football_data_foundation.soccerdata_sources.sofifa import (
    SoFIFAConnector,
)
from bet.enrichment.football_data_foundation.soccerdata_sources.understat import (
    UnderstatConnector,
)
from bet.enrichment.football_data_foundation.soccerdata_sources.whoscored import (
    WhoScoredConnector,
)

__all__ = [
    "ClubEloConnector",
    "ESPNConnector",
    "FBrefConnector",
    "FiveThirtyEightConnector",
    "MatchHistoryConnector",
    "SofascoreConnector",
    "SoFIFAConnector",
    "UnderstatConnector",
    "WhoScoredConnector",
]
