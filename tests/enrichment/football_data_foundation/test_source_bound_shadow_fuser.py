from bet.enrichment.football_data_foundation.source_bound_shadow.contracts import NormalizedFact
from bet.enrichment.football_data_foundation.source_bound_shadow.fuser import fuse_match_snapshot

def make_dummy_fact(source: str, fact_type: str, key: str, value: object, provider_match_id: str = None) -> NormalizedFact:
    return NormalizedFact(
        source=source,
        source_role="test_role",
        fact_type=fact_type,
        key=key,
        value=value,
        provider_match_id=provider_match_id or ("id_" + source),
        body_sha256="sha",
        source_file="file",
    )

def test_fuser_builds_snapshot_with_five_provider_ids():
    facts = [
        make_dummy_fact("api-football", "provider_mapping", "api-football.provider_match_id", "1489401", "1489401"),
        make_dummy_fact("sportdb", "provider_mapping", "sportdb.provider_match_id", "xSUJLPV8", "xSUJLPV8"),
        make_dummy_fact("highlightly", "provider_mapping", "highlightly.provider_match_id", "1267481035", "1267481035"),
        make_dummy_fact("football-data-org", "provider_mapping", "football-data-org.provider_match_id", "537394", "537394"),
        make_dummy_fact("espn-baseline", "provider_mapping", "espn-baseline.provider_match_id", "760454", "760454"),
        make_dummy_fact("api-football", "score", "full_time_score", {"home": 3, "away": 2}),
        make_dummy_fact("sportdb", "score", "full_time_score", {"home": 3, "away": 2}),
    ]
    snapshot = fuse_match_snapshot(facts)
    assert snapshot.provider_ids == {
        "api-football": "1489401",
        "sportdb": "xSUJLPV8",
        "highlightly": "1267481035",
        "football-data-org": "537394",
        "espn-baseline": "760454"
    }
    assert snapshot.score == {"home": 3, "away": 2}
    assert len(snapshot.conflicts) == 0

def test_fuser_detects_conflict_on_inconsistent_score():
    facts = [
        make_dummy_fact("api-football", "score", "full_time_score", {"home": 3, "away": 2}),
        make_dummy_fact("sportdb", "score", "full_time_score", {"home": 1, "away": 1}),
    ]
    snapshot = fuse_match_snapshot(facts)
    assert len(snapshot.conflicts) == 1
    assert snapshot.conflicts[0]["type"] == "score_conflict"
