"""scripts/sofa/measure_cross_league_cups.py - the cross-league cup
measurement's pure pieces on synthetic data (offline, fast)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from bet.sofa import football_rating as fr
from scripts.sofa import measure_cross_league_cups as m


def test_cup_elo_reads_nothing_until_both_leagues_have_enough_matches() -> None:
    elo = m.CupLeagueElo(eta=0.1)
    for _ in range(3):
        elo.update(1, 2, 2.0)
    assert elo.gap(1, 2, min_n=4) is None
    elo.update(1, 2, 2.0)
    gap = elo.gap(1, 2, min_n=4)
    assert gap is not None and gap > 0
    # zero-sum and symmetric
    assert elo.s[1] == pytest.approx(-elo.s[2])
    assert elo.gap(2, 1, min_n=4) == pytest.approx(-gap)
    # the home advantage is the running mean home GD
    assert elo.hfa == pytest.approx(2.0)


def test_cup_elo_ignores_a_same_league_match() -> None:
    elo = m.CupLeagueElo()
    elo.update(5, 5, 3.0)
    assert elo.n.get(5, 0) == 0 and elo.hfa_n == 0


def test_centres_reproduce_the_rating_book() -> None:
    book = fr.RatingBook(shared_league_link=True)
    for _ in range(40):
        book.leagues[(9, "goals_for")].update(1.6, 1.1)
    th, ta = book.teams[(1, "goals_for")], book.teams[(2, "goals_for")]
    th.attack, th.defence, ta.attack, ta.defence = 1.4, 0.8, 0.9, 1.2
    exp = book.expected(9, 1, 2, "goals_for", 0.15, cross=True)
    assert exp is not None
    rates = book.league_rates(9, "goals_for")
    assert rates is not None
    got = m.centres(rates[0], rates[1], 1.4, 0.8, 0.9, 1.2, 0.15, fr.CROSS_RATIO_POWER)
    assert got == pytest.approx(exp)
    a = {k: np.array([v]) for k, v in (
        ("rate_h", rates[0]), ("rate_a", rates[1]), ("att_h", 1.4), ("def_h", 0.8),
        ("att_a", 0.9), ("def_a", 1.2))}
    lh, la = m.variant_centres(a, np.array([0.15]))
    assert (lh[0], la[0]) == pytest.approx(exp)


def test_bins_and_outcomes() -> None:
    edges = (0.0, 0.2, 0.5, math.inf)
    assert m.bin_of(-0.1, edges) == 0
    assert m.bin_of(0.3, edges) == 1
    assert m.bin_of(-7.0, edges) == 2
    assert m.bin_label(edges, 2) == ">=0.5"
    assert m.bin_label(edges, 0) == "0-0.2"
    assert [m.outcome_index(*s) for s in ((2, 1), (1, 1), (0, 3))] == [0, 1, 2]


def test_oriented_puts_the_favoured_side_first() -> None:
    a = {
        "lh": np.array([1.0, 1.0]), "la": np.array([2.0, 2.0]),
        "x": np.array([3.0, 3.0]), "y": np.array([0.0, 0.0]),
        "outcome": np.array([0.0, 0.0]), "lf": np.array([0.1, 0.1]),
        "proxy": np.array([0.5, 0.5]),
    }
    o = m.oriented(a, np.array([1.0, -1.0]), 7.586)
    # row 0: S = home; row 1: S = away
    assert o["pred_gd"].tolist() == [-1.0, 1.0]
    assert o["real_gd"].tolist() == [3.0, -3.0]
    assert o["real_s_win"].tolist() == [1.0, 0.0]
    p = m.probs_1x2(a["lh"], a["la"], 7.586)
    assert o["p_s_win"][0] == pytest.approx(p[0, 0])
    assert o["p_s_win"][1] == pytest.approx(p[1, 2])


def _row(ts: float, ch: float, ca: float, x: float, y: float) -> dict[str, float]:
    return {"ts": ts, "ch": ch, "ca": ca, "x": x, "y": y, "ok": 1.0,
            "status": float(m.STATUSES.index(fr.LINKED_BY_STRENGTH)), "lf": 0.0,
            "rate_h": 1.5, "rate_a": 1.2, "att_h": 1.0, "def_h": 1.0,
            "att_a": 1.0, "def_a": 1.0}


def test_walk_cups_reads_only_earlier_time_groups() -> None:
    rows = [_row(1.0, 10, 20, 3, 0) for _ in range(12)]
    rows += [_row(2.0, 10, 20, 0, 0), _row(2.0, 20, 10, 0, 0)]
    elo, delta = m.walk_cups(rows, (0.0, 0.1))
    # the whole first group is priced before any of it is learnt
    assert all(r["d_0.1"] == 0.0 for r in rows[:12])
    assert all(math.isnan(r["proxy"]) for r in rows[:12])
    # the second group reads the first, and both of its rows read the same state
    assert rows[12]["d_0.1"] > 0
    assert rows[13]["d_0.1"] == pytest.approx(-rows[12]["d_0.1"])
    assert rows[12]["proxy"] == pytest.approx(-rows[13]["proxy"])
    assert all(r["d_0.0"] == 0.0 for r in rows)
    assert elo.n[10] == 14 and delta[0.1][10] > 0
