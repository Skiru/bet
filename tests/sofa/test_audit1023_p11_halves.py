"""Audit 2026-10-23 B11 / P11: basketball competitions played in two halves
(NCAA men) in the score-model history (score_model.parse_event `halves`,
epochs.BB_HALVES_LEAGUES_FROM_UTC).

parse_event wanted exactly four quarters, so every NCAA men's game (2,842 in
365 days) fell out of the history. The switch stays off until Superbet offers
an NCAA basketball game (none in its offer on 2026-10-23).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bet.sofa import epochs
from bet.sofa.score_model import (
    BB_HALVES_COMPETITIONS,
    REG_METRIC,
    basketball_halves,
    build_model,
    parse_event,
    period_metric,
)
from bet.sofa.shadow import SPORTS

BB = SPORTS["basketball"]


def _game(eid: int, ts: int, competition: int, halves: bool,
          home: int = 1, away: int = 2, label: str = "1st quarter"
          ) -> dict[str, Any]:
    hs = {"period1": 35, "period2": 40} if halves else {
        "period1": 20, "period2": 18, "period3": 22, "period4": 15}
    as_ = {"period1": 30, "period2": 33} if halves else {
        "period1": 18, "period2": 20, "period3": 16, "period4": 21}
    hs["current"], as_["current"] = sum(hs.values()), sum(as_.values())
    return {
        "id": eid, "startTimestamp": ts,
        "status": {"type": "finished", "description": "Ended"},
        "tournament": {"id": competition,
                       "category": {"sport": {"slug": "basketball"}},
                       "uniqueTournament": {"id": competition}},
        "homeTeam": {"id": home}, "awayTeam": {"id": away},
        "homeScore": hs, "awayScore": as_,
        "periods": {"period1": label},
    }


NCAA = 33651


def test_an_ncaa_game_parses_only_under_the_switch() -> None:
    g = _game(1, 1_700_000_000, NCAA, True)
    assert parse_event(g, BB) is None  # the rule before the audit
    r = parse_event(g, BB, halves=True)
    assert r is not None
    assert r.values == {REG_METRIC["basketball"]: (75.0, 63.0)}
    assert period_metric(1) not in r.values


def test_halves_are_a_format_not_any_two_period_game() -> None:
    # a quarter league's game cut short at half time stays out
    g = _game(2, 1_700_000_000, 21124, True)
    assert not basketball_halves(g)
    assert parse_event(g, BB, halves=True) is None
    # Sofascore's own "1st half" label is a halves format anywhere
    labelled = _game(3, 1_700_000_000, 999, True, label="1st half")
    assert basketball_halves(labelled)
    assert parse_event(labelled, BB, halves=True) is not None
    # four quarters in an NCAA competition still parse as before
    four = _game(4, 1_700_000_000, NCAA, False)
    assert parse_event(four, BB, halves=True) == parse_event(four, BB)
    assert NCAA in BB_HALVES_COMPETITIONS and 648 in BB_HALVES_COMPETITIONS


def test_hockey_never_reads_halves() -> None:
    g = _game(5, 1_700_000_000, NCAA, True)
    g["tournament"]["category"]["sport"]["slug"] = "ice-hockey"
    assert parse_event(g, SPORTS["hockey"], halves=True) is None


def test_halves_games_leave_the_quarter_shares_alone() -> None:
    t0 = 1_700_000_000
    quarters = [parse_event(_game(10 + i, t0 + i * 43200, 132, False,
                                  1 + i % 3, 4 + i % 2), BB)
                for i in range(60)]
    halves = [parse_event(_game(100 + i, t0 + i * 43200 + 3600, NCAA, True,
                                7, 8), BB, halves=True) for i in range(40)]
    base = [r for r in quarters if r is not None]
    mixed = sorted(base + [r for r in halves if r is not None],
                   key=lambda r: (r.ts, r.event_id))
    cut = t0 + 30 * 86400
    m0 = build_model(base, BB, cut, strict_league_rate=True)
    m1 = build_model(mixed, BB, cut, strict_league_rate=True)
    assert m0.shares == m1.shares
    # The quarter spread is fitted on quarter games only, but it is not
    # identical: a halves game still moves the sport's global rate that every
    # league's rate is shrunk toward (football_rating.RatingBook.update), so
    # the quarter games' expectations move a little. Not measured - one of
    # the reasons P11 stays off until measured (the P11 report).
    assert m1.period_sd > 0
    # the halves teams are rated: an NCAA pair has an expectation
    assert m1.expected(NCAA, 7, 8) is not None or m1.no_league_rate(NCAA)


def test_the_switch_is_off() -> None:
    assert epochs.BB_HALVES_LEAGUES_FROM_UTC is None
    assert not epochs.bb_halves_leagues(
        "2026-11-05", datetime(2026, 11, 5, 12, tzinfo=UTC))
