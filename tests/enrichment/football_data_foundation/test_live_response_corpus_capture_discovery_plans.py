from bet.enrichment.football_data_foundation.live_response_corpus_capture.provider_plans import (
    build_provider_discovery_plans,
)


def test_football_data_org_discovery_plan_format():
    """
    REQ-TEST-001 football-data.org discovery plan uses dateFrom/dateTo and X-Auth-Token.
    """
    fixture = {
        "fixture_slug": "worldcup2026-norway-senegal",
        "home_team": "Norway",
        "away_team": "Senegal",
        "kickoff_at": "2026-06-23T18:00:00Z",
    }
    plans = build_provider_discovery_plans(fixture)
    fdo_plan = next(p for p in plans if p.provider == "football-data-org")

    assert "dateFrom=2026-06-23" in fdo_plan.url
    assert "dateTo=2026-06-23" in fdo_plan.url
    assert fdo_plan.auth_header_name == "X-Auth-Token"
    assert fdo_plan.credential_env == "FOOTBALL_DATA_ORG_KEY"


def test_api_football_discovery_plan_format():
    """
    REQ-TEST-002 API-Football discovery plan uses fixtures?date= and x-apisports-key.
    """
    fixture = {
        "fixture_slug": "worldcup2026-norway-senegal",
        "home_team": "Norway",
        "away_team": "Senegal",
        "kickoff_at": "2026-06-23T18:00:00Z",
    }
    plans = build_provider_discovery_plans(fixture)
    af_plan = next(p for p in plans if p.provider == "api-football")

    assert "fixtures?date=2026-06-23" in af_plan.url
    assert af_plan.auth_header_name == "x-apisports-key"
    assert af_plan.credential_env == "API_FOOTBALL_KEY"
