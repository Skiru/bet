from datetime import UTC, datetime
from typing import Any

import pytest

from bet.sofa.cache import SofaCache
from bet.sofa.client import SofascoreClient, TransportResponse
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import Fixture
from bet.sofa.errors import CircuitOpenError, ProviderError
from bet.sofa.samples import process_fixture_samples


class MockResponse:
    def __init__(self, status_code: int, json_data: Any = None, is_html: bool = False):
        self._status_code = status_code
        self._json_data = json_data
        self._is_html = is_html

    @property
    def status_code(self) -> int:
        return self._status_code

    def json(self) -> Any:
        if self._is_html:
            raise ValueError("Invalid JSON")
        return self._json_data

    @property
    def text(self) -> str:
        return "<html></html>" if self._is_html else "{}"


class Always403Transport:
    def get(self, url: str, timeout: float = 10.0) -> TransportResponse:
        return MockResponse(403)


class AlwaysHtmlTransport:
    def get(self, url: str, timeout: float = 10.0) -> TransportResponse:
        return MockResponse(200, is_html=True)


class Always404Transport:
    def get(self, url: str, timeout: float = 10.0) -> TransportResponse:
        return MockResponse(404)


@pytest.fixture
def config(tmp_path: Any) -> SofaConfig:
    return SofaConfig(
        db_path=str(tmp_path / "sofa.db"),
        runs_dir=str(tmp_path / "runs"),
        target_rps=100,
        breaker_threshold=2,
    )


def test_degraded_403(config: SofaConfig) -> None:
    client = SofascoreClient(config, Always403Transport())
    with pytest.raises(ProviderError, match="HTTP 403"):
        client.event(123)
    with pytest.raises(ProviderError, match="HTTP 403"):
        client.event(456)
    with pytest.raises(CircuitOpenError):
        client.event(789)
    # The pipeline script would catch this and fail without writing sheet artifacts


def test_degraded_html(config: SofaConfig) -> None:
    client = SofascoreClient(config, AlwaysHtmlTransport())
    with pytest.raises(ProviderError, match="HTML instead of JSON"):
        client.event(123)
    with pytest.raises(ProviderError, match="HTML instead of JSON"):
        client.event(456)
    with pytest.raises(CircuitOpenError):
        client.event(789)


def test_degraded_empty_statistics(config: SofaConfig) -> None:
    # 404 for statistics shouldn't throw error but return BLOCKED in readiness
    from bet.sofa.db import migrate

    migrate(config.db_path)
    client = SofascoreClient(config, Always404Transport())
    cache = SofaCache(config)

    fixtures = [
        Fixture(
            sofascore_event_id=123,
            superbet_event_ids=["sb_1"],
            sport="football",
            kickoff_utc=datetime(2026, 9, 17, 20, 0, tzinfo=UTC),
            home_name="A",
            away_name="B",
            home_entity_id=1,
            away_entity_id=2,
            competition_name="Liga",
            competition_id=10,
            season_id=20,
            category_name="Country",
            identity="CONFIRMED",
            round_number=1,
            round_name="1",
            cup_round_type=None,
            previous_leg_event_id=None,
            venue_name=None,
            referee=None,
            ground_type=None,
            default_period_count=None,
        )
    ]

    class FakeSBClient:
        def event_odds(self, s_id):
            return {
                "data": [{"markets": [{"marketId": 12, "marketName": "Suma goli"}]}]
            }

    samples = [
        process_fixture_samples(fixtures[0], client, cache, FakeSBClient(), config)
    ]
    assert len(samples) == 1
    assert samples[0].readiness == "BLOCKED"
    for metric, sample in samples[0].metrics.items():
        assert len(sample.side_a) == 0
        assert len(sample.side_b) == 0


# --------------------------------------------------------------------------
# One bad fixture must not take the slate down with it.
# --------------------------------------------------------------------------

def test_a_provider_error_blocks_one_fixture_not_the_whole_day(tmp_path):
    """The breaker stops a dead provider; a single error is not that.

    If the exception escapes, the operator gets no 03_samples.json at all —
    strictly worse than an artifact naming the fixture that failed.
    """
    from unittest.mock import MagicMock

    from bet.sofa.cache import SofaCache
    from bet.sofa.config import SofaConfig
    from bet.sofa.contracts import Fixture, GapReason
    from bet.sofa.db import migrate
    from bet.sofa.errors import CircuitOpenError, ProviderError
    from bet.sofa.samples import process_fixture_samples

    db_path = str(tmp_path / "t.db")
    migrate(db_path)
    config = SofaConfig(db_path=db_path)
    cache = SofaCache(config)

    fixture = Fixture(
        sofascore_event_id=1,
        superbet_event_ids=["sb1"],
        sport="football",
        kickoff_utc=datetime(2026, 9, 17, 18, 0, tzinfo=UTC),
        home_name="A",
        away_name="B",
        home_entity_id=10,
        away_entity_id=20,
        competition_name="L",
        competition_id=1,
        season_id=1,
        category_name="C",
        identity="CONFIRMED",
        round_number=1,
        round_name=None,
        cup_round_type=None,
        previous_leg_event_id=None,
        venue_name=None,
        referee=None,
        ground_type=None,
        default_period_count=None,
    )

    superbet = MagicMock()
    superbet.event_odds.return_value = {"odds": [{"marketName": "Liczba goli"}]}

    for error, expected in (
        (ProviderError("HTTP 403"), GapReason.PROVIDER_ERROR),
        (CircuitOpenError("open"), GapReason.CIRCUIT_OPEN),
    ):
        client = MagicMock()
        client.entity_events.side_effect = error
        result = process_fixture_samples(fixture, client, cache, superbet, config)
        assert result.readiness == "BLOCKED"
        assert result.metrics == {}
        assert [g.reason for g in result.gaps] == [expected]
