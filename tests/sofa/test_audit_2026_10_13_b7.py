"""Audit 2026-10-13 B7: basketball's centre as pace x efficiency.

Possessions (Oliver: FGA - ORB + TOV + 0.44 FTA) and points per possession
read off the box score and rated as-of in the same RatingBook as the points;
behind epochs.BB_PACE_FROM_UTC (None: byte-identical model).
Evidence: docs/sofa/evidence/basketball_pace_2026-10-13.md.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa import score_model as sm
from bet.sofa import sport_confidence as scf
from bet.sofa.shadow import SPORTS

BB = SPORTS["basketball"]
HOCKEY = SPORTS["hockey"]
DAY = 86400


def _box(fga: tuple[int, int], fta: tuple[int, int], orb: tuple[int, int],
         tov: tuple[int, int]) -> dict[str, Any]:
    def item(key: str, vals: tuple[int, int], total: bool) -> dict[str, Any]:
        f = "Total" if total else "Value"
        return {"key": key, "homeValue": 0, "awayValue": 0,
                f"home{f}": vals[0], f"away{f}": vals[1]}
    return {"statistics": [{"period": "ALL", "groups": [
        {"groupName": "Scoring", "statisticsItems": [
            item("freeThrowsScored", fta, True),
            item("fieldGoalsScored", fga, True)]},
        {"groupName": "Other", "statisticsItems": [
            item("offensiveRebounds", orb, False),
            item("turnovers", tov, False)]}]}]}


def test_the_switch_is_off_and_asks_the_day_and_the_build_clock(monkeypatch) -> None:
    assert epochs.BB_PACE_FROM_UTC is None
    assert not epochs.bb_pace("2026-10-20", datetime(2026, 10, 20, tzinfo=UTC))
    at = datetime(2026, 10, 15, tzinfo=UTC)
    monkeypatch.setattr(epochs, "BB_PACE_FROM_UTC", at)
    assert epochs.bb_pace("2026-10-15", at)
    assert not epochs.bb_pace("2026-10-14", datetime(2026, 10, 16, tzinfo=UTC))
    assert not epochs.bb_pace("2026-10-15", datetime(2026, 10, 14, tzinfo=UTC))


def test_oliver_possessions_and_points_per_possession() -> None:
    box = _box(fga=(71, 62), fta=(13, 20), orb=(10, 14), tov=(11, 17))
    vals = sm.box_values(box, 78.0, 68.0, overtime=False)
    assert vals is not None
    home = 71 - 10 + 11 + 0.44 * 13
    away = 62 - 14 + 17 + 0.44 * 20
    poss = (home + away) / 2
    assert vals[sm.PACE_POSS] == pytest.approx((poss, poss))
    assert vals[sm.PACE_PPP] == pytest.approx((78.0 / poss, 68.0 / poss))
    # an overtime game: possessions scaled to regulation (one overtime of 5
    # minutes over 4 quarters of 10), efficiency on the whole game
    ot = sm.box_values(box, 90.0, 88.0, overtime=True)
    assert ot is not None
    assert ot[sm.PACE_POSS][0] == pytest.approx(poss * 40 / 45)
    assert ot[sm.PACE_PPP][0] == pytest.approx(90.0 / poss)
    # the raw JSON text reads the same
    import json
    assert sm.box_values(json.dumps(box), 78.0, 68.0, False) == vals


def test_a_box_score_that_does_not_add_up_is_none() -> None:
    assert sm.box_values(None, 80, 70, False) is None
    assert sm.box_values("not json", 80, 70, False) is None
    missing = _box((71, 62), (13, 20), (10, 14), (11, 17))
    missing["statistics"][0]["groups"][1]["statisticsItems"].pop()  # no turnovers
    assert sm.box_values(missing, 80, 70, False) is None
    tiny = _box((10, 10), (0, 0), (0, 0), (0, 0))
    assert sm.box_values(tiny, 20, 20, False) is None  # 10 possessions


def _history(n: int = 80, box: bool = True) -> list[sm.FootballResult]:
    """Four teams of one competition, a game every day; team 1 plays fast."""
    teams = (1, 2, 3, 4)
    out: list[sm.FootballResult] = []
    for i in range(n):
        h, a = teams[i % 4], teams[(i + 1 + i // 4) % 4]
        if h == a:
            a = teams[(i + 2) % 4]
        fast = 1 in (h, a)
        poss = 80.0 if fast else 66.0
        hp, ap = (poss * 1.05, poss * 1.0)
        values = {f"p{k}_for": (hp / 4, ap / 4) for k in (1, 2, 3, 4)}
        values[sm.REG_METRIC["basketball"]] = (hp, ap)
        r = sm.FootballResult(1000 + i, (i + 1) * DAY, 5, h, a, values)
        if box:
            r = dataclasses.replace(r, values={
                **r.values, sm.PACE_POSS: (poss, poss),
                sm.PACE_PPP: (hp / poss, ap / poss)})
        out.append(r)
    return out


def test_off_is_byte_identical_whatever_the_history_carries() -> None:
    cut = 81 * DAY
    plain = sm.build_model(_history(box=False), BB, cut, shared_league_link=True)
    boxed = sm.build_model(_history(box=True), BB, cut, shared_league_link=True)
    assert not boxed.pace and boxed.box_last is None
    assert boxed.params == plain.params
    assert boxed.period_sd == plain.period_sd
    for h, a in ((1, 2), (3, 4), (2, 1)):
        assert boxed.expected(5, h, a, cut) == plain.expected(5, h, a, cut)
        assert boxed.pace_expected(5, h, a, cut) is None


def test_on_the_centre_is_pace_times_efficiency() -> None:
    cut = 81 * DAY
    model = sm.build_model(_history(), BB, cut, shared_league_link=True, pace=True)
    assert model.pace and model.box_last
    paced = model.pace_expected(5, 1, 2, cut)
    assert paced is not None
    exp = model.expected(5, 1, 2, cut)
    assert exp is not None
    assert sum(exp[0]) == pytest.approx(paced[0])
    assert sum(exp[1]) == pytest.approx(paced[1])
    # by hand from the book: mean expected possessions x points per possession
    book = model.book
    ph, pa = book.expected(5, 1, 2, sm.PACE_POSS, strict=True)  # type: ignore[misc]
    eh, ea = book.expected(5, 1, 2, sm.PACE_PPP, strict=True)  # type: ignore[misc]
    assert paced[0] == pytest.approx((ph + pa) / 2 * eh)
    assert paced[1] == pytest.approx((ph + pa) / 2 * ea)
    # the fast team's games are expected with more possessions
    slow = model.pace_expected(5, 3, 4, cut)
    assert slow is not None and sum(paced) > sum(slow)


def test_a_stale_or_thin_box_score_falls_back_to_the_points() -> None:
    cut = 81 * DAY
    model = sm.build_model(_history(), BB, cut, shared_league_link=True, pace=True)
    points = sm.build_model(_history(box=False), BB, cut, shared_league_link=True)
    late = cut + sm.PACE_FRESH_S + DAY
    assert model.pace_expected(5, 1, 2, late) is None
    # a stale pair: the points centre (same book on the points metric); the
    # spread differs, fitted around the pace centre
    assert model.expected(5, 1, 2, late) == points.expected(5, 1, 2, late)
    # an unknown side and a competition with no box-score league rate
    assert model.pace_expected(5, 1, 99, cut) is None
    assert model.pace_expected(77, 1, 2, cut) is None
    # hockey never reads it
    hk = dataclasses.replace(model, sport=HOCKEY)
    assert hk.pace_expected(5, 1, 2, cut) is None


def test_note_game_moves_the_freshness_clock_only_with_a_box_score() -> None:
    model = sm.build_model(_history(), BB, 81 * DAY, shared_league_link=True,
                           pace=True)
    assert model.box_last is not None
    before = dict(model.box_last)
    plain = _history(box=False)[0]
    model.note_game(dataclasses.replace(plain, ts=500 * DAY))
    assert model.box_last == before
    model.note_game(dataclasses.replace(_history()[0], ts=500 * DAY))
    assert model.box_last[plain.home_id] == 500 * DAY


def test_rated_values_keep_the_pace_metrics_for_basketball_only() -> None:
    r = _history()[0]
    assert sm.PACE_POSS in sm._rated_values(r, BB).values
    assert sm.PACE_POSS not in sm._rated_values(r, HOCKEY).values


def _event(eid: int) -> dict[str, Any]:
    return {
        "id": eid, "startTimestamp": 10 * DAY,
        "tournament": {"id": 9, "uniqueTournament": {"id": 5, "name": "Liga"},
                       "category": {"sport": {"slug": "basketball"}, "name": "X"}},
        "status": {"type": "finished", "description": "Ended", "code": 100},
        "homeTeam": {"id": 1, "name": "A", "gender": "M"},
        "awayTeam": {"id": 2, "name": "B", "gender": "M"},
        "homeScore": {"current": 80, "period1": 20, "period2": 20, "period3": 20,
                      "period4": 20},
        "awayScore": {"current": 70, "period1": 18, "period2": 18, "period3": 17,
                      "period4": 17},
        "winnerCode": 1,
    }


def test_parse_history_attaches_the_box_score_only_when_given() -> None:
    events = {7: _event(7)}
    plain = scf.parse_history(events, BB)
    assert plain and sm.PACE_POSS not in plain[0].rating.values
    box = {7: _box((71, 62), (13, 20), (10, 14), (11, 17))}
    boxed = scf.parse_history(events, BB, box)
    assert sm.PACE_POSS in boxed[0].rating.values
    assert boxed[0].rating.values[sm.PACE_PPP][0] == pytest.approx(
        80 / boxed[0].rating.values[sm.PACE_POSS][0])
    # the points the book learns are unchanged
    key = sm.REG_METRIC["basketball"]
    assert boxed[0].rating.values[key] == plain[0].rating.values[key]
