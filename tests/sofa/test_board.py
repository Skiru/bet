import json
from datetime import UTC, datetime
from typing import Any

import pytest

from bet.sofa.board import fetch_board
from bet.sofa.superbet import SuperbetClient


class MockSession:
    def __init__(self, data: list[dict[str, Any]]):
        self._data = data
        self.headers = {}

    def get(self, url: str, params: dict[str, Any] | None = None, **kwargs) -> Any:
        class MockResponse:
            def __init__(self, data):
                self.data = data
                self.status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return self.data

        return MockResponse(self._data)


@pytest.fixture
def mock_superbet_events_by_date(monkeypatch, tmp_path):
    with open("tests/fixtures/sofascore/superbet_events_by_date.json") as f:
        data = json.load(f)

    def mock_init(self, *args, **kwargs):
        self.base_url = "http://mock"
        self.session = MockSession(data)
        import threading

        self.log_path = tmp_path / "run.log.jsonl"
        self._log_lock = threading.Lock()

    monkeypatch.setattr(SuperbetClient, "__init__", mock_init)


def test_fetch_board_filters_correctly(mock_superbet_events_by_date):
    fixtures = fetch_board("2026-09-17")

    # 10001 (football), 10002 (tennis, aware +00:00).
    # 10003 (sport 75 - filtered out)
    # 10004 (doubles in tennis - filtered out because it has /)
    # 10005 (wrong separator, side_b is empty - filtered out)
    # 10006 (out of date - filtered out)

    assert len(fixtures) == 2

    assert fixtures[0].superbet_event_id == "10001"
    assert fixtures[0].sport == "football"
    assert fixtures[0].side_a == "Arsenal"
    assert fixtures[0].side_b == "Chelsea"
    assert fixtures[0].kickoff_utc == datetime(2026, 9, 17, 15, 0, tzinfo=UTC)

    assert fixtures[1].superbet_event_id == "10002"
    assert fixtures[1].sport == "tennis"
    assert fixtures[1].side_a == "Iga Swiatek"
    assert fixtures[1].side_b == "Aryna Sabalenka"
    assert fixtures[1].kickoff_utc == datetime(2026, 9, 17, 16, 0, tzinfo=UTC)


def test_fetch_board_aware_local_time(monkeypatch, tmp_path):
    # Test for local time not in UTC
    data = [
        {
            "eventId": 10007,
            "matchName": "Local·Time",
            "utcDate": "2026-09-17T17:00:00+02:00",
            "sportId": 5,
            "marketCount": 10,
        }
    ]

    def mock_init(self, *args, **kwargs):
        self.base_url = "http://mock"
        self.session = MockSession(data)
        import threading

        self.log_path = tmp_path / "run.log.jsonl"
        self._log_lock = threading.Lock()

    monkeypatch.setattr(SuperbetClient, "__init__", mock_init)

    fixtures = fetch_board("2026-09-17")

    assert len(fixtures) == 1
    # 17:00 +02:00 is 15:00 UTC
    assert fixtures[0].kickoff_utc == datetime(2026, 9, 17, 15, 0, tzinfo=UTC)
