"""Coverage audit 2026-10-23 P7 (B8): a CS2 pair whose team ids are not both
MIN_MAPS_RATED gets the lineup gap's number under
epochs.CS2_LINEUP_ELO_UNRATED_FROM_UTC (10-21 Envy, 9 maps as a team id, its
players 1,078 maps - FaZe); off, no number, as before."""

from __future__ import annotations

import random
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from bet.sofa import cs2_engine as eng
from bet.sofa import epochs

STARS, OTHERS = (1, 2, 3, 4, 5), (6, 7, 8, 9, 10)


def _pmap(eid: int, ts: int, home: int, away: int, home_won: bool,
          hp: tuple[int, ...], ap: tuple[int, ...]) -> eng.MapRow:
    players = tuple((home, pid, f"p{pid}", ()) for pid in hp) + tuple(
        (away, pid, f"p{pid}", ()) for pid in ap)
    return eng.MapRow(eid, ts, 1, home, away, 13 if home_won else 5,
                      5 if home_won else 13, home_won, players)


def _history(new_teams: int = 80) -> list[eng.MapRow]:
    """Team 1 (STARS) beats team 2 (OTHERS) 75% for 400 maps; then the STARS
    play four maps each under `new_teams` fresh team ids (the unrated pairs'
    calibration points), and three maps as team id 3 - rated as players, not
    as a team."""
    rng = random.Random(3)
    hist = []
    for i in range(400):
        home, away = (1, 2) if i % 2 else (2, 1)
        lineup = {1: STARS, 2: OTHERS}
        won = rng.random() < (0.75 if home == 1 else 0.25)
        hist.append(_pmap(i, i, home, away, won, lineup[home], lineup[away]))
    eid = 400
    for k in range(new_teams):
        for _ in range(4):
            hist.append(_pmap(eid, eid, 1000 + k, 2, rng.random() < 0.8,
                              STARS, OTHERS))
            eid += 1
    for _ in range(3):
        hist.append(_pmap(eid, eid, 3, 2, True, STARS, OTHERS))
        eid += 1
    return hist


def test_an_unrated_team_id_gets_the_lineup_number_only_under_the_switch() -> None:
    hist = _history()
    old = eng.build_ratings(hist)
    new = eng.build_ratings(hist, (), True)
    assert not old.book.rated(3, 2) and old.p_fit >= eng.MIN_FIT
    assert old.p_map(3, 2, True) is None and old.u_fit == 0
    p = new.p_map(3, 2, True)
    assert p is not None and p > 0.6
    # its own calibration: the rated lineup intercept, its own slope
    gap = new.players.gap(3, 2) if new.players else None
    assert gap is not None and new.u_fit >= eng.MIN_FIT and new.ua == new.pa
    assert p == pytest.approx(eng._sigmoid(new.ua + new.ub * gap))
    # the map-number terms read the same base
    assert new.p_map_nr(3, 2, True, 3, 1) == pytest.approx(p)


def test_a_rated_pair_is_unchanged_by_the_switch() -> None:
    hist = _history()
    old, new = eng.build_ratings(hist), eng.build_ratings(hist, (), True)
    assert old.p_map(1, 2, True) == new.p_map(1, 2, True) is not None
    assert (old.a, old.b, old.pa, old.pb) == (new.a, new.b, new.pa, new.pb)


def test_no_lineup_or_no_fitted_player_model_stays_without_a_number() -> None:
    hist = _history()
    new = eng.build_ratings(hist, (), True)
    assert new.p_map(3, 77, True) is None  # team 77 has no lineup
    short = eng.build_ratings(hist[:150] + hist[400:], (), True)
    assert short.p_fit < eng.MIN_FIT and short.p_map(3, 2, True) is None
    # under MIN_FIT unrated points: no calibration, no number
    few = eng.build_ratings(_history(new_teams=10), (), True)
    assert few.p_fit >= eng.MIN_FIT and few.u_fit == 0
    assert few.p_map(3, 2, True) is None


def test_model_probability_prices_the_unrated_series_only_under_the_switch() -> None:
    hist = _history()
    line = eng.Cs2Line("e", "match_winner", 0, "", None, "T1", 1.8)
    old = eng.model_probability(line, 3, 2, "a", "b", 3, hist,
                                eng.build_ratings(hist), True)
    new = eng.model_probability(line, 3, 2, "a", "b", 3, hist,
                                eng.build_ratings(hist, (), True), True)
    assert old is None and new is not None and new.p > 0.6 and new.n == 3


def test_the_switch_is_read_by_the_offered_day(monkeypatch: pytest.MonkeyPatch
                                               ) -> None:
    from contextlib import nullcontext

    from scripts.sofa import settle_cs2 as sc

    seen: list[bool] = []
    monkeypatch.setattr(epochs, "CS2_LINEUP_ELO_UNRATED_FROM_UTC",
                        datetime(2026, 10, 24, tzinfo=UTC))
    monkeypatch.setattr(sc, "get_connection", lambda db: nullcontext(None))
    monkeypatch.setattr(sc, "load_history", lambda conn, before, eid: [])
    monkeypatch.setattr(sc, "build_ratings",
                        lambda history, terms=(), unrated=False:
                        seen.append(unrated) or {})
    monkeypatch.setattr(sc, "model_probability", lambda *a, **k: None)
    fields = {k: None for k in sc.Cs2Line.__dataclass_fields__}
    for kick in (datetime(2026, 10, 23, 23, tzinfo=UTC),
                 datetime(2026, 10, 24, 1, tzinfo=UTC)):
        sc.attach_model([dict(fields)], SimpleNamespace(team1="a", team2="b"),
                        {"id": 1, "bestOf": 3}, {}, True, kick, "x.db")
    assert seen == [False, True]
    assert not epochs.cs2_lineup_elo_unrated("2026-10-23",
                                             datetime(2026, 10, 23, tzinfo=UTC))
