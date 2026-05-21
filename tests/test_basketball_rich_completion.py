"""Targeted tests for basketball rich completion and no-write probing."""

import json
from types import SimpleNamespace

import agent_output
import pytest

import data_enrichment_agent
import db_report
import rich_stats_probe
from _helpers import basketball_rich_completion as basketball_helper
from bet.models.normalized import NormalizedMatchStats
from bet.stats.rich_coverage import classify_rich_coverage, resolve_fixture_team_scope


def _make_fixture_row(
    fixture_id: int,
    home: str,
    away: str,
    kickoff: str = "2026-05-20T18:00:00Z",
    competition: str = "NBA",
) -> dict:
    return {
        "fixture_id": fixture_id,
        "kickoff": kickoff,
        "status": "finished",
        "competition": competition,
        "home_team": home,
        "away_team": away,
    }


def _rich_basketball_stats() -> dict:
    return {
        "rebounds": {"home": 51, "away": 47},
        "assists": {"home": 26, "away": 22},
        "steals": {"home": 8, "away": 7},
        "blocks": {"home": 4, "away": 5},
        "turnovers": {"home": 13, "away": 14},
        "fouls": {"home": 18, "away": 17},
        "fg_pct": {"home": 0.47, "away": 0.44},
        "three_pct": {"home": 0.39, "away": 0.35},
        "ft_pct": {"home": 0.82, "away": 0.79},
        "points_in_paint": {"home": 44, "away": 40},
        "fast_break_points": {"home": 18, "away": 12},
    }


def _partial_basketball_stats() -> dict:
    return {
        "rebounds": {"home": 51, "away": 47},
        "assists": {"home": 26, "away": 22},
        "steals": {"home": 8, "away": 7},
    }


def _complement_basketball_stats() -> dict:
    return {
        "blocks": {"home": 4, "away": 5},
        "turnovers": {"home": 13, "away": 14},
        "fouls": {"home": 18, "away": 17},
        "fg_pct": {"home": 0.47, "away": 0.44},
        "three_pct": {"home": 0.39, "away": 0.35},
        "ft_pct": {"home": 0.82, "away": 0.79},
        "points_in_paint": {"home": 44, "away": 40},
        "fast_break_points": {"home": 18, "away": 12},
    }


def test_basketball_helper_persists_normalized_matches_via_store_in_cache(monkeypatch):
    fixtures = [
        _make_fixture_row(301, "Lakers", "Celtics", "2026-05-18T18:00:00Z"),
        _make_fixture_row(302, "Lakers", "Warriors", "2026-05-11T18:00:00Z"),
    ]
    store_calls = []

    monkeypatch.setattr(
        basketball_helper,
        "_get_recent_basketball_fixtures",
        lambda team_name, limit: (fixtures, "17"),
    )
    monkeypatch.setattr(
        basketball_helper,
        "_store_in_cache",
        lambda *args, **kwargs: store_calls.append((args, kwargs)),
    )

    rich_match = NormalizedMatchStats(
        fixture_id="301",
        source="api-basketball",
        sport="basketball",
        home_team="Lakers",
        away_team="Celtics",
        date="2026-05-18",
        stats=_rich_basketball_stats(),
    )
    clients = {
        "api-basketball": SimpleNamespace(
            api_name="api-basketball",
            is_available=lambda: True,
            get_fixture_stats=lambda fixture_id: [rich_match],
        ),
        "nba-api": SimpleNamespace(
            api_name="nba-api",
            is_available=lambda: True,
            get_fixture_stats=lambda fixture_id: [],
        ),
        "espn-basketball": SimpleNamespace(
            api_name="espn-basketball",
            is_available=lambda: True,
            get_fixture_stats=lambda fixture_id: [],
        ),
    }
    monkeypatch.setattr(basketball_helper, "get_client", lambda api_name, rate_limiter=None: clients[api_name])

    result = basketball_helper.complete_basketball_rich_stats("Lakers", "basketball", max_fixtures=2)

    assert result["status"] == "enriched"
    assert result["source"] == "api-basketball"
    assert result["fixtures_scanned"] == 1
    assert result["matches_persisted"] == 1
    assert result["rich_keys_found"] == [
        "rebounds",
        "assists",
        "steals",
        "blocks",
        "turnovers",
        "fouls",
        "fg_pct",
        "three_pct",
        "ft_pct",
        "points_in_paint",
        "fast_break_points",
    ]
    assert store_calls, "basketball helper must persist through _store_in_cache"
    persisted_matches = store_calls[0][0][2]
    assert all(isinstance(match, NormalizedMatchStats) for match in persisted_matches)
    assert persisted_matches[0].source == "api-basketball"
    assert store_calls[0][0][3] == "api-basketball"


def test_basketball_helper_gap_fills_partial_stats_via_supporting_source(monkeypatch):
    fixtures = [_make_fixture_row(303, "Lakers", "Celtics", "2026-05-18T18:00:00Z")]
    store_calls = []

    monkeypatch.setattr(
        basketball_helper,
        "_get_recent_basketball_fixtures",
        lambda team_name, limit: (fixtures, "17"),
    )
    monkeypatch.setattr(
        basketball_helper,
        "_store_in_cache",
        lambda *args, **kwargs: store_calls.append((args, kwargs)),
    )

    partial_match = NormalizedMatchStats(
        fixture_id="303",
        source="api-basketball",
        sport="basketball",
        home_team="Lakers",
        away_team="Celtics",
        date="2026-05-18",
        stats=_partial_basketball_stats(),
    )
    complement_match = NormalizedMatchStats(
        fixture_id="303",
        source="nba-api",
        sport="basketball",
        home_team="Lakers",
        away_team="Celtics",
        date="2026-05-18",
        stats=_complement_basketball_stats(),
    )
    clients = {
        "api-basketball": SimpleNamespace(
            api_name="api-basketball",
            is_available=lambda: True,
            get_fixture_stats=lambda fixture_id: [partial_match],
        ),
        "nba-api": SimpleNamespace(
            api_name="nba-api",
            is_available=lambda: True,
            get_fixture_stats=lambda fixture_id: [complement_match],
        ),
        "espn-basketball": SimpleNamespace(
            api_name="espn-basketball",
            is_available=lambda: True,
            get_fixture_stats=lambda fixture_id: [],
        ),
    }
    monkeypatch.setattr(basketball_helper, "get_client", lambda api_name, rate_limiter=None: clients[api_name])

    result = basketball_helper.complete_basketball_rich_stats("Lakers", "basketball", max_fixtures=1)

    assert result["status"] == "enriched"
    assert result["source"] == "api-basketball"
    assert result["fixtures_scanned"] == 1
    assert result["matches_persisted"] == 1
    assert result["rich_keys_found"] == [
        "rebounds",
        "assists",
        "steals",
        "blocks",
        "turnovers",
        "fouls",
        "fg_pct",
        "three_pct",
        "ft_pct",
        "points_in_paint",
        "fast_break_points",
    ]
    assert store_calls, "basketball helper must persist through _store_in_cache"
    persisted_matches = store_calls[0][0][2]
    assert all(isinstance(match, NormalizedMatchStats) for match in persisted_matches)
    assert persisted_matches[0].source == "api-basketball"
    assert store_calls[0][0][3] == "api-basketball"


def test_basketball_helper_marks_espn_empty_non_nba_as_unsupported_skip(monkeypatch):
    fixtures = [_make_fixture_row(401, "Lakers", "Celtics", competition="EuroLeague")]
    store_calls = []

    monkeypatch.setattr(
        basketball_helper,
        "_get_recent_basketball_fixtures",
        lambda team_name, limit: (fixtures, "17"),
    )
    monkeypatch.setattr(
        basketball_helper,
        "_store_in_cache",
        lambda *args, **kwargs: store_calls.append((args, kwargs)),
    )
    clients = {
        "api-basketball": SimpleNamespace(
            api_name="api-basketball",
            is_available=lambda: True,
            get_fixture_stats=lambda fixture_id: [],
        ),
        "nba-api": SimpleNamespace(
            api_name="nba-api",
            is_available=lambda: True,
            get_fixture_stats=lambda fixture_id: [],
        ),
        "espn-basketball": SimpleNamespace(
            api_name="espn-basketball",
            is_available=lambda: True,
            get_fixture_stats=lambda fixture_id: [],
        ),
    }
    monkeypatch.setattr(basketball_helper, "get_client", lambda api_name, rate_limiter=None: clients[api_name])

    result = basketball_helper.complete_basketball_rich_stats("Lakers", "basketball", max_fixtures=1)

    assert result["status"] == "failed"
    assert result["failure_reason"] == "unsupported_league_skip"
    assert result["matches_persisted"] == 0
    assert not store_calls


def test_data_enrichment_agent_routes_basketball_completion_and_summary(monkeypatch):
    partial_match = NormalizedMatchStats(
        fixture_id="1001",
        source="nba-api",
        sport="basketball",
        home_team="Lakers",
        away_team="Celtics",
        date="2026-05-20",
        stats={"points": {"home": 110.0, "away": 104.0}},
    )

    client = SimpleNamespace(api_name="nba-api", is_available=lambda: True)
    monkeypatch.setattr(data_enrichment_agent, "FALLBACK_CHAINS", {"basketball": ["nba-api"]})
    monkeypatch.setattr(data_enrichment_agent, "_source_is_down", lambda *_: False)
    monkeypatch.setattr(data_enrichment_agent, "get_client", lambda *args, **kwargs: client)
    monkeypatch.setattr(data_enrichment_agent, "fetch_team_stats", lambda *args, **kwargs: [partial_match])
    monkeypatch.setattr(data_enrichment_agent, "_store_in_cache", lambda *args, **kwargs: None)

    helper_calls = []

    def fake_completion(team_name, sport, max_fixtures=5):
        helper_calls.append((team_name, sport, max_fixtures))
        return {
            "team": team_name,
            "sport": sport,
            "source": "api-basketball",
            "status": "partial",
            "fixtures_scanned": 1,
            "matches_persisted": 1,
            "rich_keys_found": ["rebounds"],
            "missing_rich_keys": ["assists"],
            "error": None,
            "failure_reason": None,
        }

    monkeypatch.setattr(data_enrichment_agent, "complete_basketball_rich_stats", fake_completion)

    result = data_enrichment_agent.enrich_team("Lakers", "basketball")

    assert helper_calls == [("Lakers", "basketball", 5)]
    assert result["status"] == "partial"
    assert result["source"] == "nba-api"
    assert result["stats_found"]["rebounds"] is True
    assert result["supplementary_sources"] == ["api-basketball"]
    assert result["basketball_completion"]["attempted"] is True
    assert result["basketball_completion"]["success"] is True
    assert result["basketball_completion"]["status"] == "partial"
    assert result["basketball_completion"]["source"] == "api-basketball"
    assert result["basketball_completion"]["rich_keys_added"] == ["rebounds"]
    assert result["basketball_completion"]["failure_reason"] is None
    assert result["basketball_rich_complete"] is False


def test_data_enrichment_agent_batch_summary_counts_basketball_completion():
    results = [
        {
            "sport": "basketball",
            "status": "partial",
            "basketball_completion": {"needed": True, "success": True},
            "basketball_missing_rich_keys": ["assists"],
        },
        {
            "sport": "basketball",
            "status": "failed",
            "basketball_completion": {"needed": True, "success": False},
            "basketball_missing_rich_keys": ["rebounds"],
        },
        {
            "sport": "football",
            "status": "enriched",
            "football_completion": {"needed": False, "success": False},
        },
    ]

    metrics = data_enrichment_agent._summarize_enrichment_results(results)

    assert metrics["basketball_rich_eligible"] == 2
    assert metrics["basketball_completed"] == 1
    assert metrics["basketball_still_missing_rich"] == 2
    assert metrics["enriched"] == 1
    assert metrics["total"] == 3


def test_shared_rich_coverage_helper_classifies_buckets_and_details():
    required_keys = ["rebounds", "assists", "steals"]

    rich_detail = classify_rich_coverage(
        [
            ("rebounds", "api-basketball"),
            ("assists", "api-basketball"),
            ("steals", "api-basketball"),
        ],
        required_keys,
        {"api-basketball"},
    )
    baseline_detail = classify_rich_coverage(
        [("points", "league-profile-baseline")],
        required_keys,
        {"api-basketball"},
    )
    partial_detail = classify_rich_coverage(
        [("rebounds", "api-basketball"), ("turnovers", "api-basketball")],
        required_keys,
        {"api-basketball"},
    )
    no_data_detail = classify_rich_coverage([], required_keys, {"api-basketball"})

    assert rich_detail["bucket"] == "rich"
    assert baseline_detail["bucket"] == "baseline_only"
    assert partial_detail["bucket"] == "partial"
    assert no_data_detail["bucket"] == "no_data"
    assert rich_detail["rich_keys_found"] == required_keys
    assert partial_detail["missing_rich_keys"] == ["assists", "steals"]


def test_probe_reports_rich_coverage_without_writes(monkeypatch):
    teams = [(1, "Lakers"), (2, "Celtics")]
    team_form_rows = {
        1: [
            ("rebounds", "api-basketball"),
            ("assists", "api-basketball"),
            ("steals", "api-basketball"),
            ("blocks", "api-basketball"),
            ("turnovers", "api-basketball"),
            ("fouls", "api-basketball"),
            ("fg_pct", "api-basketball"),
            ("three_pct", "api-basketball"),
            ("ft_pct", "api-basketball"),
            ("points_in_paint", "api-basketball"),
            ("fast_break_points", "api-basketball"),
        ],
        2: [("points", "league-profile-baseline")],
    }

    class FakeConn:
        def execute(self, query, params=None):
            if "FROM team_form" not in query:
                raise AssertionError(f"Unexpected non-read query: {query}")
            team_id = params[0]
            return SimpleNamespace(fetchall=lambda: team_form_rows[team_id])

    class FakeDB:
        def __enter__(self):
            return FakeConn()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(rich_stats_probe, "_get_teams_for_date", lambda sport, betting_date: teams)
    monkeypatch.setattr(rich_stats_probe, "_get_sport_id", lambda sport: 1)
    monkeypatch.setattr(rich_stats_probe, "get_db", lambda: FakeDB())

    result = rich_stats_probe.probe_rich_coverage("basketball", "2026-05-20", limit=10)

    assert result["fixtures_scanned"] == 2
    assert result["eligible"] == 1
    assert result["rich"] == 1
    assert result["baseline_only"] == 1
    assert result["partial"] == 0
    assert result["no_data"] == 0
    assert result["source_choice"] == "api-basketball"
    assert len(result["team_details"]) == 2
    assert result["team_details"][0]["team"] == "Lakers"
    assert result["team_details"][0]["bucket"] == "rich"


def test_resolve_fixture_team_scope_falls_back_to_latest_finished_date():
    fallback_rows = [(1, "Lakers"), (2, "Celtics")]

    class FakeConn:
        def execute(self, query, params=None):
            if "WHERE date(f.kickoff) = ? AND f.sport_id = ?" in query:
                fixture_date = params[0]
                if fixture_date == "2026-05-20":
                    return SimpleNamespace(fetchall=lambda: [])
                if fixture_date == "2026-05-19":
                    return SimpleNamespace(fetchall=lambda: fallback_rows)
            if "date(f.kickoff) <= ?" in query:
                return SimpleNamespace(fetchone=lambda: ("2026-05-19",))
            raise AssertionError(f"Unexpected query: {query}")

    scope = resolve_fixture_team_scope(FakeConn(), 1, "2026-05-20", limit=5)

    assert scope["teams"] == fallback_rows
    assert scope["scope_date"] == "2026-05-19"
    assert scope["used_fallback"] is True


def test_probe_uses_latest_finished_scope_when_requested_date_has_no_teams(monkeypatch):
    fallback_rows = [(1, "Lakers")]
    team_form_rows = {
        1: [(key, "api-basketball") for key in [
            "rebounds",
            "assists",
            "steals",
            "blocks",
            "turnovers",
            "fouls",
            "fg_pct",
            "three_pct",
            "ft_pct",
            "points_in_paint",
            "fast_break_points",
        ]],
    }

    class FakeConn:
        def execute(self, query, params=None):
            if "date(f.kickoff) <= ?" in query:
                return SimpleNamespace(fetchone=lambda: ("2026-05-19",))
            if "WHERE date(f.kickoff) = ? AND f.sport_id = ?" in query:
                fixture_date = params[0]
                rows = [] if fixture_date == "2026-05-20" else fallback_rows
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

    monkeypatch.setattr(rich_stats_probe, "_get_sport_id", lambda sport: 1)
    monkeypatch.setattr(rich_stats_probe, "get_db", lambda: FakeDB())

    result = rich_stats_probe.probe_rich_coverage("basketball", "2026-05-20", limit=5)

    assert result["fixtures_scanned"] == 1
    assert result["rich"] == 1
    assert result["scope_date"] == "2026-05-19"
    assert result["used_fallback"] is True


def test_db_report_rich_coverage_alias_routes_to_generic_path(monkeypatch):
    captured = []

    def fake_report_rich_coverage(betting_date, sport):
        captured.append((betting_date, sport))

    monkeypatch.setattr(db_report, "report_rich_coverage", fake_report_rich_coverage)
    monkeypatch.setattr(db_report.sys, "argv", ["db_report.py", "--report", "football-rich-coverage", "--date", "2026-05-20"])

    db_report.main()

    assert captured == [("2026-05-20", "football")]


def test_db_report_rich_coverage_outputs_basketball_buckets(monkeypatch, capsys):
    rows = [(1, "Lakers"), (2, "Celtics")]
    team_form_rows = {
        1: [
            ("rebounds", "api-basketball"),
            ("assists", "api-basketball"),
            ("steals", "api-basketball"),
            ("blocks", "api-basketball"),
            ("turnovers", "api-basketball"),
            ("fouls", "api-basketball"),
            ("fg_pct", "api-basketball"),
            ("three_pct", "api-basketball"),
            ("ft_pct", "api-basketball"),
            ("points_in_paint", "api-basketball"),
            ("fast_break_points", "api-basketball"),
        ],
        2: [("points", "league-profile-baseline")],
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

    db_report.report_rich_coverage("2026-05-20", "basketball")
    output = capsys.readouterr().out

    assert "BASKETBALL RICH COVERAGE" in output
    assert "Eligible: 1" in output
    assert "Rich: 1" in output
    assert "Baseline only: 1" in output
    assert "Partial: 0" in output
    assert "No data: 0" in output


def test_db_report_rich_coverage_falls_back_to_latest_finished_date(monkeypatch, capsys):
    rows = [(1, "Lakers")]
    team_form_rows = {
        1: [(key, "api-basketball") for key in [
            "rebounds",
            "assists",
            "steals",
            "blocks",
            "turnovers",
            "fouls",
            "fg_pct",
            "three_pct",
            "ft_pct",
            "points_in_paint",
            "fast_break_points",
        ]],
    }

    class FakeConn:
        def execute(self, query, params=None):
            if "SELECT id FROM sports" in query:
                return SimpleNamespace(fetchone=lambda: (1,))
            if "date(f.kickoff) <= ?" in query:
                return SimpleNamespace(fetchone=lambda: ("2026-05-19",))
            if "WHERE date(f.kickoff) = ? AND f.sport_id = ?" in query:
                fixture_date = params[0]
                found_rows = [] if fixture_date == "2026-05-20" else rows
                return SimpleNamespace(fetchall=lambda: found_rows)
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

    db_report.report_rich_coverage("2026-05-20", "basketball")
    output = capsys.readouterr().out

    assert "using latest available fixture date 2026-05-19" in output
    assert "Rich: 1" in output


def test_data_enrichment_agent_batch_summary_counts_hockey_and_volleyball_completion():
    results = [
        {
            "sport": "hockey",
            "status": "partial",
            "hockey_completion": {"needed": True, "success": True},
            "hockey_missing_rich_keys": ["hits"],
        },
        {
            "sport": "volleyball",
            "status": "failed",
            "volleyball_completion": {"needed": True, "success": False},
            "volleyball_missing_rich_keys": ["blocks"],
        },
    ]

    metrics = data_enrichment_agent._summarize_enrichment_results(results)

    assert metrics["hockey_rich_eligible"] == 1
    assert metrics["hockey_completed"] == 1
    assert metrics["hockey_still_missing_rich"] == 1
    assert metrics["volleyball_rich_eligible"] == 1
    assert metrics["volleyball_completed"] == 0
    assert metrics["volleyball_still_missing_rich"] == 1


def test_data_enrichment_agent_date_mode_dry_run_filters_sport_and_limit(monkeypatch, capsys):
    detected = [
        {"team": "Lakers", "sport": "basketball"},
        {"team": "Celtics", "sport": "basketball"},
        {"team": "Warriors", "sport": "basketball"},
        {"team": "Iga Swiatek", "sport": "tennis"},
    ]
    captured_entries = []
    preview_results = [
        {
            "team": "Lakers",
            "sport": "basketball",
            "status": "partial",
            "basketball_completion": {"needed": True, "success": False},
            "basketball_missing_rich_keys": ["assists"],
        },
        {
            "team": "Celtics",
            "sport": "basketball",
            "status": "failed",
            "basketball_completion": {"needed": True, "success": False},
            "basketball_missing_rich_keys": ["rebounds"],
        },
    ]

    monkeypatch.setattr(data_enrichment_agent, "_detect_missing_from_shortlist", lambda date_str, shortlist_override=None: detected)
    monkeypatch.setattr(
        data_enrichment_agent,
        "_preview_enrichment_results",
        lambda entries: captured_entries.extend(entries) or preview_results,
    )
    monkeypatch.setattr(
        agent_output.AgentOutput,
        "validate_input_contract",
        classmethod(lambda cls, step_id, date, contracts=None: {"status": "OK", "found": [], "missing": [], "warnings": []}),
    )
    monkeypatch.setattr(
        data_enrichment_agent.sys,
        "argv",
        [
            "data_enrichment_agent.py",
            "--date",
            "2026-05-20",
            "--sport",
            "basketball",
            "--limit",
            "2",
            "--dry-run",
            "--verbose",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        data_enrichment_agent.main()

    assert exc_info.value.code == 0
    assert captured_entries == detected[:2]

    output = capsys.readouterr().out
    summary_line = next(line for line in output.splitlines() if line.startswith("AGENT_SUMMARY:"))
    payload = json.loads(summary_line.split("AGENT_SUMMARY:", 1)[1])

    assert payload["metrics"]["dry_run_mode"] == 1
    assert payload["metrics"]["dry_run_candidates"] == 2
    assert payload["metrics"]["basketball_rich_eligible"] == 2
    assert payload["metrics"]["basketball_completed"] == 0
    assert payload["metrics"]["basketball_still_missing_rich"] == 2
