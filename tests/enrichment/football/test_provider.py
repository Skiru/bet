# ruff: noqa: E501
from datetime import date
from unittest.mock import MagicMock

import pytest

from bet.api_clients.base_client import SourceOperationResult, SourceResultStatus
from bet.enrichment.football.contracts import (
    BatchIdsCapability,
)
from bet.enrichment.football.provider import (
    LiveAPIFootballAcquirer,
    PhysicalAttemptBudget,
)
from bet.integration.evidence import EvidenceRef


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.get_history_statistics.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value={"response": []},
    )
    return client

def test_empty_ids_and_over_20_rejected(mock_client):
    from bet.api_clients.api_football import APIFootballClient

    rl = MagicMock()
    client = APIFootballClient(rate_limiter=rl)

    # 0 IDs
    res1 = client.get_history_details([])
    assert res1.status == SourceResultStatus.UNSUPPORTED
    assert res1.error_code == "empty_batch"

    # 21 IDs
    res2 = client.get_history_details([str(i) for i in range(1, 22)])
    assert res2.status == SourceResultStatus.UNSUPPORTED
    assert res2.error_code == "too_many_ids"

def test_ids_request_sorted_hyphen_separated(mock_client):
    from bet.api_clients.api_football import APIFootballClient

    rl = MagicMock()
    client = APIFootballClient(rate_limiter=rl)

    client._request_with_evidence = MagicMock(return_value=MagicMock())
    client.get_history_details(["10", "5", "30", "10"])

    # Should deduplicate, sort numerically: "5-10-30"
    client._request_with_evidence.assert_called_once_with(
        endpoint="/fixtures",
        params={"ids": "5-10-30"},
        operation="history_details",
        expects_response_list=True,
    )

def test_ids_unsupported_causes_no_second_call(mock_client):
    acquirer = LiveAPIFootballAcquirer(mock_client)
    budget = PhysicalAttemptBudget(10)

    # Discovery returns 2 fully valid fixtures
    mock_client.get_history_discovery.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value={"response": [
            {
                "fixture": {"id": 1, "status": {"short": "FT"}, "date": "2023-01-01T12:00:00Z"},
                "league": {"id": 39, "name": "L", "season": 2023},
                "teams": {
                    "home": {"id": 10, "name": "H"},
                    "away": {"id": 20, "name": "A"}
                },
                "goals": {"home": 2, "away": 1},
                "score": {"penalty": {"home": None, "away": None}}
            },
            {
                "fixture": {"id": 2, "status": {"short": "FT"}, "date": "2023-01-01T12:00:00Z"},
                "league": {"id": 39, "name": "L", "season": 2023},
                "teams": {
                    "home": {"id": 10, "name": "H"},
                    "away": {"id": 20, "name": "A"}
                },
                "goals": {"home": 2, "away": 1},
                "score": {"penalty": {"home": None, "away": None}}
            },
        ]},
        evidence_refs=(EvidenceRef("history_discovery", "GET", "json", 100, "hash_disc", captured_at="2023-01-01T12:00:00.000000Z"),)
    )

    # Details returns PLAN_RESTRICTED (stable response)
    mock_client.get_history_details.return_value = SourceOperationResult(
        status=SourceResultStatus.PLAN_RESTRICTED,
        value=None,
    )

    res = acquirer.acquire(
        competition_provider_id="39",
        season=2023,
        from_date=date(2023, 1, 1),
        to_date=date(2023, 1, 2),
        max_fixtures=10,
        max_fallback_stats_calls=5,
        attempt_budget=budget,
        ids_capability=BatchIdsCapability.UNKNOWN,
    )

    # Should set UNSUPPORTED and details should be called only once
    assert res.ids_capability == BatchIdsCapability.UNSUPPORTED
    assert mock_client.get_history_details.call_count == 1

def test_physical_attempt_budget_accounting(mock_client):
    acquirer = LiveAPIFootballAcquirer(mock_client)
    budget = PhysicalAttemptBudget(3) # Limit to 3 physical attempts

    mock_client.get_history_discovery.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value={"response": [
            {
                "fixture": {"id": 1, "status": {"short": "FT"}, "date": "2023-01-01T12:00:00Z"},
                "league": {"id": 39, "name": "L", "season": 2023},
                "teams": {
                    "home": {"id": 10, "name": "H"},
                    "away": {"id": 20, "name": "A"}
                },
                "goals": {"home": 2, "away": 1},
                "score": {"penalty": {"home": None, "away": None}}
            },
            {
                "fixture": {"id": 2, "status": {"short": "FT"}, "date": "2023-01-01T12:00:00Z"},
                "league": {"id": 39, "name": "L", "season": 2023},
                "teams": {
                    "home": {"id": 10, "name": "H"},
                    "away": {"id": 20, "name": "A"}
                },
                "goals": {"home": 2, "away": 1},
                "score": {"penalty": {"home": None, "away": None}}
            },
        ]},
        evidence_refs=(EvidenceRef("history_discovery", "GET", "json", 100, "hash_disc", captured_at="2023-01-01T12:00:00.000000Z"),)
    )
    mock_client.get_history_details.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value={"response": []},
        evidence_refs=(EvidenceRef("history_details", "GET", "json", 100, "hash_details", captured_at="2023-01-01T12:05:00.000000Z"),)
    )

    # First call (discovery) succeeds and consumes 1 attempt (retry_count=0)
    # Remaining budget is 2.
    # Second call (details) succeeds and consumes 1 attempt.
    # Remaining budget is 1.
    # Since we need at least 2 remaining to make any further call (e.g. statistics fallback), we must not call statistics!
    res = acquirer.acquire(
        competition_provider_id="39",
        season=2023,
        from_date=date(2023, 1, 1),
        to_date=date(2023, 1, 2),
        max_fixtures=10,
        max_fallback_stats_calls=5,
        attempt_budget=budget,
        ids_capability=BatchIdsCapability.UNKNOWN,
    )

    assert res.physical_attempts == 2
    # statistics should never have been called because budget remaining was < 2 after details call!
    assert mock_client.get_history_statistics.call_count == 0


def test_t2_malformed_discovery_record_retained_invalid(mock_client):
    acquirer = LiveAPIFootballAcquirer(mock_client)
    budget = PhysicalAttemptBudget(10)

    # Discovery returns one valid and one malformed fixture
    mock_client.get_history_discovery.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value={"response": [
            {
                "fixture": {"id": 1, "status": {"short": "FT"}, "date": "2023-01-01T12:00:00Z"},
                "league": {"id": 39, "name": "L", "season": 2023},
                "teams": {"home": {"id": 10, "name": "H"}, "away": {"id": 20, "name": "A"}},
                "goals": {"home": 2, "away": 1},
                "score": {"penalty": {"home": None, "away": None}}
            },
            {
                # Missing kickoff date and teams -> malformed!
                "fixture": {"id": 2, "status": {"short": "FT"}},
                "league": {"id": 39, "season": 2023},
                "goals": {"home": 2, "away": 1}
            }
        ]},
        evidence_refs=(EvidenceRef("history_discovery", "GET", "json", 100, "hash_disc", captured_at="2023-01-01T12:00:00.000000Z"),)
    )

    res = acquirer.discover_completed_fixtures(
        competition_provider_id="39",
        season=2023,
        from_date=date(2023, 1, 1),
        to_date=date(2023, 1, 2),
        max_fixtures=10,
        attempt_budget=budget
    )

    assert len(res.valid_fixtures) == 1
    assert len(res.invalid_records) == 1
    assert res.invalid_records[0].state == "INVALID"
    assert res.invalid_records[0].provider_fixture_id == "2"
    assert res.terminal_status == "DEGRADED"

def test_t2_malformed_stats_become_transient_failed(mock_client):
    acquirer = LiveAPIFootballAcquirer(mock_client)
    budget = PhysicalAttemptBudget(10)

    # Discovery returns 1 valid fixture
    mock_client.get_history_discovery.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value={"response": [
            {
                "fixture": {"id": 1, "status": {"short": "FT"}, "date": "2023-01-01T12:00:00Z"},
                "league": {"id": 39, "name": "L", "season": 2023},
                "teams": {"home": {"id": 10, "name": "H"}, "away": {"id": 20, "name": "A"}},
                "goals": {"home": 2, "away": 1},
                "score": {"penalty": {"home": None, "away": None}}
            }
        ]},
        evidence_refs=(EvidenceRef("history_discovery", "GET", "json", 100, "hash_disc", captured_at="2023-01-01T12:00:00.000000Z"),)
    )

    # Stats returns malformed statistics response (statistics is dict, expected list of dicts)
    mock_client.get_history_statistics.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value={"response": {"malformed": "should_be_list"}},
        evidence_refs=(EvidenceRef("history_statistics", "GET", "json", 100, "hash_stats", captured_at="2023-01-01T12:10:00.000000Z"),)
    )

    res = acquirer.acquire(
        competition_provider_id="39",
        season=2023,
        from_date=date(2023, 1, 1),
        to_date=date(2023, 1, 2),
        max_fixtures=10,
        max_fallback_stats_calls=5,
        attempt_budget=budget,
        ids_capability=BatchIdsCapability.UNSUPPORTED
    )

    assert res.terminal_status == "TRANSIENT_FAILED"
    assert len(res.fixtures) == 1
    from bet.enrichment.football.contracts import (
        AcquisitionMode,
        FixtureWorkDisposition,
    )
    assert res.outcomes[0].disposition == FixtureWorkDisposition.TRANSIENT_FAILED
    assert res.fixtures[0].acquisition_mode == AcquisitionMode.DISCOVERY_ENVELOPE

def test_t2_participant_mismatch_becomes_transient_failed(mock_client):
    acquirer = LiveAPIFootballAcquirer(mock_client)
    budget = PhysicalAttemptBudget(10)

    # Discovery returns 1 valid fixture
    mock_client.get_history_discovery.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value={"response": [
            {
                "fixture": {"id": 1, "status": {"short": "FT"}, "date": "2023-01-01T12:00:00Z"},
                "league": {"id": 39, "name": "L", "season": 2023},
                "teams": {"home": {"id": 10, "name": "H"}, "away": {"id": 20, "name": "A"}},
                "goals": {"home": 2, "away": 1},
                "score": {"penalty": {"home": None, "away": None}}
            }
        ]},
        evidence_refs=(EvidenceRef("history_discovery", "GET", "json", 100, "hash_disc", captured_at="2023-01-01T12:00:00.000000Z"),)
    )

    # Stats returns statistics with an unexpected team ID (team 999 instead of 10 or 20)
    mock_client.get_history_statistics.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value={"response": [
            {"team": {"id": 999, "name": "Conflict"}, "statistics": []}
        ]},
        evidence_refs=(EvidenceRef("history_statistics", "GET", "json", 100, "hash_stats", captured_at="2023-01-01T12:10:00.000000Z"),)
    )

    res = acquirer.acquire(
        competition_provider_id="39",
        season=2023,
        from_date=date(2023, 1, 1),
        to_date=date(2023, 1, 2),
        max_fixtures=10,
        max_fallback_stats_calls=5,
        attempt_budget=budget,
        ids_capability=BatchIdsCapability.UNSUPPORTED
    )

    assert res.terminal_status == "TRANSIENT_FAILED"
    assert len(res.fixtures) == 1
    from bet.enrichment.football.contracts import (
        AcquisitionMode,
        FixtureWorkDisposition,
    )
    assert res.outcomes[0].disposition == FixtureWorkDisposition.TRANSIENT_FAILED
    assert res.fixtures[0].acquisition_mode == AcquisitionMode.DISCOVERY_ENVELOPE

def test_t2_missing_evidence_timestamp_raises_value_error(mock_client):
    acquirer = LiveAPIFootballAcquirer(mock_client)
    budget = PhysicalAttemptBudget(10)

    # Discovery returns a valid fixture but with empty evidence_refs (no captured_at!)
    mock_client.get_history_discovery.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value={"response": [
            {
                "fixture": {"id": 1, "status": {"short": "FT"}, "date": "2023-01-01T12:00:00Z"},
                "league": {"id": 39, "name": "L", "season": 2023},
                "teams": {"home": {"id": 10, "name": "H"}, "away": {"id": 20, "name": "A"}},
                "goals": {"home": 2, "away": 1},
                "score": {"penalty": {"home": None, "away": None}}
            }
        ]},
        evidence_refs=() # empty!
    )

    with pytest.raises(ValueError, match="MISSING_EVIDENCE_TIMESTAMP"):
        acquirer.acquire(
            competition_provider_id="39",
            season=2023,
            from_date=date(2023, 1, 1),
            to_date=date(2023, 1, 2),
            max_fixtures=10,
            max_fallback_stats_calls=5,
            attempt_budget=budget,
            ids_capability=BatchIdsCapability.UNSUPPORTED
        )

def test_t2_no_datetime_now_for_observed_at():
    # Physically scan provider.py and replay.py for datetime.now usage as fallback for observed_at
    prov_content = open("src/bet/enrichment/football/provider.py").read()
    replay_content = open("src/bet/enrichment/football/replay.py").read()

    assert "datetime.now(UTC)" not in prov_content
    assert "datetime.now(UTC)" not in replay_content
