"""Regression tests for provider normalization against *live* payload shapes.

Every case here was a real production failure: the code passed its
fixture-based tests while returning nothing (or nothing usable) from the actual
APIs, verified live on 2026-08-25.
"""
import pytest

from bet.simple_stats.providers import (
    _combine_stats,
    _flat_from_dict_stats,
    _normalize_team_name,
    _parse_sportdb_number,
    _season_candidates,
    _team_matches,
    normalize_sportdb_match_stats,
)


def test_sportdb_normalizer_reads_live_data_key():
    """Live SportDB MCP responses nest periods under "data"; only the REST
    captures in tests/fixtures use "body". Reading just "body" made this
    return {} for every real run."""
    live_shape = {
        "endpoint": "/api/flashscore/match/xQXUa3UG/stats",
        "data": [
            {
                "period": "Match",
                "stats": [
                    {"statName": "Corner kicks", "homeValue": "3", "awayValue": "6"},
                    {"statName": "Yellow cards", "homeValue": "1", "awayValue": "2"},
                ],
            }
        ],
    }
    combined = normalize_sportdb_match_stats(live_shape)
    assert combined["corners_total"] == 9
    assert combined["cards_total"] == 3


def test_sportdb_normalizer_still_reads_fixture_body_key():
    body_shape = {
        "body": [
            {"period": "Match", "stats": [{"statName": "Corner kicks", "homeValue": "5", "awayValue": "4"}]}
        ]
    }
    assert normalize_sportdb_match_stats(body_shape)["corners_total"] == 9


def test_sportdb_half_periods_are_ignored():
    payload = {
        "data": [
            {"period": "Match", "stats": [{"statName": "Corner kicks", "homeValue": "5", "awayValue": "4"}]},
            {"period": "1st Half", "stats": [{"statName": "Corner kicks", "homeValue": "3", "awayValue": "1"}]},
        ]
    }
    assert normalize_sportdb_match_stats(payload)["corners_total"] == 9


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("48%", 48.0),                 # possession
        ("83% (372/450)", 83.0),       # passes
        ("11", 11.0),
        ("1.66", 1.66),
        ("", None),
        (None, None),
        ("-", None),
    ],
)
def test_sportdb_values_are_strings_not_numbers(raw, expected):
    """SportDB stat values arrive as strings, and not always bare numbers;
    a plain float() raised and silently dropped the metric."""
    assert _parse_sportdb_number(raw) == expected


def test_tennis_flat_stats_derive_match_totals():
    """tennis-abstract reports one player's line as flat scalars, not
    {"home": x, "away": y}, so the football combiner returned {} for tennis and
    total_games -- a PRIORITY_METRIC -- was never populated. Aces and double
    faults must additionally be summed with the opponent's, since a "_total"
    metric feeds the combined "Total Aces" market."""
    stats = {
        "aces": 4,
        "opponent_aces": 7,
        "double_faults": 3,
        "opponent_double_faults": 2,
        "service_games": 9,
        "return_games": 9,
        "surface": "Clay",  # non-numeric, must not raise
    }
    combined = _combine_stats("tennis-abstract", stats, {})
    assert combined["aces_total"] == 11
    assert combined["double_faults_total"] == 5
    assert combined["total_games"] == 18


def test_tennis_totals_are_not_emitted_from_one_side_alone():
    """Half a match's aces must not be published as the match total -- that
    made every "Total Aces UNDER" line read as a 100% hit rate."""
    combined = _combine_stats("tennis-abstract", {"aces": 4, "double_faults": 3}, {})
    assert "aces_total" not in combined
    assert "double_faults_total" not in combined


def test_football_paired_stats_still_use_the_paired_combiner():
    combined = _combine_stats(
        "espn-football", {"corners": {"home": 5, "away": 4}}, {"corners": "corners_total"}
    )
    assert combined["corners_total"] == 9


def test_flat_combiner_without_game_counts_emits_no_total_games():
    assert "total_games" not in _flat_from_dict_stats({"aces": 4}, {})


@pytest.mark.parametrize(
    "one,two,expected",
    [
        ("Real Betis", "Betis", True),
        ("Manchester United", "Manchester Utd", True),
        ("Atletico Madrid", "Atl. Madrid", True),
        ("Athletic Bilbao", "Ath Bilbao", True),
        ("Botafogo-SP", "Botafogo RJ", False),
        ("Real Madrid", "Real Sociedad", False),
        ("", "Betis", False),
    ],
)
def test_team_matching_tolerates_provider_abbreviations(one, two, expected):
    """Flashscore abbreviates where other providers spell out; exact equality
    dropped most of SportDB's history."""
    assert _team_matches(_normalize_team_name(one), _normalize_team_name(two)) is expected


def test_season_candidates_cover_span_and_calendar_year_leagues():
    """European leagues are labelled "2025-2026", Brazil/MLS just "2026"."""
    candidates = _season_candidates("2026-2027")
    assert candidates[0] == "2026-2027"
    assert "2025-2026" in candidates  # Flashscore's current season can lag
    assert "2026" in candidates       # calendar-year leagues
