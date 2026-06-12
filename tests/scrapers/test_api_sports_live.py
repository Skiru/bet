"""API-Sports live certification tests requiring explicit opt-in."""

import os

import pytest

from bet.api_clients.api_basketball import APIBasketballClient
from bet.api_clients.api_football import APIFootballClient
from bet.api_clients.api_hockey import APIHockeyClient
from bet.api_clients.api_volleyball import APIVolleyballClient
from bet.api_clients.base_client import SourceResultStatus
from bet.api_clients.rate_limiter import RateLimiter
from bet.integration.evidence import get_evidence_root

LIVE_OPT_IN = os.getenv("BET_RUN_LIVE_API_SPORTS", "").strip() == "1"
pytestmark = [
    pytest.mark.api_sports_live,
    pytest.mark.skipif(
        not LIVE_OPT_IN,
        reason="set BET_RUN_LIVE_API_SPORTS=1 to run live API-Sports certification",
    ),
]


@pytest.fixture
def rate_limiter(tmp_path):
    return RateLimiter(
        usage_dir=tmp_path / "usage",
        limits={
            "api-football": 1000,
            "api-basketball": 1000,
            "api-volleyball": 1000,
            "api-hockey": 1000,
        },
    )


@pytest.fixture
def football_client(rate_limiter):
    return APIFootballClient(rate_limiter=rate_limiter)


@pytest.fixture
def basketball_client(rate_limiter):
    return APIBasketballClient(rate_limiter=rate_limiter)


@pytest.fixture
def volleyball_client(rate_limiter):
    return APIVolleyballClient(rate_limiter=rate_limiter)


@pytest.fixture
def hockey_client(rate_limiter):
    return APIHockeyClient(rate_limiter=rate_limiter)


def _assert_live_success(result, source_name: str):
    assert result.status is SourceResultStatus.SUCCESS, (
        f"{source_name} certification requires SUCCESS, "
        f"got status={result.status.value} code={result.error_code} "
        f"http={result.http_status} quota={result.quota_metadata}"
    )
    assert result.bundle_id and len(result.bundle_id) == 64
    assert result.evidence_refs
    assert result.parser_diagnostics["accepted_count"] >= 0
    for fixture in result.value:
        assert fixture.external_id
        assert fixture.home_participant_id
        assert fixture.away_participant_id
        assert fixture.home_participant_id != fixture.away_participant_id
        assert fixture.home_team_name
        assert fixture.away_team_name
        assert fixture.competition_name
        assert fixture.source == source_name


class TestLiveAPISportsCertification:
    def test_football_live_certification(self, football_client):
        result = football_client.get_fixtures_result(
            os.getenv("BET_API_FOOTBALL_LIVE_DATE", "2026-06-11")
        )
        _assert_live_success(result, "api-football")

    def test_basketball_live_certification(self, basketball_client):
        result = basketball_client.get_fixtures_result(
            os.getenv("BET_API_BASKETBALL_LIVE_DATE", "2026-06-11")
        )
        _assert_live_success(result, "api-basketball")

    def test_volleyball_live_certification(self, volleyball_client):
        result = volleyball_client.get_fixtures_result(
            os.getenv("BET_API_VOLLEYBALL_LIVE_DATE", "2026-06-11")
        )
        _assert_live_success(result, "api-volleyball")

    def test_hockey_live_certification(self, hockey_client):
        result = hockey_client.get_fixtures_result(
            os.getenv("BET_API_HOCKEY_LIVE_DATE", "2026-06-12")
        )
        _assert_live_success(result, "api-hockey")

    def test_live_evidence_root_is_durable(self):
        root = get_evidence_root()
        assert root.name == os.getenv("BET_EVIDENCE_ROOT", str(root)).split("/")[-1]
