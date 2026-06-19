from __future__ import annotations

import json
import socket
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
import yaml

from bet.enrichment.football_data_foundation.connector_kernel.drift import (
    DriftClassification,
    evaluate_drift,
)
from bet.enrichment.football_data_foundation.contracts import (
    NormalizedFootballDataRecord,
    RawFootballDataBundle,
)
from bet.enrichment.football_data_foundation.event_model_bridges.floodlight_bridge import (
    FloodlightBridge,
)
from bet.enrichment.football_data_foundation.event_model_bridges.kloppy_bridge import (
    KloppyBridge,
)
from bet.enrichment.football_data_foundation.event_model_bridges.mplsoccer_bridge import (
    MplSoccerBridge,
)
from bet.enrichment.football_data_foundation.event_model_bridges.socceraction_bridge import (
    SoccerActionBridge,
)
from bet.enrichment.football_data_foundation.fingerprints import (
    compute_data_fingerprint,
    compute_schema_fingerprint,
)
from bet.enrichment.football_data_foundation.normalizers import (
    flatten_multiindex_columns,
    normalize_numeric,
    normalize_value,
)
from bet.enrichment.football_data_foundation.open_reference_sources.football_data_org_bridge import (
    FootballDataOrgBridge,
)
from bet.enrichment.football_data_foundation.open_reference_sources.kaggle_european_soccer import (
    KaggleEuropeanSoccerConnector,
)
from bet.enrichment.football_data_foundation.open_reference_sources.openfootball import (
    OpenFootballConnector,
)
from bet.enrichment.football_data_foundation.open_reference_sources.statsbomb_open_data import (
    StatsBombOpenDataConnector,
)
from bet.enrichment.football_data_foundation.open_reference_sources.statsbombpy_bridge import (
    StatsBombPyBridge,
)
from bet.enrichment.football_data_foundation.rich_unofficial_sources.fotmob_probe import (
    FotMobProbe,
)
from bet.enrichment.football_data_foundation.rich_unofficial_sources.scraperfc_sofascore_bridge import (
    ScraperFCSofascoreBridge,
)
from bet.enrichment.football_data_foundation.rich_unofficial_sources.sofascore_rich_probe import (
    SofaScoreRichProbe,
)
from bet.enrichment.football_data_foundation.soccerdata_sources.clubelo import (
    ClubEloConnector,
)
from bet.enrichment.football_data_foundation.soccerdata_sources.espn import (
    ESPNConnector,
)
from bet.enrichment.football_data_foundation.soccerdata_sources.fbref import (
    FBrefConnector,
)
from bet.enrichment.football_data_foundation.soccerdata_sources.fivethirtyeight import (
    FiveThirtyEightConnector,
)
from bet.enrichment.football_data_foundation.soccerdata_sources.matchhistory import (
    MatchHistoryConnector,
)
from bet.enrichment.football_data_foundation.soccerdata_sources.sofascore import (
    SofascoreConnector,
)
from bet.enrichment.football_data_foundation.soccerdata_sources.sofifa import (
    SoFIFAConnector,
)
from bet.enrichment.football_data_foundation.soccerdata_sources.understat import (
    UnderstatConnector,
)
from bet.enrichment.football_data_foundation.soccerdata_sources.whoscored import (
    WhoScoredConnector,
)
from bet.integration.source_result import SourceOperationResult, SourceResultStatus

REPO_ROOT = Path(__file__).resolve().parents[3]
ROUTING_PATH = REPO_ROOT / "config/football_routing.yaml"
REPORT_PATH = REPO_ROOT / "reports/football_data_foundation/source_matrix.json"
SUMMARY_PATH = REPO_ROOT / "reports/football_data_foundation/capability_summary.json"
FIXTURE_ROOT = REPO_ROOT / "tests/fixtures/football_data_foundation"

SOURCE_MATRIX = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
SOURCE_INDEX = {entry["source_id"]: entry for entry in SOURCE_MATRIX["sources"]}


def source_operations(source_id: str) -> list[dict[str, object]]:
    return list(SOURCE_INDEX[source_id]["operations"])


def source_operation_names(source_id: str) -> list[str]:
    return [str(operation["operation"]) for operation in source_operations(source_id)]


def operation_entry(source_id: str, operation_name: str) -> dict[str, object]:
    for operation in source_operations(source_id):
        if operation["operation"] == operation_name:
            return operation
    raise AssertionError(f"missing operation {operation_name} for {source_id}")


def load_fixture(relative_path: str) -> object:
    return json.loads((FIXTURE_ROOT / relative_path).read_text(encoding="utf-8"))


class FakeFBref:
    def __init__(self, **kwargs: object) -> None:
        self.init_kwargs = kwargs
        self.method_calls: list[dict[str, object]] = []

    def read_team_match_stats(self, **kwargs: object) -> pd.DataFrame:
        self.method_calls.append(kwargs)
        return pd.DataFrame([{"Squad": "Arsenal", "Gls": 3}])


class FakeFootballDataOrgClient:
    def get_fixtures_result(
        self, date: str, competition: str | None = None
    ) -> SourceOperationResult[list[dict[str, str]]]:
        return SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=[{"fixture_id": "123", "date": date, "competition": competition or "PL"}],
            request_identity="FootballDataOrgClient.get_fixtures_result",
            parser_diagnostics={"mode": "fake_client"},
            parser_version="test",
            normalization_version="test",
        )


def test_contracts() -> None:
    bundle = RawFootballDataBundle(
        provider="test",
        source_family="test",
        source_class="test",
        operation="test",
        request_identity="test",
        retrieved_at=datetime.now(UTC),
        source_library="test",
        source_library_version="test",
        parser_version="test",
        schema_fingerprint="test",
        data_fingerprint="test",
        row_count=1,
    )
    assert bundle.provider == "test"

    record = NormalizedFootballDataRecord(
        provider="test",
        source_family="test",
        source_class="test",
        operation="test",
        request_identity="test",
        normalized_at=datetime.now(UTC),
        normalization_version="test",
        schema_fingerprint="test",
        data_fingerprint="test",
        row_count=1,
    )
    assert record.provider == "test"


def test_fingerprints_and_normalizers() -> None:
    df = pd.DataFrame({"col1": [1, 2], "col2": ["a", "b"]})
    assert compute_schema_fingerprint(df) == compute_schema_fingerprint(df)
    assert compute_data_fingerprint(df) == compute_data_fingerprint(df)

    df_multi = pd.DataFrame([[1, 2], [3, 4]])
    df_multi.columns = pd.MultiIndex.from_tuples([("a", "b"), ("c", "d")])
    flat_df = flatten_multiindex_columns(df_multi)
    assert "a_b" in flat_df.columns
    assert "c_d" in flat_df.columns
    assert normalize_value(None) == "UNKNOWN"
    assert normalize_numeric(None) == "UNKNOWN"
    assert normalize_numeric(0) == 0


def test_routing_config_contains_no_yaml_aliases_for_provider_identity() -> None:
    routing_text = ROUTING_PATH.read_text(encoding="utf-8")
    assert "anchors:" not in routing_text
    assert "&sdb" not in routing_text
    assert "*sdb" not in routing_text


def test_routing_config_changes_are_additive_and_preserve_existing_routes() -> None:
    routing = yaml.safe_load(ROUTING_PATH.read_text(encoding="utf-8"))
    current_discovery_routes = routing["routing"]["current_discovery"]["production_routes"]
    assert {
        (route["provider"], route["competition_scope"], route["season_scope"], route["mode"], route["selectable_status"])
        for route in current_discovery_routes
    } == {
        ("espn", "football:eng.1", "current", "shadow", "CERTIFIED_SELECTABLE"),
        ("football-data", "football:eng.1", "current", "shadow", "CERTIFIED_SELECTABLE"),
    }

    detailed_metrics_shadow = routing["routing"]["detailed_metrics"]["shadow_routes"]
    assert [route["provider"] for route in detailed_metrics_shadow] == ["sportdb", "sportdb"]


def test_source_matrix_contains_every_required_source_family() -> None:
    expected_sources = {
        "soccerdata/ClubElo",
        "soccerdata/ESPN",
        "soccerdata/FBref",
        "soccerdata/FiveThirtyEight",
        "soccerdata/MatchHistory",
        "soccerdata/Sofascore",
        "soccerdata/SoFIFA",
        "soccerdata/Understat",
        "soccerdata/WhoScored",
        "open_reference/StatsBombOpenData",
        "open_reference/StatsBombPy",
        "open_reference/KaggleEuropeanSoccer",
        "open_reference/FootballDataOrg",
        "open_reference/OpenFootball",
        "rich_unofficial/FotMobProbe",
        "rich_unofficial/SofaScoreRichProbe",
        "rich_unofficial/ScraperFCSofascore",
        "event_model/SoccerAction",
        "event_model/Kloppy",
        "event_model/Floodlight",
        "event_model/MplSoccer",
    }
    assert set(SOURCE_INDEX) == expected_sources


@pytest.mark.parametrize(
    ("source_id", "expected_operations"),
    [
        ("soccerdata/ClubElo", ["read_by_date", "read_team_history"]),
        ("soccerdata/ESPN", ["read_schedule", "read_matchsheet", "read_lineup"]),
        (
            "soccerdata/FBref",
            [
                "read_leagues",
                "read_seasons",
                "read_schedule",
                "read_team_season_stats",
                "read_team_match_stats",
                "read_player_season_stats",
                "read_player_match_stats",
                "read_lineup",
                "read_events",
            ],
        ),
        (
            "soccerdata/Understat",
            [
                "read_leagues",
                "read_seasons",
                "read_schedule",
                "read_team_match_stats",
                "read_player_season_stats",
                "read_player_match_stats",
                "read_shot_events",
            ],
        ),
        ("soccerdata/WhoScored", ["read_schedule", "read_missing_players", "read_events"]),
        (
            "soccerdata/Sofascore",
            ["read_leagues", "read_seasons", "read_league_table", "read_schedule"],
        ),
        (
            "soccerdata/SoFIFA",
            [
                "read_leagues",
                "read_versions",
                "read_teams",
                "read_players",
                "read_team_ratings",
                "read_player_ratings",
            ],
        ),
        ("soccerdata/MatchHistory", ["read_games"]),
        (
            "open_reference/StatsBombOpenData",
            ["read_competitions", "read_matches", "read_events", "read_lineups", "read_360"],
        ),
    ],
)
def test_source_matrix_uses_documented_operation_names_or_exact_local_parser_names(
    source_id: str, expected_operations: list[str]
) -> None:
    assert source_operation_names(source_id) == expected_operations
    for operation in source_operation_names(source_id):
        assert not operation.startswith("fetch_")


def test_no_selectable_or_certified_status_without_evidence_identity() -> None:
    for source in SOURCE_MATRIX["sources"]:
        for operation in source["operations"]:
            status = operation["status"]
            if status in {"SELECTABLE_CANDIDATE", "CERTIFIED_SELECTABLE"}:
                assert operation.get("evidence_identity")


@pytest.mark.parametrize(
    "connector,operation",
    [
        (StatsBombPyBridge(), "competitions"),
        (ScraperFCSofascoreBridge(), "fetch_match_stats"),
        (SoccerActionBridge(), "convert_events"),
        (KloppyBridge(), "load_tracking_data"),
        (FloodlightBridge(), "load_events"),
        (MplSoccerBridge(), "draw_pitch"),
    ],
)
def test_optional_dependency_absence_maps_to_not_supported(
    connector: object, operation: str
) -> None:
    result = connector.execute(operation)
    assert result.status is SourceResultStatus.NOT_SUPPORTED


def test_statsbomb_open_data_without_path_is_not_success() -> None:
    result = StatsBombOpenDataConnector().execute("read_matches")
    assert result.status in {SourceResultStatus.NOT_FOUND, SourceResultStatus.VALID_EMPTY}


def test_statsbomb_open_data_fixture_parse_creates_deterministic_atomic_evidence_identity() -> None:
    connector = StatsBombOpenDataConnector()
    kwargs = {
        "root_path": str(FIXTURE_ROOT / "statsbomb_open_data"),
        "competition_id": 43,
        "season_id": 3,
    }
    result_one = connector.execute("read_matches", **kwargs)
    result_two = connector.execute("read_matches", **kwargs)
    assert result_one.status is SourceResultStatus.SUCCESS
    assert result_two.status is SourceResultStatus.SUCCESS
    assert result_one.bundle_id == result_two.bundle_id
    assert result_one.request_identity == result_two.request_identity


@pytest.mark.parametrize(
    ("operation", "kwargs"),
    [
        ("read_competitions", {"root_path": str(FIXTURE_ROOT / "statsbomb_open_data")}),
        (
            "read_matches",
            {
                "root_path": str(FIXTURE_ROOT / "statsbomb_open_data"),
                "competition_id": 43,
                "season_id": 3,
            },
        ),
        (
            "read_events",
            {"root_path": str(FIXTURE_ROOT / "statsbomb_open_data"), "match_id": 1001},
        ),
        (
            "read_lineups",
            {"root_path": str(FIXTURE_ROOT / "statsbomb_open_data"), "match_id": 1001},
        ),
        (
            "read_360",
            {"root_path": str(FIXTURE_ROOT / "statsbomb_open_data"), "match_id": 1001},
        ),
    ],
)
def test_statsbomb_open_data_supports_fixture_backed_operations(
    operation: str, kwargs: dict[str, object]
) -> None:
    result = StatsBombOpenDataConnector().execute(operation, **kwargs)
    assert result.status is SourceResultStatus.SUCCESS
    assert result.bundle_id


def test_openfootball_without_fixture_path_is_not_success() -> None:
    result = OpenFootballConnector().execute("read_matches")
    assert result.status in {SourceResultStatus.NOT_FOUND, SourceResultStatus.VALID_EMPTY}


def test_openfootball_fixture_parse_is_evidence_ready() -> None:
    fixture_path = FIXTURE_ROOT / "openfootball/world_cup_2022.json"
    result = OpenFootballConnector().execute("read_matches", file_path=str(fixture_path))
    assert result.status is SourceResultStatus.SUCCESS
    assert result.bundle_id


def test_kaggle_without_db_or_csv_path_is_not_success() -> None:
    result = KaggleEuropeanSoccerConnector().execute("read_matches")
    assert result.status in {SourceResultStatus.NOT_FOUND, SourceResultStatus.VALID_EMPTY}


def test_kaggle_csv_fixture_parse_is_evidence_ready() -> None:
    fixture_path = FIXTURE_ROOT / "kaggle_european_soccer/matches.csv"
    result = KaggleEuropeanSoccerConnector().execute(
        "read_matches",
        csv_path=str(fixture_path),
        retrieved_at="2024-01-03T00:00:00Z",
    )
    assert result.status is SourceResultStatus.SUCCESS
    assert result.bundle_id


def test_rich_probes_do_not_report_selectable_candidate_from_fixture_only_data() -> None:
    fotmob_fixture = load_fixture("rich_probes/fotmob_matches.json")
    sofascore_fixture = load_fixture("rich_probes/sofascore_stats.json")

    fotmob_result = FotMobProbe().execute("probe_matches", fixture_data=fotmob_fixture)
    sofascore_result = SofaScoreRichProbe().execute("probe_stats", fixture_data=sofascore_fixture)

    assert fotmob_result.status is SourceResultStatus.VALID_EMPTY
    assert sofascore_result.status is SourceResultStatus.VALID_EMPTY
    assert SOURCE_INDEX["rich_unofficial/FotMobProbe"]["source_status"] != "SELECTABLE_CANDIDATE"
    assert SOURCE_INDEX["rich_unofficial/SofaScoreRichProbe"]["source_status"] != "SELECTABLE_CANDIDATE"


def test_football_data_org_bridge_does_not_certify_without_retained_evidence() -> None:
    result = FootballDataOrgBridge().execute("get_fixtures_result", date="2026-06-19")
    assert result.status is SourceResultStatus.AUTHENTICATION_ERROR
    assert SOURCE_INDEX["open_reference/FootballDataOrg"]["source_status"] != "CERTIFIED_SELECTABLE"


def test_football_data_org_bridge_wraps_existing_client() -> None:
    result = FootballDataOrgBridge().execute(
        "get_fixtures_result",
        date="2026-06-19",
        client=FakeFootballDataOrgClient(),
    )
    assert result.status is SourceResultStatus.SUCCESS
    assert result.operation == "get_fixtures_result"


def test_fbref_supported_operation_list_is_exact() -> None:
    assert FBrefConnector.supported_operations == (
        "read_leagues",
        "read_seasons",
        "read_schedule",
        "read_team_season_stats",
        "read_team_match_stats",
        "read_player_season_stats",
        "read_player_match_stats",
        "read_lineup",
        "read_events",
    )


def test_fbref_constructor_receives_leagues_and_seasons_but_methods_do_not() -> None:
    created: list[FakeFBref] = []

    def factory(**kwargs: object) -> FakeFBref:
        source = FakeFBref(**kwargs)
        created.append(source)
        return source

    result = FBrefConnector().execute(
        "read_team_match_stats",
        leagues="ENG-Premier League",
        seasons=2024,
        stat_type="schedule",
        source_factory=factory,
    )
    assert result.status is SourceResultStatus.SUCCESS
    assert created[0].init_kwargs == {"leagues": "ENG-Premier League", "seasons": 2024}
    assert created[0].method_calls == [{"stat_type": "schedule"}]


def test_understat_supported_operation_list_excludes_read_match_shots() -> None:
    assert UnderstatConnector.supported_operations == (
        "read_leagues",
        "read_seasons",
        "read_schedule",
        "read_team_match_stats",
        "read_player_season_stats",
        "read_player_match_stats",
        "read_shot_events",
    )
    assert "read_match_shots" not in UnderstatConnector.supported_operations


def test_whoscored_supported_operation_list_excludes_read_player_ratings() -> None:
    assert WhoScoredConnector.supported_operations == (
        "read_schedule",
        "read_missing_players",
        "read_events",
    )
    assert "read_player_ratings" not in WhoScoredConnector.supported_operations


def test_sofascore_supported_operation_list_has_no_public_fetch_ratings() -> None:
    assert SofascoreConnector.supported_operations == (
        "read_leagues",
        "read_seasons",
        "read_league_table",
        "read_schedule",
    )


def test_sofifa_supported_operation_list_is_exact() -> None:
    assert SoFIFAConnector.supported_operations == (
        "read_leagues",
        "read_versions",
        "read_teams",
        "read_players",
        "read_team_ratings",
        "read_player_ratings",
    )


def test_matchhistory_supported_operation_list_is_exact() -> None:
    assert MatchHistoryConnector.supported_operations == ("read_games",)


def test_clubelo_supported_operation_list_is_exact() -> None:
    assert ClubEloConnector.supported_operations == ("read_by_date", "read_team_history")


def test_additive_schema_drift_does_not_demote_operation() -> None:
    entry = operation_entry("soccerdata/ClubElo", "read_by_date")
    assert evaluate_drift(["team", "elo", "country"], ["team", "elo"]) == DriftClassification.ADDITIVE_SCHEMA_DRIFT
    assert entry["status"] == "IMPLEMENTED_ACTIVE"
    assert entry["additive_schema_action"] == "KEEP_STATUS_WITH_DIAGNOSTIC"


def test_breaking_schema_drift_quarantines_one_operation_capability_tuple() -> None:
    entry = operation_entry("soccerdata/FBref", "read_team_match_stats")
    assert evaluate_drift(["team"], ["team", "shots"]) == DriftClassification.BREAKING_SCHEMA_DRIFT
    assert entry["breaking_schema_action"] == "QUARANTINE_OPERATION_CAPABILITY_TUPLE"


def test_unit_tests_block_real_network_calls() -> None:
    with pytest.raises(RuntimeError, match="network access disabled"):
        socket.create_connection(("example.com", 443), timeout=1)


def test_pyproject_packaging_still_includes_src_bet() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    packages = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    assert "src/bet" in packages


def test_connector_kernel_metadata_is_present() -> None:
    connectors = [
        ClubEloConnector(),
        ESPNConnector(),
        FBrefConnector(),
        FiveThirtyEightConnector(),
        MatchHistoryConnector(),
        SofascoreConnector(),
        SoFIFAConnector(),
        UnderstatConnector(),
        WhoScoredConnector(),
        StatsBombOpenDataConnector(),
        StatsBombPyBridge(),
        KaggleEuropeanSoccerConnector(),
        FootballDataOrgBridge(),
        OpenFootballConnector(),
        FotMobProbe(),
        SofaScoreRichProbe(),
        ScraperFCSofascoreBridge(),
        SoccerActionBridge(),
        KloppyBridge(),
        FloodlightBridge(),
        MplSoccerBridge(),
    ]
    required_attrs = {
        "provider",
        "source_family",
        "source_class",
        "supported_operations",
        "supported_capabilities",
        "access_requirements",
        "dependency_requirements",
        "transport_type",
        "pagination_model",
        "cache_policy",
        "state_model",
        "evidence_policy",
        "drift_policy",
    }
    for connector in connectors:
        assert required_attrs.issubset(set(dir(connector)))


def test_capability_summary_reflects_demoted_non_selectable_sources() -> None:
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    assert "FootballDataOrg" in summary["summary"]["implemented_active_sources"]
    assert "FotMobProbe" in summary["summary"]["not_supported_sources"]
