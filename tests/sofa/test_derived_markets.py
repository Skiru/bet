"""The both-teams, comparative and handicap families.

Every test here fails on the code as it stood on 2026-09-18, when all of these
markets went to `unmapped_markets` — 42,426 market names in one day — and none
of them could be priced at all.
"""

from datetime import timedelta
from typing import Any

import pytest

from bet.sofa.contracts import (
    Fixture,
    FixtureOffer,
    FixtureSamples,
    MetricSample,
    Observation,
    PricedRung,
)
from bet.sofa.derived import (
    _market_probabilities,
    price_derived_rungs,
    resolve_subject,
)
from bet.sofa.market_mapper import classify_derived_market, classify_market
from bet.sofa.offer import OfferFetcher
from bet.sofa.timeutil import now


def make_fixture(home: str = "Brentford", away: str = "Chelsea") -> Fixture:
    return Fixture(
        sofascore_event_id=1,
        superbet_event_ids=["101"],
        sport="football",
        kickoff_utc=now(),
        home_name=home,
        away_name=away,
        home_entity_id=1,
        away_entity_id=2,
        competition_name="Premier League",
        competition_id=17,
        season_id=1,
        category_name="England",
        identity="CONFIRMED",
        round_number=None,
        round_name=None,
        cup_round_type=None,
        previous_leg_event_id=None,
        venue_name=None,
        referee=None,
        ground_type=None,
        default_period_count=2,
    )


def observations(values: list[float]) -> list[Observation]:
    base = now()
    return [
        Observation(
            sofascore_event_id=1000 + i,
            match_date_utc=base - timedelta(days=i + 1),
            opponent=f"Opp{i}",
            value=v,
            competition_id=17,
            season_id=1,
            venue=None,
        )
        for i, v in enumerate(values)
    ]


def make_samples(
    metric: str, side_a: list[float], side_b: list[float]
) -> FixtureSamples:
    return FixtureSamples(
        sofascore_event_id=1,
        readiness="READY",
        metrics={
            metric: MetricSample(
                metric=metric,
                side_a=observations(side_a),
                side_b=observations(side_b),
                h2h=[],
            )
        },
        gaps=[],
    )


class DummyClient:
    def __init__(self, items: list[dict[str, Any]]):
        self.items = items

    def event_odds(self, _event_id: str | int) -> dict[str, Any]:
        return {"odds": self.items}


class TestMapperRegressions:
    def test_player_games_market_has_no_dash(self) -> None:
        """Superbet sends "<player> liczba gemow", not "<player> - liczba gemow".

        The dashed pattern matched nothing, so games_won_for — a declared
        metric with a working extractor — was unreachable, and 139 priced
        markets a day were discarded over one character.
        """
        assert classify_market("Adrian Andreev liczba gemów") == (
            "games_won_for",
            "adrian andreev",
        )

    def test_whole_match_games_market_still_wins(self) -> None:
        assert classify_market("liczba gemów") == ("games_total", "")

    @pytest.mark.parametrize(
        "name",
        [
            "1. set - Adrian Andreev liczba gemów",
            "2 set - Oleg Prihodko liczba gemów",
            "X. set - Adrian Andreev liczba gemów",
        ],
    )
    def test_set_scoped_games_market_is_refused(self, name: str) -> None:
        """A set line priced against a whole-match sample is F29 in tennis.

        268 of these were quoted on 2026-09-18 against 139 whole-match ones,
        so the no-dash pattern without this guard would have mispriced twice
        as many markets as it recovered.
        """
        assert classify_market(name) is None

    def test_combination_market_is_not_a_participant(self) -> None:
        assert classify_market("Mecz & liczba gemów") is None


class TestDerivedClassification:
    @pytest.mark.parametrize(
        ("market", "selection", "line", "expected"),
        [
            (
                "Każda z drużyn powyżej X rzutów rożnych",
                "Powyżej 3.5 - tak",
                "3.5",
                ("both_over_corners", "", 3.5, "OVER"),
            ),
            (
                "Każda z drużyn powyżej X kartek",
                "Powyżej 1.5 - nie",
                "1.5",
                ("both_over_cards_points", "", 1.5, "UNDER"),
            ),
            (
                # Superbet reverses the order for fouls and only for fouls.
                "Każda z drużyn powyżej X fauli",
                "Tak - 8.5",
                "8.5",
                ("both_over_fouls", "", 8.5, "OVER"),
            ),
            (
                "Każda z drużyn powyżej X celnych strzałów",
                "Powyżej 2.5 - tak",
                "2.5",
                ("both_over_shots_on_target", "", 2.5, "OVER"),
            ),
            (
                "Obie drużyny strzelą",
                "tak",
                None,
                ("both_over_goals", "", 0.5, "OVER"),
            ),
            (
                "Obie drużyny strzelą powyżej 1.5 gola",
                "nie",
                None,
                ("both_over_goals", "", 1.5, "UNDER"),
            ),
            (
                "Liczba rzutów rożnych - H2H",
                "remis",
                None,
                ("most_corners", "__draw__", 0.0, "OVER"),
            ),
            (
                "Najwięcej kartek",
                "1",
                None,
                ("most_cards_points", "1", 0.0, "OVER"),
            ),
            (
                "Rzuty rożne handicap",
                "Chelsea (1.5)",
                "-1.5",
                ("handicap_corners", "chelsea", 1.5, "OVER"),
            ),
            (
                "Handicap gemy",
                "Adrian Andreev (8.5)",
                "8.5",
                ("handicap_games", "adrian andreev", 8.5, "OVER"),
            ),
        ],
    )
    def test_selection_maps_to_market(
        self, market: str, selection: str, line: str | None, expected: tuple
    ) -> None:
        assert classify_derived_market(market, selection, line) == expected

    def test_bet_builder_combination_is_refused(self) -> None:
        assert (
            classify_derived_market(
                "Każda z drużyn powyżej 2.5 rz.rożnych; Obie drużyny strzelą gola",
                "tak",
                "2.5",
            )
            is None
        )

    def test_half_time_handicap_is_refused(self) -> None:
        """There is no half-time sample, so there must be no half-time row."""
        assert (
            classify_derived_market(
                "1. połowa - rzuty rożne - handicap", "Brentford (-0.5)", "-0.5"
            )
            is None
        )

    def test_handicap_line_comes_from_the_selection_not_the_market(self) -> None:
        """Both sides of a handicap share one specialBetValue.

        Reading the line from there gives the away side the home side's
        handicap and prices the wrong proposition.
        """
        home = classify_derived_market(
            "Rzuty rożne handicap", "Brentford (-1.5)", "-1.5"
        )
        away = classify_derived_market("Rzuty rożne handicap", "Chelsea (1.5)", "-1.5")
        assert home is not None and away is not None
        assert home[2] == -1.5
        assert away[2] == 1.5


class TestOfferParsing:
    def test_derived_rungs_reach_the_offer(self) -> None:
        items = [
            {
                "marketName": "Każda z drużyn powyżej X rzutów rożnych",
                "name": "Powyżej 3.5 - tak",
                "specialBetValue": "3.5",
                "price": 1.9,
            },
            {
                "marketName": "Obie drużyny strzelą",
                "name": "tak",
                "specialBetValue": None,
                "price": 1.45,
            },
            {
                "marketName": "Obie drużyny strzelą",
                "name": "nie",
                "specialBetValue": None,
                "price": 2.75,
            },
            {
                "marketName": "Najwięcej kartek",
                "name": "Brentford",
                "specialBetValue": None,
                "price": 2.72,
            },
        ]
        offers = OfferFetcher(DummyClient(items)).fetch_offers([make_fixture()])
        markets = {(r.market, r.line): r for r in offers[0].rungs}

        assert ("both_over_corners", 3.5) in markets
        assert markets[("both_over_goals", 0.5)].over_odds == 1.45
        assert markets[("both_over_goals", 0.5)].under_odds == 2.75
        assert ("most_cards_points", 0.0) in markets
        assert offers[0].unmapped_markets == []

    def test_a_market_with_no_line_still_reaches_the_offer(self) -> None:
        """"Obie drużyny strzelą" carries no specialBetValue at all.

        The old loop discarded any market without one before it could be
        classified, which is why the most heavily quoted both-teams market on
        the board was invisible.
        """
        items = [
            {
                "marketName": "Obie drużyny strzelą",
                "name": "tak",
                "specialBetValue": None,
                "price": 1.45,
            }
        ]
        offers = OfferFetcher(DummyClient(items)).fetch_offers([make_fixture()])
        assert [r.market for r in offers[0].rungs] == ["both_over_goals"]


class TestSubjectResolution:
    def test_numeric_selections_are_the_two_sides(self) -> None:
        fixture = make_fixture()
        assert resolve_subject("1", fixture) == "side_a"
        assert resolve_subject("2", fixture) == "side_b"

    def test_draw_is_its_own_outcome(self) -> None:
        assert resolve_subject("__draw__", make_fixture()) == "draw"

    def test_an_unrecognised_subject_is_refused_not_guessed(self) -> None:
        assert resolve_subject("Some Other Club", make_fixture()) is None


class TestHandicapDevig:
    def test_complement_is_the_other_side_at_the_negated_line(self) -> None:
        """Superbet quotes {A(-0.5), B(+0.5)} and {A(+0.5), B(-0.5)} both.

        Grouping on |line| pools four selections that do not sum to one, and
        the devig then produced nothing at all — every handicap row lost its
        market price and with it its only external check.
        """
        rungs = [
            PricedRung(
                market="handicap_corners",
                subject="brentford",
                line=-0.5,
                over_odds=1.97,
                under_odds=None,
                fetched_at_utc=now(),
            ),
            PricedRung(
                market="handicap_corners",
                subject="chelsea",
                line=0.5,
                over_odds=1.73,
                under_odds=None,
                fetched_at_utc=now(),
            ),
            PricedRung(
                market="handicap_corners",
                subject="brentford",
                line=0.5,
                over_odds=1.63,
                under_odds=None,
                fetched_at_utc=now(),
            ),
            PricedRung(
                market="handicap_corners",
                subject="chelsea",
                line=-0.5,
                over_odds=2.12,
                under_odds=None,
                fetched_at_utc=now(),
            ),
        ]
        probabilities = _market_probabilities(rungs)
        assert probabilities[("brentford", -0.5, "OVER")] + probabilities[
            ("chelsea", 0.5, "OVER")
        ] == pytest.approx(1.0)
        assert probabilities[("brentford", 0.5, "OVER")] + probabilities[
            ("chelsea", -0.5, "OVER")
        ] == pytest.approx(1.0)

    def test_three_way_comparative_devigs_across_all_outcomes(self) -> None:
        rungs = [
            PricedRung(
                market="most_corners",
                subject=subject,
                line=0.0,
                over_odds=price,
                under_odds=None,
                fetched_at_utc=now(),
            )
            for subject, price in (
                ("brentford", 1.97),
                ("__draw__", 6.6),
                ("chelsea", 2.12),
            )
        ]
        probabilities = _market_probabilities(rungs)
        assert sum(probabilities.values()) == pytest.approx(1.0)


class TestDerivedPricing:
    def _offer(self, rungs: list[PricedRung]) -> FixtureOffer:
        return FixtureOffer(
            sofascore_event_id=1, status="PRICED", rungs=rungs, unmapped_markets=[]
        )

    def _corner_ladder(self) -> list[PricedRung]:
        return [
            PricedRung(
                market="both_over_corners",
                subject="",
                line=line,
                over_odds=price,
                under_odds=None,
                fetched_at_utc=now(),
            )
            for line, price in (
                (2.5, 1.36),
                (3.5, 1.9),
                (4.5, 2.95),
                (5.5, 5.0),
                (6.5, 8.5),
            )
        ]

    def test_both_teams_rows_are_produced(self) -> None:
        samples = make_samples(
            "corners_for",
            [7, 6, 9, 6, 1, 3, 6, 9, 6, 8],
            [9, 10, 8, 3, 8, 9, 9, 8, 4, 6],
        )
        rows, _ = price_derived_rungs(
            fixture=make_fixture(),
            samples=samples,
            offer=self._offer(self._corner_ladder()),
            correlations={"corners": -0.1452},
            vetoes=[],
            min_sample=5,
            max_ladder_sigma=1.5,
            k_price=10.0,
            unfitted=[],
        )
        assert rows
        assert all(r.market == "both_over_corners" for r in rows)
        # p falls as the line rises, on the quoted side.
        overs = sorted(
            [r for r in rows if r.direction == "OVER"], key=lambda r: r.line
        )
        assert [r.p_central for r in overs] == sorted(
            [r.p_central for r in overs], reverse=True
        )

    def test_ladder_scale_is_the_minimum_not_the_sum(self) -> None:
        """Regression for the gate that passed a whole ladder at once.

        "Każda z drużyn powyżej n" is "min(A, B) > n". Scaling the
        disagreement by the spread of A + B halves every sigma, and on
        2026-09-18 that put all five rungs of one corners ladder through the
        VALUE gate together — which is the signature of a centre that
        disagrees with the market, not of five separate edges.
        """
        samples = make_samples(
            "corners_for",
            [7, 6, 9, 6, 1, 3, 6, 9, 6, 8],
            [9, 10, 8, 3, 8, 9, 9, 8, 4, 6],
        )
        rows, _ = price_derived_rungs(
            fixture=make_fixture(),
            samples=samples,
            offer=self._offer(self._corner_ladder()),
            correlations={"corners": -0.1452},
            vetoes=[],
            min_sample=5,
            max_ladder_sigma=1.5,
            k_price=10.0,
            unfitted=[],
        )
        sigmas = [r.ladder_sigma for r in rows if r.ladder_sigma is not None]
        assert sigmas, "a one-sided ladder must still produce a ladder check"
        sum_sd = (2.0 * 6.0) ** 0.5
        assert all(r.sample_sd < sum_sd for r in rows)

    def test_a_thin_sample_produces_no_row(self) -> None:
        samples = make_samples("corners_for", [5, 6], [7, 8])
        rows, skipped = price_derived_rungs(
            fixture=make_fixture(),
            samples=samples,
            offer=self._offer(self._corner_ladder()),
            correlations={"corners": -0.1452},
            vetoes=[],
            min_sample=5,
            max_ladder_sigma=1.5,
            k_price=10.0,
            unfitted=[],
        )
        assert rows == []
        assert skipped and all(s[1].value == "THIN_SAMPLE" for s in skipped)

    def test_an_unmeasured_correlation_says_so(self) -> None:
        samples = make_samples(
            "corners_for", [7, 6, 9, 6, 1, 3, 6, 9], [9, 10, 8, 3, 8, 9, 9, 8]
        )
        rows, _ = price_derived_rungs(
            fixture=make_fixture(),
            samples=samples,
            offer=self._offer(self._corner_ladder()),
            correlations={},
            vetoes=[],
            min_sample=5,
            max_ladder_sigma=1.5,
            k_price=10.0,
            unfitted=[],
        )
        assert rows
        assert any("UNMEASURED" in note for note in rows[0].notes)

    def test_comparative_and_handicap_agree_where_they_must(self) -> None:
        """P(A most) and P(A covers -0.5) are the same proposition.

        They are computed by different code paths, so agreement is a real
        check on both.
        """
        samples = make_samples(
            "corners_for",
            [7, 6, 9, 6, 1, 3, 6, 9, 6, 8],
            [9, 10, 8, 3, 8, 9, 9, 8, 4, 6],
        )
        rungs = [
            PricedRung(
                market="most_corners",
                subject="chelsea",
                line=0.0,
                over_odds=2.12,
                under_odds=None,
                fetched_at_utc=now(),
            ),
            PricedRung(
                market="handicap_corners",
                subject="chelsea",
                line=-0.5,
                over_odds=2.12,
                under_odds=None,
                fetched_at_utc=now(),
            ),
        ]
        rows, _ = price_derived_rungs(
            fixture=make_fixture(),
            samples=samples,
            offer=self._offer(rungs),
            correlations={"corners": -0.1452},
            vetoes=[],
            min_sample=5,
            max_ladder_sigma=1.5,
            k_price=10.0,
            unfitted=[],
        )
        by_market = {r.market: r for r in rows}
        assert by_market["most_corners"].p_central == pytest.approx(
            by_market["handicap_corners"].p_central, abs=1e-4
        )


class TestSamplesKnowsWhatDerivedMarketsNeed:
    def test_a_derived_market_asks_for_the_metric_not_its_own_name(self) -> None:
        """Regression for the gap that silenced the whole tennis family.

        SAMPLES decides which metrics to build from the names in the offer
        artifact. A derived market is named for the question it asks
        ("handicap_games"), not for the sample it needs ("games_won_for"), so
        passing the name straight through meant the metric was never built,
        SHEET reported STAT_KEY_ABSENT, and 863 priced tennis rungs looked
        like a provider gap. The failure is silent in both directions: the
        offer says the market is priced and the sample says the data is
        missing, and neither names the other.
        """
        from bet.sofa.samples import metrics_from_offer

        offer = FixtureOffer(
            sofascore_event_id=1,
            status="PRICED",
            rungs=[
                PricedRung(
                    market="handicap_games",
                    subject="adrian andreev",
                    line=8.5,
                    over_odds=1.9,
                    under_odds=None,
                    fetched_at_utc=now(),
                ),
                PricedRung(
                    market="both_over_corners",
                    subject="",
                    line=3.5,
                    over_odds=1.9,
                    under_odds=None,
                    fetched_at_utc=now(),
                ),
                PricedRung(
                    market="goals_total",
                    subject="",
                    line=2.5,
                    over_odds=1.9,
                    under_odds=1.9,
                    fetched_at_utc=now(),
                ),
            ],
            unmapped_markets=[],
        )
        assert metrics_from_offer(offer) == {
            "games_won_for",
            "corners_for",
            "goals_total",
        }
