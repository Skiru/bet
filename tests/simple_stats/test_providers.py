"""Regression tests for provider normalization against *live* payload shapes.

Every case here was a real production failure: the code passed its
fixture-based tests while returning nothing (or nothing usable) from the actual
APIs, verified live on 2026-08-25.
"""
import pytest

from bet.integration.source_result import SourceOperationResult, SourceResultStatus
from bet.simple_stats import providers
from bet.simple_stats.providers import (
    _ALIASES_BY_PROVIDER,
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


def test_tennis_flat_stats_carry_match_totals():
    """tennis-abstract reports one player's line as flat scalars, not
    {"home": x, "away": y}, so the football combiner returned {} for tennis.
    Aces and double faults are summed with the opponent's, since a "_total"
    metric feeds the combined "Total Aces" market."""
    stats = {
        "aces": 4,
        "opponent_aces": 7,
        "double_faults": 3,
        "opponent_double_faults": 2,
        "total_games": 19.0,
        "total_sets": 2.0,
        "games_won": 13.0,
        "surface": "Clay",  # non-numeric, must not raise
        "score": "7-6(2) 6-3",  # ditto
    }
    combined = _combine_stats(
        "tennis-abstract", stats, _ALIASES_BY_PROVIDER["tennis-abstract"]
    )
    assert combined["aces_total"] == 11
    assert combined["double_faults_total"] == 5
    assert combined["total_games"] == 19
    assert combined["total_sets"] == 2
    # The queried player's own line, for the per-player markets.
    assert combined["aces_for"] == 4
    assert combined["double_faults_for"] == 3
    assert combined["games_won"] == 13


def test_tennis_total_games_is_never_rebuilt_from_service_games():
    """The defect this replaced, guarded so it cannot come back.

    ``service_games + return_games`` counts every game that had a server, and a
    tie-break game has none, so the sum is one short per 7-6 set -- on 98.37% of
    the tie-break rows in tennis-abstract's own cache. A row whose score could
    not be parsed must therefore contribute **no** total_games at all, rather
    than a figure that is reliably low.
    """
    combined = _combine_stats(
        "tennis-abstract",
        {"aces": 4, "opponent_aces": 7, "service_games": 9, "return_games": 9},
        _ALIASES_BY_PROVIDER["tennis-abstract"],
    )
    assert "total_games" not in combined
    assert combined["aces_total"] == 11, "the rest of the row still counts"


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


# --- Faza 1f: goals from the L10/H2H listing row itself, zero extra calls ---


class _FakeFixtureStats:
    def __init__(self, stats):
        self.stats = stats


class _FakeEspnFootballClient:
    def __init__(self, team_id, fixtures, stats_by_fixture):
        self._team_id = team_id
        self._fixtures = fixtures
        self._stats_by_fixture = stats_by_fixture

    def resolve_team_id(self, name):
        return self._team_id

    def get_team_last_fixtures(self, team_id, last_n=10):
        return self._fixtures

    def get_fixture_stats(self, fixture_id):
        return self._stats_by_fixture[fixture_id]


def test_espn_football_goals_ride_on_the_fixture_score_no_extra_call(monkeypatch):
    """espn.py's own fixture-listing row already carries the final score
    (verified live), so goals cost zero extra requests: they are read from
    the same ``fx`` the corners combiner already has in hand."""
    fixtures = [{
        "id": "400001",
        "date": "2026-08-18T19:00:00Z",
        "home_team": "Team A",
        "away_team": "Team B",
        "score": "2-1",
        "home_participant_id": "10",
        "away_participant_id": "20",
    }]
    stats = {"400001": _FakeFixtureStats({"corners": {"home": 5, "away": 4}})}
    client = _FakeEspnFootballClient("10", fixtures, stats)
    monkeypatch.setattr(providers, "_provider_client", lambda *a, **k: client)

    outcome = providers._fetch_l10_generic("espn-football", "Team A", rate_limiter=None)

    assert outcome.metrics["corners_total"][0].value == 9
    assert outcome.metrics["goals_total"][0].value == 3
    assert outcome.metrics["goals_for"][0].value == 2  # team_id "10" was home
    assert outcome.metrics["goals_against"][0].value == 1


def test_espn_football_missing_score_yields_no_goals_but_keeps_the_rest(monkeypatch):
    """A fixture with no reported score (score == "") must not block the other
    metrics the same row already produces."""
    fixtures = [{
        "id": "400002",
        "date": "2026-08-18T19:00:00Z",
        "home_team": "Team A",
        "away_team": "Team B",
        "score": "",
        "home_participant_id": "10",
        "away_participant_id": "20",
    }]
    stats = {"400002": _FakeFixtureStats({"corners": {"home": 5, "away": 4}})}
    client = _FakeEspnFootballClient("10", fixtures, stats)
    monkeypatch.setattr(providers, "_provider_client", lambda *a, **k: client)

    outcome = providers._fetch_l10_generic("espn-football", "Team A", rate_limiter=None)

    assert "corners_total" in outcome.metrics
    assert "goals_total" not in outcome.metrics


class _FakeHighlightlyClient:
    def __init__(self, l10_matches=None, h2h_matches=None, stats_by_match_id=None):
        self._l10_matches = l10_matches or []
        self._h2h_matches = h2h_matches or []
        self._stats = stats_by_match_id or {}

    def get_last_five_games_result(self, team_id, requested_sample_size=5):
        return SourceOperationResult(SourceResultStatus.SUCCESS, value={"matches": self._l10_matches})

    def get_head_to_head_result(self, team_id_one, team_id_two):
        return SourceOperationResult(SourceResultStatus.SUCCESS, value={"matches": self._h2h_matches})

    def get_statistics_result(self, match_id, *, home_team_id, away_team_id):
        return self._stats.get(
            str(match_id), SourceOperationResult(SourceResultStatus.SCHEMA_ERROR, value=None)
        )


def test_highlightly_l10_goals_ride_on_the_listing_score(monkeypatch):
    """``_normalize_match_row`` already parses ``score`` into ``{"home":
    int, "away": int}`` and computes this team's own ``home_away`` side, so
    l10 goals cost zero extra requests beyond the /statistics call the other
    metrics already make."""
    match = {
        "provider_match_id": "9001",
        "date": "2026-08-18T19:00:00Z",
        "home_team": {"provider_team_id": "10", "team_name": "Team A"},
        "away_team": {"provider_team_id": "20", "team_name": "Team B"},
        "home_away": "home",
        "score": {"display": "2-1", "home": 2, "away": 1},
        "match_status": "finished",
    }
    stats = {"9001": SourceOperationResult(SourceResultStatus.SUCCESS, value={"statistics": []})}
    monkeypatch.setattr(
        providers, "get_client",
        lambda *a, **k: _FakeHighlightlyClient(l10_matches=[match], stats_by_match_id=stats),
    )

    outcome = providers.fetch_highlightly_history("10", "20", rate_limiter=None, mode="l10")

    assert outcome.metrics["goals_total"][0].value == 3
    assert outcome.metrics["goals_for"][0].value == 2
    assert outcome.metrics["goals_against"][0].value == 1


def test_highlightly_h2h_never_emits_a_per_team_goal(monkeypatch):
    """``_normalize_h2h_row`` never sets ``home_away`` (the meeting is not
    read for one side), so an h2h match must yield ``goals_total`` only --
    the same split bzzoiro's own h2h path applies."""
    match = {
        "provider_match_id": "9002",
        "date": "2026-08-18T19:00:00Z",
        "home_team_id": "10",
        "home_team_name": "Team A",
        "away_team_id": "20",
        "away_team_name": "Team B",
        "score": {"display": "1-1", "home": 1, "away": 1},
        "status": "finished",
    }
    stats = {"9002": SourceOperationResult(SourceResultStatus.SUCCESS, value={"statistics": []})}
    monkeypatch.setattr(
        providers, "get_client",
        lambda *a, **k: _FakeHighlightlyClient(h2h_matches=[match], stats_by_match_id=stats),
    )

    outcome = providers.fetch_highlightly_history("10", "20", rate_limiter=None, mode="h2h")

    assert outcome.metrics["goals_total"][0].value == 2
    assert "goals_for" not in outcome.metrics
    assert "goals_against" not in outcome.metrics


def test_highlightly_goals_survive_a_statistics_call_that_fails(monkeypatch):
    """A match with a result but no published /statistics (the highlightly
    analogue of bzzoiro's "8 of 10 h2h meetings have no box score") must
    still contribute its goals -- goals are read from the listing row before
    the /statistics call, and never depend on it succeeding."""
    match = {
        "provider_match_id": "9003",
        "date": "2026-08-18T19:00:00Z",
        "home_team": {"provider_team_id": "10", "team_name": "Team A"},
        "away_team": {"provider_team_id": "20", "team_name": "Team B"},
        "home_away": "home",
        "score": {"display": "0-0", "home": 0, "away": 0},
        "match_status": "finished",
    }
    stats = {"9003": SourceOperationResult(SourceResultStatus.SCHEMA_ERROR, value=None)}
    monkeypatch.setattr(
        providers, "get_client",
        lambda *a, **k: _FakeHighlightlyClient(l10_matches=[match], stats_by_match_id=stats),
    )

    outcome = providers.fetch_highlightly_history("10", "20", rate_limiter=None, mode="l10")

    assert outcome.metrics["goals_total"][0].value == 0
    assert outcome.metrics["goals_for"][0].value == 0
    assert outcome.metrics["goals_against"][0].value == 0
    assert "corners_total" not in outcome.metrics


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
