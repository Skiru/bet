from __future__ import annotations

from pathlib import Path

import pytest

from bet.enrichment.football_data_foundation.kernel.contracts import FactType, ProofLevel
from bet.enrichment.football_data_foundation.kernel.errors import ProviderCapabilityError
from bet.enrichment.football_data_foundation.soccerdata_replay.pass2_replay import (
    normalize_soccerdata_replay,
)

FIXTURES_DIR = (
    Path(__file__).parent.parent.parent
    / "fixtures"
    / "enrichment"
    / "football_data_foundation"
    / "pass2"
)


def test_soccerdata_replay_normalization() -> None:
    sources_and_types = [
        ("clubelo", FactType.TEAM_RATING),
        ("espn", FactType.REFERENCE_RESULT),
        ("fbref", FactType.MATCH_STATISTIC),
        ("fivethirtyeight", FactType.HISTORICAL_PRIOR),
        ("matchhistory", FactType.ODDS_REFERENCE),
        ("sofascore", FactType.MATCH_STATISTIC),
        ("sofifa", FactType.PLAYER_DATA_CONTEXT),
        ("understat", FactType.XG),
    ]

    for source, fact_type in sources_and_types:
        input_path = FIXTURES_DIR / "soccerdata" / f"{source}.json"
        batch = normalize_soccerdata_replay(source, input_path)

        assert len(batch.claims) == 1
        claim = batch.claims[0]

        if source == "espn":
            assert batch.source_key == "soccerdata-espn"

        assert claim.fact_type == fact_type
        assert claim.proof_level == ProofLevel.REAL_DEPENDENCY_REPLAY_PROOF
        assert claim.freshness.is_current_truth_allowed is False

        if source == "fivethirtyeight":
            assert "staleness_risk" in claim.claim_value

        if source == "matchhistory":
            assert claim.claim_value["odds_reference_not_decision"] is True


def test_soccerdata_whoscored_fails_closed() -> None:
    input_path = FIXTURES_DIR / "soccerdata" / "clubelo.json"
    with pytest.raises(ProviderCapabilityError):
        normalize_soccerdata_replay("whoscored", input_path)


def test_unsupported_source() -> None:
    with pytest.raises(ProviderCapabilityError):
        normalize_soccerdata_replay("invalid-source", FIXTURES_DIR / "soccerdata" / "clubelo.json")

