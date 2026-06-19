from __future__ import annotations
import pytest
import pandas as pd
from datetime import datetime, timezone
from bet.integration.source_result import SourceResultStatus
from bet.enrichment.football_data_foundation.contracts import RawFootballDataBundle, NormalizedFootballDataRecord
from bet.enrichment.football_data_foundation.fingerprints import compute_schema_fingerprint, compute_data_fingerprint
from bet.enrichment.football_data_foundation.normalizers import flatten_multiindex_columns, normalize_value, normalize_numeric
from bet.enrichment.football_data_foundation.connector_kernel.drift import evaluate_drift, DriftClassification
from bet.enrichment.football_data_foundation.soccerdata_sources.clubelo import ClubEloConnector
from bet.enrichment.football_data_foundation.soccerdata_sources.espn import ESPNConnector
from bet.enrichment.football_data_foundation.soccerdata_sources.fbref import FBrefConnector
from bet.enrichment.football_data_foundation.soccerdata_sources.fivethirtyeight import FiveThirtyEightConnector
from bet.enrichment.football_data_foundation.soccerdata_sources.matchhistory import MatchHistoryConnector
from bet.enrichment.football_data_foundation.soccerdata_sources.sofascore import SofascoreConnector
from bet.enrichment.football_data_foundation.soccerdata_sources.sofifa import SoFIFAConnector
from bet.enrichment.football_data_foundation.soccerdata_sources.understat import UnderstatConnector
from bet.enrichment.football_data_foundation.soccerdata_sources.whoscored import WhoScoredConnector
from bet.enrichment.football_data_foundation.open_reference_sources.statsbomb_open_data import StatsBombOpenDataConnector
from bet.enrichment.football_data_foundation.open_reference_sources.statsbombpy_bridge import StatsBombPyBridge
from bet.enrichment.football_data_foundation.open_reference_sources.kaggle_european_soccer import KaggleEuropeanSoccerConnector
from bet.enrichment.football_data_foundation.open_reference_sources.football_data_org_bridge import FootballDataOrgBridge
from bet.enrichment.football_data_foundation.open_reference_sources.openfootball import OpenFootballConnector
from bet.enrichment.football_data_foundation.rich_unofficial_sources.fotmob_probe import FotMobProbe
from bet.enrichment.football_data_foundation.rich_unofficial_sources.sofascore_rich_probe import SofaScoreRichProbe
from bet.enrichment.football_data_foundation.rich_unofficial_sources.scraperfc_sofascore_bridge import ScraperFCSofascoreBridge
from bet.enrichment.football_data_foundation.event_model_bridges.socceraction_bridge import SoccerActionBridge
from bet.enrichment.football_data_foundation.event_model_bridges.kloppy_bridge import KloppyBridge
from bet.enrichment.football_data_foundation.event_model_bridges.floodlight_bridge import FloodlightBridge
from bet.enrichment.football_data_foundation.event_model_bridges.mplsoccer_bridge import MplSoccerBridge

def test_contracts() -> None:
    bundle = RawFootballDataBundle(
        provider="test",
        source_family="test",
        source_class="test",
        operation="test",
        request_identity="test",
        retrieved_at=datetime.now(timezone.utc),
        source_library="test",
        source_library_version="test",
        parser_version="test",
        schema_fingerprint="test",
        data_fingerprint="test",
        row_count=1
    )
    assert bundle.provider == "test"

    record = NormalizedFootballDataRecord(
        provider="test",
        source_family="test",
        source_class="test",
        operation="test",
        request_identity="test",
        normalized_at=datetime.now(timezone.utc),
        normalization_version="test",
        schema_fingerprint="test",
        data_fingerprint="test",
        row_count=1
    )
    assert record.provider == "test"

def test_fingerprints() -> None:
    df = pd.DataFrame({"col1": [1, 2], "col2": ["a", "b"]})
    schema1 = compute_schema_fingerprint(df)
    schema2 = compute_schema_fingerprint(df)
    assert schema1 == schema2

    data1 = compute_data_fingerprint(df)
    data2 = compute_data_fingerprint(df)
    assert data1 == data2

    # Verify MultiIndex safe
    df_multi = pd.DataFrame([[1, 2], [3, 4]])
    df_multi.columns = pd.MultiIndex.from_tuples([("a", "b"), ("c", "d")])
    schema_multi = compute_schema_fingerprint(df_multi)
    assert isinstance(schema_multi, str)

def test_normalizers() -> None:
    df = pd.DataFrame([[1, 2], [3, 4]])
    df.columns = pd.MultiIndex.from_tuples([("a", "b"), ("c", "d")])
    flat_df = flatten_multiindex_columns(df)
    assert "a_b" in flat_df.columns
    assert "c_d" in flat_df.columns

    assert normalize_value(None) == "UNKNOWN"
    assert normalize_value("None") == "UNKNOWN"
    assert normalize_value(float("nan")) == "UNKNOWN"
    assert normalize_value("Arsenal") == "Arsenal"

    assert normalize_numeric(None) == "UNKNOWN"
    assert normalize_numeric("None") == "UNKNOWN"
    assert normalize_numeric(12.5) == 12.5
    assert normalize_numeric("42") == 42
    # Ensure zero is preserved, not coerced
    assert normalize_numeric(0) == 0

def test_drift() -> None:
    assert evaluate_drift(["col1", "col2"], ["col1", "col2"]) == DriftClassification.NO_DRIFT
    # Additive drift does not demote
    assert evaluate_drift(["col1", "col2", "col3"], ["col1", "col2"]) == DriftClassification.ADDITIVE_SCHEMA_DRIFT
    # Breaking drift quarantines
    assert evaluate_drift(["col1"], ["col1", "col2"]) == DriftClassification.BREAKING_SCHEMA_DRIFT

def test_all_soccerdata_connectors() -> None:
    # Test ClubElo
    mock_elo = pd.DataFrame({"team": ["Arsenal"], "elo": [1850], "date": ["2026-06-19"]})
    conn_elo = ClubEloConnector()
    res_elo = conn_elo.execute("fetch_ratings", mock_data=mock_elo)
    assert res_elo.status is SourceResultStatus.SUCCESS
    assert res_elo.value[0]["team_name"] == "Arsenal"

    # Test ESPN
    mock_espn = pd.DataFrame({"home_team": ["Arsenal"], "away_team": ["Chelsea"], "date": ["2026-06-19"]})
    conn_espn = ESPNConnector()
    res_espn = conn_espn.execute("fetch_schedule", mock_data=mock_espn)
    assert res_espn.status is SourceResultStatus.SUCCESS

    # Test FBref
    mock_fbref = pd.DataFrame({"Squad": ["Arsenal"], "Gls": [3], "Ast": [2]})
    conn_fbref = FBrefConnector()
    res_fbref = conn_fbref.execute("fetch_team_stats", mock_data=mock_fbref)
    assert res_fbref.status is SourceResultStatus.SUCCESS

    # Test FiveThirtyEight (always returns NOT_SUPPORTED but is robust and safe)
    conn_538 = FiveThirtyEightConnector()
    res_538 = conn_538.execute("fetch_predictions")
    assert res_538.status is SourceResultStatus.NOT_SUPPORTED

    # Test MatchHistory
    mock_mh = pd.DataFrame({"HomeTeam": ["Arsenal"], "AwayTeam": ["Chelsea"], "FTHG": [2], "FTAG": [1]})
    conn_mh = MatchHistoryConnector()
    res_mh = conn_mh.execute("fetch_results", mock_data=mock_mh)
    assert res_mh.status is SourceResultStatus.SUCCESS

    # Test Sofascore
    mock_sofa = pd.DataFrame({"player": ["Saka"], "team": ["Arsenal"], "rating": [8.2]})
    conn_sofa = SofascoreConnector()
    res_sofa = conn_sofa.execute("fetch_ratings", mock_data=mock_sofa)
    assert res_sofa.status is SourceResultStatus.SUCCESS

    # Test SoFIFA
    mock_sofifa = pd.DataFrame({"team": ["Arsenal"], "overall": [84], "att": [85], "mid": [84], "def": [83]})
    conn_sofifa = SoFIFAConnector()
    res_sofifa = conn_sofifa.execute("fetch_ratings", mock_data=mock_sofifa)
    assert res_sofifa.status is SourceResultStatus.SUCCESS

    # Test Understat
    mock_ust = pd.DataFrame({"xG": [0.85], "player": ["Saka"], "result": ["Goal"]})
    conn_ust = UnderstatConnector()
    res_ust = conn_ust.execute("fetch_xg", mock_data=mock_ust)
    assert res_ust.status is SourceResultStatus.SUCCESS

    # Test WhoScored
    mock_ws = pd.DataFrame({"player": ["Saka"], "rating": [7.85]})
    conn_ws = WhoScoredConnector()
    res_ws = conn_ws.execute("fetch_ratings", mock_data=mock_ws)
    assert res_ws.status is SourceResultStatus.SUCCESS

def test_open_reference_connectors() -> None:
    # Test StatsBomb Open Data local parser
    conn_sb = StatsBombOpenDataConnector()
    res_sb = conn_sb.execute("parse_matches")
    assert res_sb.status is SourceResultStatus.SUCCESS
    assert res_sb.value[0]["home_team"] == "Argentina"

    # Test StatsBombPy Bridge (safe offline behavior)
    conn_sbpy = StatsBombPyBridge()
    res_sbpy = conn_sbpy.execute("fetch_competitions")
    # statsbombpy is optional; should return SUCCESS (with mocks) or NOT_SUPPORTED safely
    assert res_sbpy.status in (SourceResultStatus.SUCCESS, SourceResultStatus.NOT_SUPPORTED)

    # Test Kaggle European Soccer
    conn_kag = KaggleEuropeanSoccerConnector()
    res_kag = conn_kag.execute("query_matches")
    assert res_kag.status is SourceResultStatus.SUCCESS

    # Test Football-Data Org Bridge
    conn_fd = FootballDataOrgBridge()
    # It attempts to import inside execute; should return gracefully if not fully active
    res_fd = conn_fd.execute("fetch_fixtures")
    assert res_fd.status in (SourceResultStatus.SUCCESS, SourceResultStatus.PARSE_ERROR, SourceResultStatus.UPSTREAM_ERROR)

    # Test OpenFootball Connector
    conn_of = OpenFootballConnector()
    res_of = conn_of.execute("fetch_worldcup_matches")
    assert res_of.status is SourceResultStatus.SUCCESS
    assert res_of.value[0]["team1"] == "Qatar"

def test_rich_unofficial_and_event_bridges() -> None:
    # Rich probes
    conn_fot = FotMobProbe()
    assert conn_fot.execute("probe_matches").status is SourceResultStatus.SUCCESS

    conn_sofr = SofaScoreRichProbe()
    assert conn_sofr.execute("probe_stats").status is SourceResultStatus.SUCCESS

    conn_scr = ScraperFCSofascoreBridge()
    assert conn_scr.execute("fetch_match_stats").status in (SourceResultStatus.SUCCESS, SourceResultStatus.NOT_SUPPORTED)

    # Event bridges
    assert SoccerActionBridge().execute("convert_events").status in (SourceResultStatus.SUCCESS, SourceResultStatus.NOT_SUPPORTED)
    assert KloppyBridge().execute("load_tracking_data").status in (SourceResultStatus.SUCCESS, SourceResultStatus.NOT_SUPPORTED)
    assert FloodlightBridge().execute("load_events").status in (SourceResultStatus.SUCCESS, SourceResultStatus.NOT_SUPPORTED)
    assert MplSoccerBridge().execute("draw_pitch").status in (SourceResultStatus.SUCCESS, SourceResultStatus.NOT_SUPPORTED)
