from pathlib import Path
from bet.enrichment.football_data_foundation.worldcup_20260624_live_shadow.normalizer import normalize_fixture_snapshot

def test_normalizer_produces_summary_facts() -> None:
    # TEST-007: normalizer produces summary facts, not raw payloads.
    snapshot = normalize_fixture_snapshot(
        fixture_slug="worldcup2026-switzerland-canada",
        home_team="Switzerland",
        away_team="Canada",
        group="B",
        kickoff_utc="2026-06-24T21:00:00Z",
        cache_dir=Path("/tmp"),
        run_id="run_123"
    )
    
    assert snapshot["fixture_slug"] == "worldcup2026-switzerland-canada"
    assert "raw_payload" not in snapshot
    assert "raw_headers" not in snapshot
    assert "cookie" not in snapshot
    
    # Check that summary facts are generated
    fact_types = {fact["fact_type"] for fact in snapshot["facts"]}
    assert "provider_mapping" in fact_types
    assert "fixture_identity" in fact_types
    assert "score" in fact_types
    assert "match_status" in fact_types


def test_odds_are_reference_only() -> None:
    # TEST-008: odds are odds_reference only.
    snapshot = normalize_fixture_snapshot(
        fixture_slug="worldcup2026-switzerland-canada",
        home_team="Switzerland",
        away_team="Canada",
        group="B",
        kickoff_utc="2026-06-24T21:00:00Z",
        cache_dir=Path("/tmp"),
        run_id="run_123"
    )
    
    odds_facts = [f for f in snapshot["facts"] if f["fact_type"] == "odds_reference"]
    assert len(odds_facts) > 0
    for fact in odds_facts:
        assert fact["key"] == "odds_reference_available"
        assert isinstance(fact["value"], dict)
        assert fact["value"]["odds_reference_available"] is True
        # Ensure no concrete price/payout/bet/prediction/edge text is present
        assert "price" not in str(fact["value"]).lower()
        assert "edge" not in str(fact["value"]).lower()
