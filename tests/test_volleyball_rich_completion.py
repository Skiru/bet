"""Targeted volleyball rich-completion tests."""

from types import SimpleNamespace

import _helpers as volleyball_helpers
import data_enrichment_agent
import db_report
import rich_stats_probe
from _helpers import volleyball_rich_completion as volleyball_helper_module
from bet.api_clients.api_volleyball import APIVolleyballClient, STAT_TYPE_MAP
from bet.api_clients.rate_limiter import RateLimiter
from bet.api_clients.volleyball_data import VolleyballDataClient
from bet.models.normalized import NormalizedMatchStats
from bet.stats.fallback_chains import RICH_COMPLETION_POLICY


def _fixture(
    fixture_id: int,
    competition: str = "FIVB Nations League",
    fixture_source: str = "api-volleyball",
    provider_ids: dict[str, str] | None = None,
) -> dict:
    if provider_ids is None:
        provider_ids = {
            "api-volleyball": f"api-{fixture_id}",
            "espn-volleyball": f"espn-{fixture_id}",
        }

    return {
        "fixture_id": fixture_id,
        "external_id": provider_ids.get(fixture_source, f"fixture-{fixture_id}"),
        "fixture_source": fixture_source,
        "kickoff": "2026-05-20T18:00:00Z",
        "status": "finished",
        "competition": competition,
        "home_team": "Poland",
        "away_team": "Brazil",
        "provider_ids": provider_ids,
    }


def test_volleyball_policy_declares_minimum_rich_contract():
    policy = RICH_COMPLETION_POLICY["volleyball"]

    assert policy["required_rich_keys"] == ["aces", "blocks", "hitting_pct", "points"]
    assert policy["canonical_source"] == "api-volleyball"
    assert policy["supporting_sources"] == ["espn-volleyball"]
    assert policy["aggregate_only_sources"] == ["volleybox"]


def test_api_volleyball_normalizes_attack_pct_to_hitting_pct(monkeypatch):
    client = APIVolleyballClient(rate_limiter=RateLimiter())
    client.api_key = "test-key"

    monkeypatch.setattr(client, "_check_api_key", lambda: True)
    monkeypatch.setattr(client, "_check_cache", lambda *args, **kwargs: None)
    monkeypatch.setattr(client, "_save_cache", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        client,
        "_request",
        lambda path, params=None: {
            "response": [
                {
                    "team": {"name": "Poland"},
                    "statistics": [
                        {"type": "Attack %", "home": "51.2", "away": "47.8"},
                        {"type": "Aces", "home": "7", "away": "4"},
                        {"type": "Blocks", "home": "9", "away": "6"},
                        {"type": "Points", "home": "78", "away": "71"},
                    ],
                },
                {
                    "team": {"name": "Brazil"},
                    "statistics": [
                        {"type": "Attack %", "home": "51.2", "away": "47.8"},
                        {"type": "Aces", "home": "7", "away": "4"},
                        {"type": "Blocks", "home": "9", "away": "6"},
                        {"type": "Points", "home": "78", "away": "71"},
                    ],
                },
            ]
        },
    )

    result = client.get_fixture_stats("601")

    assert STAT_TYPE_MAP["attack_pct"] == "hitting_pct"
    assert len(result) == 1
    assert result[0].stats["hitting_pct"] == {"home": 51.2, "away": 47.8}
    assert "attack_pct" not in result[0].stats


def test_volleyball_data_match_stats_prefers_canonical_provider_and_normalizes_hitting_pct(monkeypatch):
    client = object.__new__(VolleyballDataClient)
    calls = []

    def fake_get_client(name):
        calls.append(name)
        if name == "api-volleyball":
            return SimpleNamespace(
                get_fixture_stats=lambda fixture_id: [
                    SimpleNamespace(
                        stats={
                            "attack_pct": {"home": 50.1, "away": 44.4},
                            "points": {"home": 75, "away": 69},
                        }
                    )
                ]
            )
        raise AssertionError("espn-volleyball should not run after canonical success")

    monkeypatch.setattr("bet.api_clients.get_client", fake_get_client)

    result = client.fetch_match_stats("777")

    assert calls == ["api-volleyball"]
    assert result == {
        "hitting_pct": {"home": 50.1, "away": 44.4},
        "points": {"home": 75, "away": 69},
    }


def test_volleyball_helper_persists_via_store_in_cache_and_supporting_fill(monkeypatch):
    monkeypatch.setattr(data_enrichment_agent, "_is_known_missing", lambda team_name, sport: False)
    store_calls = []
    monkeypatch.setattr(volleyball_helper_module, "_get_recent_volleyball_fixtures", lambda team_name, limit: ([_fixture(801)], "17"))
    monkeypatch.setattr(volleyball_helper_module, "_store_in_cache", lambda *args, **kwargs: store_calls.append((args, kwargs)))

    partial_match = NormalizedMatchStats(
        fixture_id="801",
        source="api-volleyball",
        sport="volleyball",
        home_team="Poland",
        away_team="Brazil",
        date="2026-05-20",
        stats={"aces": {"home": 7, "away": 4}, "blocks": {"home": 9, "away": 6}},
    )
    supporting_match = NormalizedMatchStats(
        fixture_id="801",
        source="espn-volleyball",
        sport="volleyball",
        home_team="Poland",
        away_team="Brazil",
        date="2026-05-20",
        stats={
            "kills": {"home": 42, "away": 39},
            "hitting_pct": {"home": 51.2, "away": 47.8},
            "points": {"home": 78, "away": 71},
        },
    )
    clients = {
        "api-volleyball": SimpleNamespace(is_available=lambda: True, get_fixture_stats=lambda fixture_id: [partial_match]),
        "espn-volleyball": SimpleNamespace(is_available=lambda: True, get_fixture_stats=lambda fixture_id: [supporting_match]),
    }
    provider_calls = []

    def _get_client(api_name, rate_limiter=None):
        client = clients[api_name]

        def _get_fixture_stats(fixture_id):
            provider_calls.append((api_name, fixture_id))
            return client.get_fixture_stats(fixture_id)

        return SimpleNamespace(is_available=client.is_available, get_fixture_stats=_get_fixture_stats)

    monkeypatch.setattr(volleyball_helper_module, "get_client", _get_client)

    result = volleyball_helpers.complete_volleyball_rich_stats("Poland", "volleyball", max_fixtures=1)

    assert result["status"] == "enriched"
    assert result["source"] == "api-volleyball"
    assert result["rich_keys_found"] == RICH_COMPLETION_POLICY["volleyball"]["required_rich_keys"]
    assert provider_calls == [("api-volleyball", "api-801"), ("espn-volleyball", "espn-801")]
    assert store_calls
    persisted = store_calls[0][0][2][0]
    assert isinstance(persisted, NormalizedMatchStats)
    assert persisted.fixture_id == "api-801"
    assert persisted.stats["kills"] == {"home": 42, "away": 39}
    assert store_calls[0][0][3] == "api-volleyball"


def test_volleyball_helper_requires_source_specific_fixture_ids(monkeypatch):
    fixtures = [_fixture(802, fixture_source="sofascore", provider_ids={})]
    store_calls = []
    provider_calls = []

    monkeypatch.setattr(
        volleyball_helpers,
        "_get_recent_volleyball_fixtures",
        lambda team_name, limit: (fixtures, "17"),
    )
    monkeypatch.setattr(
        volleyball_helpers,
        "_store_in_cache",
        lambda *args, **kwargs: store_calls.append((args, kwargs)),
    )

    def _unexpected_client(api_name, rate_limiter=None):
        provider_calls.append(api_name)
        return SimpleNamespace(is_available=lambda: True, get_fixture_stats=lambda fixture_id: [])

    monkeypatch.setattr(volleyball_helper_module, "get_client", _unexpected_client)

    result = volleyball_helpers.complete_volleyball_rich_stats("Poland", "volleyball", max_fixtures=1)

    assert result["status"] == "failed"
    assert result["failure_reason"] == "missing_source_fixture_id"
    assert result["matches_persisted"] == 0
    assert not provider_calls
    assert not store_calls


def test_volleyball_helper_marks_espn_empty_non_fivb_as_unsupported_skip(monkeypatch):
    fixtures = [_fixture(803, competition="Polish League")]
    store_calls = []

    monkeypatch.setattr(
        volleyball_helpers,
        "_get_recent_volleyball_fixtures",
        lambda team_name, limit: (fixtures, "17"),
    )
    monkeypatch.setattr(
        volleyball_helpers,
        "_store_in_cache",
        lambda *args, **kwargs: store_calls.append((args, kwargs)),
    )

    clients = {
        "api-volleyball": SimpleNamespace(is_available=lambda: True, get_fixture_stats=lambda fixture_id: []),
        "espn-volleyball": SimpleNamespace(is_available=lambda: True, get_fixture_stats=lambda fixture_id: []),
    }
    monkeypatch.setattr(volleyball_helper_module, "get_client", lambda api_name, rate_limiter=None: clients[api_name])

    result = volleyball_helpers.complete_volleyball_rich_stats("Poland", "volleyball", max_fixtures=1)

    assert result["status"] == "failed"
    assert result["failure_reason"] == "unsupported_league_skip"
    assert result["matches_persisted"] == 0
    assert not store_calls


def test_data_enrichment_agent_routes_volleyball_completion_and_summary(monkeypatch):
    baseline_match = NormalizedMatchStats(
        fixture_id="9101",
        source="espn-volleyball",
        sport="volleyball",
        home_team="Poland",
        away_team="Brazil",
        date="2026-05-20",
        stats={"points": {"home": 75, "away": 69}},
    )
    client = SimpleNamespace(api_name="espn-volleyball", is_available=lambda: True)
    monkeypatch.setattr(data_enrichment_agent, "FALLBACK_CHAINS", {"volleyball": ["espn-volleyball"]})
    monkeypatch.setattr(data_enrichment_agent, "_source_is_down", lambda *_: False)
    monkeypatch.setattr(data_enrichment_agent, "get_client", lambda *args, **kwargs: client)
    monkeypatch.setattr(data_enrichment_agent, "fetch_team_stats", lambda *args, **kwargs: [baseline_match])
    monkeypatch.setattr(data_enrichment_agent, "_store_in_cache", lambda *args, **kwargs: None)
    monkeypatch.setattr(data_enrichment_agent, "_is_known_missing", lambda team_name, sport: False)

    routed = []

    def fake_apply(result, max_fixtures=5):
        routed.append((result["team"], result["sport"], max_fixtures, dict(result["stats_found"])))
        result["status"] = "enriched"
        result["source"] = "api-volleyball"
        result["supplementary_sources"] = ["espn-volleyball"]
        result["stats_found"].update({"aces": True, "blocks": True, "hitting_pct": True})
        result["volleyball_completion"] = {
            "needed": True,
            "attempted": True,
            "success": True,
            "status": "enriched",
            "source": "api-volleyball",
            "rich_keys_added": ["aces", "blocks", "hitting_pct"],
        }
        result["volleyball_missing_rich_keys"] = []
        return result

    monkeypatch.setattr(data_enrichment_agent, "_apply_volleyball_rich_completion", fake_apply)

    result = data_enrichment_agent.enrich_team("Poland", "volleyball")
    metrics = data_enrichment_agent._summarize_enrichment_results([result])

    assert routed == [("Poland", "volleyball", 5, {"points": True})]
    assert result["status"] == "enriched"
    assert result["source"] == "api-volleyball"
    assert result["supplementary_sources"] == ["espn-volleyball"]
    assert result["volleyball_completion"]["attempted"] is True
    assert result["volleyball_completion"]["rich_keys_added"] == ["aces", "blocks", "hitting_pct"]
    assert metrics["volleyball_rich_eligible"] == 1
    assert metrics["volleyball_completed"] == 1
    assert metrics["volleyball_still_missing_rich"] == 0


def test_volleyball_probe_and_report_do_not_promote_aggregate_only_rows(monkeypatch, capsys):
    teams = [(1, "Poland"), (2, "Brazil")]
    team_form_rows = {
        1: [(key, "api-volleyball") for key in RICH_COMPLETION_POLICY["volleyball"]["required_rich_keys"]],
        2: [(key, "volleybox") for key in RICH_COMPLETION_POLICY["volleyball"]["required_rich_keys"]],
    }

    class ProbeConn:
        def execute(self, query, params=None):
            if not str(query).strip().upper().startswith("SELECT"):
                raise AssertionError(f"Unexpected non-read query: {query}")
            return SimpleNamespace(fetchall=lambda: team_form_rows[params[0]])

    class ProbeDB:
        def __enter__(self):
            return ProbeConn()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(rich_stats_probe, "_get_teams_for_date", lambda sport, betting_date: teams)
    monkeypatch.setattr(rich_stats_probe, "_get_sport_id", lambda sport: 1)
    monkeypatch.setattr(rich_stats_probe, "get_db", lambda: ProbeDB())

    probe = rich_stats_probe.probe_rich_coverage("volleyball", "2026-05-20", limit=10)

    assert probe["fixtures_scanned"] == 2
    assert probe["rich"] == 1
    assert probe["partial"] == 1
    assert probe["source_choice"] == "api-volleyball"

    class ReportConn:
        def execute(self, query, params=None):
            if "SELECT id FROM sports" in query:
                return SimpleNamespace(fetchone=lambda: (1,))
            if "JOIN teams t ON t.id IN (f.home_team_id, f.away_team_id)" in query:
                return SimpleNamespace(fetchall=lambda: teams)
            if "FROM team_form" in query:
                return SimpleNamespace(fetchall=lambda: team_form_rows[params[0]])
            raise AssertionError(f"Unexpected query: {query}")

    class ReportDB:
        def __enter__(self):
            return ReportConn()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(db_report, "get_db", lambda: ReportDB())
    db_report.report_rich_coverage("2026-05-20", "volleyball")
    output = capsys.readouterr().out

    assert "VOLLEYBALL RICH COVERAGE" in output
    assert "Eligible: 1" in output
    assert "Rich: 1" in output
    assert "Partial: 1" in output
