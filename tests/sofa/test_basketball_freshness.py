"""Basketball noise by freshness (epochs.BB_FRESHNESS_FROM_UTC, 2026-10-07).

Ratings carried over a season break are stale: walk-forward on 35,534 games
the margin spread of a game whose thinner side played <= 2 games in the last
120 days is 1.085x that of an established one (3..9 games: 1.026x).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from bet.sofa import epochs
from bet.sofa import score_model as sm
from bet.sofa.shadow import SPORTS

BASKETBALL = SPORTS["basketball"]
HOCKEY = SPORTS["hockey"]
DAY = 86400
AT = 200 * DAY


def _model(recent: dict[int, list[int]] | None, sport=BASKETBALL) -> sm.ScoreModel:
    return sm.ScoreModel(sport, sm.RatingBook(), 6.0, ((0.25,) * 4, (0.25,) * 4),
                         sm.SimParams(), recent=recent)


def _games(n: int, last: int = AT - DAY) -> list[int]:
    return [last - i * 3 * DAY for i in range(n)]


def test_the_class_is_the_thinner_sides_games_in_the_window() -> None:
    model = _model({1: _games(12), 2: _games(1), 3: _games(5), 4: _games(30)})
    le2, le9 = model.params.bb_fresh_mult
    assert model.noise_mult(1, 2, AT) == le2          # 1 game: <= 2
    assert model.noise_mult(1, 3, AT) == le9          # 5 games: 3..9
    assert model.noise_mult(1, 4, AT) == 1.0          # both >= 10
    assert model.noise_mult(1, 99, AT) == le2         # no games at all
    # games older than the 120-day window do not count
    old = _model({1: _games(20, last=AT - 130 * DAY), 2: _games(20)})
    assert old.noise_mult(1, 2, AT) == le2


def test_nothing_changes_outside_basketball_or_without_a_clock() -> None:
    assert _model({1: [], 2: []}, HOCKEY).noise_mult(1, 2, AT) == 1.0
    assert _model(None).noise_mult(1, 2, AT) == 1.0
    assert _model({1: [], 2: []}).noise_mult(1, 2, None) == 1.0


def test_the_switch_asks_the_day_and_the_build_clock() -> None:
    at = epochs.BB_FRESHNESS_FROM_UTC
    assert at is not None
    day = epochs.BB_FRESHNESS_DATE
    assert epochs.bb_freshness_enabled(day, at)
    assert not epochs.bb_freshness_enabled(day, at.replace(minute=at.minute - 1))
    assert not epochs.bb_freshness_enabled(
        "2026-10-06", datetime(2026, 10, 9, tzinfo=UTC))


def test_a_stale_game_is_simulated_wider_and_the_default_is_unchanged() -> None:
    model = _model({})

    def margin_sd(mult: float) -> float:
        games = model.simulate([20.0] * 4, [20.0] * 4, seed=3, n=3000,
                               noise_mult=mult)
        d = [g.t1_full - g.t2_full for g in games]
        m = sum(d) / len(d)
        return (sum((x - m) ** 2 for x in d) / len(d)) ** 0.5

    base = margin_sd(1.0)
    assert margin_sd(1.085) == pytest.approx(1.085 * base, rel=0.06)
    default = model.simulate([20.0] * 4, [20.0] * 4, seed=3, n=50)
    explicit = model.simulate([20.0] * 4, [20.0] * 4, seed=3, n=50, noise_mult=1.0)
    assert [g.t1_full for g in default] == [g.t1_full for g in explicit]


def test_build_model_records_the_recent_games_of_basketball_only() -> None:
    rows = [sm.FootballResult(i, i, 5, 100 + i % 2, 200 + i % 2,
                              {f"p{k}_for": (20.0, 19.0) for k in (1, 2, 3, 4)}
                              | {sm.REG_METRIC["basketball"]: (80.0, 76.0)})
            for i in range(1, 60)]
    cut = 100 * DAY
    for r in rows:
        object.__setattr__(r, "ts", 95 * DAY + r.event_id * 3600)
    model = sm.build_model(rows, BASKETBALL, cut)
    assert model.recent is not None and set(model.recent) == {100, 101, 200, 201}
    assert all(t >= cut - sm.FRESH_WINDOW_S for ts in model.recent.values()
               for t in ts)
