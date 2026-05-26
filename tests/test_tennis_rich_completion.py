"""Targeted tennis rich-completion tests."""

from types import SimpleNamespace

import data_enrichment_agent
import db_report
import rich_stats_probe
from _helpers import tennis_rich_completion as tennis_helper
from bet.models.normalized import NormalizedMatchStats
from bet.stats.fallback_chains import RICH_COMPLETION_POLICY
from bet.stats.rich_coverage import classify_rich_coverage


def _make_tennis_fixture_row(
    fixture_id: int,
    home: str,
    away: str,
    kickoff: str = "2026-05-20T18:00:00Z",
    competition: str = "Roland Garros",
) -> dict:
    return {
        "fixture_id": fixture_id,
        "kickoff": kickoff,
        "status": "finished",
        "competition": competition,
        "home_team": home,
        "away_team": away,
    }


def _full_tennis_rich_stats() -> dict:
    return {
        "aces": 8,
        "double_faults": 2,
        "first_serve_pct": 66.4,
        "first_serve_win_pct": 74.2,
        "second_serve_win_pct": 54.1,
        "break_points_saved_pct": 71.4,
        "hold_pct": 83.3,
        "break_pct": 41.7,
    }


def _partial_tennis_rich_stats() -> dict:
    return {
        "aces": 8,
        "double_faults": 2,
        "first_serve_pct": 66.4,
    }


def _supporting_tennis_rich_stats() -> dict:
    return {
        "first_serve_win_pct": 74.2,
        "second_serve_win_pct": 54.1,
        "break_points_saved_pct": 71.4,
        "hold_pct": 83.3,
        "break_pct": 41.7,
        "total_games": 22,
    }


def test_tennis_policy_declares_baseline_and_rich_contract():
    policy = RICH_COMPLETION_POLICY["tennis"]

    assert policy["baseline_keys"] == [
        "sets_won",
        "total_sets",
        "games_won",
        "total_games",
    ]
    assert policy["required_rich_keys"] == [
        "aces",
        "double_faults",
        "first_serve_pct",
        "first_serve_win_pct",
        "second_serve_win_pct",
        "break_points_saved_pct",
        "hold_pct",
        "break_pct",
    ]
    assert policy["canonical_source"] == "tennis-abstract"
    assert policy["supporting_sources"] == ["flashscore-tennis", "sackmann"]
    assert policy["aggregate_only_sources"] == ["sackmann-season-aggregate"]


def test_classify_rich_coverage_treats_espn_tennis_enriched_as_baseline_only():
    policy = RICH_COMPLETION_POLICY["tennis"]
    detail = classify_rich_coverage(
        [
            ("sets_won", "espn-tennis-enriched"),
            ("total_sets", "espn-tennis-enriched"),
            ("games_won", "espn-tennis-enriched"),
            ("total_games", "espn-tennis-enriched"),
        ],
        policy["required_rich_keys"],
        {policy["canonical_source"], *policy["supporting_sources"]},
        baseline_sources=set(policy["baseline_sources"]),
    )

    assert detail["bucket"] == "baseline_only"
    assert detail["eligible"] is True
    assert detail["sources"] == ["espn-tennis-enriched"]
    assert detail["rich_keys_found"] == []
    assert detail["missing_rich_keys"] == policy["required_rich_keys"]


def test_tennis_helper_persists_only_rich_keys_via_store_in_cache(monkeypatch):
    fixtures = [
        _make_tennis_fixture_row(501, "Iga Swiatek", "Aryna Sabalenka", "2026-05-18T18:00:00Z"),
    ]
    store_calls = []

    monkeypatch.setattr(
        tennis_helper,
        "_get_recent_tennis_fixtures",
        lambda team_name, limit: (fixtures, "17"),
    )
    monkeypatch.setattr(
        tennis_helper,
        "_store_in_cache",
        lambda *args, **kwargs: store_calls.append((args, kwargs)),
    )

    ta_match = NormalizedMatchStats(
        fixture_id="ta_iga_2026-05-18_aryna",
        source="tennis-abstract",
        sport="tennis",
        home_team="Iga Swiatek",
        away_team="Aryna Sabalenka",
        date="2026-05-18",
        stats={
            **_full_tennis_rich_stats(),
            "sets_won": 2,
            "total_games": 22,
            "surface": "Clay",
        },
    )

    clients = {
        "tennis-abstract": SimpleNamespace(
            api_name="tennis-abstract",
            is_available=lambda: True,
            get_fixture_stats_for_player=lambda team_name, last_n=10: [ta_match],
        ),
        "sackmann": SimpleNamespace(
            api_name="sackmann",
            is_available=lambda: True,
            resolve_team_id=lambda team_name: team_name,
            get_team_last_fixtures=lambda team_id, last_n=10: [],
            get_fixture_stats=lambda fixture_id: None,
            get_player_season_stats=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("season stats must not be used")),
        ),
    }
    monkeypatch.setattr(tennis_helper, "get_client", lambda api_name, rate_limiter=None: clients[api_name])

    result = tennis_helper.complete_tennis_rich_stats("Iga Swiatek", "tennis", max_fixtures=1)

    assert result["status"] == "enriched"
    assert result["source"] == "tennis-abstract"
    assert result["fixtures_scanned"] == 1
    assert result["matches_persisted"] == 1
    assert result["rich_keys_found"] == list(RICH_COMPLETION_POLICY["tennis"]["required_rich_keys"])
    assert store_calls, "tennis helper must persist through _store_in_cache"
    persisted_matches = store_calls[0][0][2]
    assert len(persisted_matches) == 1
    assert persisted_matches[0].stats == _full_tennis_rich_stats()
    assert "sets_won" not in persisted_matches[0].stats
    assert "total_games" not in persisted_matches[0].stats


def test_tennis_helper_uses_supporting_source_without_season_aggregates(monkeypatch):
    fixtures = [
        _make_tennis_fixture_row(502, "Iga Swiatek", "Aryna Sabalenka", "2026-05-18T18:00:00Z"),
    ]
    store_calls = []
    season_calls = []

    monkeypatch.setattr(
        tennis_helper,
        "_get_recent_tennis_fixtures",
        lambda team_name, limit: (fixtures, "17"),
    )
    monkeypatch.setattr(
        tennis_helper,
        "_store_in_cache",
        lambda *args, **kwargs: store_calls.append((args, kwargs)),
    )

    ta_match = NormalizedMatchStats(
        fixture_id="ta_iga_2026-05-18_aryna",
        source="tennis-abstract",
        sport="tennis",
        home_team="Iga Swiatek",
        away_team="Aryna Sabalenka",
        date="2026-05-18",
        stats=_partial_tennis_rich_stats(),
    )
    sack_fixture = SimpleNamespace(fixture_id="sack_20260518_1")
    sack_match = NormalizedMatchStats(
        fixture_id="sack_20260518_1",
        source="sackmann",
        sport="tennis",
        home_team="Iga Swiatek",
        away_team="Aryna Sabalenka",
        date="2026-05-18",
        stats=_supporting_tennis_rich_stats(),
    )

    clients = {
        "tennis-abstract": SimpleNamespace(
            api_name="tennis-abstract",
            is_available=lambda: True,
            get_fixture_stats_for_player=lambda team_name, last_n=10: [ta_match],
        ),
        "sackmann": SimpleNamespace(
            api_name="sackmann",
            is_available=lambda: True,
            resolve_team_id=lambda team_name: team_name,
            get_team_last_fixtures=lambda team_id, last_n=10: [sack_fixture],
            get_fixture_stats=lambda fixture_id: sack_match,
            get_player_season_stats=lambda *args, **kwargs: season_calls.append((args, kwargs)),
        ),
    }
    monkeypatch.setattr(tennis_helper, "get_client", lambda api_name, rate_limiter=None: clients[api_name])

    result = tennis_helper.complete_tennis_rich_stats("Iga Swiatek", "tennis", max_fixtures=1)

    assert season_calls == []
    assert result["status"] == "enriched"
    assert result["rich_keys_found"] == list(RICH_COMPLETION_POLICY["tennis"]["required_rich_keys"])
    assert store_calls, "tennis helper must persist enriched matches"
    assert "total_games" not in store_calls[0][0][2][0].stats


def test_data_enrichment_agent_routes_tennis_completion_and_summary(monkeypatch):
    baseline_match = NormalizedMatchStats(
        fixture_id="9001",
        source="espn-tennis",
        sport="tennis",
        home_team="Iga Swiatek",
        away_team="Aryna Sabalenka",
        date="2026-05-20",
        stats={"sets_won": {"home": 2, "away": 1}},
    )

    client = SimpleNamespace(api_name="espn-tennis", is_available=lambda: True)
    monkeypatch.setattr(data_enrichment_agent, "FALLBACK_CHAINS", {"tennis": ["espn-tennis"]})
    monkeypatch.setattr(data_enrichment_agent, "_source_is_down", lambda *_: False)
    monkeypatch.setattr(data_enrichment_agent, "get_client", lambda *args, **kwargs: client)
    monkeypatch.setattr(data_enrichment_agent, "fetch_team_stats", lambda *args, **kwargs: [baseline_match])
    monkeypatch.setattr(data_enrichment_agent, "_store_in_cache", lambda *args, **kwargs: None)

    coverage_details = iter(
        [
            {
                "bucket": "baseline_only",
                "eligible": True,
                "stat_keys": ["sets_won", "total_sets", "games_won", "total_games"],
                "sources": ["espn-tennis-enriched"],
                "rich_keys_found": [],
                "missing_rich_keys": list(RICH_COMPLETION_POLICY["tennis"]["required_rich_keys"]),
            },
            {
                "bucket": "partial",
                "eligible": True,
                "stat_keys": ["sets_won", "total_sets", "games_won", "total_games", "hold_pct"],
                "sources": ["espn-tennis-enriched", "tennis-abstract"],
                "rich_keys_found": ["hold_pct"],
                "missing_rich_keys": [
                    "aces",
                    "double_faults",
                    "first_serve_pct",
                    "first_serve_win_pct",
                    "second_serve_win_pct",
                    "break_points_saved_pct",
                    "break_pct",
                ],
            },
        ]
    )
    monkeypatch.setattr(data_enrichment_agent, "_get_tennis_coverage_detail", lambda team_name: next(coverage_details))

    helper_calls = []

    def fake_completion(team_name, sport, max_fixtures=5):
        helper_calls.append((team_name, sport, max_fixtures))
        return {
            "team": team_name,
            "sport": sport,
            "source": "tennis-abstract",
            "status": "partial",
            "fixtures_scanned": 1,
            "matches_persisted": 1,
            "rich_keys_found": ["hold_pct"],
            "missing_rich_keys": [
                "aces",
                "double_faults",
                "first_serve_pct",
                "first_serve_win_pct",
                "second_serve_win_pct",
                "break_points_saved_pct",
                "break_pct",
            ],
            "error": None,
            "failure_reason": None,
        }

    monkeypatch.setattr(data_enrichment_agent, "complete_tennis_rich_stats", fake_completion)

    result = data_enrichment_agent.enrich_team("Iga Swiatek", "tennis")

    assert helper_calls == [("Iga Swiatek", "tennis", 5)]
    assert result["status"] == "partial"
    assert result["source"] == "espn-tennis"
    assert result["supplementary_sources"] == ["tennis-abstract"]
    assert result["stats_found"]["hold_pct"] is True
    assert result["tennis_completion"]["attempted"] is True
    assert result["tennis_completion"]["success"] is True
    assert result["tennis_completion"]["status"] == "partial"
    assert result["tennis_completion"]["source"] == "tennis-abstract"
    assert result["tennis_completion"]["rich_keys_added"] == ["hold_pct"]
    assert result["tennis_completion"]["baseline_only"] is False


def test_data_enrichment_agent_batch_summary_counts_tennis_completion():
    results = [
        {
            "sport": "tennis",
            "status": "partial",
            "tennis_completion": {"needed": True, "success": True, "baseline_only": False},
            "tennis_missing_rich_keys": ["hold_pct"],
        },
        {
            "sport": "tennis",
            "status": "failed",
            "tennis_completion": {"needed": True, "success": False, "baseline_only": True},
            "tennis_missing_rich_keys": ["aces"],
        },
        {
            "sport": "basketball",
            "status": "enriched",
            "basketball_completion": {"needed": False, "success": False},
        },
    ]

    metrics = data_enrichment_agent._summarize_enrichment_results(results)

    assert metrics["tennis_rich_eligible"] == 2
    assert metrics["tennis_completed"] == 1
    assert metrics["tennis_still_missing_rich"] == 2
    assert metrics["tennis_baseline_only"] == 1
    assert metrics["enriched"] == 1
    assert metrics["total"] == 3


def test_set_result_status_marks_fully_rich_tennis_as_enriched():
    result = {
        "sport": "tennis",
        "stats_found": {
            key: True for key in RICH_COMPLETION_POLICY["tennis"]["required_rich_keys"]
        },
    }

    data_enrichment_agent._set_result_status(result)

    assert result["tennis_rich_complete"] is True
    assert result["status"] == "enriched"


def test_apply_tennis_completion_skips_when_coverage_is_already_rich(monkeypatch):
    policy = RICH_COMPLETION_POLICY["tennis"]
    rich_detail = {
        "bucket": "rich",
        "eligible": False,
        "stat_keys": list(policy["required_rich_keys"]),
        "sources": ["tennis-abstract"],
        "rich_keys_found": list(policy["required_rich_keys"]),
        "missing_rich_keys": [],
    }

    monkeypatch.setattr(data_enrichment_agent, "_get_tennis_coverage_detail", lambda team_name: rich_detail)
    monkeypatch.setattr(
        data_enrichment_agent,
        "complete_tennis_rich_stats",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("helper should not run for rich coverage")),
    )

    result = data_enrichment_agent._apply_tennis_rich_completion(
        {
            "team": "Iga Swiatek",
            "sport": "tennis",
            "status": "partial",
            "stats_found": {},
            "source": "tennis-abstract",
            "error": None,
        }
    )

    assert result["status"] == "enriched"
    assert result["tennis_rich_complete"] is True
    assert result["tennis_completion"]["needed"] is False
    assert result["tennis_completion"]["attempted"] is False
    assert result["tennis_completion"]["status"] == "not_needed"
    assert result["tennis_completion"]["missing_after"] == []


def test_apply_tennis_completion_skips_known_missing_team(monkeypatch):
    policy = RICH_COMPLETION_POLICY["tennis"]
    baseline_detail = {
        "bucket": "baseline_only",
        "eligible": True,
        "stat_keys": list(policy["baseline_keys"]),
        "sources": ["espn-tennis-enriched"],
        "rich_keys_found": [],
        "missing_rich_keys": list(policy["required_rich_keys"]),
    }

    monkeypatch.setattr(data_enrichment_agent, "_get_tennis_coverage_detail", lambda team_name: baseline_detail)
    monkeypatch.setattr(
        data_enrichment_agent,
        "complete_tennis_rich_stats",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("helper should not run for known missing team")),
    )

    result = data_enrichment_agent._apply_tennis_rich_completion(
        {
            "team": "Unknown Player",
            "sport": "tennis",
            "status": "failed",
            "stats_found": {},
            "source": None,
            "error": "Known missing team (cached 404): Unknown Player",
        }
    )

    assert result["status"] == "partial"
    assert result["tennis_completion"]["needed"] is False
    assert result["tennis_completion"]["attempted"] is False
    assert result["tennis_completion"]["success"] is False
    assert result["tennis_completion"]["status"] == "skipped"
    assert result["tennis_completion"]["baseline_only"] is True
    assert result["tennis_completion"]["missing_after"] == list(policy["required_rich_keys"])


def test_probe_reports_tennis_rich_coverage_without_writes(monkeypatch):
    teams = [(1, "Iga Swiatek"), (2, "Aryna Sabalenka")]
    team_form_rows = {
        1: [(key, "tennis-abstract") for key in RICH_COMPLETION_POLICY["tennis"]["required_rich_keys"]],
        2: [
            ("sets_won", "espn-tennis-enriched"),
            ("total_sets", "espn-tennis-enriched"),
            ("games_won", "espn-tennis-enriched"),
            ("total_games", "espn-tennis-enriched"),
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

    monkeypatch.setattr(rich_stats_probe, "_get_teams_for_date", lambda sport, betting_date: teams)
    monkeypatch.setattr(rich_stats_probe, "_get_sport_id", lambda sport: 1)
    monkeypatch.setattr(rich_stats_probe, "get_db", lambda: FakeDB())

    result = rich_stats_probe.probe_rich_coverage("tennis", "2026-05-20", limit=10)

    assert result["fixtures_scanned"] == 2
    assert result["eligible"] == 1
    assert result["rich"] == 1
    assert result["baseline_only"] == 1
    assert result["partial"] == 0
    assert result["no_data"] == 0
    assert result["source_choice"] == "tennis-abstract"


def test_db_report_rich_coverage_outputs_tennis_buckets(monkeypatch, capsys):
    rows = [(1, "Iga Swiatek"), (2, "Aryna Sabalenka")]
    team_form_rows = {
        1: [(key, "tennis-abstract") for key in RICH_COMPLETION_POLICY["tennis"]["required_rich_keys"]],
        2: [
            ("sets_won", "espn-tennis-enriched"),
            ("total_sets", "espn-tennis-enriched"),
            ("games_won", "espn-tennis-enriched"),
            ("total_games", "espn-tennis-enriched"),
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

    db_report.report_rich_coverage("2026-05-20", "tennis")
    output = capsys.readouterr().out

    assert "TENNIS RICH COVERAGE" in output
    assert "Eligible: 1" in output
    assert "Rich: 1" in output
    assert "Baseline only: 1" in output
    assert "Partial: 0" in output
    assert "No data: 0" in output