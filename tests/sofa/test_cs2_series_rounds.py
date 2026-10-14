"""CS2 series rounds (epochs.CS2_SERIES_ROUNDS_FROM_UTC): the series-rounds
distribution, its switch in the engine / SPORT_CONFIDENCE's allowed families,
the history replay's rows and the fit script's Superbet-line orientation."""

from datetime import UTC, datetime

import pytest

from bet.sofa import cs2_engine as eng
from bet.sofa import epochs
from bet.sofa import sport_confidence as scf
from bet.sofa.cs2 import Cs2Line, actual_value
from scripts.sofa import fit_cs2_series_rounds as fit


@pytest.mark.parametrize("best_of", [1, 2, 3, 5])
@pytest.mark.parametrize("p", [0.2, 0.5, 0.8])
def test_the_distribution_is_a_distribution(best_of: int, p: float) -> None:
    d = eng.series_rounds_distribution(p, best_of)
    assert sum(d.values()) == pytest.approx(1.0, abs=1e-6)
    maps_min = {1: 1, 2: 2, 3: 2, 5: 3}[best_of]
    # every played map has a winner with at least 13 rounds
    assert min(a + b for a, b in d) >= 13 * maps_min


def test_best_of_one_is_the_maps_round_race() -> None:
    race = dict(eng._race_dist(0.65))
    one = eng.series_rounds_distribution(0.65, 1)
    for k in set(race) | set(one):
        assert one.get(k, 0.0) == pytest.approx(race.get(k, 0.0), abs=2e-3)


def test_more_maps_more_rounds_and_sides_add_up() -> None:
    even = eng.series_rounds_distribution(0.5, 3)
    lopsided = eng.series_rounds_distribution(0.9, 3)

    def mean(d: dict[tuple[int, int], float]) -> float:
        return sum((a + b) * q for (a, b), q in d.items())

    # a lopsided series ends 2-0 more often: fewer rounds
    assert mean(lopsided) < mean(even)
    for fam, line, sides, idx in (("rounds_total", 48.5, ("OVER", "UNDER"), None),
                                  ("team_rounds", 26.5, ("OVER", "UNDER"), 0),
                                  ("rounds_handicap", -3.5, ("T1", "T2"), None)):
        a, b = (eng.series_rounds_side_p(0.7, 3, fam, line, s, idx) for s in sides)
        assert a is not None and b is not None
        assert a + b == pytest.approx(1.0)
    # an even series: team1 -0.5 rounds is a coin
    p = eng.series_rounds_side_p(0.5, 3, "rounds_handicap", -0.5, "T1", None)
    assert p == pytest.approx(0.5, abs=0.02)
    # a stronger team1 covers a handicap more often
    strong = eng.series_rounds_side_p(0.8, 3, "rounds_handicap", -5.5, "T1", None)
    weak = eng.series_rounds_side_p(0.4, 3, "rounds_handicap", -5.5, "T1", None)
    assert strong is not None and weak is not None and strong > weak
    assert eng.series_rounds_side_p(0.5, 3, "team_rounds", 26.5, "OVER", None) is None
    assert eng.series_rounds_side_p(0.5, 3, "maps_total", 2.5, "OVER", None) is None


def _ratings() -> eng.RatingModel:
    book = eng.EloBook(ratings={1: 1600.0, 2: 1500.0})
    book.played[1] = book.played[2] = eng.MIN_MAPS_RATED
    return eng.RatingModel(book, a=0.1, b=0.6)


def test_the_engine_prices_them_only_behind_the_switch() -> None:
    ratings = _ratings()
    line = Cs2Line("9", "team_rounds", 0, "B", 24.5, "OVER", 1.85)

    def mp(on: bool) -> eng.ModelP | None:
        return eng.model_probability(line, 1, 2, "A", "B", 3, [], ratings,
                                     False, series_rounds=on)

    assert mp(False) is None  # off: byte-identical (no number, as before)
    got = mp(True)
    assert got is not None and got.model == "series_round_race"
    p1 = ratings.p_map(1, 2, False)
    assert p1 is not None
    want = eng.series_rounds_side_p(p1, 3, "team_rounds", 24.5, "OVER", 1)
    assert want is not None and got.p == pytest.approx(eng.clamp(want))


def test_family_allowed_only_with_the_switch() -> None:
    assert scf.family_of("cs2", None, "rounds_total", True) is None
    assert scf.family_of("cs2", None, "rounds_total", False,
                         series_rounds=True) is None
    assert scf.family_of("cs2", None, "rounds_total", True,
                         series_rounds=True) == "rounds_total"
    assert scf.family_of("cs2", None, "map_rounds_odd_even", True,
                         series_rounds=True) is None


def test_switch_is_day_and_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "CS2_SERIES_ROUNDS_FROM_UTC",
                        datetime(2026, 10, 15, tzinfo=UTC))
    assert not epochs.cs2_series_rounds("2026-10-14",
                                        datetime(2026, 10, 15, 1, tzinfo=UTC))
    assert not epochs.cs2_series_rounds("2026-10-15",
                                        datetime(2026, 10, 14, 23, tzinfo=UTC))
    assert epochs.cs2_series_rounds("2026-10-15", datetime(2026, 10, 15, tzinfo=UTC))
    monkeypatch.setattr(epochs, "CS2_SERIES_ROUNDS_FROM_UTC", None)
    assert not epochs.cs2_series_rounds("2026-10-20",
                                        datetime(2026, 10, 20, tzinfo=UTC))


def _map(order: int, hr: int | None, ar: int | None, home_won: bool) -> eng.MapRow:
    return eng.MapRow(7, 1000, order, 1, 2, hr, ar, home_won, (), None, 3)


def test_history_rows_grade_the_whole_series_and_refuse_a_partial_one() -> None:
    srow = scf.SeriesRow(7, 1000, 1, 2, 2, 1, 3)
    smaps = [_map(1, 13, 9, True), _map(2, 10, 13, False), _map(3, 16, 14, True)]
    rows = scf.cs2_series_rounds_rows(
        7, smaps, srow, 0.6, "history",
        [("rounds_handicap", -3.5, "T1", ""), ("team_rounds", 38.5, "UNDER", "T2")])
    by = {(r["family"], r["line"], r["side"], r["subject"], r["source"]): r["y"]
          for r in rows}
    # 39 - 36 rounds, 75 in all
    assert by[("rounds_total", 55.5, "OVER", "", "history")] == 1
    assert by[("rounds_handicap", -2.5, "T1", "", "history")] == 1
    assert by[("rounds_handicap", -3.5, "T1", "", "history_superbet")] == 0
    assert by[("team_rounds", 28.5, "OVER", "T2", "history")] == 1
    assert by[("team_rounds", 38.5, "UNDER", "T2", "history_superbet")] == 1
    assert all(r["key"] in ("rounds_total|OVER", "rounds_total|UNDER",
                            "rounds_handicap|TEAM", "team_rounds|OVER",
                            "team_rounds|UNDER") for r in rows)
    # a map without its round score, or maps missing from the series: nothing
    assert scf.cs2_series_rounds_rows(
        7, [_map(1, 13, 9, True), _map(2, None, None, False), _map(3, 16, 14, True)],
        srow, 0.6, "history") == []
    assert scf.cs2_series_rounds_rows(7, smaps[:2], srow, 0.6, "history") == []


def test_superbet_lines_are_turned_to_the_home_side() -> None:
    assert fit.home_oriented("rounds_total", 48.5, "OVER", None, False) == (
        "rounds_total", 48.5, "OVER", "")
    # team1 away with +6.5: home's handicap is -6.5 on the other side
    assert fit.home_oriented("rounds_handicap", 6.5, "T1", None, False) == (
        "rounds_handicap", -6.5, "T2", "")
    assert fit.home_oriented("rounds_handicap", 6.5, "T1", None, True) == (
        "rounds_handicap", 6.5, "T1", "")
    assert fit.home_oriented("team_rounds", 24.5, "UNDER", "T1", False) == (
        "team_rounds", 24.5, "UNDER", "T2")
    assert fit.home_oriented("team_rounds", 24.5, "UNDER", None, True) is None


def test_the_grader_counts_only_played_maps() -> None:
    from bet.sofa.cs2 import MapResult

    maps = [MapResult(13, 5, {}), MapResult(13, 11, {})]  # a 2-0: no map 3
    line = Cs2Line("1", "rounds_total", 0, "", 41.5, "UNDER", 1.8)
    assert actual_value(line, maps, "A", "B") == 42.0
    hcp = Cs2Line("1", "rounds_handicap", 0, "", -9.5, "T1", 1.8)
    assert actual_value(hcp, maps, "A", "B") == 10.0
