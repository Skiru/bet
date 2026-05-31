import json
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
import requests

from bet.resilience import (
    CircuitBreaker,
    CircuitOpenError,
    RequestResult,
    atomic_json_write,
    atomic_write,
    resilient_request,
    retry,
    safe_json_load,
)


def test_retry_success_first_try():
    mock_func = MagicMock(return_value="success")
    
    @retry(max_retries=2, base_delay=0.01)
    def test_func():
        return mock_func()
        
    assert test_func() == "success"
    assert mock_func.call_count == 1


def test_retry_success_after_failure():
    mock_func = MagicMock(side_effect=[ValueError("fail"), "success"])
    
    @retry(max_retries=2, base_delay=0.01, exceptions=(ValueError,))
    def test_func():
        return mock_func()
        
    assert test_func() == "success"
    assert mock_func.call_count == 2


def test_retry_exhausted():
    mock_func = MagicMock(side_effect=ValueError("fail"))
    
    @retry(max_retries=2, base_delay=0.01, exceptions=(ValueError,))
    def test_func():
        return mock_func()
        
    with pytest.raises(ValueError, match="fail"):
        test_func()
    assert mock_func.call_count == 3


@patch("bet.resilience.requests.request")
def test_resilient_request_success(mock_request):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"key": "value"}
    mock_request.return_value = mock_response

    result = resilient_request("GET", "http://test.com")
    
    assert result.success is True
    assert result.data == {"key": "value"}
    assert result.status_code == 200
    assert result.error is None
    assert result.elapsed_ms > 0
    assert mock_request.call_count == 1


@patch("bet.resilience.requests.request")
@patch("bet.resilience.time.sleep") # Mock sleep to speed up test
def test_resilient_request_retries_on_connection_error(mock_sleep, mock_request):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"key": "success"}

    mock_request.side_effect = [
        requests.exceptions.ConnectionError("conn dropped"),
        mock_response
    ]

    result = resilient_request("GET", "http://test.com", base_delay=0.01)
    
    assert result.success is True
    assert result.data == {"key": "success"}
    assert mock_request.call_count == 2


@patch("bet.resilience.requests.request")
@patch("bet.resilience.time.sleep")
def test_resilient_request_failure(mock_sleep, mock_request):
    mock_request.side_effect = requests.exceptions.Timeout("timeout")

    result = resilient_request("GET", "http://test.com", max_retries=1, base_delay=0.01)
    
    assert result.success is False
    assert result.data is None
    assert result.status_code is None
    assert result.error == "timeout"
    assert mock_request.call_count == 2


def test_safe_json_load_valid_string():
    assert safe_json_load('{"a": 1}') == {"a": 1}


def test_safe_json_load_invalid_string():
    assert safe_json_load('{invalid', default={}) == {}


def test_safe_json_load_file():
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write('{"key": "file_value"}')
        temp_path = f.name

    try:
        assert safe_json_load(temp_path) == {"key": "file_value"}
    finally:
        import os
        os.unlink(temp_path)


def test_atomic_write():
    with tempfile.TemporaryDirectory() as tmpdir:
        target_path = Path(tmpdir) / "test_file.txt"
        atomic_write(target_path, "test content")
        
        assert target_path.exists()
        assert target_path.read_text() == "test content"


def test_atomic_json_write():
    with tempfile.TemporaryDirectory() as tmpdir:
        target_path = Path(tmpdir) / "data.json"
        data = {"hello": "world"}
        atomic_json_write(target_path, data)
        
        assert target_path.exists()
        assert json.loads(target_path.read_text()) == data


def test_circuit_breaker_transitions():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)

    # 1st failure
    try:
        with cb:
            raise ValueError("fail")
    except ValueError:
        pass
    assert cb.state == CircuitBreaker.CLOSED
    assert cb.failures == 1

    # 2nd failure triggers OPEN
    try:
        with cb:
            raise ValueError("fail")
    except ValueError:
        pass
    assert cb.state == CircuitBreaker.OPEN
    assert cb.failures == 2

    # Circuit is OPEN, calls are rejected
    with pytest.raises(CircuitOpenError):
        with cb:
            pass

    # Wait for recovery timeout
    time.sleep(0.15)

    # First call after timeout is HALF_OPEN and succeeds
    with cb:
        assert cb.state == CircuitBreaker.HALF_OPEN
        pass # success
        
    # Circuit closes after success
    assert cb.state == CircuitBreaker.CLOSED
    assert cb.failures == 0
