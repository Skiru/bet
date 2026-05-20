"""Targeted hockey rich-completion tests."""

from types import SimpleNamespace

import data_enrichment_agent
import db_report
import rich_stats_probe
from _helpers import hockey_rich_completion as hockey_helper
from bet.models.normalized import NormalizedMatchStats
from bet.stats.fallback_chains import RICH_COMPLETION_POLICY
from bet.stats.rich_coverage import classify_rich_coverage


def _make_hockey_fixture_row(
    fixture_id: int,
    home: str,
    away: str,
    kickoff: str = "2026-05-20T18:00:00Z",
    competition: str = "NHL",
) -> dict:
    return {
        "fixture_id": fixture_id,
        "kickoff": kickoff,
        "status": "finished",
        "competition": competition,
        "home_team": home,
        "away_team": away,
    }


def _full_hockey_rich_stats() -> dict:
    return {
        "shots": {"home": 34, "away": 28},
        "hits": {"home": 19, "away": 22},
        "blocks": {"home": 13, "away": 15},
        "pim": {"home": 6, "away": 8},
        "powerplay_goals": {"home": 1, "away": 0},
        "faceoff_pct": {"home": 52.1, "away": 47.9},
        "goals": {"home": 4, "away": 2},
    }


def _partial_hockey_rich_stats() -> dict:
    return {
        "shots": {"home": 34, "away": 28},
        "hits": {"home": 19, "away": 22},
        "blocks": {"home": 13, "away": 15},
    }


def _supporting_hockey_stats() -> dict:
    return {
        "pim": {"home": 6, "away": 8},
        "powerplay_goals": {"home": 1, "away": 0},
        "faceoff_pct": {"home": 52.1, "away": 47.9},
        "penalties": {"home": 3, "away": 4},
        "takeaways": {"home": 8, "away": 7},
        "giveaways": {"home": 5, "away": 6},
    }


def test_hockey_policy_declares_canonical_supporting_and_aggregate_contract():
    policy = RICH_COMPLETION_POLICY["hockey"]

    assert policy["required_rich_keys"] == [
        "shots",
        "hits",
        "blocks",
        "pim",
        "powerplay_goals",
        "faceoff_pct",
    ]
    assert policy["canonical_source"] == "api-hockey"
    assert policy["supporting_sources"] == ["espn-hockey"]
    assert policy["aggregate_only_sources"] == ["moneypuck", "scrapernhl"]


def test_set_result_status_ignores_hockey_baseline_and_supplementary_only_keys():
    result = {
        "sport": "hockey",
        "stats_found": {
            "goals": True,
            "penalties": True,
            "takeaways": True,
            "giveaways": True,
            "shots": True,
            "hits": True,
            "blocks": True,
            "pim": True,
            "powerplay_goals": True,
        },
    }

    data_enrichment_agent._set_result_status(result)

    assert result["status"] == "partial"
    assert result["hockey_rich_complete"] is False
    assert result["hockey_rich_keys_found"] == [
        "blocks",
        "hits",
        "pim",
        "powerplay_goals",
        "shots",
    ]
    assert result["hockey_missing_rich_keys"] == ["faceoff_pct"]


def test_classify_rich_coverage_excludes_aggregate_only_hockey_sources():
    detail = classify_rich_coverage(
        [
            ("shots", "moneypuck"),
            ("hits", "scrapernhl"),
            ("blocks", "moneypuck"),
            ("pim", "scrapernhl"),
            ("powerplay_goals", "moneypuck"),
            ("faceoff_pct", "scrapernhl"),
        ],
        RICH_COMPLETION_POLICY["hockey"]["required_rich_keys"],
        {
            RICH_COMPLETION_POLICY["hockey"]["canonical_source"],
            *RICH_COMPLETION_POLICY["hockey"]["supporting_sources"],
        },
    )

    assert detail["bucket"] == "partial"
    assert detail["eligible"] is True
    assert detail["rich_keys_found"] == []
    assert detail["missing_rich_keys"] == RICH_COMPLETION_POLICY["hockey"]["required_rich_keys"]


def test_hockey_helper_persists_normalized_matches_via_store_in_cache(monkeypatch):
    fixtures = [_make_hockey_fixture_row(701, "Edmonton Oilers", "Dallas Stars")]
    store_calls = []

    monkeypatch.setattr(
        hockey_helper,
        "_get_recent_hockey_fixtures",
        lambda team_name, limit: (fixtures, "17"),
    )
    monkeypatch.setattr(
        hockey_helper,
        "_store_in_cache",
        lambda *args, **kwargs: store_calls.append((args, kwargs)),
    )

    rich_match = NormalizedMatchStats(
        fixture_id="701",
        source="api-hockey",
        sport="hockey",
        home_team="Edmonton Oilers",
        away_team="Dallas Stars",
        date="2026-05-20",
        stats=_full_hockey_rich_stats(),
    )
    clients = {
        "api-hockey": SimpleNamespace(
            api_name="api-hockey",
            is_available=lambda: True,
            get_fixture_stats=lambda fixture_id: [rich_match],
        ),
        "espn-hockey": SimpleNamespace(
            api_name="espn-hockey",
            is_available=lambda: True,
            get_fixture_stats=lambda fixture_id: [],
        ),
    }
    monkeypatch.setattr(hockey_helper, "get_client", lambda api_name, rate_limiter=None: clients[api_name])

    result = hockey_helper.complete_hockey_rich_stats("Edmonton Oilers", "hockey", max_fixtures=1)

    assert result["status"] == "enriched"
    assert result["source"] == "api-hockey"
    assert result["fixtures_scanned"] == 1
    assert result["matches_persisted"] == 1
    assert result["rich_keys_found"] == RICH_COMPLETION_POLICY["hockey"]["required_rich_keys"]
    assert store_calls, "hockey helper must persist through _store_in_cache"
    persisted_matches = store_calls[0][0][2]
    assert all(isinstance(match, NormalizedMatchStats) for match in persisted_matches)
    assert persisted_matches[0].source == "api-hockey"
    assert store_calls[0][0][3] == "api-hockey"


def test_hockey_helper_gap_fills_partial_stats_via_supporting_source(monkeypatch):
    fixtures = [_make_hockey_fixture_row(702, "Edmonton Oilers", "Dallas Stars")]
    store_calls = []

    monkeypatch.setattr(
        hockey_helper,
        "_get_recent_hockey_fixtures",
        lambda team_name, limit: (fixtures, "17"),
    )
    monkeypatch.setattr(
        hockey_helper,
        "_store_in_cache",
        lambda *args, **kwargs: store_calls.append((args, kwargs)),
    )

    partial_match = NormalizedMatchStats(
        fixture_id="702",
        source="api-hockey",
        sport="hockey",
        home_team="Edmonton Oilers",
        away_team="Dallas Stars",
        date="2026-05-20",
        stats=_partial_hockey_rich_stats(),
    )
    supporting_match = NormalizedMatchStats(
        fixture_id="702",
        source="espn-hockey",
        sport="hockey",
        home_team="Edmonton Oilers",
        away_team="Dallas Stars",
        date="2026-05-20",
        stats=_supporting_hockey_stats(),
    )
    clients = {
        "api-hockey": SimpleNamespace(
            api_name="api-hockey",
            is_available=lambda: True,
            get_fixture_stats=lambda fixture_id: [partial_match],
        ),
        "espn-hockey": SimpleNamespace(
            api_name="espn-hockey",
            is_available=lambda: True,
            get_fixture_stats=lambda fixture_id: [supporting_match],
        ),
    }
    monkeypatch.setattr(hockey_helper, "get_client", lambda api_name, rate_limiter=None: clients[api_name])

    result = hockey_helper.complete_hockey_rich_stats("Edmonton Oilers", "hockey", max_fixtures=1)

    assert result["status"] == "enriched"
    assert result["source"] == "api-hockey"
    assert result["rich_keys_found"] == RICH_COMPLETION_POLICY["hockey"]["required_rich_keys"]
    assert store_calls, "hockey helper must persist enriched matches"
    assert store_calls[0][0][2][0].stats["penalties"] == {"home": 3, "away": 4}
    assert store_calls[0][0][2][0].stats["pim"] == {"home": 6, "away": 8}


def test_hockey_helper_marks_espn_empty_non_nhl_as_unsupported_skip(monkeypatch):
    fixtures = [_make_hockey_fixture_row(703, "Dynamo Minsk", "SKA Saint Petersburg", competition="KHL")]
    store_calls = []

    monkeypatch.setattr(
        hockey_helper,
        "_get_recent_hockey_fixtures",
        lambda team_name, limit: (fixtures, "17"),
    )
    monkeypatch.setattr(
        hockey_helper,
        "_store_in_cache",
        lambda *args, **kwargs: store_calls.append((args, kwargs)),
    )
    clients = {
        "api-hockey": SimpleNamespace(
            api_name="api-hockey",
            is_available=lambda: True,
            get_fixture_stats=lambda fixture_id: [],
        ),
        "espn-hockey": SimpleNamespace(
            api_name="espn-hockey",
            is_available=lambda: True,
            get_fixture_stats=lambda fixture_id: [],
        ),
    }
    monkeypatch.setattr(hockey_helper, "get_client", lambda api_name, rate_limiter=None: clients[api_name])

    result = hockey_helper.complete_hockey_rich_stats("Dynamo Minsk", "hockey", max_fixtures=1)

    assert result["status"] == "failed"
    assert result["failure_reason"] == "unsupported_league_skip"
    assert result["matches_persisted"] == 0
    assert not store_calls


def test_data_enrichment_agent_routes_hockey_completion_without_promoting_aggregate_source(monkeypatch):
    aggregate_match = NormalizedMatchStats(
        fixture_id="10001",
        source="moneypuck",
        sport="hockey",
        home_team="Edmonton Oilers",
        away_team="Dallas Stars",
        date="2026-05-20",
        stats={"xg_pct": {"home": 0.58, "away": 0.42}},
    )

    client = SimpleNamespace(api_name="moneypuck", is_available=lambda: True)
    monkeypatch.setattr(data_enrichment_agent, "FALLBACK_CHAINS", {"hockey": ["moneypuck"]})
    monkeypatch.setattr(data_enrichment_agent, "_source_is_down", lambda *_: False)
    monkeypatch.setattr(data_enrichment_agent, "get_client", lambda *args, **kwargs: client)
    monkeypatch.setattr(data_enrichment_agent, "fetch_team_stats", lambda *args, **kwargs: [aggregate_match])
    monkeypatch.setattr(data_enrichment_agent, "_store_in_cache", lambda *args, **kwargs: None)

    coverage_details = iter(
        [
            {
                "bucket": "partial",
                "eligible": True,
                "stat_keys": ["xg_pct"],
                "sources": ["moneypuck"],
                "rich_keys_found": [],
                "missing_rich_keys": list(RICH_COMPLETION_POLICY["hockey"]["required_rich_keys"]),
            },
            {
                "bucket": "rich",
                "eligible": False,
                "stat_keys": ["xg_pct", *RICH_COMPLETION_POLICY["hockey"]["required_rich_keys"]],
                "sources": ["api-hockey", "moneypuck"],
                "rich_keys_found": list(RICH_COMPLETION_POLICY["hockey"]["required_rich_keys"]),
                "missing_rich_keys": [],
            },
        ]
    )
    monkeypatch.setattr(data_enrichment_agent, "_get_hockey_coverage_detail", lambda team_name: next(coverage_details))

    helper_calls = []

    def fake_completion(team_name, sport, max_fixtures=5):
        helper_calls.append((team_name, sport, max_fixtures))
        return {
            "team": team_name,
            "sport": sport,
            "source": "api-hockey",
            "status": "enriched",
            "fixtures_scanned": 1,
            "matches_persisted": 1,
            "rich_keys_found": list(RICH_COMPLETION_POLICY["hockey"]["required_rich_keys"]),
            "missing_rich_keys": [],
            "error": None,
            "failure_reason": None,
        }

    monkeypatch.setattr(data_enrichment_agent, "complete_hockey_rich_stats", fake_completion)

    result = data_enrichment_agent.enrich_team("Edmonton Oilers", "hockey")

    assert helper_calls == [("Edmonton Oilers", "hockey", 5)]
    assert result["status"] == "enriched"
    assert result["source"] == "moneypuck"
    assert result["supplementary_sources"] == ["api-hockey"]
    assert result["hockey_completion"]["attempted"] is True
    assert result["hockey_completion"]["success"] is True
    assert result["hockey_completion"]["source"] == "api-hockey"
    assert result["hockey_rich_complete"] is True


def test_probe_reports_hockey_rich_coverage_without_aggregate_promotion(monkeypatch):
    teams = [(1, "Edmonton Oilers"), (2, "Dallas Stars")]
    team_form_rows = {
        1: [(key, "api-hockey") for key in RICH_COMPLETION_POLICY["hockey"]["required_rich_keys"]],
        2: [
            ("shots", "moneypuck"),
            ("hits", "scrapernhl"),
            ("blocks", "moneypuck"),
            ("pim", "scrapernhl"),
            ("powerplay_goals", "moneypuck"),
            ("faceoff_pct", "scrapernhl"),
        ],
    }

    class FakeConn:
        def execute(self, query, params=None):
            if not str(query).strip().upper().startswith("SELECT"):
                raise AssertionError(f"Unexpected non-read query: {query}")
            team_id = params[0]
            return SimpleNamespace(fetchall=lambda: team_form_rows[team_id])

    class FakeDB:
        def __enter__(self):
            return FakeConn()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(rich_stats_probe, "_get_sport_id", lambda sport: 1)
    monkeypatch.setattr(rich_stats_probe, "get_db", lambda: FakeDB())
    monkeypatch.setattr(rich_stats_probe, "_get_teams_for_date", lambda sport, betting_date: teams)

    result = rich_stats_probe.probe_rich_coverage("hockey", "2026-05-20", limit=10)

    assert result["fixtures_scanned"] == 2
    assert result["eligible"] == 1
    assert result["rich"] == 1
    assert result["baseline_only"] == 0
    assert result["partial"] == 1
    assert result["no_data"] == 0
    assert result["source_choice"] == "api-hockey"


def test_db_report_rich_coverage_outputs_hockey_buckets(monkeypatch, capsys):
    rows = [(1, "Edmonton Oilers"), (2, "Dallas Stars")]
    team_form_rows = {
        1: [(key, "api-hockey") for key in RICH_COMPLETION_POLICY["hockey"]["required_rich_keys"]],
        2: [
            ("shots", "moneypuck"),
            ("hits", "scrapernhl"),
            ("blocks", "moneypuck"),
            ("pim", "scrapernhl"),
            ("powerplay_goals", "moneypuck"),
            ("faceoff_pct", "scrapernhl"),
        ],
    }

    class FakeConn:
        def execute(self, query, params=None):
            if "SELECT id FROM sports" in query:
                return SimpleNamespace(fetchone=lambda: (1,))
            if "JOIN teams t ON t.id IN (f.home_team_id, f.away_team_id)" in query:
                return SimpleNamespace(fetchall=lambda: rows)
            if "FROM team_form" in query:
                team_id = params[0]
                return SimpleNamespace(fetchall=lambda: team_form_rows[team_id])
            raise AssertionError(f"Unexpected query: {query}")

    class FakeDB:
        def __enter__(self):
            return FakeConn()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(db_report, "get_db", lambda: FakeDB())

    db_report.report_rich_coverage("2026-05-20", "hockey")
    output = capsys.readouterr().out

    assert "HOCKEY RICH COVERAGE" in output
    assert "Eligible: 1" in output
    assert "Rich: 1" in output
    assert "Baseline only: 0" in output
    assert "Partial: 1" in output
    assert "No data: 0" in output
