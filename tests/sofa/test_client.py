import json
import time
from typing import Any

import pytest
from curl_cffi.requests.errors import RequestsError

from bet.sofa.client import SofascoreClient, TransportResponse
from bet.sofa.config import SofaConfig
from bet.sofa.stage import stage
from bet.sofa.errors import CircuitOpenError, ProviderError


class MockResponse:
    def __init__(
        self, status_code: int, json_data: Any = None, is_html: bool = False
    ) -> None:
        self._status_code = status_code
        self._json_data = json_data
        self._is_html = is_html

    @property
    def status_code(self) -> int:
        return self._status_code

    @property
    def text(self) -> str:
        return "<html></html>" if self._is_html else "{}"

    def json(self) -> Any:
        if self._is_html:
            raise ValueError("Invalid JSON")
        return self._json_data


class MockTransport:
    def __init__(self) -> None:
        self.responses: list[Any] = []
        self.calls = 0

    def get(self, url: str, timeout: float = 10.0) -> TransportResponse:
        self.calls += 1
        if not self.responses:
            return MockResponse(200, {})
        resp = self.responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp  # type: ignore


@pytest.fixture
def config(tmp_path: Any) -> SofaConfig:
    return SofaConfig(
        db_path=str(tmp_path / "sofa.db"),
        runs_dir=str(tmp_path / "runs"),
        target_rps=100,  # fast for normal tests
        breaker_threshold=3,
    )


def test_client_200_json(config: SofaConfig) -> None:
    transport = MockTransport()
    transport.responses = [MockResponse(200, {"data": "ok"})]
    client = SofascoreClient(config, transport)

    assert client.search("test") == {"data": "ok"}
    assert client.breaker.failures == 0


def test_client_404(config: SofaConfig) -> None:
    transport = MockTransport()
    transport.responses = [MockResponse(404)]
    client = SofascoreClient(config, transport)

    assert client.search("test") is None
    assert client.breaker.failures == 0


@pytest.mark.parametrize("status", [403, 429, 500, 502])
def test_client_error_statuses(config: SofaConfig, status: int) -> None:
    transport = MockTransport()
    transport.responses = [MockResponse(status)]
    client = SofascoreClient(config, transport)

    with pytest.raises(ProviderError, match=f"HTTP {status}"):
        client.search("test")
    assert client.breaker.failures == 1


def test_client_html_fallback(config: SofaConfig) -> None:
    transport = MockTransport()
    transport.responses = [MockResponse(200, is_html=True)]
    client = SofascoreClient(config, transport)

    with pytest.raises(ProviderError, match="HTML instead of JSON"):
        client.search("test")
    assert client.breaker.failures == 1


def test_client_timeout_retry(config: SofaConfig) -> None:
    transport = MockTransport()
    transport.responses = [RequestsError("timeout"), MockResponse(200, {"ok": 1})]
    client = SofascoreClient(config, transport)

    assert client.search("test") == {"ok": 1}
    assert transport.calls == 2
    assert client.breaker.failures == 0


def test_client_timeout_failure(config: SofaConfig, monkeypatch: Any) -> None:
    # speed up test by removing sleep
    monkeypatch.setattr(time, "sleep", lambda x: None)

    transport = MockTransport()
    transport.responses = [RequestsError("timeout"), RequestsError("timeout")]
    client = SofascoreClient(config, transport)

    with pytest.raises(ProviderError, match="Network error after retry"):
        client.search("test")
    assert transport.calls == 2
    assert client.breaker.failures == 1


def test_breaker_opens_and_blocks(config: SofaConfig) -> None:
    transport = MockTransport()
    # 3 failures -> threshold reached
    transport.responses = [
        MockResponse(500),
        MockResponse(500),
        MockResponse(500),
        MockResponse(200),
    ]
    client = SofascoreClient(config, transport)

    for _ in range(3):
        with pytest.raises(ProviderError):
            client.search("test")

    assert client.breaker.is_open
    assert transport.calls == 3

    # 4th call does not reach transport
    with pytest.raises(CircuitOpenError):
        client.search("test")

    assert transport.calls == 3


def test_404_resets_breaker(config: SofaConfig) -> None:
    transport = MockTransport()
    # 2 failures, then 404
    transport.responses = [MockResponse(500), MockResponse(500), MockResponse(404)]
    client = SofascoreClient(config, transport)

    with pytest.raises(ProviderError):
        client.search("test")
    with pytest.raises(ProviderError):
        client.search("test")

    assert client.breaker.failures == 2

    assert client.search("test") is None
    assert client.breaker.failures == 0
    assert not client.breaker.is_open


def test_rate_limit_pacing(config: SofaConfig, monkeypatch: Any) -> None:
    config = SofaConfig(
        db_path=config.db_path,
        runs_dir=config.runs_dir,
        target_rps=10,
        breaker_threshold=3,
    )
    transport = MockTransport()
    client = SofascoreClient(config, transport)

    # Fake time
    current_time = [0.0]

    def fake_monotonic() -> float:
        return current_time[0]

    def fake_sleep(t: float) -> None:
        current_time[0] += t

    monkeypatch.setattr(time, "monotonic", fake_monotonic)
    monkeypatch.setattr(time, "sleep", fake_sleep)

    # Must explicitly reset last_update since we hijacked time after client init
    client.bucket.last_update = 0.0

    start = fake_monotonic()
    for _ in range(30):
        client.search("test")
    end = fake_monotonic()

    assert transport.calls == 30
    assert end - start >= 2.9


def test_log_format(config: SofaConfig, monkeypatch: Any) -> None:
    dt = __import__("datetime")

    def mock_now() -> Any:
        return dt.datetime(2026, 9, 17, 12, 0, tzinfo=dt.UTC)

    monkeypatch.setattr("bet.sofa.client.now", mock_now)

    transport = MockTransport()
    transport.responses = [MockResponse(200, {"ok": 1})]
    client = SofascoreClient(config, transport)

    # The stage is the caller's, not the method's (F22): search() is used
    # by RESOLVE and by SAMPLES both.
    with stage("RESOLVE"):
        client.search("test")

    log_file = client.log_path
    assert log_file.exists()

    with open(log_file) as f:
        line = f.readline()

    row = json.loads(line)
    assert row["ts_utc"] == "2026-09-17T12:00:00Z"
    assert row["stage"] == "RESOLVE"
    assert row["method"] == "GET"
    assert row["url"] == "https://api.sofascore.com/api/v1/search/all?q=test"
    assert row["status"] == 200
    assert isinstance(row["elapsed_ms"], int)
    assert row["cache_hit"] is False
    assert row["breaker_state"] == "CLOSED"
