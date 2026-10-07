"""The rating's link rule: a pair is LINKED only through a league both sides'
domains share (epochs.link_shared_league, from 2026-10-08 00:00Z).

2026-10-07: football_rating linked a pair when the shared competition was the
league of EITHER side. A promoted side keeps its old league as its domain for
months, so Visby/Roma (Ettan -> HockeyAllsvenskan) was LINKED with its new
opponents three games in, and its Ettan ratios were read 1:1 with no league
strength; 10 hockey legs of the day were removed by NO_BET reads.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa import football_rating as fr
from bet.sofa import score_model as sm
from bet.sofa.football_rating import (
    LINKED,
    LINKED_BY_STRENGTH,
    UNLINKED,
    FootballResult,
    RatingBook,
    replay,
)

DAY = 86400
OLD_LEAGUE, NEW_LEAGUE, CUP = 714, 416, 99
PROMOTED, RIVAL = 1, 2


def _book(shared: bool) -> RatingBook:
    return RatingBook(shared_league_link=shared)


def _played(book: RatingBook, team: int, comp: int, n: int, start: int) -> int:
    for i in range(n):
        book.team_comps[team].append((start + i * DAY, comp))
    book.last_ts = max(book.last_ts, start + (n - 1) * DAY)
    return start + n * DAY


def _promoted_pair(book: RatingBook) -> None:
    # the promoted side: a season in its old league, three games in the new
    end = _played(book, PROMOTED, OLD_LEAGUE, 20, 0)
    _played(book, PROMOTED, NEW_LEAGUE, 3, end)
    # its opponent has lived in the new league all along
    _played(book, RIVAL, NEW_LEAGUE, 23, 0)


@pytest.mark.parametrize("shared, expected", [(False, True), (True, False)])
def test_a_promoted_side_is_not_linked_through_its_new_league(shared, expected):
    book = _book(shared)
    _promoted_pair(book)
    assert book.domain(PROMOTED) == OLD_LEAGUE
    assert book.domain(RIVAL) == NEW_LEAGUE
    assert book.linked(PROMOTED, RIVAL) is expected
    assert book.linked(RIVAL, PROMOTED) is expected


def test_a_promoted_side_is_priced_through_the_league_strength():
    book = _book(True)
    _promoted_pair(book)
    # no measured strength: the pairing says it has no centre
    assert book.link(PROMOTED, RIVAL, "goals_for") == (UNLINKED, 0.0)
    book.strength[(OLD_LEAGUE, "goals_for")] = fr._Strength(-0.3, 50)
    book.strength[(NEW_LEAGUE, "goals_for")] = fr._Strength(0.1, 50)
    status, lf = book.link(PROMOTED, RIVAL, "goals_for")
    assert status == LINKED_BY_STRENGTH
    assert lf == pytest.approx(-0.4)
    # the old rule read the Ettan ratios 1:1
    old = _book(False)
    _promoted_pair(old)
    old.strength.update(book.strength)
    assert old.link(PROMOTED, RIVAL, "goals_for") == (LINKED, 0.0)


@pytest.mark.parametrize("shared", [False, True])
def test_two_sides_of_one_league_stay_linked(shared):
    book = _book(shared)
    _played(book, PROMOTED, NEW_LEAGUE, 10, 0)
    _played(book, RIVAL, NEW_LEAGUE, 10, 0)
    assert book.linked(PROMOTED, RIVAL)
    assert book.link(PROMOTED, RIVAL, "goals_for") == (LINKED, 0.0)


@pytest.mark.parametrize("shared", [False, True])
def test_a_shared_cup_links_nobody(shared):
    book = _book(shared)
    end = _played(book, PROMOTED, OLD_LEAGUE, 10, 0)
    _played(book, PROMOTED, CUP, 3, end)
    end = _played(book, RIVAL, NEW_LEAGUE, 10, 0)
    _played(book, RIVAL, CUP, 3, end)
    assert not book.linked(PROMOTED, RIVAL)


def test_last_seasons_regional_group_still_links_within_its_competition():
    # Both domains are units of one competition (a group minted per season):
    # the pair shares this season's group, so it stays LINKED.
    book = _book(True)
    last_group, this_group = -501, -502
    book.unit_comp.update({last_group: NEW_LEAGUE, this_group: NEW_LEAGUE})
    end = _played(book, PROMOTED, last_group, 10, 0)
    _played(book, PROMOTED, this_group, 3, end)
    _played(book, RIVAL, this_group, 13, 0)
    assert book.domain(PROMOTED) == last_group
    assert book.domain(RIVAL) == this_group
    assert book.linked(PROMOTED, RIVAL)


def test_an_unseen_side_is_never_linked():
    book = _book(True)
    _played(book, RIVAL, NEW_LEAGUE, 10, 0)
    assert book.domain(PROMOTED) is None
    assert not book.linked(PROMOTED, RIVAL)


def _match(eid: int, ts: int, comp: int, home: int, away: int,
           goals: tuple[float, float] = (1.0, 1.0)) -> FootballResult:
    return FootballResult(eid, ts, comp, home, away, {"goals_for": goals})


def _promotion_history() -> list[FootballResult]:
    """PROMOTED scores 3 a game in the old league, then moves up."""
    out: list[FootballResult] = []
    eid = 0
    for i in range(20):  # old league: PROMOTED against 10, 11, ...
        out.append(_match(eid, i * DAY, OLD_LEAGUE, PROMOTED, 10 + i % 4, (3.0, 0.0)))
        eid += 1
        out.append(_match(eid, i * DAY + 1, OLD_LEAGUE, 10 + i % 4, 14 + i % 4))
        eid += 1
    for i in range(20):  # new league: RIVAL against 20..
        out.append(_match(eid, i * DAY + 2, NEW_LEAGUE, RIVAL, 20 + i % 4))
        eid += 1
        out.append(_match(eid, i * DAY + 3, NEW_LEAGUE, 20 + i % 4, 24 + i % 4))
        eid += 1
    for i in range(3):  # the promoted side's first three games up
        out.append(_match(eid, (21 + i) * DAY, NEW_LEAGUE, PROMOTED, 20 + i))
        eid += 1
        out.append(_match(eid, (21 + i) * DAY, NEW_LEAGUE, RIVAL, 24 + i))
        eid += 1
    return out


def test_the_replay_carries_the_rule_into_the_update_and_the_forecast():
    history = _promotion_history()
    cut = 30 * DAY
    old = replay(history, cut, shared_league_link=False)
    new = replay(history, cut, shared_league_link=True)
    assert old.linked(PROMOTED, RIVAL) and not new.linked(PROMOTED, RIVAL)
    # the old rule forecasts the Ettan attack 1:1; the new one shrinks it
    # toward the pool (CROSS_RATIO_POWER) and says it is cross-league
    e_old = old.expected(NEW_LEAGUE, PROMOTED, RIVAL, "goals_for")
    status, lf = new.link(PROMOTED, RIVAL, "goals_for")
    e_new = new.expected(NEW_LEAGUE, PROMOTED, RIVAL, "goals_for", lf,
                         cross=status != LINKED)
    assert e_old is not None and e_new is not None
    assert e_new[0] < e_old[0]


def test_the_book_follows_the_epoch_by_default(monkeypatch):
    monkeypatch.setattr(epochs, "LINK_SHARED_LEAGUE_FROM_UTC",
                        datetime(2000, 1, 1, tzinfo=UTC))
    assert RatingBook().shared_league_link
    assert replay([], 0).shared_league_link
    monkeypatch.setattr(epochs, "LINK_SHARED_LEAGUE_FROM_UTC", None)
    assert not RatingBook().shared_league_link
    assert not replay([], 0).shared_league_link


def test_the_switch_acts_from_the_next_days_midnight_never_mid_day(monkeypatch):
    assert epochs.LINK_SHARED_LEAGUE_FROM_UTC == datetime(2026, 10, 8, tzinfo=UTC)
    assert epochs.LINK_SHARED_LEAGUE_DATE == "2026-10-08"
    before = datetime(2026, 10, 7, 23, 59, tzinfo=UTC)
    after = datetime(2026, 10, 8, 0, 0, tzinfo=UTC)
    assert not epochs.link_shared_league("2026-10-08", before)
    assert epochs.link_shared_league("2026-10-08", after)
    # a rebuild of a day printed under the old rule keeps it
    assert not epochs.link_shared_league("2026-10-07", after)
    # no day (a refit's as-of replay): the wall clock, never SOFA_NOW
    monkeypatch.setenv("SOFA_NOW", "2026-09-20T10:00:00Z")
    assert epochs.link_shared_league(None, after)


@pytest.mark.parametrize("shared", [False, True])
def test_the_score_model_builds_its_book_under_the_given_rule(shared):
    history = _promotion_history()
    model = sm.build_model(history, sm.SPORTS["hockey"], 30 * DAY,
                           shared_league_link=shared)
    assert model.book.shared_league_link is shared


def test_sport_confidence_rates_with_the_rule_of_the_day_it_builds(monkeypatch):
    from scripts.sofa import run_sport_confidence as rsc

    seen: list[Any] = []

    def fake_build_model(history, sport, cut, params=None, shared_league_link=None):
        seen.append(shared_league_link)
        return SimpleNamespace()

    monkeypatch.setattr(sm, "build_model", fake_build_model)
    monkeypatch.setattr(sm, "load_events", lambda db, sp: {})
    monkeypatch.setattr(rsc.scf.TeamGames, "build",
                        classmethod(lambda cls, events, sp: None))
    at = datetime(2026, 10, 8, 6, 0, tzinfo=UTC)
    monkeypatch.setattr(epochs, "datetime", SimpleNamespace(now=lambda tz: at))
    rsc.DbForecaster("unused.db", at, "2026-10-08")._shadow_model("hockey")
    rsc.DbForecaster("unused.db", at, "2026-10-07")._shadow_model("hockey")
    assert seen == [True, False]


def test_the_measurement_scores_both_rules_on_the_matches_they_link_apart():
    from scripts.sofa import measure_link_rule as mlr

    # three more games up: from the fourth, LINK_MIN_MATCHES is met
    history = _promotion_history() + [
        _match(1000 + i, (25 + i) * DAY, NEW_LEAGUE, RIVAL, PROMOTED)
        for i in range(3)]
    records = mlr.walk(history, ["goals_for"], 21 * DAY, 30 * DAY)
    rows = records["goals_for"]
    changed = [r for r in rows if r["changed"]]
    # PROMOTED's games up are the only ones the two rules link differently
    assert changed and all(r["status_old"] == LINKED for r in changed)
    assert all(r["status_new"] != LINKED for r in changed)
    summary = mlr.summarise(records)["goals_for"]
    assert summary["changed"]["n"] == len(changed)
    point, lo, hi = mlr.bootstrap_diff(rows, "old", "new")
    assert lo <= point <= hi
