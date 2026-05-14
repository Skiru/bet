#!/usr/bin/env python3
"""Tests for ingest_scan_stats.py — discovery module ingestion."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


class TestParseOddsVal:
    """Test fractional odds parsing."""

    def test_fractional_5_4(self):
        from ingest_scan_stats import _parse_odds_val
        result = _parse_odds_val({"fractionalValue": "5/4"})
        assert result == 2.25

    def test_fractional_1_1(self):
        from ingest_scan_stats import _parse_odds_val
        result = _parse_odds_val({"fractionalValue": "1/1"})
        assert result == 2.0

    def test_fractional_67_100(self):
        from ingest_scan_stats import _parse_odds_val
        result = _parse_odds_val({"fractionalValue": "67/100"})
        assert result == pytest.approx(1.67, abs=0.01)

    def test_decimal_value(self):
        from ingest_scan_stats import _parse_odds_val
        result = _parse_odds_val({"decimalValue": 2.50})
        assert result == 2.50

    def test_negative_fractional_rejected(self):
        from ingest_scan_stats import _parse_odds_val
        result = _parse_odds_val({"fractionalValue": "-1/4"})
        assert result is None

    def test_zero_denominator(self):
        from ingest_scan_stats import _parse_odds_val
        result = _parse_odds_val({"fractionalValue": "5/0"})
        assert result is None

    def test_none_value(self):
        from ingest_scan_stats import _parse_odds_val
        result = _parse_odds_val({})
        assert result is None

    def test_malformed_fractional(self):
        from ingest_scan_stats import _parse_odds_val
        result = _parse_odds_val({"fractionalValue": "5/4/2"})
        assert result is None


class TestNormalizeDiscoveryEvent:
    """Test discovery event normalization."""

    def _make_event(self, **overrides):
        base = {
            "id": 12345,
            "sport": "football",
            "home_team": "Team A",
            "away_team": "Team B",
            "tournament": "Test League",
            "country": "Test",
            "start_time": "2026-05-12T18:00:00+00:00",
            "form": {},
            "h2h": {},
            "odds": [],
        }
        base.update(overrides)
        return base

    def test_basic_normalization(self):
        from ingest_scan_stats import _normalize_discovery_event
        ev = self._make_event()
        url, norm = _normalize_discovery_event(ev)
        assert norm["home"] == "Team A"
        assert norm["away"] == "Team B"
        assert norm["source"] == "sofascore"
        assert "football/12345" in url

    def test_form_data_preserves_position(self):
        from ingest_scan_stats import _normalize_discovery_event
        ev = self._make_event(form={
            "homeTeam": {"position": 3, "value": "45", "form": ["W", "W", "L"]},
            "awayTeam": {"position": 8, "value": "30", "form": ["L", "D", "W"]},
            "label": "Pts"
        })
        _, norm = _normalize_discovery_event(ev)
        assert norm["form_home"] == ["W", "W", "L"]
        assert norm["form_away"] == ["L", "D", "W"]
        assert norm["standings"]["home_pos"] == 3
        assert norm["standings"]["away_pos"] == 8
        assert norm["standings"]["home_pts"] == "45"
        assert norm["standings"]["label"] == "Pts"

    def test_1x2_odds_extraction(self):
        from ingest_scan_stats import _normalize_discovery_event
        ev = self._make_event(odds=[
            {"marketName": "Full time", "choices": [
                {"name": "1", "fractionalValue": "5/4"},
                {"name": "X", "fractionalValue": "2/1"},
                {"name": "2", "fractionalValue": "3/1"},
            ]}
        ])
        _, norm = _normalize_discovery_event(ev)
        assert norm["odds"]["w1"] == 2.25
        assert norm["odds"]["x"] == 3.0
        assert norm["odds"]["w2"] == 4.0

    def test_btts_odds_extraction(self):
        from ingest_scan_stats import _normalize_discovery_event
        ev = self._make_event(odds=[
            {"marketName": "Both teams to score", "choices": [
                {"name": "Yes", "fractionalValue": "4/5"},
                {"name": "No", "fractionalValue": "5/6"},
            ]}
        ])
        _, norm = _normalize_discovery_event(ev)
        assert "btts_yes" in norm["odds"]
        assert "btts_no" in norm["odds"]
        assert norm["odds"]["btts_yes"] == pytest.approx(1.8, abs=0.01)

    def test_corners_odds_extraction(self):
        from ingest_scan_stats import _normalize_discovery_event
        ev = self._make_event(odds=[
            {"marketName": "Corners 2-Way", "choices": [
                {"name": "Over 9.5", "fractionalValue": "10/11"},
                {"name": "Under 9.5", "fractionalValue": "10/11"},
            ]}
        ])
        _, norm = _normalize_discovery_event(ev)
        assert "corners" in norm["odds"]
        assert "Over 9.5" in norm["odds"]["corners"]
        assert "Under 9.5" in norm["odds"]["corners"]

    def test_cards_odds_extraction(self):
        from ingest_scan_stats import _normalize_discovery_event
        ev = self._make_event(odds=[
            {"marketName": "Cards in match", "choices": [
                {"name": "Over 3.5", "fractionalValue": "4/5"},
                {"name": "Under 3.5", "fractionalValue": "1/1"},
            ]}
        ])
        _, norm = _normalize_discovery_event(ev)
        assert "cards" in norm["odds"]
        assert "Over 3.5" in norm["odds"]["cards"]

    def test_double_chance_extraction(self):
        from ingest_scan_stats import _normalize_discovery_event
        ev = self._make_event(odds=[
            {"marketName": "Double chance", "choices": [
                {"name": "1X", "fractionalValue": "1/3"},
                {"name": "12", "fractionalValue": "1/5"},
                {"name": "X2", "fractionalValue": "1/2"},
            ]}
        ])
        _, norm = _normalize_discovery_event(ev)
        assert "double_chance" in norm["odds"]
        assert "1X" in norm["odds"]["double_chance"]

    def test_half_time_1st_and_2nd(self):
        from ingest_scan_stats import _normalize_discovery_event
        ev = self._make_event(odds=[
            {"marketName": "1st half", "choices": [
                {"name": "1", "fractionalValue": "2/1"},
            ]},
            {"marketName": "2nd Half Result", "choices": [
                {"name": "1", "fractionalValue": "3/1"},
            ]},
        ])
        _, norm = _normalize_discovery_event(ev)
        assert "half_time" in norm["odds"]
        assert "half_time_2nd" in norm["odds"]

    def test_expected_stats_passthrough(self):
        from ingest_scan_stats import _normalize_discovery_event
        ev = self._make_event(expected_stats={"corners": {"home": 5.2, "away": 4.1}})
        _, norm = _normalize_discovery_event(ev)
        assert norm["expected_stats"]["corners"]["home"] == 5.2

    def test_period_markets_basketball(self):
        from ingest_scan_stats import _normalize_discovery_event
        ev = self._make_event(sport="basketball", odds=[
            {"marketName": "1st quarter winner", "choices": [
                {"name": "1", "fractionalValue": "10/11"},
                {"name": "2", "fractionalValue": "10/11"},
            ]}
        ])
        _, norm = _normalize_discovery_event(ev)
        assert "period_markets" in norm["odds"]

    def test_total_lines_extraction(self):
        from ingest_scan_stats import _normalize_discovery_event
        ev = self._make_event(odds=[
            {"marketName": "Match goals", "choices": [
                {"name": "Over 2.5", "fractionalValue": "4/5"},
                {"name": "Under 2.5", "fractionalValue": "1/1"},
            ]}
        ])
        _, norm = _normalize_discovery_event(ev)
        assert "total_lines" in norm["odds"]
        assert "over_Over 2.5" in norm["odds"]["total_lines"]
        assert "under_Under 2.5" in norm["odds"]["total_lines"]


class TestIngestTeamSideOddsPassthrough:
    """Test that _ingest_team_side passes through all market types."""

    def test_scan_odds_captures_all_markets(self):
        odds_raw = {
            "w1": 2.25,
            "x": 3.0,
            "w2": 4.0,
            "btts_yes": 1.8,
            "btts_no": 1.9,
            "total_lines": {"over_Over 2.5": 1.9, "under_Under 2.5": 1.9},
            "corners": {"Over 9.5": 1.9, "Under 9.5": 1.9},
            "cards": {"Over 3.5": 1.8},
            "double_chance": {"1X": 1.33},
            "draw_no_bet": {"home": 1.5, "away": 2.2},
            "handicap_lines": {"Home -1": 2.5},
            "half_time": {"1": 2.5},
            "half_time_2nd": {"1": 3.0},
            "set_winner": {"1st set_1": 1.9},
            "period_markets": {"1st_quarter_winner_1": 1.9},
        }
        
        scan_odds = {}
        for key in ("w1", "w2", "x", "draw"):
            if key in odds_raw and odds_raw[key]:
                scan_odds[key] = odds_raw[key]
        for market_key in ("handicap_lines", "total_lines", "double_chance",
                           "draw_no_bet", "corners", "cards", "half_time",
                           "half_time_2nd", "set_winner", "period_markets"):
            if odds_raw.get(market_key):
                scan_odds[market_key] = odds_raw[market_key]
        for scalar_key in ("btts_yes", "btts_no"):
            if odds_raw.get(scalar_key):
                scan_odds[scalar_key] = odds_raw[scalar_key]

        assert scan_odds["w1"] == 2.25
        assert scan_odds["btts_yes"] == 1.8
        assert "corners" in scan_odds
        assert "cards" in scan_odds
        assert "half_time" in scan_odds
        assert "half_time_2nd" in scan_odds
        assert "period_markets" in scan_odds
