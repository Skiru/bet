"""The score model's league rate restarts after an off-season
(epochs.LEAGUE_SEASON_RESTART_FROM_UTC, RatingBook.season_restart,
football_rating.SEASON_GAP_S / SEASON_PRIOR_MATCHES). Offline, fast.

The NBA rate (ALPHA_LEAGUE 0.02, ~ the last 50 games) carried the 2026
playoffs into October: 218.1 points against the 228.6 its first games
averaged (docs/sofa/history/NBA_SEZON_STAWKA_LIGI_2026-10-22.md)."""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa import football_rating as fr
from bet.sofa import score_model as sm
from bet.sofa.shadow import SPORTS

DAY = 86400
BB = SPORTS["basketball"]
COMP = 132


def _game(eid: int, ts: int, total_h: float, total_a: float,
          home: int = 1, away: int = 2) -> fr.FootballResult:
    q_h, q_a = total_h / 4, total_a / 4
    vals = {sm.period_metric(i + 1): (q_h, q_a) for i in range(4)}
    vals[sm.REG_METRIC["basketball"]] = (total_h, total_a)
    return fr.FootballResult(eid, ts, COMP, home, away, vals)


def _season(start_eid: int, start_ts: int, n: int, total_h: float,
            total_a: float) -> list[fr.FootballResult]:
    """n games, one a day, sides rotating among six teams."""
    return [_game(start_eid + i, start_ts + i * DAY, total_h, total_a,
                  home=1 + i % 6, away=7 + i % 6) for i in range(n)]


def _history() -> list[fr.FootballResult]:
    """A regular season at 115 / 112, a 'playoff' tail of 60 games at
    104 / 100, then 120 days of off-season and two games of a new season."""
    regular = _season(0, 0, 100, 115.0, 112.0)
    playoffs = _season(1000, 100 * DAY, 60, 104.0, 100.0)
    new = _season(2000, (160 + 120) * DAY, 2, 118.0, 114.0)
    return regular + playoffs + new


def _book(history: list[fr.FootballResult], restart: bool,
          until: int) -> fr.RatingBook:
    book = fr.RatingBook()
    book.season_restart = restart
    for r in history:
        if r.ts >= until:
            break
        book.update(r)
    return book


def test_off_the_rule_is_the_rule_as_it_was() -> None:
    history = _history()
    off = _book(history, False, 10**9)
    # the plain running mean, then ALPHA_LEAGUE: replayed by hand
    h = a = 0.0
    for i, r in enumerate(history):
        vh, va = r.values["bb_reg_for"]
        step = max(fr.ALPHA_LEAGUE, 1.0 / (i + 1))
        h += step * (vh - h)
        a += step * (va - a)
    league = off.leagues[(COMP, "bb_reg_for")]
    assert (league.home_mean, league.away_mean) == pytest.approx((h, a))
    assert league.n == len(history)
    assert league.weight is None and league.last_ts is None
    assert league.season_n == 0  # nothing kept off the rule


def test_the_first_game_after_an_off_season_reads_the_ended_season() -> None:
    history = _history()
    first_new = history[160].ts
    old = _book(history, False, first_new)
    new = _book(history, True, first_new)
    # the book's clock moves with any league; a game of another league the
    # day before the new season opens
    other = fr.FootballResult(9999, first_new - DAY, 77, 50, 51,
                              {"bb_reg_for": (80.0, 78.0)})
    old.update(other)
    new.update(other)
    stale = old.league_rates(COMP, "bb_reg_for")
    fresh = new.league_rates(COMP, "bb_reg_for")
    assert stale is not None and fresh is not None
    # the slow mean still remembers the playoff tail
    assert stale[0] < 108.0
    # the ended season's plain mean: (100 x 115 + 60 x 104) / 160
    assert fresh == pytest.approx(((100 * 115 + 60 * 104) / 160,
                                   (100 * 112 + 60 * 100) / 160))


def test_the_rate_restarts_from_the_ended_season_worth_k_matches() -> None:
    history = _history()
    new = _book(history, True, history[161].ts)  # the first new game learnt
    league = new.leagues[(COMP, "bb_reg_for")]
    ended_h = (100 * 115 + 60 * 104) / 160
    ended_a = (100 * 112 + 60 * 100) / 160
    k = fr.SEASON_PRIOR_MATCHES
    # the level at the fast step, the home share at the slow one
    total = ended_h + ended_a + (232.0 - ended_h - ended_a) / (k + 1)
    share0 = ended_h / (ended_h + ended_a)
    share = share0 + fr.ALPHA_LEAGUE * (118.0 / 232.0 - share0)
    assert league.home_mean == pytest.approx(total * share)
    assert league.away_mean == pytest.approx(total * (1 - share))
    assert league.weight == k + 1
    # the match count (the MIN_LEAGUE_MATCHES gate) is not reset
    assert league.n == 161
    assert league.season_n == 1


def test_a_short_break_is_not_an_off_season() -> None:
    history = _season(0, 0, 60, 110.0, 108.0) + _season(
        100, 59 * DAY + fr.SEASON_GAP_S - DAY, 1, 130.0, 120.0)
    on = _book(history, True, 10**9)
    off = _book(history, False, 10**9)
    assert (on.leagues[(COMP, "bb_reg_for")].home_mean
            == pytest.approx(off.leagues[(COMP, "bb_reg_for")].home_mean))


def test_a_thin_ended_season_keeps_the_running_mean() -> None:
    # 20 games (< MIN_LEAGUE_MATCHES) then 120 days off: no season mean to
    # restart from, the step restarts alone
    history = _season(0, 0, 20, 110.0, 108.0) + _season(
        100, 140 * DAY, 1, 130.0, 120.0)
    book = _book(history, True, history[-1].ts)
    league = book.leagues[(COMP, "bb_reg_for")]
    assert league.season_mean() is None
    assert book.league_rates(COMP, "bb_reg_for") is None  # 20 < 30, as before
    book.update(history[-1])
    total = 218.0 + (250.0 - 218.0) / (fr.SEASON_PRIOR_MATCHES + 1)
    share = 110.0 / 218.0 + fr.ALPHA_LEAGUE * (130.0 / 250.0 - 110.0 / 218.0)
    assert league.home_mean == pytest.approx(total * share)


def test_both_sides_at_the_fast_step_was_the_measured_alternative(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fr, "SEASON_RESTART_LEVEL_ONLY", False)
    history = _history()
    league = _book(history, True, history[161].ts).leagues[(COMP, "bb_reg_for")]
    ended = (100 * 115 + 60 * 104) / 160
    k = fr.SEASON_PRIOR_MATCHES
    assert league.home_mean == pytest.approx(ended + (118.0 - ended) / (k + 1))


def test_the_fast_level_ends_at_the_slow_step() -> None:
    # 60 games into the new season the step is ALPHA_LEAGUE again: the
    # per-side update, as before any restart
    history = _season(0, 0, 100, 115.0, 112.0) + _season(
        1000, 220 * DAY, 60, 120.0, 116.0)
    book = _book(history, True, 10**9)
    league = book.leagues[(COMP, "bb_reg_for")]
    assert league.weight == fr.SEASON_PRIOR_MATCHES + 60
    before = (league.home_mean, league.away_mean)
    book.update(_game(5000, 300 * DAY, 130.0, 100.0))
    assert league.home_mean == pytest.approx(
        before[0] + fr.ALPHA_LEAGUE * (130.0 - before[0]))
    assert league.away_mean == pytest.approx(
        before[1] + fr.ALPHA_LEAGUE * (100.0 - before[1]))


def test_build_model_sets_the_rule_on_its_book() -> None:
    history = _history()
    on = sm.build_model(history, BB, 10**9, season_restart=True)
    off = sm.build_model(history, BB, 10**9)
    assert on.book.season_restart and not off.book.season_restart
    # football's own replay never sets it
    assert not fr.replay(history, 10**9).season_restart


def test_the_switch_reads_the_day_the_clock_and_the_sport(
        monkeypatch: pytest.MonkeyPatch) -> None:
    on = datetime(2026, 10, 23, tzinfo=UTC)
    assert epochs.LEAGUE_SEASON_RESTART_FROM_UTC == on
    assert epochs.LEAGUE_SEASON_RESTART == "league_season_restart_v1"
    late = datetime(2026, 10, 23, 6, tzinfo=UTC)
    early = datetime(2026, 10, 22, 23, 59, tzinfo=UTC)
    assert epochs.league_season_restart("basketball", "2026-10-23", late)
    assert not epochs.league_season_restart("basketball", "2026-10-22", late)
    assert not epochs.league_season_restart("basketball", "2026-10-23", early)
    assert epochs.league_season_restart("basketball", None, late)
    # measured worse for hockey and volleyball: never on for them
    for sport in ("hockey", "volleyball", "cs2"):
        assert not epochs.league_season_restart(sport, "2026-10-23", late)
    assert not epochs.league_season_restart("football", "2026-10-23", late)
    monkeypatch.setattr(epochs, "LEAGUE_SEASON_RESTART_FROM_UTC", None)
    assert not epochs.league_season_restart("basketball", "2026-10-23", late)


def test_sport_confidence_builds_with_the_rule_of_its_day(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.sofa import run_sport_confidence as rsc

    seen: list[Any] = []

    def fake_build_model(history: Any, sport: Any, cut: Any, *_a: Any,
                         season_restart: bool = False, **_kw: Any) -> Any:
        seen.append(season_restart)
        return SimpleNamespace()

    monkeypatch.setattr(sm, "build_model", fake_build_model)
    monkeypatch.setattr(sm, "load_events", lambda db, sp: {})
    monkeypatch.setattr(rsc.scf.TeamGames, "build",
                        classmethod(lambda cls, events, sp: None))
    at = datetime(2026, 10, 23, 6, 0, tzinfo=UTC)
    rsc.DbForecaster("unused.db", at, "2026-10-23")._shadow_model("basketball")
    before = datetime(2026, 10, 22, 6, 0, tzinfo=UTC)
    rsc.DbForecaster("unused.db", before, "2026-10-22")._shadow_model("basketball")
    rsc.DbForecaster("unused.db", at, "2026-10-23")._shadow_model("hockey")
    assert seen == [True, False, False]


def test_the_history_replay_carries_the_rule() -> None:
    from bet.sofa import sport_confidence as scf

    history = [scf.HistoryGame(r, None, {}) for r in _history()]
    seen: list[bool] = []
    real = scf.build_model

    def spy(*a: Any, season_restart: bool = False, **kw: Any) -> Any:
        seen.append(season_restart)
        return real(*a, season_restart=season_restart, **kw)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(scf, "build_model", spy)
        scf.walk_forward_rows(history, BB, history[150].rating.ts, 10**9, 10,
                              None, "t", season_restart=True)
        scf.walk_forward_rows(history, BB, history[150].rating.ts, 10**9, 10,
                              None, "t")
    assert True in seen and False in seen
