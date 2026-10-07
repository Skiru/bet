"""One competition, several regional groups that never meet.

2026-10-02, JBK Pietarsaari - FC Honka, Kakkonen play-offs: Sofascore keeps
Kakkonen's Groups A, B and C under one uniqueTournament (11509), each group a
stage of its own (tournament.id). The rating read the competition as one
league, so a Group C side and a Group B side were LINKED and Honka's goals
were cut by a JBK defence earned against Group C. assign_league_units makes
every round-robin component of a (competition, season) its own league unit.
"""

from dataclasses import replace

import pytest

from bet.sofa.football_rating import (
    LINKED,
    LINKED_BY_STRENGTH,
    MIN_GROUP_TEAMS,
    MIN_STRENGTH_LINKS,
    UNLINKED,
    FootballForecast,
    FootballResult,
    assign_league_units,
    league_groups,
    parse_event,
    replay,
)

DAY = 86400
COMP, SEASON, CUP = 11509, 90226, 777
GROUP_A = list(range(1, 1 + MIN_GROUP_TEAMS))
GROUP_B = list(range(101, 101 + MIN_GROUP_TEAMS))


def _m(eid, ts, home, away, goals=(1.0, 1.0), comp=COMP, season=SEASON,
       stage=None):
    return FootballResult(eid, ts, comp, home, away, {"goals_for": goals},
                          season_id=season, stage_id=stage)


def _round_robin(teams, stage, eid, ts, comp=COMP, season=SEASON):
    out = []
    for _ in range(2):  # home and away
        for i, h in enumerate(teams):
            for a in teams[i + 1:]:
                out.append(_m(eid, ts, h, a, comp=comp, season=season,
                              stage=stage))
                eid += 1
                ts += 3600
    return out, eid, ts


def _two_groups():
    a, eid, ts = _round_robin(GROUP_A, 501, 0, 0)
    b, eid, ts = _round_robin(GROUP_B, 502, eid, 0)
    return a + b, eid, max(r.ts for r in a + b) + DAY


def _sorted(history):
    return sorted(history, key=lambda r: (r.ts, r.event_id))


def test_a_cross_group_fixture_is_unlinked():
    history, _eid, t = _two_groups()
    old = replay(_sorted(history), cut_ts=t)
    # What the rating did before: one competition, one league.
    assert old.link(GROUP_A[0], GROUP_B[0], "goals_for")[0] == LINKED
    book = replay(assign_league_units(_sorted(history)), cut_ts=t)
    assert book.domain(GROUP_A[0]) == -501 and book.domain(GROUP_B[0]) == -502
    assert book.link(GROUP_A[0], GROUP_A[1], "goals_for") == (LINKED, 0.0)
    assert book.link(GROUP_A[0], GROUP_B[0], "goals_for") == (UNLINKED, 0.0)
    forecast = FootballForecast(book, COMP, GROUP_A[0], GROUP_B[0])
    assert forecast.fixture_link() == UNLINKED


def test_a_play_off_between_groups_joins_nothing():
    history, eid, t = _two_groups()
    # Knockout stage of the same competition and season: one tie per pair.
    playoff = [_m(eid + i, t + i * 3600, GROUP_A[i], GROUP_B[i], stage=503)
               for i in range(2)]
    units = assign_league_units(_sorted(history + playoff))
    tie = next(r for r in units if r.event_id == eid)
    assert (tie.home_unit, tie.away_unit) == (-501, -502)
    book = replay(units, cut_ts=t + DAY)
    assert book.link(GROUP_A[3], GROUP_B[3], "goals_for")[0] == UNLINKED


def test_a_single_connected_league_is_unchanged():
    league, _eid, ts = _round_robin(GROUP_A + GROUP_B, 600, 0, 0)
    history = _sorted(league)
    units = assign_league_units(history)
    assert all(u is r for u, r in zip(units, history, strict=True))
    book = replay(units, cut_ts=ts + DAY)
    assert book.domain(GROUP_A[0]) == COMP
    assert book.link(GROUP_A[0], GROUP_B[0], "goals_for") == (LINKED, 0.0)


def test_cup_matches_between_the_groups_measure_the_gap():
    history, eid, t = _two_groups()
    # Group B is the stronger one: it wins every cup tie 3-0.
    cup = []
    for i in range(MIN_STRENGTH_LINKS + 4):
        cup.append(_m(eid, t, GROUP_B[1 + i % 5], GROUP_A[1 + i % 5],
                      (3.0, 0.0), comp=CUP, season=1, stage=CUP))
        eid += 1
        t += DAY
    book = replay(assign_league_units(_sorted(history + cup)), cut_ts=t + DAY)
    assert book.domain(GROUP_B[0]) == -502  # the cup never becomes the league
    status, gap = book.link(GROUP_B[0], GROUP_A[0], "goals_for")
    assert status == LINKED_BY_STRENGTH and gap > 0


def test_a_chain_of_qualifying_ties_is_not_a_group():
    """Components that are not round robins (UEFA qualification: pairs meet
    over two legs, a few go on) leave the competition whole."""
    def chain(teams, stage, eid0):
        out, eid = [], eid0
        for i in range(0, len(teams) - 1):
            legs = 4 if i % 2 == 0 else 1
            for _ in range(legs):
                out.append(_m(eid, eid * 3600, teams[i], teams[i + 1],
                              stage=stage))
                eid += 1
        return out, eid
    a, eid = chain(GROUP_A, 900, 0)
    b, _eid = chain(GROUP_B, 900, eid)
    assert league_groups(a + b) == []


def test_two_components_under_one_stage_get_two_units():
    a, eid, _ = _round_robin(GROUP_A, 700, 0, 0)
    b, _eid, _ = _round_robin(GROUP_B, 700, eid, 0)
    units = assign_league_units(_sorted(a + b))
    seen = {r.home_unit for r in units}
    assert len(seen) == 2 and None not in seen


def test_a_result_without_a_season_is_never_split():
    history, _eid, _t = _two_groups()
    bare = [replace(r, season_id=None) for r in history]
    assert all(u is r for u, r in zip(assign_league_units(bare), bare,
                                      strict=True))


def test_the_event_payload_gives_season_and_stage():
    event = {
        "id": 17148930,
        "startTimestamp": 1_790_000_000,
        "status": {"type": "finished"},
        "tournament": {
            "id": 175557, "name": "Kakkonen, Group C", "isGroup": True,
            "groupName": "Group C",
            "category": {"name": "Finland", "sport": {"slug": "football"}},
            "uniqueTournament": {"id": COMP, "name": "Kakkonen"},
        },
        "season": {"id": SEASON},
        "homeTeam": {"id": 22387, "name": "JBK Pietarsaari"},
        "awayTeam": {"id": 2260, "name": "FC Honka"},
        "homeScore": {"current": 2, "period1": 1, "period2": 1},
        "awayScore": {"current": 1, "period1": 0, "period2": 1},
    }
    r = parse_event(event)
    assert r is not None
    assert (r.competition_id, r.season_id, r.stage_id) == (COMP, SEASON, 175557)
    assert r.home_unit is None and r.away_unit is None


@pytest.mark.parametrize("shared", [False, True])
def test_sides_of_one_group_link_when_neither_calls_it_home(shared):
    """Units are minted per season, so a side's modal unit can be last
    season's league. Two sides meeting in this season's group are LINKED
    by it when it belongs to their domain competition (replayed 2026-10-01:
    Nueva Santa Rosa - Mictlan, one Guatemalan group). Before 2026-10-08
    (shared=False) either side's domain was enough, which also linked a side
    that arrived from another league (epochs.link_shared_league)."""
    old_season, eid, ts = _round_robin(GROUP_A + GROUP_B, 600, 0, 0,
                                       season=1)  # one league last season
    newcomer = 50
    other, eid, ts = _round_robin([newcomer] + list(range(60, 67)), 990, eid,
                                  ts, comp=99, season=7)
    group_a = GROUP_A[:-1] + [newcomer]
    a, eid, ts2 = _round_robin(group_a, 501, eid, ts)
    b, eid, ts3 = _round_robin(GROUP_B, 502, eid, ts)
    history = _sorted(old_season + other + a + b)
    book = replay(assign_league_units(history), cut_ts=max(ts2, ts3) + DAY,
                  shared_league_link=shared)
    assert book.domain(GROUP_A[0]) == COMP  # 22 matches last season
    assert book.domain(newcomer) == 99      # 14 matches in its old league
    # the newcomer's ratios were earned in competition 99: cross-league now
    assert (book.link(GROUP_A[0], newcomer, "goals_for") == (LINKED, 0.0)) is not shared
    # two of last season's sides, this season in one group: still LINKED
    assert book.link(GROUP_A[0], GROUP_A[1], "goals_for") == (LINKED, 0.0)
    # The groups still do not link through this season ...
    assert book.link(newcomer, GROUP_B[0], "goals_for")[0] != LINKED
    # ... and last season's shared league still links its two members.
    assert book.link(GROUP_A[0], GROUP_B[0], "goals_for") == (LINKED, 0.0)
