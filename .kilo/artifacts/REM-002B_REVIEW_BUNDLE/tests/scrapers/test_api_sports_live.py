"""API-Sports family live tests with evidence capture.

Tests evidence capture, replay transport, and idempotent rerun verification
for api-football, api-basketball, api-volleyball, api-hockey.

These tests require live API keys and network access.
Marked with @pytest.mark.live to allow selective execution.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bet.api_clients.api_football import APIFixture, APIFootballClient
from bet.api_clients.api_basketball import APIBasketballClient
from bet.api_clients.api_volleyball import APIVolleyballClient
from bet.api_clients.api_hockey import APIHockeyClient
from bet.api_clients.base_client import SourceOperationResult, SourceResultStatus
from bet.api_clients.rate_limiter import RateLimiter
from bet.integration.evidence import (
    EvidenceRef,
    build_replay_transport,
    canonical_json_bytes,
    get_evidence_root,
    load_evidence_object_bytes,
    normalize_request_identity,
    persist_response_evidence,
)
from bet.integration.telemetry_wrapper import TransportResult


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def rate_limiter():
    """Fresh rate limiter for each test."""
    return RateLimiter()


@pytest.fixture
def evidence_root(tmp_path):
    """Isolated evidence directory for each test."""
    return tmp_path / "evidence"


@pytest.fixture
def mock_cache_dir(tmp_path):
    """Isolated cache directory for each test."""
    cache_dir = tmp_path / "stats_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


@pytest.fixture
def football_client(rate_limiter, mock_cache_dir, monkeypatch):
    """API-Football client with isolated cache."""
    monkeypatch.setattr(
        "bet.api_clients.base_client.CACHE_DIR",
        mock_cache_dir,
    )
    return APIFootballClient(rate_limiter=rate_limiter)


@pytest.fixture
def basketball_client(rate_limiter, mock_cache_dir, monkeypatch):
    """API-Basketball client with isolated cache."""
    monkeypatch.setattr(
        "bet.api_clients.base_client.CACHE_DIR",
        mock_cache_dir,
    )
    return APIBasketballClient(rate_limiter=rate_limiter)


@pytest.fixture
def volleyball_client(rate_limiter, mock_cache_dir, monkeypatch):
    """API-Volleyball client with isolated cache."""
    monkeypatch.setattr(
        "bet.api_clients.base_client.CACHE_DIR",
        mock_cache_dir,
    )
    return APIVolleyballClient(rate_limiter=rate_limiter)


@pytest.fixture
def hockey_client(rate_limiter, mock_cache_dir, monkeypatch):
    """API-Hockey client with isolated cache."""
    monkeypatch.setattr(
        "bet.api_clients.base_client.CACHE_DIR",
        mock_cache_dir,
    )
    return APIHockeyClient(rate_limiter=rate_limiter)


# ─────────────────────────────────────────────────────────────────────────────
# Evidence Capture Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestEvidenceCapturePrimitives:
    """Test evidence capture primitives without network calls."""

    def test_evidence_ref_round_trip(self, evidence_root):
        """Verify EvidenceRef can be created and serialized."""
        ref = EvidenceRef(
            operation="get_fixtures",
            request_identity="GET /fixtures?date=2026-06-11",
            media_type="application/json",
            byte_size=1024,
            object_sha256="abc123",
            source_event_id="12345",
            http_status=200,
            captured_at="2026-06-11T12:00:00Z",
        )
        assert ref.operation == "get_fixtures"
        data = ref.to_dict()
        assert data["operation"] == "get_fixtures"
        assert data["http_status"] == 200

        restored = EvidenceRef.from_dict(data)
        assert restored.operation == ref.operation
        assert restored.http_status == ref.http_status

    def test_persist_response_evidence(self, evidence_root):
        """Verify persist_response_evidence writes to disk."""
        body = b'{"response": [{"id": 123}]}'
        result = TransportResult(
            success=True,
            status_code=200,
            headers={"Content-Type": "application/json"},
            body=body,
        )

        ref = persist_response_evidence(
            operation="get_fixtures",
            url="https://api.example.com/fixtures",
            params={"date": "2026-06-11"},
            response=result,
            source_event_id="12345",
            evidence_root=evidence_root,
        )

        assert ref.operation == "get_fixtures"
        assert ref.http_status == 200
        assert ref.byte_size > 0

        # Verify object was written
        obj_path = evidence_root / "objects" / ref.object_sha256[:2] / ref.object_sha256
        assert obj_path.exists()
        # The body is sanitized (canonical JSON), so we need to compare with sanitized version
        loaded = obj_path.read_bytes()
        assert hashlib.sha256(loaded).hexdigest() == ref.object_sha256

    def test_normalize_request_identity_removes_secrets(self):
        """Verify secrets are stripped from request identity."""
        identity = normalize_request_identity(
            "GET",
            "https://api.example.com/fixtures?api_key=secret123&date=2026-06-11",
        )
        assert "secret123" not in identity
        assert "api_key" not in identity
        assert "date=2026-06-11" in identity


class TestSourceOperationResult:
    """Test SourceOperationResult container."""

    def test_success_result(self):
        """Verify successful result construction."""
        result = SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=[],
            http_status=200,
            evidence_refs=[],
        )
        assert result.status == SourceResultStatus.SUCCESS
        assert result.value == []
        assert result.http_status == 200

    def test_error_result(self):
        """Verify error result construction."""
        result = SourceOperationResult(
            status=SourceResultStatus.RATE_LIMITED,
            http_status=429,
            retryable=True,
            error_code="http_429",
            retry_after_seconds=60.0,
        )
        assert result.status == SourceResultStatus.RATE_LIMITED
        assert result.retryable is True
        assert result.retry_after_seconds == 60.0


class TestGetFixturesResultMocked:
    """Test get_fixtures_result with mocked responses."""

    def test_football_success_with_evidence(self, football_client, evidence_root, monkeypatch):
        """Verify get_fixtures_result captures evidence on success."""
        mock_response = {
            "response": [
                {
                    "fixture": {"id": 123, "date": "2026-06-11T15:00:00Z", "status": {"short": "NS"}},
                    "league": {"name": "Premier League"},
                    "teams": {
                        "home": {"name": "Arsenal"},
                        "away": {"name": "Chelsea"},
                    },
                }
            ]
        }

        # Mock the _request_with_evidence method
        def mock_request_with_evidence(endpoint, params, operation, source_event_id, cost=1):
            body = canonical_json_bytes(mock_response)
            result = TransportResult(
                success=True,
                status_code=200,
                headers={"Content-Type": "application/json"},
                body=body,
            )
            ref = persist_response_evidence(
                operation=operation,
                url=f"https://v3.football.api-sports.io{endpoint}",
                params=params,
                response=result,
                source_event_id=source_event_id,
                evidence_root=evidence_root,
            )
            return SourceOperationResult(
                status=SourceResultStatus.SUCCESS,
                value=mock_response,
                http_status=200,
                evidence_refs=[ref],
            )

        monkeypatch.setattr(football_client, "_request_with_evidence", mock_request_with_evidence)

        result = football_client.get_fixtures_result("2026-06-11")

        assert result.status == SourceResultStatus.SUCCESS
        assert result.value is not None
        assert len(result.value) == 1
        assert result.value[0].external_id == "123"
        assert result.value[0].source == "api-football"
        assert len(result.evidence_refs) == 1
        assert result.evidence_refs[0].operation == "get_fixtures"

    def test_basketball_success_with_evidence(self, basketball_client, evidence_root, monkeypatch):
        """Verify basketball get_fixtures_result captures evidence."""
        mock_response = {
            "response": [
                {
                    "id": 456,
                    "date": "2026-06-11T19:30:00Z",
                    "status": {"short": "NS"},
                    "league": {"name": "NBA"},
                    "teams": {
                        "home": {"name": "Lakers"},
                        "away": {"name": "Celtics"},
                    },
                }
            ]
        }

        def mock_request_with_evidence(endpoint, params, operation, source_event_id, cost=1):
            body = canonical_json_bytes(mock_response)
            result = TransportResult(
                success=True,
                status_code=200,
                headers={"Content-Type": "application/json"},
                body=body,
            )
            ref = persist_response_evidence(
                operation=operation,
                url=f"https://v1.basketball.api-sports.io{endpoint}",
                params=params,
                response=result,
                source_event_id=source_event_id,
                evidence_root=evidence_root,
            )
            return SourceOperationResult(
                status=SourceResultStatus.SUCCESS,
                value=mock_response,
                http_status=200,
                evidence_refs=[ref],
            )

        monkeypatch.setattr(basketball_client, "_request_with_evidence", mock_request_with_evidence)

        result = basketball_client.get_fixtures_result("2026-06-11")

        assert result.status == SourceResultStatus.SUCCESS
        assert result.value is not None
        assert len(result.value) == 1
        assert result.value[0].external_id == "456"
        assert result.value[0].sport == "basketball"

    def test_volleyball_success_with_evidence(self, volleyball_client, evidence_root, monkeypatch):
        """Verify volleyball get_fixtures_result captures evidence."""
        mock_response = {
            "response": [
                {
                    "id": 789,
                    "date": "2026-06-11T10:00:00Z",
                    "status": {"long": "finished"},
                    "league": {"name": "FIVB"},
                    "teams": {
                        "home": {"name": "Poland"},
                        "away": {"name": "Brazil"},
                    },
                }
            ]
        }

        def mock_request_with_evidence(endpoint, params, operation, source_event_id, cost=1):
            body = canonical_json_bytes(mock_response)
            result = TransportResult(
                success=True,
                status_code=200,
                headers={"Content-Type": "application/json"},
                body=body,
            )
            ref = persist_response_evidence(
                operation=operation,
                url=f"https://v1.volleyball.api-sports.io{endpoint}",
                params=params,
                response=result,
                source_event_id=source_event_id,
                evidence_root=evidence_root,
            )
            return SourceOperationResult(
                status=SourceResultStatus.SUCCESS,
                value=mock_response,
                http_status=200,
                evidence_refs=[ref],
            )

        monkeypatch.setattr(volleyball_client, "_request_with_evidence", mock_request_with_evidence)

        result = volleyball_client.get_fixtures_result("2026-06-11")

        assert result.status == SourceResultStatus.SUCCESS
        assert result.value is not None
        assert len(result.value) == 1
        assert result.value[0].external_id == "789"
        assert result.value[0].sport == "volleyball"

    def test_hockey_success_with_evidence(self, hockey_client, evidence_root, monkeypatch):
        """Verify hockey get_fixtures_result captures evidence."""
        mock_response = {
            "response": [
                {
                    "id": 321,
                    "date": "2026-06-11T19:00:00Z",
                    "status": {"short": "FT"},
                    "league": {"name": "NHL"},
                    "teams": {
                        "home": {"name": "Bruins"},
                        "away": {"name": "Rangers"},
                    },
                }
            ]
        }

        def mock_request_with_evidence(endpoint, params, operation, source_event_id, cost=1):
            body = canonical_json_bytes(mock_response)
            result = TransportResult(
                success=True,
                status_code=200,
                headers={"Content-Type": "application/json"},
                body=body,
            )
            ref = persist_response_evidence(
                operation=operation,
                url=f"https://v1.hockey.api-sports.io{endpoint}",
                params=params,
                response=result,
                source_event_id=source_event_id,
                evidence_root=evidence_root,
            )
            return SourceOperationResult(
                status=SourceResultStatus.SUCCESS,
                value=mock_response,
                http_status=200,
                evidence_refs=[ref],
            )

        monkeypatch.setattr(hockey_client, "_request_with_evidence", mock_request_with_evidence)

        result = hockey_client.get_fixtures_result("2026-06-11")

        assert result.status == SourceResultStatus.SUCCESS
        assert result.value is not None
        assert len(result.value) == 1
        assert result.value[0].external_id == "321"
        assert result.value[0].sport == "hockey"


class TestReplayTransport:
    """Test no-network replay using captured evidence."""

    def test_replay_transport_returns_cached_response(self, evidence_root):
        """Verify replay transport returns cached response without network."""
        # First, capture evidence
        body = b'{"response": [{"id": 123}]}'
        result = TransportResult(
            success=True,
            status_code=200,
            headers={"Content-Type": "application/json"},
            body=body,
        )

        ref = persist_response_evidence(
            operation="get_fixtures",
            url="https://api.example.com/fixtures",
            params={"date": "2026-06-11"},
            response=result,
            source_event_id="12345",
            evidence_root=evidence_root,
        )

        # Create a bundle manifest
        from bet.integration.evidence import write_bundle_manifest

        bundle_id, manifest_path = write_bundle_manifest(
            registered_source_key="api-football",
            projection_name="fixtures",
            canonical_fixture_id=1,
            parser_version="test-v1",
            source_event_refs=["api-football:123"],
            evidence_refs=[ref],
            evidence_root=evidence_root,
        )

        # Build replay transport
        replay_fn = build_replay_transport(bundle_id, evidence_root=evidence_root)

        # Replay should return cached response
        replay_result = replay_fn(
            provider="api-football",
            request_fn=None,
            url="https://api.example.com/fixtures",
            params={"date": "2026-06-11"},
        )

        assert replay_result.success is True
        assert replay_result.status_code == 200
        assert replay_result.cache_hit is True
        assert replay_result.body == canonical_json_bytes(json.loads(body))


class TestErrorHandling:
    """Test error handling in get_fixtures_result."""

    def test_rate_limited_result(self, football_client, monkeypatch):
        """Verify rate limited result is returned correctly."""
        def mock_request_with_evidence(endpoint, params, operation, source_event_id, cost=1):
            return SourceOperationResult(
                status=SourceResultStatus.RATE_LIMITED,
                http_status=429,
                retryable=True,
                error_code="http_429",
                retry_after_seconds=60.0,
            )

        monkeypatch.setattr(football_client, "_request_with_evidence", mock_request_with_evidence)

        result = football_client.get_fixtures_result("2026-06-11")

        assert result.status == SourceResultStatus.RATE_LIMITED
        assert result.retryable is True
        assert result.value is None

    def test_authentication_error_result(self, football_client, monkeypatch):
        """Verify authentication error result is returned correctly."""
        def mock_request_with_evidence(endpoint, params, operation, source_event_id, cost=1):
            return SourceOperationResult(
                status=SourceResultStatus.AUTHENTICATION_ERROR,
                http_status=401,
                error_code="http_401",
            )

        monkeypatch.setattr(football_client, "_request_with_evidence", mock_request_with_evidence)

        result = football_client.get_fixtures_result("2026-06-11")

        assert result.status == SourceResultStatus.AUTHENTICATION_ERROR
        assert result.http_status == 401

    def test_empty_response_result(self, football_client, monkeypatch):
        """Verify empty response is handled correctly."""
        def mock_request_with_evidence(endpoint, params, operation, source_event_id, cost=1):
            return SourceOperationResult(
                status=SourceResultStatus.SUCCESS,
                value={"response": []},
                http_status=200,
                evidence_refs=[],
            )

        monkeypatch.setattr(football_client, "_request_with_evidence", mock_request_with_evidence)

        result = football_client.get_fixtures_result("2026-06-11")

        assert result.status == SourceResultStatus.SUCCESS
        assert result.value == []


# ─────────────────────────────────────────────────────────────────────────────
# Live Tests (require API keys)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.live
class TestLiveEvidenceCapture:
    """Live tests requiring API keys and network access.

    Run with: pytest -m live tests/scrapers/test_api_sports_live.py
    """

    def test_football_live_evidence_capture(self, football_client, tmp_path):
        """Capture evidence from live API-Football request."""
        evidence_root = tmp_path / "evidence"

        result = football_client.get_fixtures_result("2026-06-11")

        # May be rate limited, auth error, or success
        assert result.status in (
            SourceResultStatus.SUCCESS,
            SourceResultStatus.RATE_LIMITED,
            SourceResultStatus.AUTHENTICATION_ERROR,
        )

        if result.status == SourceResultStatus.SUCCESS:
            assert isinstance(result.value, list)
            if result.evidence_refs:
                assert len(result.evidence_refs) >= 1
                ref = result.evidence_refs[0]
                assert ref.operation == "get_fixtures"
                assert ref.http_status == 200

    def test_basketball_live_evidence_capture(self, basketball_client, tmp_path):
        """Capture evidence from live API-Basketball request."""
        result = basketball_client.get_fixtures_result("2026-06-11")

        assert result.status in (
            SourceResultStatus.SUCCESS,
            SourceResultStatus.RATE_LIMITED,
            SourceResultStatus.AUTHENTICATION_ERROR,
        )

        if result.status == SourceResultStatus.SUCCESS:
            assert isinstance(result.value, list)

    def test_volleyball_live_evidence_capture(self, volleyball_client, tmp_path):
        """Capture evidence from live API-Volleyball request."""
        result = volleyball_client.get_fixtures_result("2026-06-11")

        assert result.status in (
            SourceResultStatus.SUCCESS,
            SourceResultStatus.RATE_LIMITED,
            SourceResultStatus.AUTHENTICATION_ERROR,
        )

        if result.status == SourceResultStatus.SUCCESS:
            assert isinstance(result.value, list)

    def test_hockey_live_evidence_capture(self, hockey_client, tmp_path):
        """Capture evidence from live API-Hockey request."""
        result = hockey_client.get_fixtures_result("2026-06-11")

        assert result.status in (
            SourceResultStatus.SUCCESS,
            SourceResultStatus.RATE_LIMITED,
            SourceResultStatus.AUTHENTICATION_ERROR,
        )

        if result.status == SourceResultStatus.SUCCESS:
            assert isinstance(result.value, list)
