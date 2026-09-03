"""The draw rule in ``scope_values``, and the plumbing that feeds it.

Written from the 2026-09-03 artefact: fifteen ATP US Open ties, every one of
them enriched to a full nine-metric dossier, and **zero** ATP rows on a
708-row tennis sheet. The whole men's slate was suppressed by the best-of-five
gate, and the gate was not wrong to distrust the sample -- 205 of its 474
``total_sets`` observations were two-set matches, arithmetically impossible in
best-of-five -- it was wrong about the instrument. It withheld the *market*
when the objection was to *observations*, and the sample held both kinds.

The old test was a share of matches that ran to four sets or longer, which
cannot answer the question it was asked: a best-of-five won 3-0 and a
best-of-three won 2-1 are both three sets. 225 of those 474 observations were
exactly three and therefore mute, and Taylor Fritz -- six 2026 Grand Slam
wins, all in straight sets -- scored zero out of six.

So the draw is read from the provider instead: tennis-abstract has stated it
as ``level`` on all 78,750 cached rows and espn-tennis names the tournament.
Properties, not pinned numbers: a tour match leaves a best-of-five sample, a
Grand Slam match stays, an unstated draw leaves *and is counted separately*,
and a fixture nobody pinned is untouched.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from bet.api_clients.tennis_abstract import TennisAbstractClient
from bet.simple_stats.analyze import (
    _TENNIS_LENGTH_DEPENDENT_MARKETS,
    _format_scope_for,
    scope_values,
    tennis_match_format,
)
from bet.simple_stats.contracts import ProviderValue
from bet.simple_stats.providers import (
    _draw_filter_kwargs,
    _match_level_or_none,
    _row_match_level,
    tennis_match_format_for_competition,
)

SLAM = "GRAND_SLAM"
TOUR = "TOUR"


def _pv(
    value: float,
    *,
    match_level: str | None = None,
    provider: str = "tennis-abstract",
    match_id: str = "m1",
    surface: str | None = None,
    opponent: str = "someone",
) -> ProviderValue:
    return ProviderValue(
        provider=provider,
        match_id=match_id,
        match_date="2026-06-29",
        opponent=opponent,
        value=value,
        observed_at="2026-09-03T12:00:00+00:00",
        surface=surface,
        match_level=match_level,
    )


class TestDrawRule:
    def test_a_tour_match_is_dropped_from_a_best_of_five_sample(self) -> None:
        values = [
            _pv(38.0, match_level=SLAM, match_id="s1"),
            _pv(21.0, match_level=TOUR, match_id="t1"),
        ]
        kept, dropped = scope_values(values, match_format="BO5")
        assert [pv.value for pv in kept] == [38.0]
        assert dropped == {"MATCH_FORMAT_MISMATCH": 1}

    def test_an_unstated_draw_is_dropped_under_its_own_reason(self) -> None:
        """The one rule in this module where unknown does not mean kept.

        Four of a men's ~65 events a year are best-of-five, so an unstated
        draw is best-of-three with near-certainty -- and the artefact is not a
        slightly wrong number, it is a tautology priced against Superbet's
        best-of-five ladder. Counted apart from a stated mismatch so that a
        provider we have not taught to speak is never read as a match that was
        measurably a different game.
        """
        kept, dropped = scope_values(
            [
                _pv(21.0, match_id="u1", opponent="Alex de Minaur"),
                _pv(38.0, match_level=SLAM, match_id="s1", opponent="Jack Draper"),
            ],
            match_format="BO5",
        )
        assert [pv.value for pv in kept] == [38.0]
        assert dropped == {"MATCH_FORMAT_UNKNOWN": 1}

    def test_one_meeting_with_an_opponent_lends_its_draw_to_the_others(self) -> None:
        """The residual of grouping by opponent, pinned so it is a known
        property rather than a surprise.

        The two tennis providers cannot be joined on a date: tennis-abstract
        stamps every round of a tournament with the tournament's *start* date
        (all six of Struff's 2026 Wimbledon rows read 2026-06-29) while ESPN
        stamps the match. Opponent is the only key that crosses them, so two
        meetings with one opponent share a group, and a group where the stating
        rows agree hands that value on. Where they disagree nothing moves --
        see the test below, which is the case this one becomes as soon as the
        second meeting is also stated.
        """
        values = [
            _pv(38.0, match_level=SLAM, match_id="ta1", opponent="Carlos Alcaraz"),
            _pv(21.0, provider="espn-tennis", match_id="e9", opponent="Carlos Alcaraz"),
        ]
        kept, _ = scope_values(values, match_format="BO5")
        assert len(kept) == 2

    def test_a_best_of_three_fixture_drops_nothing(self) -> None:
        """A Grand Slam observation in a women's sample is best-of-three too:
        the draw is the same, the format is not. Folding the two would suppress
        every WTA row at the same tournament."""
        values = [
            _pv(21.0, match_level=SLAM, match_id="s1"),
            _pv(18.0, match_level=TOUR, match_id="t1"),
            _pv(20.0, match_id="u1"),
        ]
        kept, dropped = scope_values(values, match_format="BO3")
        assert len(kept) == 3
        assert dropped == {}

    def test_an_unpinned_fixture_drops_nothing(self) -> None:
        values = [_pv(21.0, match_level=TOUR, match_id="t1"), _pv(20.0, match_id="u1")]
        kept, dropped = scope_values(values, match_format=None)
        assert len(kept) == 2
        assert dropped == {}

    def test_the_draw_reaches_the_rows_of_the_same_match_that_omit_it(self) -> None:
        """``_share_within_a_match``, on the draw instead of the surface.

        espn-tennis states no ``level`` and spells its tournaments "ATP
        National Bank Open presented by Rogers", so the format pin resolves its
        Grand Slam rows and leaves the rest unstated. Without this, the draw
        rule could only ever fire on tennis-abstract and would reweight every
        length-dependent sample toward ESPN -- the failure the surface rule
        already had and fixed.
        """
        values = [
            _pv(38.0, match_level=SLAM, match_id="ta1", opponent="Carlos Alcaraz"),
            _pv(39.0, provider="espn-tennis", match_id="e1", opponent="Carlos Alcaraz"),
        ]
        kept, dropped = scope_values(values, match_format="BO5")
        assert sorted(pv.value for pv in kept) == [38.0, 39.0]
        assert dropped == {}

    def test_two_meetings_that_disagree_share_nothing(self) -> None:
        """Unanimity is what makes the sharing safe. One opponent met in a slam
        and again on tour puts both in one group; the group disagrees, so the
        ESPN row keeps its None and is dropped as unknown rather than assumed
        to be either."""
        values = [
            _pv(38.0, match_level=SLAM, match_id="ta1", opponent="Carlos Alcaraz"),
            _pv(21.0, match_level=TOUR, match_id="ta2", opponent="Carlos Alcaraz"),
            _pv(39.0, provider="espn-tennis", match_id="e1", opponent="Carlos Alcaraz"),
        ]
        kept, dropped = scope_values(values, match_format="BO5")
        assert [pv.value for pv in kept] == [38.0]
        assert dropped == {"MATCH_FORMAT_MISMATCH": 1, "MATCH_FORMAT_UNKNOWN": 1}


class TestWhichMarketsTheRuleAddresses:
    def test_length_dependent_markets_are_scoped(self) -> None:
        for market in _TENNIS_LENGTH_DEPENDENT_MARKETS:
            assert _format_scope_for(market, "BO5") == "BO5", market

    @pytest.mark.parametrize(
        "market",
        ["first_serve_pct", "break_points_faced", "break_points_saved_pct"],
    )
    def test_a_rate_is_the_same_quantity_in_either_format(self, market: str) -> None:
        """The objection is that a market's value scales with match length, so
        it has no business shrinking a sample for one that does not. A player's
        tour season is where nearly all their observations live: on the
        2026-09-03 slate, scoping the rates too would have taken samples of
        29-37 matches into single digits to no purpose."""
        assert _format_scope_for(market, "BO5") is None


class TestDrawIngest:
    def test_only_level_bearing_providers_record_it(self) -> None:
        assert _match_level_or_none("tennis-abstract", "G") == SLAM
        assert _match_level_or_none("espn-football", "G") is None
        assert _match_level_or_none("bzzoiro", "G") is None

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("G", SLAM),
            ("g", SLAM),
            (" G ", SLAM),
            ("M", TOUR),
            ("A", TOUR),
            ("C", TOUR),
            ("S", TOUR),
            ("F", TOUR),
            ("25", TOUR),
            ("15", TOUR),
        ],
    )
    def test_the_level_column_is_normalised(self, raw: str, expected: str) -> None:
        assert _match_level_or_none("tennis-abstract", raw) == expected

    @pytest.mark.parametrize("raw", ["D", "O"])
    def test_davis_cup_and_the_olympics_state_nothing(self, raw: str) -> None:
        """Both were best-of-five within living memory -- Davis Cup rubbers
        until 2018, the Olympic men's final until 2012 -- so neither may be
        asserted best-of-three. Inside the 500-day observation window this
        costs nothing; it is here so that widening that window cannot turn a
        wrong assertion into deleted observations."""
        assert _match_level_or_none("tennis-abstract", raw) is None

    @pytest.mark.parametrize("raw", ["", "unknown", None, 3, "grand slam"])
    def test_anything_unplaceable_is_not_stated(self, raw: object) -> None:
        assert _match_level_or_none("tennis-abstract", raw) is None

    def test_a_stated_level_is_preferred_to_the_tournament_name(self) -> None:
        assert _row_match_level("tennis-abstract", {"level": "A"}, None) == "A"

    def test_espn_rows_are_resolved_through_the_format_pin(self) -> None:
        class _Fixture:
            competition_name = "ATP US Open"

        assert _match_level_or_none(
            "espn-tennis", _row_match_level("espn-tennis", {}, _Fixture())
        ) == SLAM

    def test_an_unpinned_tournament_name_is_not_read_as_a_tour_event(self) -> None:
        """A slam we failed to recognise must cost an observation we cannot
        place, never a real best-of-five observation asserted to be something
        else. ESPN's own cache holds "ATP National Bank Open presented by
        Rogers", so this path is exercised on most of its rows."""
        class _Fixture:
            competition_name = "ATP National Bank Open presented by Rogers"

        assert _row_match_level("espn-tennis", {}, _Fixture()) is None


class TestTheFetchIsScopedTooOrTheRuleHasNothingToKeep:
    """The draw rule can only keep observations that reached the dossier.

    A chronological last-ten reaches almost none: an ATP player's last ten
    matches in September are Cincinnati, Winston-Salem and Challengers. On the
    2026-09-03 slate the fifteen men's dossiers held 170 aces observations and
    not one came from a Grand Slam, while those same players' caches held
    between 51 and 201 Slam matches each. Filtering after the slice is a
    correct rule over a sample that cannot answer.
    """

    def test_a_best_of_five_fixture_asks_for_grand_slam_matches(self) -> None:
        assert _draw_filter_kwargs("tennis-abstract", "ATP US Open") == {"level": "G"}

    @pytest.mark.parametrize(
        "competition", ["WTA US Open", "ATP Cincinnati Open", "Championship", ""]
    )
    def test_every_other_competition_asks_for_what_it_always_did(
        self, competition: str
    ) -> None:
        assert _draw_filter_kwargs("tennis-abstract", competition) == {}

    @pytest.mark.parametrize("provider", ["espn-tennis", "espn-football", "bzzoiro"])
    def test_only_a_provider_that_can_answer_cheaply_is_asked(
        self, provider: str
    ) -> None:
        """espn-tennis is deliberately absent: its route is per season and
        already returns the year, so its Grand Slam rows are in the sample
        without asking, and asking would cost calls it has no cheap answer
        for."""
        assert _draw_filter_kwargs(provider, "ATP US Open") == {}

    def test_the_filter_selects_before_the_slice_not_after(self) -> None:
        """The distinction the whole fix turns on. Ten tour matches followed by
        two slams: slicing first leaves nothing."""
        matches = [{"level": "A", "date": f"2026-08-{i + 1:02d}"} for i in range(10)]
        matches += [
            {"level": "G", "date": "2026-06-29"},
            {"level": "G", "date": "2026-05-25"},
        ]
        assert len(TennisAbstractClient._of_level(matches, "G")[:10]) == 2
        assert TennisAbstractClient._of_level(matches, None) == matches

    @pytest.mark.parametrize("level", ["G", "g"])
    def test_the_site_s_own_spelling_is_accepted(self, level: str) -> None:
        matches = [{"level": "G"}, {"level": "M"}]
        assert TennisAbstractClient._of_level(matches, level) == [{"level": "G"}]

    def test_a_row_with_no_level_is_never_taken_for_a_slam(self) -> None:
        assert TennisAbstractClient._of_level([{"level": ""}, {}], "G") == []

    def test_qualifying_is_not_selected_for_a_best_of_five_fixture(self) -> None:
        """Grand Slam qualifying is best-of-three, at all four tournaments and
        on both tours, and tennis-abstract files it under the same ``level`` as
        the main draw. Found by reading the sample this filter built: four of
        the six matches it selected for Blockx-Trungelliti were Q1/Q2/Q3."""
        matches = [
            {"level": "G", "round": "R128"},
            {"level": "G", "round": "Q1"},
            {"level": "G", "round": "Q2"},
            {"level": "G", "round": "Q3"},
        ]
        assert TennisAbstractClient._of_level(matches, "G") == [
            {"level": "G", "round": "R128"}
        ]

    def test_a_quarter_final_is_not_qualifying(self) -> None:
        """"QF" starts with a Q and is the deepest main-draw round there is."""
        matches = [{"level": "G", "round": "QF"}, {"level": "G", "round": "SF"}]
        assert TennisAbstractClient._of_level(matches, "G") == matches


class TestQualifyingIsItsOwnDraw:
    @pytest.mark.parametrize(
        "round_name", ["Q1", "Q2", "Q3", "q1", " Q2 ", "Qualifying"]
    )
    def test_a_slam_qualifier_is_not_the_main_draw(self, round_name: str) -> None:
        assert _match_level_or_none(
            "tennis-abstract",
            _row_match_level(
                "tennis-abstract", {"level": "G", "round": round_name}, None
            ),
        ) == "GRAND_SLAM_QUALIFYING"

    @pytest.mark.parametrize(
        "round_name", ["R128", "R64", "R32", "R16", "QF", "SF", "F"]
    )
    def test_every_main_draw_round_is_the_main_draw(self, round_name: str) -> None:
        assert _match_level_or_none(
            "tennis-abstract",
            _row_match_level(
                "tennis-abstract", {"level": "G", "round": round_name}, None
            ),
        ) == SLAM

    def test_a_qualifier_leaves_a_best_of_five_sample_as_a_mismatch(self) -> None:
        """Not as "unknown": the draw is known, it is simply the best-of-three
        one. Left in, it would be this whole change's own defect arriving by a
        new route and wearing the label GRAND_SLAM."""
        kept, dropped = scope_values(
            [
                _pv(38.0, match_level=SLAM, match_id="m1", opponent="one"),
                _pv(
                    18.0, match_level="GRAND_SLAM_QUALIFYING",
                    match_id="m2", opponent="two",
                ),
            ],
            match_format="BO5",
        )
        assert [pv.value for pv in kept] == [38.0]
        assert dropped == {"MATCH_FORMAT_MISMATCH": 1}

    def test_a_tour_round_named_q1_does_not_exist_but_is_harmless(self) -> None:
        """The round is only consulted for Grand Slam rows, so a tour event
        that spells a round oddly keeps its own class."""
        row = {"level": "A", "round": "Q1"}
        assert _row_match_level("tennis-abstract", row, None) == "A"


class TestTheFormatTableIsReadOnce:
    def test_both_sides_of_the_comparison_read_the_same_loader(self) -> None:
        """ANALYZE asks what format tonight's fixture is; the ingest side asks
        whether a historical ESPN row was a Grand Slam match. Two loaders of
        one table is how the two come to disagree about a name and delete every
        observation that was in fact a match."""
        for name in ("ATP US Open", "WTA Wimbledon", "Championship", None, ""):
            assert tennis_match_format(name) == (
                tennis_match_format_for_competition(name)
            )

    def test_every_pinned_name_is_a_grand_slam(self) -> None:
        """``_row_match_level`` reads "pinned" as "Grand Slam", which holds
        because men's Grand Slam main-draw singles is the whole of
        best-of-five and the WTA halves are listed only so a checked
        competition is distinguishable from an unchecked one. If a
        best-of-three tour event is ever added to this table, that inference
        breaks and this test is where it says so."""
        pinned = json.loads(
            (
                pathlib.Path(__file__).resolve().parents[2]
                / "config"
                / "tennis_match_format.json"
            ).read_text(encoding="utf-8")
        )["formats"]
        slams = {
            "US Open", "Australian Open", "Roland Garros",
            "French Open", "Wimbledon",
        }
        for name in pinned:
            tour, _, tournament = name.partition(" ")
            assert tour in {"ATP", "WTA"}, name
            assert tournament in slams, name
