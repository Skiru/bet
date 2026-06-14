"""API-Sports family deterministic contract tests."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from bet.api_clients.api_basketball import APIBasketballClient
from bet.api_clients.api_football import APIFixture, APIFootballClient
from bet.api_clients.api_hockey import APIHockeyClient
from bet.api_clients.api_volleyball import APIVolleyballClient
from bet.api_clients.base_client import SourceOperationResult, SourceResultStatus
from bet.api_clients.rate_limiter import RateLimiter
from bet.db.schema import init_db
from bet.discovery.coordinator import EventDiscoveryCoordinator
from bet.discovery.dedup import DeduplicationEngine
from bet.discovery.models import DiscoveredEvent, MergedFixture, SourceRef
from bet.discovery.sources.api_basketball import APIBasketballAdapter
from bet.integration.evidence import build_replay_transport
from bet.scrapers.engine import Base


@pytest.fixture
def rate_limiter(tmp_path):
    return RateLimiter(
        usage_dir=tmp_path / "usage",
        limits={
            "api-football": 1000,
            "api-basketball": 1000,
            "api-hockey": 1000,
            "api-volleyball": 1000,
        },
    )


@pytest.fixture
def mock_cache_dir(tmp_path):
    cache_dir = tmp_path / "stats_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


@pytest.fixture
def football_client(rate_limiter, mock_cache_dir, monkeypatch):
    monkeypatch.setattr("bet.api_clients.base_client.CACHE_DIR", mock_cache_dir)
    client = APIFootballClient(rate_limiter=rate_limiter)
    client.api_key = "test-key"
    return client


@pytest.fixture
def basketball_client(rate_limiter, mock_cache_dir, monkeypatch):
    monkeypatch.setattr("bet.api_clients.base_client.CACHE_DIR", mock_cache_dir)
    client = APIBasketballClient(rate_limiter=rate_limiter)
    client.api_key = "test-key"
    return client


@pytest.fixture
def hockey_client(rate_limiter, mock_cache_dir, monkeypatch):
    monkeypatch.setattr("bet.api_clients.base_client.CACHE_DIR", mock_cache_dir)
    client = APIHockeyClient(rate_limiter=rate_limiter)
    client.api_key = "test-key"
    return client


@pytest.fixture
def volleyball_client(rate_limiter, mock_cache_dir, monkeypatch):
    monkeypatch.setattr("bet.api_clients.base_client.CACHE_DIR", mock_cache_dir)
    client = APIVolleyballClient(rate_limiter=rate_limiter)
    client.api_key = "test-key"
    return client


class TestAPISportsTransportClassification:
    def test_provider_error_payload_becomes_authentication_error(
        self, football_client, monkeypatch
    ):
        class Response:
            status_code = 200
            headers = {"Content-Type": "application/json"}
            content = (
                b'{"errors":{"requests":"Free plans do not have access to this '
                b'date"},"response":[]}'
            )

        monkeypatch.setattr(
            "bet.api_clients.base_client.requests.get",
            lambda *args, **kwargs: Response(),
        )

        result = football_client._request_with_evidence(
            endpoint="/fixtures",
            params={"date": "2026-06-11"},
            operation="get_fixtures",
            expects_response_list=True,
        )

        assert result.status is SourceResultStatus.PLAN_RESTRICTED
        assert result.error_code == "provider_plan_restricted"

    def test_missing_response_list_becomes_schema_error(
        self, football_client, monkeypatch
    ):
        class Response:
            status_code = 200
            headers = {"Content-Type": "application/json"}
            content = b'{"response":{}}'

        monkeypatch.setattr(
            "bet.api_clients.base_client.requests.get",
            lambda *args, **kwargs: Response(),
        )

        result = football_client._request_with_evidence(
            endpoint="/fixtures",
            params={"date": "2026-06-11"},
            operation="get_fixtures",
            expects_response_list=True,
        )

        assert result.status is SourceResultStatus.SCHEMA_ERROR
        assert result.error_code == "response_not_list"

    def test_evidence_failure_is_not_success(self, football_client, monkeypatch):
        class Response:
            status_code = 200
            headers = {"Content-Type": "application/json"}
            content = b'{"response":[]}'

        monkeypatch.setattr(
            "bet.api_clients.base_client.requests.get",
            lambda *args, **kwargs: Response(),
        )
        monkeypatch.setattr(
            "bet.integration.evidence.persist_response_evidence",
            lambda **kwargs: (_ for _ in ()).throw(RuntimeError("disk full")),
        )

        result = football_client._request_with_evidence(
            endpoint="/fixtures",
            params={"date": "2026-06-11"},
            operation="get_fixtures",
            expects_response_list=True,
        )

        assert result.status is SourceResultStatus.EVIDENCE_ERROR
        assert result.error_code == "evidence_persist_failed"

    def test_retry_is_bounded_to_two_total_attempts(self, football_client, monkeypatch):
        calls = {"count": 0}

        class Response:
            status_code = 200
            headers = {"Content-Type": "application/json"}
            content = b'{"response":[]}'

        def fake_get(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise ConnectionError("boom")
            return Response()

        monkeypatch.setattr("bet.api_clients.base_client.requests.get", fake_get)
        monkeypatch.setattr("time.sleep", lambda *_args, **_kwargs: None)

        result = football_client._request_with_evidence(
            endpoint="/fixtures",
            params={"date": "2026-06-11"},
            operation="get_fixtures",
            expects_response_list=True,
        )

        assert calls["count"] == 2
        assert result.status is SourceResultStatus.SUCCESS
        assert result.retry_count == 1


class TestTypedFixtureParsing:
    def test_football_populates_identity_and_bundle(
        self, football_client, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("BET_EVIDENCE_ROOT", str(tmp_path / "evidence"))

        payload = {
            "response": [
                {
                    "fixture": {
                        "id": 123,
                        "date": "2026-06-11T15:00:00+00:00",
                        "status": {"short": "NS"},
                    },
                    "league": {"id": 39, "name": "Premier League", "season": 2026},
                    "teams": {
                        "home": {"id": 1, "name": "Arsenal"},
                        "away": {"id": 2, "name": "Chelsea"},
                    },
                }
            ]
        }
        monkeypatch.setattr(
            football_client,
            "_request_with_evidence",
            lambda **kwargs: SourceOperationResult(
                status=SourceResultStatus.SUCCESS,
                value=payload,
                http_status=200,
                evidence_refs=[],
            ),
        )

        result = football_client.get_fixtures_result("2026-06-11")

        assert result.status is SourceResultStatus.SUCCESS
        assert result.parser_diagnostics == {
            "raw_count": 1,
            "accepted_count": 1,
            "rejected_count": 0,
        }
        fixture = result.value[0]
        assert fixture.external_id == "123"
        assert fixture.home_participant_id == "1"
        assert fixture.away_participant_id == "2"
        assert fixture.competition_id == "39"
        assert fixture.season_id == "2026"

    def test_invalid_rows_do_not_return_success(self, basketball_client, monkeypatch):
        payload = {
            "response": [
                {
                    "id": "",
                    "date": "",
                    "league": {"name": "NBA"},
                    "teams": {
                        "home": {"id": "", "name": "Unknown"},
                        "away": {"id": "", "name": "Unknown"},
                    },
                }
            ]
        }
        monkeypatch.setattr(
            basketball_client,
            "_request_with_evidence",
            lambda **kwargs: SourceOperationResult(
                status=SourceResultStatus.SUCCESS,
                value=payload,
                http_status=200,
                evidence_refs=[],
            ),
        )

        result = basketball_client.get_fixtures_result("2026-06-11")

        assert result.status is SourceResultStatus.SCHEMA_ERROR
        assert result.error_code == "no_valid_fixture_rows"
        assert result.parser_diagnostics["rejected_count"] == 1

    def test_no_network_replay_reuses_bundle(
        self, football_client, monkeypatch, tmp_path
    ):
        evidence_root = tmp_path / "evidence"
        monkeypatch.setenv("BET_EVIDENCE_ROOT", str(evidence_root))

        class Response:
            status_code = 200
            headers = {"Content-Type": "application/json"}
            content = (
                b'{"response":[{"fixture":{"id":123,"date":"2026-06-11T15:00:00+00:00",'
                b'"status":{"short":"NS"}},"league":{"id":39,"name":"Premier League",'
                b'"season":2026},"teams":{"home":{"id":1,"name":"Arsenal"},'
                b'"away":{"id":2,"name":"Chelsea"}}}]}'
            )

        monkeypatch.setattr(
            "bet.api_clients.base_client.requests.get",
            lambda *args, **kwargs: Response(),
        )

        live_result = football_client.get_fixtures_result("2026-06-11")

        assert live_result.status is SourceResultStatus.SUCCESS
        assert live_result.bundle_id

        replay_client = APIFootballClient(
            rate_limiter=RateLimiter(
                usage_dir=tmp_path / "replay_usage",
                limits={"api-football": 1000},
            )
        )
        replay_client.api_key = "test-key"
        monkeypatch.setattr(
            "bet.integration.telemetry_wrapper.wrap_request",
            build_replay_transport(live_result.bundle_id, evidence_root=evidence_root),
        )
        monkeypatch.setattr(
            "bet.api_clients.base_client.requests.get",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("network access blocked during replay")
            ),
        )

        replay_result = replay_client.get_fixtures_result("2026-06-11")

        assert replay_result.status is SourceResultStatus.SUCCESS
        assert [f.external_id for f in replay_result.value] == [
            f.external_id for f in live_result.value
        ]
        assert replay_result.bundle_id == live_result.bundle_id


class TestProductionWiring:
    def test_basketball_adapter_uses_typed_result(self, monkeypatch):
        adapter = APIBasketballAdapter()
        captured = {"called": False}

        def fake_get_fixtures_result(date):
            captured["called"] = True
            return SourceOperationResult(
                status=SourceResultStatus.SUCCESS,
                value=[
                    APIFixture(
                        external_id="game-1",
                        source="api-basketball",
                        sport="basketball",
                        competition_name="NBA",
                        home_team_name="Lakers",
                        away_team_name="Celtics",
                        kickoff="2026-06-11T19:30:00+00:00",
                        home_participant_id="10",
                        away_participant_id="20",
                        competition_id="12",
                        season_id="2026",
                    )
                ],
                http_status=200,
                bundle_id="b" * 64,
                parser_diagnostics={
                    "raw_count": 1,
                    "accepted_count": 1,
                    "rejected_count": 0,
                },
            )

        monkeypatch.setattr(
            adapter._client, "get_fixtures_result", fake_get_fixtures_result
        )
        monkeypatch.setattr(
            adapter._client,
            "get_fixtures",
            lambda date: (_ for _ in ()).throw(AssertionError("legacy path used")),
        )

        events = adapter.fetch_events("2026-06-11", "basketball")

        assert captured["called"] is True
        assert len(events) == 1
        assert events[0].raw_data["evidence_bundle_id"] == "b" * 64
        assert events[0].raw_data["provider_participant_ids"] == {
            "home": "10",
            "away": "20",
        }

    def test_default_sources_include_api_basketball(self):
        names = [source.name for source in EventDiscoveryCoordinator._default_sources()]
        assert "api-basketball" in names

    def test_persistence_rerun_is_duplicate_free(self, tmp_path):
        engine = create_engine(
            "sqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(engine, "connect")
        def _set_pragma(dbapi_conn, _rec):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        raw_conn = engine.raw_connection()
        try:
            raw_conn.row_factory = None
            init_db(raw_conn)
        finally:
            raw_conn.close()

        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        session = session_factory()
        coordinator = EventDiscoveryCoordinator(session=session, sources=[])

        fixture = MergedFixture(
            sport="basketball",
            competition="NBA",
            home_team="Lakers",
            away_team="Celtics",
            kickoff=datetime.fromisoformat("2026-06-11T19:30:00+00:00"),
            sources=[
                SourceRef(
                    source="api-basketball",
                    external_id="game-1",
                    raw_data={
                        "evidence_bundle_id": "b" * 64,
                        "provider_participant_ids": {"home": "10", "away": "20"},
                    },
                )
            ],
            primary_source="api-basketball",
            primary_external_id="game-1",
        )

        first = coordinator._persist("2026-06-11", [fixture])
        second = coordinator._persist("2026-06-11", [fixture])

        fixture_rows = session.execute(
            text("SELECT COUNT(*) FROM fixtures")
        ).scalar_one()
        source_rows = session.execute(
            text(
                "SELECT COUNT(*) FROM fixture_sources "
                "WHERE source = 'api-basketball' AND external_id = 'game-1'"
            )
        ).scalar_one()
        raw_data = session.execute(
            text(
                "SELECT raw_data FROM fixture_sources "
                "WHERE source = 'api-basketball' AND external_id = 'game-1'"
            )
        ).scalar_one()

        assert first == 1
        assert second == 1
        assert fixture_rows == 1
        assert source_rows == 1
        assert '"evidence_bundle_id": "' + ("b" * 64) + '"' in raw_data

        session.close()


@pytest.mark.parametrize(
    ("client_fixture", "payload", "expected_id", "expected_date"),
    [
        (
            "football_client",
            {
                "response": [
                    {
                        "fixture": {
                            "id": 10,
                            "date": "2026-06-10T12:00:00+00:00",
                            "status": {"short": "FT"},
                        },
                        "league": {"id": 39, "name": "Premier League", "season": 2026},
                        "teams": {
                            "home": {"id": 1, "name": "Arsenal"},
                            "away": {"id": 2, "name": "Chelsea"},
                        },
                    },
                    {
                        "fixture": {
                            "id": 11,
                            "date": "2026-06-12T12:00:00+00:00",
                            "status": {"short": "FT"},
                        },
                        "league": {"id": 39, "name": "Premier League", "season": 2026},
                        "teams": {
                            "home": {"id": 1, "name": "Arsenal"},
                            "away": {"id": 3, "name": "Liverpool"},
                        },
                    },
                ]
            },
            "10",
            "2026-06-10T12:00:00+00:00",
        ),
        (
            "basketball_client",
            {
                "response": [
                    {
                        "id": 20,
                        "date": "2026-06-10T19:00:00+00:00",
                        "status": {"short": "FT", "long": "Game Finished"},
                        "league": {"id": 12, "name": "NBA", "season": "2025-2026"},
                        "teams": {
                            "home": {"id": 10, "name": "Lakers"},
                            "away": {"id": 11, "name": "Celtics"},
                        },
                    },
                    {
                        "id": 21,
                        "date": "2026-06-12T19:00:00+00:00",
                        "status": {"short": "FT", "long": "Game Finished"},
                        "league": {"id": 12, "name": "NBA", "season": "2025-2026"},
                        "teams": {
                            "home": {"id": 10, "name": "Lakers"},
                            "away": {"id": 12, "name": "Bulls"},
                        },
                    },
                ]
            },
            "20",
            "2026-06-10T19:00:00+00:00",
        ),
        (
            "hockey_client",
            {
                "response": [
                    {
                        "id": 30,
                        "date": "2026-06-10T17:00:00+00:00",
                        "status": {"short": "FT"},
                        "league": {"id": 57, "name": "NHL", "season": 2026},
                        "teams": {
                            "home": {"id": 50, "name": "Rangers"},
                            "away": {"id": 51, "name": "Bruins"},
                        },
                    },
                    {
                        "id": 31,
                        "date": "2026-06-12T17:00:00+00:00",
                        "status": {"short": "FT"},
                        "league": {"id": 57, "name": "NHL", "season": 2026},
                        "teams": {
                            "home": {"id": 50, "name": "Rangers"},
                            "away": {"id": 52, "name": "Leafs"},
                        },
                    },
                ]
            },
            "30",
            "2026-06-10T17:00:00+00:00",
        ),
        (
            "volleyball_client",
            {
                "response": [
                    {
                        "id": 40,
                        "date": "2026-06-10T18:00:00+00:00",
                        "status": {"short": "FT", "long": "Match Finished"},
                        "league": {"id": 88, "name": "PlusLiga", "season": 2026},
                        "teams": {
                            "home": {"id": 70, "name": "ZAKSA"},
                            "away": {"id": 71, "name": "Jastrzebski"},
                        },
                    },
                    {
                        "id": 41,
                        "date": "2026-06-12T18:00:00+00:00",
                        "status": {"short": "FT", "long": "Match Finished"},
                        "league": {"id": 88, "name": "PlusLiga", "season": 2026},
                        "teams": {
                            "home": {"id": 70, "name": "ZAKSA"},
                            "away": {"id": 72, "name": "Resovia"},
                        },
                    },
                ]
            },
            "40",
            "2026-06-10T18:00:00+00:00",
        ),
    ],
)
def test_team_last_fixtures_result_applies_cutoff(
    request, monkeypatch, client_fixture, payload, expected_id, expected_date
):
    client = request.getfixturevalue(client_fixture)
    monkeypatch.setattr(
        client,
        "_request_with_evidence",
        lambda **kwargs: SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=payload,
            http_status=200,
            evidence_refs=[],
        ),
    )

    result = client.get_team_last_fixtures_result(
        "team-1",
        last_n=10,
        analysis_cutoff_at="2026-06-11T00:00:00+00:00",
        exclude_event_ids={"999"},
        season_id="2026",
        competition_id="league-1",
    )

    assert result.status is SourceResultStatus.SUCCESS
    assert [item["id"] for item in result.value] == [expected_id]
    assert result.value[0]["date"] == expected_date


def test_fixture_stats_result_uses_participant_ids_not_order(
    football_client, monkeypatch
):
    monkeypatch.setattr(
        football_client,
        "_request_with_evidence",
        lambda **kwargs: SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value={
                "response": [
                    {
                        "team": {"id": 11, "name": "Chelsea"},
                        "statistics": [{"type": "Corner Kicks", "value": "5"}],
                    },
                    {
                        "team": {"id": 10, "name": "Arsenal"},
                        "statistics": [{"type": "Corner Kicks", "value": "7"}],
                    },
                ]
            },
            http_status=200,
            evidence_refs=[],
        ),
    )

    result = football_client.get_fixture_stats_result(
        "fixture-1",
        home_participant_id="10",
        away_participant_id="11",
    )

    assert result.status is SourceResultStatus.SUCCESS
    assert result.value[0].stats["corners"] == {"away": 5.0, "home": 7.0}


class TestDeduplicationSafety:
    def test_same_source_distinct_external_ids_do_not_merge(self):
        engine = DeduplicationEngine()
        kickoff = datetime.fromisoformat("2026-06-11T19:30:00+00:00")
        merged = engine.merge(
            {
                "api-basketball": [
                    DiscoveredEvent(
                        source="api-basketball",
                        external_id="game-1",
                        sport="basketball",
                        competition="NBA",
                        home_team="Lakers",
                        away_team="Celtics",
                        kickoff=kickoff,
                    ),
                    DiscoveredEvent(
                        source="api-basketball",
                        external_id="game-2",
                        sport="basketball",
                        competition="NBA",
                        home_team="Lakers",
                        away_team="Celtics",
                        kickoff=kickoff,
                    ),
                ]
            }
        )

        assert len(merged) == 2
