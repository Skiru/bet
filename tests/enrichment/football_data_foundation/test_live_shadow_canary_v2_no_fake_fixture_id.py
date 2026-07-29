import os
from unittest.mock import MagicMock
from unittest.mock import patch
import pytest

from bet.enrichment.football_data_foundation.live_shadow_canary.contracts import OfficialFixtureContext
from bet.enrichment.football_data_foundation.live_shadow_canary.provider_probe import run_provider_shadow_probes


@pytest.fixture
def clean_env() -> None:
    with patch.dict(
        os.environ,
        {
            "SPORTDB_API_KEY": "",
            "FOOTBALL_DATA_API_KEY": "",
            "HIGHLIGHTLY_API_KEY": "",
        },
    ):
        yield


def test_provider_probes_blocked_on_missing_match_id(clean_env) -> None:
    # Context has NO match_id
    context = OfficialFixtureContext(
        fixture_slug="slug",
        competition_name="Comp",
        official_source_url="url",
        official_source_name="name",
        match_id=None,  # MISSING
        home_team="Norway",
        away_team="Senegal",
        kickoff_at="2026-06-22T20:00:00Z",
    )

    mock_env = {
        "SPORTDB_API_KEY": "test_sportdb_key",
        "FOOTBALL_DATA_API_KEY": "test_fdorg_key",
        "HIGHLIGHTLY_API_KEY": "test_highlightly_key",
    }

    mock_transport = MagicMock()
    # Mock transport response for FootballDataOrg (which does not depend on match_id)
    mock_resp = MagicMock()
    mock_resp.body = {"standings": [], "season": {"startDate": "2026-01-01"}}
    mock_resp.body_hash = "a" * 64
    mock_resp.byte_count = 100
    mock_resp.record_count = 1
    mock_transport.get.return_value = mock_resp

    with patch.dict(os.environ, mock_env):
        out_batches = []
        results = run_provider_shadow_probes(
            context, transport=mock_transport, out_batches=out_batches
        )

        assert len(results) == 3

        # SportDB: blocked on missing match_id
        sportdb_res = next(r for r in results if r.provider == "sportdb")
        assert sportdb_res.status == "BLOCKED_MISSING_PROVIDER_MATCH_ID"
        assert sportdb_res.request_attempted is False

        # Highlightly: blocked on missing match_id
        highlightly_res = next(r for r in results if r.provider == "highlightly")
        assert highlightly_res.status == "BLOCKED_MISSING_PROVIDER_MATCH_ID"
        assert highlightly_res.request_attempted is False

        # FootballDataOrg: succeeds because it's competition-wide and doesn't need match_id
        fdorg_res = next(r for r in results if r.provider == "football-data-org")
        assert fdorg_res.status == "SUCCESS"
        assert fdorg_res.request_attempted is True


def test_no_canary_fixture_1_exists() -> None:
    # Double check that our test file doesn't have the string
    # We check that the source code does not contain it.
    source_dir = os.path.dirname(__file__) + "/../../src/bet/enrichment/football_data_foundation/live_shadow_canary"
    for root, _, files in os.walk(source_dir):
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(root, f)
                with open(path, "r", encoding="utf-8") as file_handle:
                    content = file_handle.read()
                    assert "canary-fixture-1" not in content, f"Found forbidden canary-fixture-1 in {f}"
