"""Test suite for source-preserving discovery models and deduplication (Cases 01-06)."""

from datetime import UTC, datetime
import pytest

from bet.discovery.models import DiscoveredEvent, MergedFixture, SourceRef, ProviderEventCandidate
from bet.discovery.dedup import DeduplicationEngine


# C4_CASE_01_RAW_STATUS_SURVIVES
def test_c4_case_01_raw_status_survives():
    evt = DiscoveredEvent(
        source="api_football",
        external_id="p_123",
        sport="football",
        competition="Premier League",
        home_team="Arsenal",
        away_team="Chelsea",
        kickoff=datetime(2026, 7, 30, 15, 0, tzinfo=UTC),
        status="NS",
    )
    dedup = DeduplicationEngine()
    merged = dedup.deduplicate_events([evt])
    assert len(merged) == 1
    assert merged[0].sources[0].raw_status == "NS"


# C4_CASE_02_RAW_KICKOFF_SURVIVES
def test_c4_case_02_raw_kickoff_survives():
    ko = datetime(2026, 7, 30, 15, 0, tzinfo=UTC)
    evt = DiscoveredEvent(
        source="api_football",
        external_id="p_123",
        sport="football",
        competition="Premier League",
        home_team="Arsenal",
        away_team="Chelsea",
        kickoff=ko,
        status="NS",
    )
    dedup = DeduplicationEngine()
    merged = dedup.deduplicate_events([evt])
    assert len(merged) == 1
    assert merged[0].sources[0].raw_kickoff == ko


# C4_CASE_03_RAW_PARTICIPANTS_SURVIVE
def test_c4_case_03_raw_participants_survive():
    evt = DiscoveredEvent(
        source="api_football",
        external_id="p_123",
        sport="football",
        competition="Premier League",
        home_team="Arsenal FC",
        away_team="Chelsea FC",
        kickoff=datetime(2026, 7, 30, 15, 0, tzinfo=UTC),
        status="NS",
    )
    dedup = DeduplicationEngine()
    merged = dedup.deduplicate_events([evt])
    assert len(merged) == 1
    ref = merged[0].sources[0]
    assert ref.raw_home_team == "Arsenal FC"
    assert ref.raw_away_team == "Chelsea FC"


# C4_CASE_04_PROVIDER_ID_SURVIVES
def test_c4_case_04_provider_id_survives():
    evt = DiscoveredEvent(
        source="api_football",
        external_id="p_unique_999",
        sport="football",
        competition="Premier League",
        home_team="Arsenal",
        away_team="Chelsea",
        kickoff=datetime(2026, 7, 30, 15, 0, tzinfo=UTC),
        status="NS",
    )
    dedup = DeduplicationEngine()
    merged = dedup.deduplicate_events([evt])
    assert len(merged) == 1
    assert merged[0].sources[0].external_id == "p_unique_999"


# C4_CASE_05_MULTIPLE_SOURCE_REFS_SURVIVE
def test_c4_case_05_multiple_source_refs_survive():
    evt1 = DiscoveredEvent(
        source="api_football",
        external_id="p_1",
        sport="football",
        competition="La Liga",
        home_team="Real Madrid",
        away_team="Barcelona",
        kickoff=datetime(2026, 7, 30, 20, 0, tzinfo=UTC),
        status="NS",
    )
    evt2 = DiscoveredEvent(
        source="odds_api",
        external_id="oa_1",
        sport="football",
        competition="La Liga",
        home_team="Real Madrid",
        away_team="Barcelona",
        kickoff=datetime(2026, 7, 30, 20, 0, tzinfo=UTC),
        status="NS",
    )
    dedup = DeduplicationEngine()
    merged = dedup.merge({"api_football": [evt1], "odds_api": [evt2]})
    assert len(merged) == 1
    assert len(merged[0].sources) == 2


# C4_CASE_06_SOURCE_DISAGREEMENT_VISIBLE
def test_c4_case_06_source_disagreement_visible():
    evt1 = DiscoveredEvent(
        source="api_football",
        external_id="p_1",
        sport="football",
        competition="La Liga",
        home_team="Real Madrid",
        away_team="Barcelona",
        kickoff=datetime(2026, 7, 30, 20, 0, tzinfo=UTC),
        status="NS",
    )
    evt2 = DiscoveredEvent(
        source="odds_api",
        external_id="oa_1",
        sport="football",
        competition="La Liga",
        home_team="Real Madrid",
        away_team="Barcelona",
        kickoff=datetime(2026, 7, 30, 20, 0, tzinfo=UTC),
        status="LIVE",
    )
    dedup = DeduplicationEngine()
    merged = dedup.merge({"api_football": [evt1], "odds_api": [evt2]})
    assert len(merged) == 1
    sources_dict = {s.source: s.raw_status for s in merged[0].sources}
    assert sources_dict["api_football"] == "NS"
    assert sources_dict["odds_api"] == "LIVE"
