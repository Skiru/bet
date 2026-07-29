from bet.enrichment.football_data_foundation.worldcup_20260624_live_shadow.fixtures import (
    load_target_fixtures,
    execute_fixture_preflight
)

def test_six_target_fixtures_declared() -> None:
    # TEST-001: six target fixtures are declared.
    fixtures = load_target_fixtures()
    assert len(fixtures) == 6
    slugs = [f.slug for f in fixtures]
    assert len(set(slugs)) == 6

    # Check some of the required target fixtures
    assert "worldcup2026-switzerland-canada" in slugs
    assert "worldcup2026-bosnia-herzegovina-qatar" in slugs
    assert "worldcup2026-scotland-brazil" in slugs
    assert "worldcup2026-morocco-haiti" in slugs
    assert "worldcup2026-czechia-mexico" in slugs
    assert "worldcup2026-south-africa-korea-republic" in slugs
