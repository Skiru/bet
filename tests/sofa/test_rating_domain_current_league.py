"""epochs.RATING_DOMAIN_CURRENT_LEAGUE: the football rating's domain is the
league a side plays now (RatingBook.current_league_domain), not the modal
league of its last 40 matches in 365 days. 2026-10-29: Arka, Betclic 1. Liga
from 2026-07-24, still read Ekstraklasa twelve games in (202:21 vs 229:12),
so Arka - Stal (both 229) was a cross-league pair. Offline."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from bet.sofa import epochs, timeutil
from bet.sofa import football_rating as fr

DAY = 86400
T0 = int(datetime(2026, 1, 10, tzinfo=UTC).timestamp())
OLD, NEW, CUP = 202, 229, 281
ARKA, STAL = 5064, 7000


def res(eid: int, ts: int, comp: int, home: int, away: int, season: int,
        knockout: bool = False) -> fr.FootballResult:
    return fr.FootballResult(
        event_id=eid, ts=ts, competition_id=comp, home_id=home, away_id=away,
        values={"goals_for": (1.0, 1.0)}, season_id=season, knockout=knockout)


def history(new_games: int) -> list[fr.FootballResult]:
    """Arka: 20 Ekstraklasa games (season 1, Jan..May), relegated; from
    August `new_games` in the 1. Liga (season 2). Stal: 1. Liga all along."""
    out: list[fr.FootballResult] = []
    eid = 1
    for i in range(20):
        out.append(res(eid, T0 + i * 7 * DAY, OLD, ARKA, 100 + i, 1))
        out.append(res(eid + 1, T0 + i * 7 * DAY + 3600, NEW, STAL, 300 + i, 11))
        eid += 2
    start = T0 + 200 * DAY
    for i in range(new_games):
        out.append(res(eid, start + i * 7 * DAY, NEW, ARKA, 400 + i, 2))
        out.append(res(eid + 1, start + i * 7 * DAY + 3600, NEW, STAL, 500 + i, 12))
        eid += 2
    return sorted(out, key=lambda r: r.ts)


def book(rs: list[fr.FootballResult], on: bool) -> fr.RatingBook:
    return fr.replay(rs, 2**40, shared_league_link=True, current_league_domain=on)


def test_off_a_relegated_side_keeps_its_old_league() -> None:
    b = book(history(12), on=False)
    assert b.domain(ARKA) == OLD and not b.linked(ARKA, STAL)
    assert not b.team_leagues  # nothing kept while off


def test_on_it_reads_the_league_it_plays_now_from_its_third_game() -> None:
    assert book(history(2), on=True).domain(ARKA) == OLD  # 2 < LINK_MIN_MATCHES
    b = book(history(3), on=True)
    assert b.domain(ARKA) == NEW and b.domain(STAL) == NEW
    assert b.linked(ARKA, STAL)


def test_a_cup_run_is_no_league() -> None:
    rs = history(3)
    last = rs[-1].ts
    rs += [res(9000 + i, last + (i + 1) * DAY, CUP, ARKA, 600 + i, 3,
               knockout=True) for i in range(5)]
    assert book(rs, on=True).domain(ARKA) == NEW


def test_an_old_league_still_active_keeps_the_side_until_it_lapses() -> None:
    # the new league starts 10 days after the old one's last game: inside
    # DOMAIN_ACTIVE_S the old league's 20 games of its season win
    rs = [res(i + 1, T0 + i * 7 * DAY, OLD, ARKA, 100 + i, 1) for i in range(20)]
    last = rs[-1].ts
    rs += [res(50 + i, last + (10 + i * 7) * DAY, NEW, ARKA, 400 + i, 2)
           for i in range(3)]
    assert book(rs, on=True).domain(ARKA) == OLD
    # ... and once it is older than DOMAIN_ACTIVE_S, the new league
    rs += [res(60 + i, last + (40 + i * 7) * DAY, NEW, ARKA, 450 + i, 2)
           for i in range(5)]
    assert book(rs, on=True).domain(ARKA) == NEW


def test_score_model_books_never_read_it() -> None:
    assert fr.RatingBook().current_league_domain is False


def test_parse_event_reads_the_round() -> None:
    def event(round_info: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": 1, "startTimestamp": T0, "status": {"type": "finished"},
            "homeTeam": {"id": 1}, "awayTeam": {"id": 2},
            "homeScore": {"current": 1, "normaltime": 1, "period1": 0},
            "awayScore": {"current": 0, "normaltime": 0, "period1": 0},
            "roundInfo": round_info,
            "tournament": {"id": 5, "name": "Puchar Polski",
                           "uniqueTournament": {"id": CUP, "name": "Puchar Polski"},
                           "category": {"sport": {"slug": "football"}}},
        }
    cup = fr.parse_event(event({"round": 3, "name": "1/16", "cupRoundType": 16}))
    league = fr.parse_event(event({"round": 12}))
    assert cup is not None and cup.knockout
    assert league is not None and not league.knockout


def test_the_switch_reads_the_day_and_the_build_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(epochs, "RATING_DOMAIN_CURRENT_LEAGUE_FROM_UTC",
                        datetime(2026, 10, 30, tzinfo=UTC))
    monkeypatch.setattr(timeutil, "now",
                        lambda: datetime(2026, 10, 30, 6, tzinfo=UTC))
    assert epochs.rating_domain_current_league("2026-10-30")
    assert not epochs.rating_domain_current_league("2026-10-29")
    assert not epochs.rating_domain_current_league(
        "2026-10-30", datetime(2026, 10, 29, 23, tzinfo=UTC))
    monkeypatch.setattr(epochs, "RATING_DOMAIN_CURRENT_LEAGUE_FROM_UTC", None)
    assert not epochs.rating_domain_current_league("2026-10-30")
