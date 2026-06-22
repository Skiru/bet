from __future__ import annotations

from pathlib import Path

from bet.enrichment.football_data_foundation.kernel.contracts import FactType, ProofLevel
from bet.enrichment.football_data_foundation.open_data_adapters.pass2_parsers import (
    parse_kaggle_european_soccer_csv,
    parse_openfootball_text,
    parse_statsbomb_tree,
)

FIXTURES_DIR = (
    Path(__file__).parent.parent.parent
    / "fixtures"
    / "enrichment"
    / "football_data_foundation"
    / "pass2"
)


def test_statsbomb_open_data_parser() -> None:
    root = FIXTURES_DIR / "open_data" / "statsbomb"
    batch = parse_statsbomb_tree(root)
    
    assert len(batch.claims) == 1
    claim = batch.claims[0]
    
    assert claim.claim_value["competition_count"] == 1
    assert claim.claim_value["event_count"] == 3
    assert claim.claim_value["shot_count"] == 2
    assert claim.claim_value["xg_sum"] == 0.35
    assert claim.claim_value["lineups_count"] == 1
    assert claim.claim_value["three_sixty_frame_count"] == 1
    
    assert claim.proof_level == ProofLevel.REAL_LOCAL_OPEN_DATA_PROOF
    assert claim.source.supports_live is False
    assert claim.freshness.is_current_truth_allowed is False


def test_openfootball_parser() -> None:
    path = FIXTURES_DIR / "openfootball_results.txt"
    batch = parse_openfootball_text(path)
    
    assert len(batch.claims) == 1
    claim = batch.claims[0]
    
    assert claim.fact_type == FactType.REFERENCE_RESULT
    assert claim.claim_value["line_count"] == 2
    assert claim.claim_value["fixture_count"] == 2


def test_kaggle_parser() -> None:
    path = FIXTURES_DIR / "kaggle_matches.csv"
    batch = parse_kaggle_european_soccer_csv(path)
    
    assert len(batch.claims) == 1
    claim = batch.claims[0]
    
    assert claim.fact_type == FactType.HISTORICAL_PRIOR
    assert claim.claim_value["record_count"] == 1
    assert claim.claim_value["temporal_decay_required"] is True
    assert claim.freshness.is_current_truth_allowed is False

