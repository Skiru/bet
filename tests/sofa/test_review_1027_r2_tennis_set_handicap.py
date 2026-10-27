"""Review 2026-10-27 R2: the per-set games handicap
(handicap_games_won_set1 / _set2) is read from the rating neighbours' own set
margins under epochs.tennis_set_handicap_neighbours, never from an
independent (rho 0) joint of the two players' games in the set - a set is
never level, the joint put a quarter of its mass on a level margin."""

from datetime import timedelta

from bet.sofa.contracts import (
    Fixture,
    FixtureOffer,
    FixtureSamples,
    MetricSample,
    Observation,
    PricedRung,
)
from bet.sofa.derived import price_derived_rungs
from bet.sofa.tennis_rating import (
    SET_HANDICAP_MARKETS,
    SET_HANDICAP_NOTE,
    MatchForecast,
    Outcome,
)
from bet.sofa.timeutil import now
from scripts.sofa.run_sheet import _stats_only_rating_p


def _outcome(set1: tuple[int, int], set2: tuple[int, int]) -> Outcome:
    gf = set1[0] + set2[0]
    ga = set1[1] + set2[1]
    return Outcome(0.5, gf, ga, 2, 0, set1, set2)


# The home player's neighbours: set 1 margins +6, +4, -2, -1 (7-6 lost 6-7),
# set 2 margins +1 (7-6), -3, +2 (7-5), -6.
HOME = (
    _outcome((6, 0), (7, 6)),
    _outcome((6, 2), (3, 6)),
    _outcome((4, 6), (7, 5)),
    _outcome((6, 7), (0, 6)),
)
# The away player's: set 1 margins -4, +1, +3.
AWAY = (
    _outcome((2, 6), (6, 4)),
    _outcome((7, 6), (6, 3)),
    _outcome((6, 3), (6, 1)),
)


def _forecast(set_handicap: bool = True) -> MatchForecast:
    return MatchForecast(0.55, HOME, AWAY, 30, 30).with_set_handicap(
        set_handicap)


def test_a_set_is_never_level_and_the_handicap_reads_the_set_margin() -> None:
    f = _forecast()
    # Margins are never 0: the two sides of an integer 0 line sum to 1 ...
    p_home_0 = f.read_set_handicap("handicap_games_won_set1", "side_a", 0.0, "OVER")
    assert p_home_0 == 0.5  # margin > 0: +6, +4
    # ... and -0.5 / +0.5 give exactly the same answer as 0 (no mass at 0).
    assert f.read_set_handicap(
        "handicap_games_won_set1", "side_a", -0.5, "OVER") == p_home_0
    assert f.read_set_handicap(
        "handicap_games_won_set1", "side_a", 0.5, "OVER") == p_home_0
    # X (-3.5): margin > 3.5 -> +6, +4
    assert f.read_set_handicap(
        "handicap_games_won_set1", "side_a", -3.5, "OVER") == 0.5
    # X (+1.5): margin > -1.5 -> +6, +4, -1
    assert f.read_set_handicap(
        "handicap_games_won_set1", "side_a", 1.5, "OVER") == 0.75
    # X (+2.5): every neighbour
    assert f.read_set_handicap(
        "handicap_games_won_set1", "side_a", 2.5, "OVER") == 1.0
    # set 2 reads set 2: margins +1, -3, +2, -6; X (+2.5) -> +1, +2
    assert f.read_set_handicap(
        "handicap_games_won_set2", "side_a", 2.5, "OVER") == 0.5
    # an integer line landing exactly is a push, not a win: X (+3) set 2
    # wins on +1, +2 only (-3 lands)
    assert f.read_set_handicap(
        "handicap_games_won_set2", "side_a", 3.0, "OVER") == 0.5


def test_the_second_player_reads_his_own_neighbours() -> None:
    f = _forecast()
    # away set-1 margins -4, +1, +3
    assert f.read_set_handicap(
        "handicap_games_won_set1", "side_b", -1.5, "OVER") == 1 / 3
    assert f.read_set_handicap(
        "handicap_games_won_set1", "side_b", 0.0, "OVER") == 2 / 3
    assert f.read_set_handicap(
        "handicap_games_won_set1", "side_b", 4.5, "OVER") == 1.0
    # set 2 margins +2, +3, +5
    assert f.read_set_handicap(
        "handicap_games_won_set2", "side_b", -2.5, "OVER") == 2 / 3


def test_other_markets_sides_and_directions_are_not_read() -> None:
    f = _forecast()
    assert f.read_set_handicap("handicap_games", "side_a", 1.5, "OVER") is None
    assert f.read_set_handicap(
        "handicap_games_won_set1", "side_a", 1.5, "UNDER") is None
    assert f.read_set_handicap(
        "handicap_games_won_set1", None, 1.5, "OVER") is None
    assert MatchForecast(0.5, (), (), 0, 0).read_set_handicap(
        "handicap_games_won_set1", "side_a", 1.5, "OVER") is None


def test_the_stats_only_reader_prices_the_set_handicap_only_when_on() -> None:
    on = _stats_only_rating_p(_forecast(True))
    off = _stats_only_rating_p(_forecast(False))
    assert on("handicap_games_won_set1", "side_a", 1.5, "OVER") == 0.75
    assert off("handicap_games_won_set1", "side_a", 1.5, "OVER") is None
    assert off("handicap_games_won_set2", "side_b", 1.5, "OVER") is None
    # the match handicap is the same read either way
    assert on("handicap_games", "side_a", -1.5, "OVER") == off(
        "handicap_games", "side_a", -1.5, "OVER")
    assert set(SET_HANDICAP_MARKETS) == {
        "handicap_games_won_set1", "handicap_games_won_set2"}


def test_with_set_handicap_returns_itself_when_unchanged() -> None:
    f = _forecast(False)
    assert f.with_set_handicap(False) is f
    assert f.with_set_handicap(True).set_handicap is True


# --- the derived path end to end ------------------------------------------


def _fixture() -> Fixture:
    return Fixture(
        sofascore_event_id=1,
        superbet_event_ids=["101"],
        sport="tennis",
        kickoff_utc=now(),
        home_name="Lloyd Harris",
        away_name="Juncheng Shang",
        home_entity_id=1,
        away_entity_id=2,
        competition_name="Shanghai",
        competition_id=17,
        season_id=1,
        category_name="ATP",
        identity="CONFIRMED",
        round_number=None,
        round_name=None,
        cup_round_type=None,
        previous_leg_event_id=None,
        venue_name=None,
        referee=None,
        ground_type="Hardcourt outdoor",
        default_period_count=3,
    )


def _obs(values: list[float]) -> list[Observation]:
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


def _samples() -> FixtureSamples:
    return FixtureSamples(
        sofascore_event_id=1,
        readiness="READY",
        metrics={
            "games_won_set1_for": MetricSample(
                metric="games_won_set1_for",
                side_a=_obs([6, 6, 4, 6, 7, 3, 6, 6, 2, 6]),
                side_b=_obs([4, 3, 6, 2, 6, 6, 1, 4, 6, 3]),
                h2h=[],
            )
        },
        gaps=[],
    )


def _offer() -> FixtureOffer:
    rungs = [
        PricedRung(market="handicap_games_won_set1", subject=subject,
                   line=line, over_odds=odds, under_odds=None,
                   fetched_at_utc=now())
        for subject, line, odds in (("lloyd harris", 1.5, 1.4),
                                    ("juncheng shang", -1.5, 2.8))
    ]
    return FixtureOffer(sofascore_event_id=1, status="PRICED", rungs=rungs,
                        unmapped_markets=[])


def _price(set_handicap: bool) -> list[tuple[str, float, float, list[str]]]:
    rows, _ = price_derived_rungs(
        fixture=_fixture(),
        samples=_samples(),
        offer=_offer(),
        correlations={},
        vetoes=[],
        min_sample=5,
        max_ladder_sigma=1.5,
        k_price=10.0,
        unfitted=[],
        rating_p=_stats_only_rating_p(_forecast(set_handicap)),
        stats_only=True,
    )
    return sorted((r.subject, r.line, r.p_central, r.notes) for r in rows)


def test_on_the_rows_read_the_neighbours_and_say_so() -> None:
    rows = _price(True)
    by_subject = {s: (p, notes) for s, _, p, notes in rows}
    # home (+1.5): 0.75; away (-1.5): margin > 1.5 -> +3 only = 1/3
    assert by_subject["lloyd harris"][0] == 0.75
    assert by_subject["juncheng shang"][0] == round(1 / 3, 4)
    for _, notes in by_subject.values():
        assert any(n.startswith(SET_HANDICAP_NOTE + ":") for n in notes)


def test_off_the_rows_are_the_old_joint_without_the_marker() -> None:
    old, _ = price_derived_rungs(
        fixture=_fixture(), samples=_samples(), offer=_offer(),
        correlations={}, vetoes=[], min_sample=5, max_ladder_sigma=1.5,
        k_price=10.0, unfitted=[], rating_p=None, stats_only=True,
    )
    new, _ = price_derived_rungs(
        fixture=_fixture(), samples=_samples(), offer=_offer(),
        correlations={}, vetoes=[], min_sample=5, max_ladder_sigma=1.5,
        k_price=10.0, unfitted=[],
        rating_p=_stats_only_rating_p(_forecast(False)), stats_only=True,
    )
    assert [r.model_dump() for r in new] == [r.model_dump() for r in old]
    off = _price(False)
    for *_, notes in off:
        assert not any(SET_HANDICAP_NOTE in n for n in notes)
        assert notes[0].endswith("(UNMEASURED, independent)")
