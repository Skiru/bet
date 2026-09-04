"""The tennis source layer, after the 2026-09-02 consolidation.

Three providers went in and two came out. What these tests hold in place is
not the roster but the reasons: that both remaining providers compute games and
sets from the same published quantity, that ESPN's rows can be scoped like
everyone else's, and that each of the four ways a scoreboard row can lie is
refused rather than averaged.

Every number quoted in a docstring here was measured against live provider data
on 2026-09-02 and the measurement is named, so a future reader can re-run it
rather than trust it.
"""
from __future__ import annotations

import pytest

from bet.api_clients.espn import (
    _TENNIS_SCAN_DAYS,
    _TENNIS_SCAN_STRIDE,
    _parse_tennis_competition,
    _tennis_scan_offsets,
)
from bet.api_clients.tennis_abstract import TennisAbstractClient
from bet.api_clients.tennis_score import parse_tennis_score
from bet.simple_stats.analyze import tennis_surface
from bet.simple_stats.providers import (
    _ALIASES_BY_PROVIDER,
    _combine_stats,
    _make_values,
    _row_match_level,
    _row_surface,
    _tennis_match_unfinished,
    reset_tennis_tournament_map_cache,
    tennis_surface_for_competition,
    tennis_tournament_by_id,
)

# --- the score, which is now the definition ---------------------------------


@pytest.mark.parametrize(
    "raw,games,sets",
    [
        # ESPN's sentence form: seeding and tie-break points both sit in
        # brackets and neither is a set score.
        (
            "(2) Carlos Alcaraz (ESP) bt Roman Safiullin (RUS) 6-4 6-4 6-4",
            30.0,
            3,
        ),
        (
            "Jacob Fearnley (GBR) bt Roberto Carballes Baena (ESP) 7-6 (7-3) 6-3",
            22.0,
            2,
        ),
        # tennis-abstract's compact form.
        ("7-6(2) 6-3", 22.0, 2),
        ("6-4 3-6 7-5", 31.0, 3),
        # A match tie-break written in square brackets.
        ("6-3 4-6 [10-7]", 19.0, 2),
    ],
)
def test_a_published_score_reads_the_same_whoever_published_it(raw, games, sets):
    """One parser, both feeds. The two providers only corroborate each other on
    total games because they now answer the same question the same way."""
    parsed = parse_tennis_score(raw)
    assert parsed is not None
    assert parsed.games == games
    assert parsed.sets == sets
    assert parsed.completed


@pytest.mark.parametrize(
    "raw",
    [
        "Tomas Machac (CZE) bt (1) Carlos Alcaraz (ESP) w/o",
        "6-4 1-2 ret",
        "7-6(3) 6-7(5) 1-0 ret",  # 27 games: clears every threshold, still not a match
    ],
)
def test_a_match_that_did_not_finish_says_so(raw):
    """The reason the ``completed`` flag exists rather than a games threshold.

    ``providers._is_absent_not_zero`` infers an abandonment from a match being
    shorter than 6-0 6-0. A retirement at 7-6 6-7 1-0 is twenty-seven games and
    three sets, so it clears that bar comfortably -- while being exactly the
    shape that flatters an UNDER.
    """
    parsed = parse_tennis_score(raw)
    assert parsed is None or not parsed.completed


def test_a_string_that_states_no_score_is_not_a_zero():
    """tennis-abstract writes "Walkover" and "&nbsp;" on a handful of rows."""
    for raw in (None, "", "Walkover", "&nbsp;", ">"):
        assert parse_tennis_score(raw) is None


def test_total_games_is_not_service_games():
    """The defect the parser was written for, stated as arithmetic.

    ``games``/``ogames`` are service games. A tie-break game has no server, so
    it appears in neither, and their sum is one short per 7-6 set. Measured on
    tennis-abstract's own cache: across 56,280 completed rows carrying serve
    data the shortfall equalled the number of tie-break sets on 98.37% of them
    (38,036 rows with no tie-break agreed; 14,733 with one were one short; 2,387
    with two were two short; 200 with three were three short).
    """
    parsed = parse_tennis_score("7-6(2) 6-3")
    assert parsed.tie_break_sets == 1
    assert parsed.games == 22.0
    # Which is what a 7-6 set is worth: 13 games, not the 12 that had a server.
    assert parsed.set_scores[0] == (7, 6)


# --- tennis-abstract: whose games were those --------------------------------


@pytest.mark.parametrize(
    "score,result,expected",
    [
        ("7-6(2) 6-3", "W", 13.0),   # winner is listed first, and won
        ("6-3 7-6(5)", "L", 9.0),    # winner is still listed first; we are second
        ("6-4 3-6 7-5", "W", 16.0),
    ],
)
def test_the_players_own_games_come_from_the_score_and_the_result(
    score, result, expected
):
    """tennis-abstract writes the score **winner-first**, not player-first.

    Measured over the whole cache: on 31,141 rows marked ``L`` the first-listed
    side had won more sets 31,109 times, and on 45,261 marked ``W`` it had
    45,218 times. So ``wl`` is what says which column is ours, and this is what
    restores the per-player markets that left with bzzoiro-tennis.
    """
    assert (
        TennisAbstractClient._player_games_won(parse_tennis_score(score), result)
        == expected
    )


@pytest.mark.parametrize(
    "score,result",
    [
        ("3-6 6-7(5)", "L"),   # loser-first spelling: the two columns disagree
        ("6-4 6-4", None),     # no result marker at all
        ("6-4 6-4", "?"),
    ],
)
def test_an_ambiguous_row_yields_no_per_player_figure(score, result):
    """Refused, not guessed. 75 of 76,402 completed rows land here.

    A per-player games figure attributed to the wrong player is the opponent's
    line filed under this player's name -- the Benoit Paire fabrication in
    miniature, and the reason this module never scores a near-match.
    """
    assert TennisAbstractClient._player_games_won(
        parse_tennis_score(score), result
    ) is None


# --- espn: what a scoreboard row is allowed to become ------------------------


def _competition(**overrides):
    comp = {
        "id": "184689",
        "date": "2026-08-26T15:05Z",
        "tournamentId": 189,
        "status": {"type": {"name": "STATUS_FINAL", "state": "post"}},
        "type": {"slug": "mens-singles", "text": "Men's Singles"},
        "round": {"displayName": "Round 1"},
        "format": {"regulation": {"periods": 5}},
        "notes": [{"text": "A Player (GBR) bt B Player (ESP) 7-6 (7-3) 6-3"}],
        "competitors": [
            {
                "id": "222", "homeAway": "away", "order": 2,
                "athlete": {"displayName": "B Player"},
                "linescores": [{"value": 6.0, "tiebreak": 3}, {"value": 3.0}],
            },
            {
                "id": "111", "homeAway": "home", "order": 1,
                "athlete": {"displayName": "A Player"},
                "curatedRank": {"current": 4},
                "linescores": [
                    {"value": 7.0, "tiebreak": 7, "winner": True},
                    {"value": 6.0, "winner": True},
                ],
            },
        ],
    }
    comp.update(overrides)
    return comp


_EVENT = {"id": "189-2026", "name": "US Open", "season": {"year": 2026}}
_GROUPING = {"grouping": {"slug": "mens-singles", "displayName": "Men's Singles"}}


def test_a_scoreboard_row_arrives_with_everything_needed_to_scope_it():
    """Every ESPN tennis observation used to reach ANALYZE with
    ``competition_id=None, season_id=None`` and no surface, which is precisely
    what ``scope_values`` needs in order to drop anything -- so nothing could
    ever be scoped out of an ESPN sample."""
    row = _parse_tennis_competition(_EVENT, _GROUPING, _competition())

    assert row["competition_provider_id"] == "189"
    assert row["season"] == "2026"
    assert row["tour"] == "ATP"
    assert row["round"] == "Round 1"
    # Spelled the way DISCOVER spells a competition, so one table serves both
    # sides of the surface comparison.
    assert row["competition_name"] == "ATP US Open"
    assert tennis_surface_for_competition(row["competition_name"]) == "Hard"


def test_a_missing_tournament_id_is_a_data_gap_not_the_event_id():
    """Step 2 of the source-consolidation plan: ``tournamentId`` used to fall
    back to ``event.get("id")``, which numbers one *match* (per round, per
    year), not a tournament. A row that never states its tournamentId must
    read as unknown so config/tennis_tournament_map.json is never asked to
    pin a number that was never really a tournament id."""
    comp = _competition()
    del comp["tournamentId"]
    row = _parse_tennis_competition(_EVENT, _GROUPING, comp)
    assert row["competition_provider_id"] == ""


def test_the_sides_are_ordered_by_what_espn_calls_them_not_by_position():
    """Across all 6,546 finished singles matches in a year of ATP scoreboards,
    ``homeAway`` read ("away", "home") -- every single row. Indexing by list
    position therefore labelled every ESPN tennis observation backwards. Totals
    survived that; a per-side figure such as ``ranking`` did not."""
    row = _parse_tennis_competition(_EVENT, _GROUPING, _competition())

    assert row["home_team"] == "A Player"
    assert row["home_participant_id"] == "111"
    assert row["stats"]["games_won"] == {"home": 13.0, "away": 9.0}
    assert row["stats"]["ranking"] == {"home": 4.0}


def test_the_match_format_is_not_read_off_the_scoreboard():
    """``format.regulation.periods`` is the obvious candidate and is a property
    of the *URL*, not the match: probed live, the ATP scoreboard reported 5 for
    everything it served -- including the US Open women's singles and
    Monte-Carlo, where a men's final is best-of-three -- while the WTA
    scoreboard reported 3 for everything including men's singles."""
    row = _parse_tennis_competition(_EVENT, _GROUPING, _competition())
    assert "best_of" not in row
    assert "best_of" not in row["stats"]


@pytest.mark.parametrize(
    "status",
    ["STATUS_RETIRED", "STATUS_WALKOVER", "STATUS_SUSPENDED", "STATUS_SCHEDULED"],
)
def test_only_a_final_is_a_match(status):
    """``state == "post"`` is every match that stopped happening. Over a year of
    ATP scoreboards: 6,327 STATUS_FINAL, 174 STATUS_RETIRED, 37
    STATUS_WALKOVER, 8 STATUS_SUSPENDED. The walkovers carry no linescores at
    all and used to arrive as matches in which both players won zero games."""
    comp = _competition(status={"type": {"name": status, "state": "post"}})
    assert _parse_tennis_competition(_EVENT, _GROUPING, comp) is None


def test_a_provider_contradicting_itself_is_dropped_whole():
    """The linescores and the published score line are two transcriptions of one
    result. Measured on 310 finished matches they agreed on 309; the tenth
    parsed row of the year was ESPN's own "6-3 6-4 6-4 6-4" -- four sets won by
    the same player -- against linescores summing to 29."""
    comp = _competition(notes=[{"text": "A Player bt B Player 6-3 6-4 6-4 6-4"}])
    assert _parse_tennis_competition(_EVENT, _GROUPING, comp) is None


def test_doubles_never_enter_the_pipeline():
    """A doubles draw sits in the same groupings list as the singles one, and
    nothing downstream models a pair."""
    grouping = {"grouping": {"slug": "mens-doubles", "displayName": "Men's Doubles"}}
    assert _parse_tennis_competition(_EVENT, grouping, _competition()) is None


# --- the scan window ---------------------------------------------------------


def test_the_scan_walks_recent_days_one_by_one_and_then_strides():
    """A tennis scoreboard date returns the whole draw of every tournament
    running that day, not that day's matches -- probed live, ``dates=20260902``
    returned 625 competitions dated 2026-08-24 to 2026-09-13. That is what makes
    a stride safe here and made it unsafe before.

    Measured against ground truth (365 consecutive days of the ATP scoreboard,
    6,546 unique finished singles matches): this offset list found all 6,546 in
    102 requests, where 60 consecutive days found 1,737.
    """
    offsets = _tennis_scan_offsets()

    assert offsets == sorted(offsets), "most recent first, and no repeats"
    assert len(set(offsets)) == len(offsets)
    assert offsets[:14] == list(range(14)), "the recent fortnight is not thinned"
    assert max(offsets) >= _TENNIS_SCAN_DAYS - _TENNIS_SCAN_STRIDE
    # The shortest run of days on which any of the year's 62 events was visible
    # was five, so the stride has to clear five with something to spare.
    gaps = [b - a for a, b in zip(offsets, offsets[1:])]
    assert max(gaps) <= 4 < 5


# --- the surface, on both sides of the comparison ----------------------------


def test_espn_rows_are_surfaced_from_the_tournament_they_name():
    """espn-tennis states no surface and never will. Until 2026-09-02 that did
    not mean "no information", it meant **immunity**: ``scope_values`` drops an
    observation only when both surfaces are known, so on that day's slate
    tennis-abstract lost 145 of its 522 total_games observations to the filter
    and espn-tennis lost 0 of 478 -- and the raw pool's 47.8% ESPN became 55.9%
    of the scoped one."""
    fixture = {"competition_name": "ATP US Open"}
    assert _row_surface("espn-tennis", {}, fixture) == "Hard"
    # A stated surface still wins where there is one.
    assert _row_surface("tennis-abstract", {"surface": "Clay"}, {}) == "Clay"

    # Composed with the gate that decides whether a provider may carry one at
    # all: ``_row_surface`` reports what the row says, ``_surface_or_none``
    # decides who is allowed to say it, and a football provider is not.
    tennis = _make_values(
        "espn-tennis", "1", "2026-08-26", "B Player", {"total_games": 22.0},
        surface=_row_surface("espn-tennis", {}, fixture),
    )
    assert tennis["total_games"].surface == "Hard"
    football = _make_values(
        "espn-football", "1", "2026-08-26", "Betis", {"corners_total": 9.0},
        surface=_row_surface("espn-football", {"surface": "Clay"}, fixture),
    )
    assert football["corners_total"].surface is None


def test_both_sides_of_the_surface_rule_read_one_table():
    """The fixture's surface and a historical row's meet in an ``!=`` inside
    ``scope_values``. Answering them from two config reads is how "Hard" comes
    to be compared with "hard" and every correctly surfaced observation is
    silently deleted."""
    assert tennis_surface("ATP US Open") == tennis_surface_for_competition(
        "ATP US Open"
    )
    assert tennis_surface("WTA Wimbledon") == "Grass"
    # An unpinned tournament filters nothing, in either direction.
    assert tennis_surface("ATP Rolex Monte-Carlo Masters") is None
    unpinned = {"competition_name": "ATP Winston-Salem Open"}
    assert _row_surface("espn-tennis", {}, unpinned) is None


def test_tournament_id_covers_events_the_name_table_never_did():
    """Step 2: config/tennis_surface_map.json pins ten Grand Slam names and
    nothing else, so before this table, an espn-tennis row from any of the
    other ~18 tournaments a real slate touches (Cincinnati, Halle, Monte-Carlo
    ...) carried no surface at all. Keyed by ESPN's own tournamentId instead
    of by name, so "Ostrava" vs "Ostrava CH" style collisions cannot happen."""
    reset_tennis_tournament_map_cache()
    cincinnati = {"competition_provider_id": "718", "competition_name": "ATP Cincinnati Open"}
    assert _row_surface("espn-tennis", {}, cincinnati) == "Hard"
    monte_carlo = {"competition_provider_id": "42", "competition_name": "ATP Rolex Monte-Carlo Masters"}
    assert _row_surface("espn-tennis", {}, monte_carlo) == "Clay"
    # tennis-abstract never states a tournamentId, so it is untouched by this
    # table and keeps resolving through its own stated ``surface`` field.
    assert _row_surface("tennis-abstract", {}, {"competition_provider_id": "718"}) is None


def test_tournament_id_takes_priority_but_falls_back_to_the_name_table():
    """The id table is tried first, but a row with no id (or an unpinned one)
    still resolves through the name table exactly as it did before this table
    existed -- nothing that worked before this change stops working."""
    reset_tennis_tournament_map_cache()
    us_open_by_name_only = {"competition_name": "ATP US Open"}
    assert _row_surface("espn-tennis", {}, us_open_by_name_only) == "Hard"
    unlisted_id = {"competition_provider_id": "999999", "competition_name": "ATP US Open"}
    assert _row_surface("espn-tennis", {}, unlisted_id) == "Hard"


def test_tournament_id_gives_a_tour_match_its_own_draw_class():
    """A men's tour event (not a Grand Slam) must read as best-of-three, not
    as unknown -- unknown and best-of-three are not the same claim, even
    though both currently drop a best-of-five sample's observation. Getting
    this right on espn-tennis's own row matters once tennis-abstract stops
    being the only source ``_share_within_a_match`` can recover it from (step
    4 narrows tennis-abstract to aces/double-faults only)."""
    reset_tennis_tournament_map_cache()
    cincinnati = {"competition_provider_id": "718", "round": "Round 1"}
    assert _row_match_level("espn-tennis", {}, cincinnati) == "A"
    us_open = {"competition_provider_id": "189", "round": "Round 1"}
    assert _row_match_level("espn-tennis", {}, us_open) == "G"
    us_open_qualifying = {"competition_provider_id": "189", "round": "Q1"}
    assert _row_match_level("espn-tennis", {}, us_open_qualifying) == "GQ"


def test_tennis_tournament_by_id_is_unknown_not_a_guess():
    reset_tennis_tournament_map_cache()
    assert tennis_tournament_by_id(None) is None
    assert tennis_tournament_by_id("") is None
    assert tennis_tournament_by_id("0") is None
    assert tennis_tournament_by_id("999999") is None
    assert tennis_tournament_by_id("718") == {"surface": "Hard", "level": "TOUR"}
    assert tennis_tournament_by_id("189") == {"surface": "Hard", "level": "GRAND_SLAM"}


# --- what the two providers now have in common -------------------------------


def test_the_two_providers_report_the_same_quantity_for_total_games():
    """The point of the whole exercise. Both derive games and sets from the
    published set score, so ``AGREE`` on a tennis total_games row means the two
    read the same match -- not that one of them is reliably one game low and the
    tolerance is 1.0."""
    espn = _parse_tennis_competition(_EVENT, _GROUPING, _competition())
    espn_combined = _combine_stats(
        "espn-tennis", espn["stats"], _ALIASES_BY_PROVIDER["espn-tennis"]
    )

    abstract_combined = _combine_stats(
        "tennis-abstract",
        {
            "total_games": 22.0,
            "total_sets": 2.0,
            "score": "7-6(2) 6-3",
            "completed": True,
        },
        _ALIASES_BY_PROVIDER["tennis-abstract"],
    )

    assert espn_combined["total_games"] == abstract_combined["total_games"] == 22.0
    assert espn_combined["total_sets"] == abstract_combined["total_sets"] == 2.0


@pytest.mark.parametrize("provider", ["espn-tennis", "tennis-abstract"])
def test_an_unfinished_match_is_refused_by_both_providers(provider):
    assert _tennis_match_unfinished(
        provider, {"completed": False, "score": "6-4 1-2 ret"}
    )
    assert not _tennis_match_unfinished(
        provider, {"completed": True, "score": "6-4 6-4"}
    )
    # A payload that says nothing falls through to the threshold rule instead.
    assert not _tennis_match_unfinished(provider, {})


def test_football_is_never_subject_to_the_tennis_completion_rule():
    assert not _tennis_match_unfinished("espn-football", {"completed": False})
