"""bet.sofa.season_table and the score model's season-table arm (item 5 of
the refit 2026-11-05, frozen rule in docs/sofa/evidence/
refit_replay_2026-11-05.md section 6): the table counts only games noted
before the forecast, reads the competition's newest season, is 0 below
MIN_GAMES and shrunk by n / (n + 5); off (no weight) the model is exactly
the old one. Offline."""

from __future__ import annotations

import random
from typing import Any

import pytest

from bet.sofa import score_model as sm
from bet.sofa import season_table as st
from bet.sofa.shadow import SPORTS

BASKETBALL = SPORTS["basketball"]
ONE = st.TableScales(ppg=1.0, position=1.0, diff=1.0)


def _table(games: list[tuple[int, int, float, float]], season: int = 7,
           comp: int = 5) -> st.SeasonTable:
    t = st.SeasonTable(win_points=1.0, draw_points=0.5)
    for i, (h, a, hs, as_) in enumerate(games):
        t.note(comp, season, h, a, hs, as_, ts=1000 + i)
    return t


def test_the_table_reads_points_position_and_difference_per_game() -> None:
    # 1 beats 2 three times by 10, 3 beats 2 once by 2
    t = _table([(1, 2, 90, 80)] * 3 + [(3, 2, 80, 78)])
    ppg, pos, diff, n = t.raw(5, 1, 2) or (0, 0, 0, 0)
    assert ppg == pytest.approx(1.0)
    assert pos == pytest.approx(1.0)          # first (1.0) vs last (0.0)
    assert diff == pytest.approx(10 - (-32 / 4))
    assert n == 3
    # d: mean of the three, shrunk by 3 / (3 + 5)
    assert t.d(5, 1, 2, ONE) == pytest.approx((1.0 + 1.0 + 18.0) / 3 * 3 / 8)


def test_below_min_games_or_without_a_row_d_is_zero() -> None:
    t = _table([(1, 2, 90, 80)] * 2)
    assert t.d(5, 1, 2, ONE) == 0.0
    assert t.d(5, 1, 99, ONE) == 0.0
    assert t.d(6, 1, 2, ONE) == 0.0
    # a game with no season id is not counted
    t.note(5, None, 1, 2, 90, 80, ts=5000)
    assert t.raw(5, 1, 2) is not None and t.raw(5, 1, 2)[3] == 2  # type: ignore[index]


def test_a_new_season_restarts_the_table() -> None:
    t = _table([(1, 2, 90, 80)] * 5, season=7)
    assert t.d(5, 1, 2, ONE) > 0
    t.note(5, 8, 3, 4, 70, 60, ts=10_000)   # the competition's next season
    assert t.d(5, 1, 2, ONE) == 0.0


def test_adjust_moves_the_margin_not_the_level_first_order() -> None:
    h, a = st.adjust(100.0, 100.0, 1.0, 0.04)
    assert h > 100 > a
    assert h * a == pytest.approx(100.0 * 100.0)
    assert st.adjust(100.0, 90.0, 0.0, 0.04) == (100.0, 90.0)


def _event(eid: int, ts: int, home: int, away: int, hq: list[int],
           aq: list[int], season: int | None = 7) -> dict[str, Any]:
    e: dict[str, Any] = {
        "id": eid, "startTimestamp": ts,
        "tournament": {"id": 9, "uniqueTournament": {"id": 5, "name": "League"},
                       "category": {"sport": {"slug": "basketball"}}},
        "status": {"type": "finished", "description": "Ended"},
        "homeTeam": {"id": home, "gender": "M"},
        "awayTeam": {"id": away, "gender": "M"},
        "homeScore": {"current": sum(hq),
                      **{f"period{i + 1}": v for i, v in enumerate(hq)}},
        "awayScore": {"current": sum(aq),
                      **{f"period{i + 1}": v for i, v in enumerate(aq)}},
    }
    if season is not None:
        e["season"] = {"id": season}
    return e


def test_parse_event_carries_the_season_and_the_final_score() -> None:
    r = sm.parse_event(_event(1, 1000, 10, 20, [20, 20, 20, 25], [19, 21, 20, 20]),
                       BASKETBALL)
    assert r is not None and r.season_id == 7 and r.final == (85.0, 80.0)
    r2 = sm.parse_event(_event(2, 1000, 10, 20, [20, 20, 20, 25], [19, 21, 20, 20],
                               season=None), BASKETBALL)
    assert r2 is not None and r2.season_id is None


def _history() -> list[sm.FootballResult]:
    rng = random.Random(4)
    out = []
    for i in range(240):
        home, away = 100 + i % 6, 100 + (i + 1 + i // 6) % 6
        if home == away:
            continue
        strong = 3 if home == 100 else (-3 if away == 100 else 0)
        hq = [20 + strong + rng.randint(-4, 4) for _ in range(4)]
        aq = [20 + rng.randint(-4, 4) for _ in range(4)]
        r = sm.parse_event(_event(i, 10_000 + i * 3600, home, away, hq, aq),
                           BASKETBALL)
        assert r is not None
        out.append(r)
    return out


def test_off_the_model_is_the_old_one_and_on_the_leader_moves_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hist = _history()
    cut = 10**9
    old = sm.build_model(hist, BASKETBALL, cut)
    # no weight set: season_table=True changes nothing
    same = sm.build_model(hist, BASKETBALL, cut, season_table=True)
    assert same.table is None
    assert same.expected(5, 100, 101) == old.expected(5, 100, 101)
    monkeypatch.setitem(sm.SEASON_TABLE_W, "basketball", 0.05)
    monkeypatch.setitem(sm.SEASON_TABLE_SCALES, "basketball", ONE)
    on = sm.build_model(hist, BASKETBALL, cut, season_table=True)
    assert on.table is not None
    e_old, e_on = old.expected(5, 100, 101), on.expected(5, 100, 101)
    assert e_old is not None and e_on is not None
    # team 100 leads the table: its centre goes up, its opponent's down
    assert sum(e_on[0]) > sum(e_old[0]) and sum(e_on[1]) < sum(e_old[1])
    # not asked for (season_table False): untouched even with a weight set
    assert sm.build_model(hist, BASKETBALL, cut).table is None


def test_the_table_is_as_of_the_cut_and_note_game_keeps_it_current(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sm.SEASON_TABLE_W, "basketball", 0.05)
    monkeypatch.setitem(sm.SEASON_TABLE_SCALES, "basketball", ONE)
    hist = _history()
    cut = hist[120].ts
    model = sm.build_model(hist, BASKETBALL, cut, season_table=True)
    assert model.table is not None
    counted = sum(r.games for r in model.table.rows[(5, 7)].values()) // 2
    assert counted == sum(1 for r in hist if r.ts < cut)
    model.note_game(hist[120])
    assert sum(r.games for r in model.table.rows[(5, 7)].values()) // 2 == counted + 1
