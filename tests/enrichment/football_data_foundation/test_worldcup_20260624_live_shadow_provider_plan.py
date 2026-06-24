from bet.enrichment.football_data_foundation.worldcup_20260624_live_shadow.provider_plan import build_provider_plans

def test_provider_plan_includes_required_providers() -> None:
    # TEST-002: provider plan includes SportDB, Highlightly, API-Football, football-data.org, ESPN baseline.
    plans = build_provider_plans()
    keys = {p.provider_key for p in plans}
    assert "sportdb" in keys
    assert "highlightly" in keys
    assert "api-football" in keys
    assert "football-data-org" in keys
    assert "espn-baseline" in keys


def test_sportdb_rps_limit() -> None:
    # TEST-003: SportDB max_rps <= 2.5.
    plans = build_provider_plans()
    sportdb_plan = next(p for p in plans if p.provider_key == "sportdb")
    assert sportdb_plan.max_rps is not None
    assert sportdb_plan.max_rps <= 2.5


def test_provider_request_budget_limits() -> None:
    # TEST-004: no provider request budget exceeds 10 per fixture.
    plans = build_provider_plans()
    for p in plans:
        assert p.max_requests_per_fixture <= 10
        assert p.max_requests_per_fixture > 0
        assert p.provider_key is not None
