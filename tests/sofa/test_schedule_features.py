"""bet.sofa.schedule_features - as-of, order-free, parity with schedule.py."""

from __future__ import annotations

import random
from typing import Any

from bet.sofa import schedule
from bet.sofa.schedule_features import (
    DAY_S,
    FOOTBALL_COLUMNS,
    Calendar,
    calendar_from_events,
    match_from_event,
    rest_bucket,
)

T0 = 1_760_000_000 - 1_760_000_000 % DAY_S + 18 * 3600  # 18:00Z
UCL = 7


def ev(eid: int, ts: int, home: int, away: int, *, status: str = "finished",
       comp: int = 17, season: int = 1, national: bool = False,
       extra: bool = False) -> dict[str, Any]:
    e: dict[str, Any] = {
        "id": eid,
        "startTimestamp": ts,
        "homeTeam": {"id": home, "national": national},
        "awayTeam": {"id": away, "national": national},
        "status": {"type": status, "code": 110 if extra else 100},
        "tournament": {"uniqueTournament": {"id": comp}, "id": comp * 10},
        "season": {"id": season},
        "homeScore": {"current": 1, "normaltime": 1},
        "awayScore": {"current": 1, "normaltime": 1},
    }
    return e


def cal(events: list[dict[str, Any]]) -> Calendar:
    return calendar_from_events(events, "football", continental=[UCL])


def test_rest_buckets_hours_over_24() -> None:
    assert rest_bucket(3.49) == "R1"
    assert rest_bucket(3.5) == "R2"
    assert rest_bucket(6.0) == "R3"
    assert rest_bucket(20.4) == "R4"
    assert rest_bucket(21.0) == "R5"
    assert rest_bucket(None) is None


def test_as_of_ignores_kickoff_and_later() -> None:
    k = T0 + 30 * DAY_S
    base = [ev(1, k - 4 * DAY_S, 100, 200)]
    late = [ev(2, k, 100, 300), ev(3, k + 3600, 100, 400),
            ev(4, k + 2 * DAY_S, 100, 500)]
    a = cal(base).football_side(100, k, 17, 1)
    b = cal(base + late).football_side(100, k, 17, 1)
    assert a.rest_d == b.rest_d == 4.0
    assert a.matches_7d == b.matches_7d == 1


def test_order_within_day_irrelevant() -> None:
    k = T0 + 40 * DAY_S
    events = [ev(i, k - (i % 9) * DAY_S - i * 60, 100 + i % 5, 200 + i % 7)
              for i in range(1, 60)]
    feats = []
    for seed in range(5):
        shuffled = events[:]
        random.Random(seed).shuffle(shuffled)
        c = cal(shuffled)
        feats.append([c.football_side(s, k, 17, 1) for s in range(100, 105)])
    assert all(f == feats[0] for f in feats)


def test_postponed_and_friendly_not_load() -> None:
    k = T0 + 30 * DAY_S
    events = [
        ev(1, k - 10 * DAY_S, 100, 200),
        ev(2, k - 2 * DAY_S, 100, 300, status="postponed"),
    ]
    f = cal(events).football_side(100, k, 17, 1)
    assert f.rest_bucket == "R4"


def test_parity_with_schedule_display() -> None:
    k = T0 + 60 * DAY_S
    events = [ev(i, k - i * 2 * DAY_S - 3600, 100, 200 + i) for i in range(1, 12)]
    events.append(ev(99, k - DAY_S, 100, 999, status="postponed"))
    disp = schedule.side_schedule(events, k)
    f = cal(events).football_side(100, k, 17, 1)
    assert f.rest_d is not None and disp.rest_days == round(f.rest_d, 1)
    assert disp.matches_7d == f.matches_7d
    assert disp.matches_14d == f.matches_14d


def test_display_flags_unchanged() -> None:
    k = T0 + 60 * DAY_S
    a = [ev(1, k - 25 * DAY_S, 100, 200)]
    b = [ev(2, k - 6 * DAY_S, 300, 400), ev(3, k - 4 * DAY_S, 300, 401),
         ev(4, k - 2 * DAY_S, 300, 402)]
    fx = schedule.fixture_schedule(a, b, 100, 300, 17, k, 1000)
    assert fx.flags() == ["LONG_LAYOFF(home 25 d)", "CONGESTED(away 3 in 7 d)"]


def test_layoff_kinds_and_continental() -> None:
    k = T0 + 200 * DAY_S
    events = [
        ev(1, k - 30 * DAY_S, 100, 200, season=1),  # old season
        ev(2, k - 3 * DAY_S, 300, 400, comp=UCL, extra=True),
        ev(3, k - 10 * DAY_S, 300, 401),
        ev(4, k + 2 * DAY_S, 300, 402, comp=UCL, status="notstarted"),
    ]
    c = cal(events)
    f = c.football_side(100, k, 17, 2)
    assert f.rest_bucket == "R5" and f.layoff_kind == "season_start"
    g = c.football_side(300, k, 17, 1)
    assert g.rest_bucket == "R1" and g.cont_prev4 and g.et_prev and g.cont_next4
    cols = g.indicators()
    assert set(cols) == set(FOOTBALL_COLUMNS)
    assert cols["R1"] == cols["cont_prev4_x_R1"] == 1


def test_intl_break_return() -> None:
    k = T0 + 100 * DAY_S
    events = [ev(1, k - 14 * DAY_S, 100, 200)]
    day = k - 7 * DAY_S
    events += [ev(1000 + i, day + i, 5000 + 2 * i, 5001 + 2 * i, comp=11, national=True)
               for i in range(30)]
    f = cal(events).football_side(100, k, 17, 1)
    assert f.rest_bucket == "R4" and f.intl_return
    f2 = cal(events[:1] + events[2:]).football_side(100, k, 17, 1)
    assert not f2.intl_return


def test_no_coverage_zero_columns() -> None:
    f = cal([]).football_side(100, T0, 17, 1)
    assert not f.coverage
    assert set(f.indicators().values()) == {0}


def tev(eid: int, ts: int, home: int, away: int, hg: tuple[int, int],
        ag: tuple[int, int], winner: int, tour: int = 1,
        desc: str = "Ended") -> dict[str, Any]:
    return {
        "id": eid,
        "startTimestamp": ts,
        "homeTeam": {"id": home},
        "awayTeam": {"id": away},
        "status": {"type": "finished", "description": desc},
        "tournament": {"id": tour, "uniqueTournament": {"id": tour},
                       "category": {"name": "ATP"}, "name": "X"},
        "homeScore": {"period1": hg[0], "period2": hg[1]},
        "awayScore": {"period1": ag[0], "period2": ag[1]},
        "winnerCode": winner,
        "groundType": "Clay",
    }


def test_tennis_load_and_doubles_skipped() -> None:
    k = T0 + 50 * DAY_S
    events = [
        tev(1, k - DAY_S, 10, 20, (6, 7), (4, 6), 1, tour=5),
        tev(2, k - 2 * DAY_S, 10, 21, (6, 6), (3, 2), 1, tour=5),
        tev(3, k - 5 * DAY_S, 10, 22, (6, 6), (1, 1), 1, tour=4),
    ]
    doubles = tev(4, k - 3600, 10, 23, (6, 6), (0, 0), 1, tour=5)
    doubles["homeTeam"]["subTeams"] = [{"id": 10}, {"id": 11}]
    assert match_from_event(doubles, "tennis") is None
    c = calendar_from_events([*events, doubles], "tennis")
    f = c.tennis_player(10, k, tournament=5, surface="clay")
    assert f.games78 == (23 + 17) / 10
    assert f.games7d_prev == 14 / 10
    assert f.rounds_cur == 2
    assert not f.layoff21 and not f.ret14


def test_tennis_retirement_flag() -> None:
    k = T0 + 50 * DAY_S
    events = [tev(1, k - 5 * DAY_S, 10, 20, (3, 0), (6, 1), 2, desc="Retired")]
    f = calendar_from_events(events, "tennis").tennis_player(10, k, 9, None)
    assert f.ret14
    events.append(tev(2, k - 2 * DAY_S, 10, 21, (6, 6), (1, 1), 1))
    g = calendar_from_events(events, "tennis").tennis_player(10, k, 9, None)
    assert not g.ret14
