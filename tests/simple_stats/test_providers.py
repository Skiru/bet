"""Regression tests for provider normalization against *live* payload shapes.

Every case here was a real production failure: the code passed its
fixture-based tests while returning nothing (or nothing usable) from the actual
APIs, verified live on 2026-08-25.
"""
import pytest

from bet.simple_stats import providers
from bet.simple_stats.providers import (
    _combine_stats,
    _league_fields_either_team,
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


@pytest.mark.parametrize(
    "one,two",
    [
        # 2026-08-25: SportDB resolved "Saudi Pro League" to Switzerland's
        # "Super League" (name ratio 0.786, over the 0.75 gate) and the team
        # filter then failed to reject it, because "basel" contains "a" then
        # "l" in order and _token_matches read that as a contraction of "Al-".
        ("Al-Taawoun", "Basel"),
        ("Al-Fayha", "FC Basel"),
        ("Al-Khaleej", "Basel"),
        # Same shape, other direction: no shared first letter, no match.
        ("Al-Hilal", "Thun"),
    ],
)
def test_team_matching_rejects_letters_that_merely_appear_in_order(one, two):
    assert _team_matches(_normalize_team_name(one), _normalize_team_name(two)) is False


# Two real Swiss Super League rows from 2026-08-25, exactly as
# flashscore_get_competition_results returned them, plus the Saudi fixture that
# was wrongly served them.
_SWISS_SEASON_ROWS = [
    {
        "eventId": "4OCMUGc4",
        "homeName": "Basel",
        "awayName": "Zurich",
        "eventStage": "FINISHED",
        "startDateTimeUtc": "2026-08-22T18:30:00.000Z",
    },
    {
        "eventId": "KGGZJaqn",
        "homeName": "Basel",
        "awayName": "Thun",
        "eventStage": "FINISHED",
        "startDateTimeUtc": "2026-08-09T14:30:00.000Z",
    },
]


def test_wrong_league_season_is_rejected_by_its_participants():
    """The league gate must not depend on name distance: no threshold separates
    "Saudi Pro League" from Switzerland's "Super League"."""
    assert (
        _league_fields_either_team(
            _SWISS_SEASON_ROWS,
            _normalize_team_name("Al-Taawoun"),
            _normalize_team_name("Al-Fayha"),
        )
        is False
    )


def test_right_league_season_is_accepted_from_one_side_alone():
    """Either side suffices -- a promoted team with no rows yet must not veto an
    otherwise correct league."""
    rows = [
        {
            "eventId": "x1",
            "homeName": "Al-Taawoun",
            "awayName": "Al-Nassr",
            "eventStage": "FINISHED",
            "startDateTimeUtc": "2026-08-18T16:00:00.000Z",
        }
    ]
    assert (
        _league_fields_either_team(
            rows, _normalize_team_name("Al-Fayha"), _normalize_team_name("Al-Taawoun")
        )
        is True
    )


def test_history_from_a_wrong_league_is_a_data_gap_not_observations(monkeypatch):
    """End to end: a mis-resolved competition yields zero observations and an
    explicit data_gap. On 2026-08-25 it instead yielded the four highest-p_low
    rows in the artifact."""
    monkeypatch.setattr(
        providers, "_sportdb_season_results", lambda *a, **k: _SWISS_SEASON_ROWS
    )
    monkeypatch.setattr(providers, "SportDBMCPShadowAdapter", lambda *a, **k: object())

    def _must_not_be_called(*args, **kwargs):
        raise AssertionError("per-match stats were fetched for a rejected league")

    monkeypatch.setattr(providers, "fetch_sportdb_match", _must_not_be_called)

    outcome = providers.fetch_sportdb_history(
        "Al-Taawoun", "Al-Fayha", "Saudi Pro League", "2026-2027", mode="l10"
    )

    assert outcome.metrics == {}
    assert any("wrong league" in gap for gap in outcome.data_gaps), outcome.data_gaps


@pytest.mark.parametrize(
    "one,two",
    [
        # A two- or three-letter fragment used to anchor a whole name, because
        # the substantive-token rule accepted 4+ chars on either side. All four
        # of these are real names from the 2026-08-25 slate.
        ("Botafogo-SP", "Southampton"),      # "sp" is a subsequence of "southampton"
        ("Barnsley", "Hapoel Be'er Sheva"),  # the apostrophe splits off "be"
        ("Brentford", "Hapoel Be'er Sheva"),
        ("Bodø/Glimt", "Brentford"),         # folding dropped the o-slash: "bod"
    ],
)
def test_short_fragments_cannot_anchor_a_team_identity(one, two):
    assert _team_matches(_normalize_team_name(one), _normalize_team_name(two)) is False


@pytest.mark.parametrize(
    "one,two",
    [
        ("Ulsan Hyundai", "Ulsan HD"),   # short token still participates...
        ("Manchester United", "Man Utd"),
        ("FC Seoul", "Seoul"),
        ("Bodø/Glimt", "Bodo/Glimt"),    # ...and o-slash still folds to "o"
        ("Lech Poznań", "Lech Poznan"),
        ("Legia Warszawa", "Legia Warsaw"),
    ],
)
def test_tightening_keeps_genuine_abbreviations(one, two):
    assert _team_matches(_normalize_team_name(one), _normalize_team_name(two)) is True


def test_letters_nfkd_cannot_decompose_are_transliterated_not_dropped():
    """"Bodø" folded to "bod", and that remnant matched unrelated clubs."""
    assert _normalize_team_name("Bodø/Glimt") == "bodo glimt"
    assert _normalize_team_name("Łódź") == "lodz"
    assert _normalize_team_name("Beşiktaş") == "besiktas"


def test_unreadable_season_payload_is_not_blamed_on_the_league():
    """A key rename in the payload is a payload problem. Reporting it as the
    wrong league would send the next reader to the resolver."""
    rows = [{"eventId": "x", "home_name": "Al-Taawoun", "away_name": "Al-Nassr"}]
    assert _league_fields_either_team(rows, "al taawoun", "al nassr") is None
