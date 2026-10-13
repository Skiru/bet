"""Audit 2026-10-13 B7b: basketball's box-score pace scales only the level.

The total of the points rating's centre times (expected game possessions /
the competition's possession rate), the margin kept and the spread fitted
around the points centre - so winner and handicap stay as today up to
rounding; behind epochs.BB_PACE_LEVEL_FROM_UTC (None: byte-identical model).
Evidence: docs/sofa/evidence/basketball_pace_level_2026-10-13.md.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest

from bet.sofa import epochs
from bet.sofa import score_model as sm
from bet.sofa.shadow import SPORTS

BB = SPORTS["basketball"]
HOCKEY = SPORTS["hockey"]
DAY = 86400
CUT = 81 * DAY


def _history(n: int = 80, box: bool = True) -> list[sm.FootballResult]:
    """Four teams of one competition, a game every day; team 1 plays fast and
    scores more for it, team 2 is the stronger side on points."""
    teams = (1, 2, 3, 4)
    out: list[sm.FootballResult] = []
    for i in range(n):
        h, a = teams[i % 4], teams[(i + 1 + i // 4) % 4]
        if h == a:
            a = teams[(i + 2) % 4]
        poss = 80.0 if 1 in (h, a) else 66.0
        hp = poss * (1.15 if h == 2 else 1.05)
        ap = poss * (1.15 if a == 2 else 1.0)
        values = {f"p{k}_for": (hp / 4, ap / 4) for k in (1, 2, 3, 4)}
        values[sm.REG_METRIC["basketball"]] = (hp, ap)
        r = sm.FootballResult(1000 + i, (i + 1) * DAY, 5, h, a, values)
        if box:
            r = dataclasses.replace(r, values={
                **r.values, sm.PACE_POSS: (poss, poss),
                sm.PACE_PPP: (hp / poss, ap / poss)})
        out.append(r)
    return out


def _models() -> tuple[sm.ScoreModel, sm.ScoreModel]:
    """(today's model, the B7b model) on the same box-score history."""
    hist = _history()
    today = sm.build_model(hist, BB, CUT, shared_league_link=True)
    level = sm.build_model(hist, BB, CUT, shared_league_link=True,
                           pace_level=True)
    return today, level


def test_the_switch_is_off_and_asks_the_day_and_the_build_clock(monkeypatch) -> None:
    assert epochs.BB_PACE_LEVEL_FROM_UTC is None
    assert not epochs.bb_pace_level("2026-10-20", datetime(2026, 10, 20, tzinfo=UTC))
    at = datetime(2026, 10, 15, tzinfo=UTC)
    monkeypatch.setattr(epochs, "BB_PACE_LEVEL_FROM_UTC", at)
    assert epochs.bb_pace_level("2026-10-15", at)
    assert not epochs.bb_pace_level("2026-10-14", datetime(2026, 10, 16, tzinfo=UTC))
    assert not epochs.bb_pace_level("2026-10-15", datetime(2026, 10, 14, tzinfo=UTC))


def test_off_is_byte_identical_whatever_the_history_carries() -> None:
    plain = sm.build_model(_history(box=False), BB, CUT, shared_league_link=True)
    boxed = sm.build_model(_history(), BB, CUT, shared_league_link=True)
    assert not boxed.pace_level and boxed.box_last is None
    assert boxed.params == plain.params and boxed.period_sd == plain.period_sd
    for h, a in ((1, 2), (3, 4), (2, 1)):
        assert boxed.expected(5, h, a, CUT) == plain.expected(5, h, a, CUT)
        assert boxed.level_factor(5, h, a, CUT) is None


def test_on_the_total_scales_and_the_margin_stays() -> None:
    today, level = _models()
    f = level.level_factor(5, 1, 2, CUT)
    assert f is not None and f > 1.0  # the fast side's games: more possessions
    old, new = today.expected(5, 1, 2, CUT), level.expected(5, 1, 2, CUT)
    assert old is not None and new is not None
    assert sum(new[0]) + sum(new[1]) == pytest.approx(f * (sum(old[0]) + sum(old[1])))
    assert sum(new[0]) - sum(new[1]) == pytest.approx(sum(old[0]) - sum(old[1]))
    # by hand from the book: mean expected possessions over the league's rate
    book = level.book
    ph, pa = book.expected(5, 1, 2, sm.PACE_POSS, strict=True)  # type: ignore[misc]
    lh, la = book.league_rates(5, sm.PACE_POSS, strict=True)  # type: ignore[misc]
    assert f == pytest.approx(((ph + pa) / 2) / ((lh + la) / 2))
    slow = level.level_factor(5, 3, 4, CUT)
    assert slow is not None and slow < f


def test_the_spread_is_the_points_centres() -> None:
    today, level = _models()
    assert level.params == today.params
    assert level.period_sd == today.period_sd
    assert level.shares == today.shares


def test_winner_and_handicap_are_unchanged_up_to_rounding() -> None:
    """The simulated margin keeps its distribution (the RNG stream desyncs
    game by game - the tie pull and the overtime draw are conditional - so
    the check is on the distribution, not game by game), the total moves."""
    today, level = _models()
    old, new = today.expected(5, 1, 2, CUT), level.expected(5, 1, 2, CUT)
    assert old is not None and new is not None
    n = 4000
    so = today.simulate(old[0], old[1], seed=7, n=n)
    sn = level.simulate(new[0], new[1], seed=7, n=n)

    def margin(gs: list[sm.GameResult]) -> float:
        return sum(sum(g.t1_periods) - sum(g.t2_periods) for g in gs) / len(gs)

    def total(gs: list[sm.GameResult]) -> float:
        return sum(sum(g.t1_periods) + sum(g.t2_periods) for g in gs) / len(gs)

    f = level.level_factor(5, 1, 2, CUT)
    assert f is not None
    assert total(sn) - total(so) == pytest.approx(
        (f - 1) * (sum(old[0]) + sum(old[1])), abs=1.0)
    assert margin(sn) == pytest.approx(margin(so), abs=0.6)
    w_old = sum(g.winner == "T1" for g in so) / n
    w_new = sum(g.winner == "T1" for g in sn) / n
    assert abs(w_old - w_new) < 0.03


def test_a_stale_thin_or_foreign_pair_keeps_todays_total() -> None:
    today, level = _models()
    late = CUT + sm.PACE_FRESH_S + DAY
    assert level.level_factor(5, 1, 2, late) is None
    assert level.expected(5, 1, 2, late) == today.expected(5, 1, 2, late)
    assert level.level_factor(5, 1, 99, CUT) is None  # an unknown side
    assert level.level_factor(77, 1, 2, CUT) is None  # no possession rate
    hk = dataclasses.replace(level, sport=HOCKEY)
    assert hk.level_factor(5, 1, 2, CUT) is None


def test_a_history_without_box_scores_keeps_todays_model() -> None:
    plain = sm.build_model(_history(box=False), BB, CUT, shared_league_link=True)
    level = sm.build_model(_history(box=False), BB, CUT, shared_league_link=True,
                           pace_level=True)
    assert level.level_factor(5, 1, 2, CUT) is None
    assert level.expected(5, 1, 2, CUT) == plain.expected(5, 1, 2, CUT)


def test_the_b7_centre_wins_when_both_are_on() -> None:
    hist = _history()
    both = sm.build_model(hist, BB, CUT, shared_league_link=True, pace=True,
                          pace_level=True)
    paced = both.pace_expected(5, 1, 2, CUT)
    exp = both.expected(5, 1, 2, CUT)
    assert paced is not None and exp is not None
    assert sum(exp[0]) == pytest.approx(paced[0])
