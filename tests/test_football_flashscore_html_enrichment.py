"""Targeted tests for the Flashscore HTML football enrichment adapter and routing."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = str(ROOT_DIR / "scripts")
SRC_DIR = str(ROOT_DIR / "src")

for path in (SCRIPTS_DIR, SRC_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

import data_enrichment_agent
import flashscore_bulk_enrich
from _helpers import football_flashscore_html_enrichment as football_helper
from bet.models.normalized import NormalizedMatchStats


def _make_fixture_row(fixture_id: int, home: str, away: str, kickoff: str = "2026-05-20T18:00:00Z") -> dict:
    return {
        "fixture_id": fixture_id,
        "kickoff": kickoff,
        "status": "finished",
        "competition": "Premier League",
        "home_team": home,
        "away_team": away,
    }


def test_adapter_persists_flashscore_html_matches_via_store_in_cache(monkeypatch):
    fixtures = [
        _make_fixture_row(101, "Arsenal", "Chelsea", "2026-05-18T18:00:00Z"),
        _make_fixture_row(102, "Arsenal", "Liverpool", "2026-05-11T18:00:00Z"),
    ]
    store_calls = []

    monkeypatch.setattr(
        football_helper,
        "_get_recent_football_fixtures",
        lambda team_name, limit: (fixtures, "17"),
    )
    monkeypatch.setattr(
        football_helper,
        "_store_in_cache",
        lambda *args, **kwargs: store_calls.append((args, kwargs)),
    )

    match_results = iter(
        [
            {
                "source": "flashscore-html",
                "status": "ok",
                "match_id": "MATCH101",
                "stats": {
                    "corners": {"home": 7, "away": 3},
                    "shots": {"home": 21, "away": 12},
                },
                "rich_keys_found": ["corners", "shots"],
                "missing_rich_keys": ["yellow_cards", "red_cards", "shots_on_target", "fouls", "possession"],
                "error": None,
                "failure_reason": None,
                "requests_used": 2,
            },
            {
                "source": "flashscore-html",
                "status": "ok",
                "match_id": "MATCH102",
                "stats": {
                    "yellow_cards": {"home": 2, "away": 4},
                    "fouls": {"home": 15, "away": 18},
                    "possession": {"home": 61, "away": 39},
                },
                "rich_keys_found": ["yellow_cards", "fouls", "possession"],
                "missing_rich_keys": ["corners", "red_cards", "shots", "shots_on_target"],
                "error": None,
                "failure_reason": None,
                "requests_used": 2,
            },
        ]
    )
    monkeypatch.setattr(
        football_helper,
        "fetch_flashscore_match_page_stats",
        lambda *args, **kwargs: next(match_results),
    )

    result = football_helper.complete_football_flashscore_html_stats(
        "Arsenal",
        "football",
        max_fixtures=2,
        c_requests=object(),
        sleep_seconds=0,
    )

    assert result["status"] == "partial"
    assert result["fixtures_scanned"] == 2
    assert result["matches_persisted"] == 2
    assert result["rich_keys_found"] == ["corners", "yellow_cards", "shots", "fouls", "possession"]
    assert store_calls, "adapter must persist through _store_in_cache"
    persisted_matches = store_calls[0][0][2]
    assert all(isinstance(match, NormalizedMatchStats) for match in persisted_matches)
    assert persisted_matches[0].source == "flashscore-html"
    assert store_calls[0][0][3] == "flashscore-html"


def test_adapter_reports_html_blocked_when_match_pages_block(monkeypatch):
    fixtures = [_make_fixture_row(201, "Arsenal", "Chelsea")]
    monkeypatch.setattr(
        football_helper,
        "_get_recent_football_fixtures",
        lambda team_name, limit: (fixtures, "17"),
    )
    monkeypatch.setattr(
        football_helper,
        "fetch_flashscore_match_page_stats",
        lambda *args, **kwargs: {
            "source": "flashscore-html",
            "status": "failed",
            "match_id": None,
            "stats": None,
            "rich_keys_found": [],
            "missing_rich_keys": list(football_helper.FOOTBALL_RICH_STAT_KEYS),
            "error": "403 blocked",
            "failure_reason": "html_blocked",
            "requests_used": 1,
        },
    )

    result = football_helper.complete_football_flashscore_html_stats(
        "Arsenal",
        "football",
        max_fixtures=1,
        c_requests=object(),
        sleep_seconds=0,
    )

    assert result["status"] == "failed"
    assert result["failure_reason"] == "html_blocked"
    assert result["matches_persisted"] == 0


def test_data_enrichment_agent_uses_flashscore_html_completion_and_preserves_source_shape(monkeypatch):
    partial_match = NormalizedMatchStats(
        fixture_id="1001",
        source="espn-football",
        sport="football",
        home_team="Arsenal",
        away_team="Chelsea",
        date="2026-05-20",
        stats={"goals": {"home": 2.0, "away": 1.0}},
    )

    client = MagicMock()
    client.is_available.return_value = True

    monkeypatch.setattr(data_enrichment_agent, "FALLBACK_CHAINS", {"football": ["espn-football"]})
    monkeypatch.setattr(data_enrichment_agent, "_source_is_down", lambda *_: False)
    monkeypatch.setattr(data_enrichment_agent, "get_client", lambda *args, **kwargs: client)
    monkeypatch.setattr(data_enrichment_agent, "fetch_team_stats", lambda *args, **kwargs: [partial_match])
    monkeypatch.setattr(data_enrichment_agent, "_store_in_cache", lambda *args, **kwargs: None)

    helper_calls = []

    def fake_completion(team_name, sport, max_fixtures=5, **kwargs):
        helper_calls.append((team_name, sport, max_fixtures))
        return {
            "team": team_name,
            "sport": sport,
            "source": "flashscore-html",
            "status": "partial",
            "fixtures_scanned": 1,
            "matches_persisted": 1,
            "rich_keys_found": ["corners"],
            "missing_rich_keys": [
                "yellow_cards",
                "red_cards",
                "shots",
                "shots_on_target",
                "fouls",
                "possession",
            ],
            "error": None,
            "failure_reason": None,
        }

    monkeypatch.setattr(data_enrichment_agent, "complete_football_rich_stats", fake_completion)

    result = data_enrichment_agent.enrich_team("Arsenal", "football")

    assert helper_calls == [("Arsenal", "football", 5)]
    assert result["status"] == "partial"
    assert result["source"] == "espn-football"
    assert result["stats_found"]["corners"] is True
    assert result["supplementary_sources"] == ["flashscore-html"]
    assert result["football_completion"]["attempted"] is True
    assert result["football_completion"]["source"] == "flashscore-html"
    assert result["football_completion"]["rich_keys_added"] == ["corners"]
    assert result["football_rich_complete"] is False


def test_flashscore_bulk_enrich_invokes_flashscore_html_completion_when_rich_keys_missing(monkeypatch):
    mock_conn = MagicMock()
    mock_conn.execute.return_value = MagicMock()
    mock_conn.__enter__ = lambda self: mock_conn
    mock_conn.__exit__ = lambda self, *args: None
    monkeypatch.setattr(flashscore_bulk_enrich, "get_db", lambda: mock_conn)
    monkeypatch.setattr(
        flashscore_bulk_enrich,
        "_try_flashscore_results_page",
        lambda team_name, sport: ({"goals": [1.0, 0.0]}, None),
    )

    helper_calls = []

    def fake_completion(team_name, sport, max_fixtures=5, **kwargs):
        helper_calls.append((team_name, sport, max_fixtures))
        return {
            "team": team_name,
            "sport": sport,
            "source": "flashscore-html",
            "status": "enriched",
            "fixtures_scanned": 1,
            "matches_persisted": 1,
            "rich_keys_found": ["corners"],
            "missing_rich_keys": [],
            "error": None,
            "failure_reason": None,
        }

    monkeypatch.setattr(flashscore_bulk_enrich, "complete_football_rich_stats", fake_completion)

    result = flashscore_bulk_enrich.enrich_and_write(
        [
            {
                "team_name": "Arsenal",
                "sport": "football",
                "team_id": 1,
                "sport_id": 1,
            }
        ],
        verbose=False,
    )

    assert helper_calls == [("Arsenal", "football", 5)]
    assert result["flashscore_html_fallback_successes"] == 1
    assert result["flashscore_html_matches_persisted"] == 1
    assert result["enriched"] == 1
