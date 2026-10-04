"""The hockey / basketball / volleyball shadow measurement (src/bet/sofa/shadow.py)
and its stages SHADOW / SHADOW_SETTLE: parsing Superbet's lines by marketId,
rebuilding a game from Sofascore's score, grading, and the stages end to end
against fake clients. Every payload shape here was captured live 2026-09-29.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa.cs2 import fair_probability, one_side_per_line, summarize
from bet.sofa.errors import CircuitOpenError
from bet.sofa.shadow import (
    PARTNER,
    SPORTS,
    ShadowLine,
    actual_value,
    build_result,
    event_state,
    grade,
    latest_pre_kickoff,
    parse_event,
    parse_line,
    settle_event,
)
from scripts.sofa import (
    audit_shadow,
    run_pipeline,
    run_shadow,
    settle_shadow,
    shadow_daily,
)

HOCKEY, BASKETBALL, VOLLEYBALL = (
    SPORTS["hockey"],
    SPORTS["basketball"],
    SPORTS["volleyball"],
)
T1, T2 = "Ocelari Trinec", "Rytiri Kladno"


def item(
    market_id: int,
    market: str,
    name: str,
    price: float,
    spec: dict[str, str] | None = None,
    code: str | None = None,
    info: str = "",
    status: str = "active",
) -> dict[str, Any]:
    return {
        "marketId": market_id,
        "marketName": market,
        "name": name,
        "info": info,
        "price": price,
        "specifiers": spec,
        "code": code,
        "status": status,
        "tags": "v2",
    }


# --- parsing ---------------------------------------------------------------------


def test_total_side_comes_from_code_and_text_and_they_must_agree() -> None:
    over = item(623, "Liczba goli", "powyżej 4.5", 1.67, {"total": "4.5"}, "+")
    line = parse_line(over, "hockey", "1", T1, T2)
    assert line is not None
    assert (line.family, line.side, line.line, line.period) == ("total", "OVER", 4.5, 0)
    # A code that says UNDER on an outcome that reads "powyżej" is dropped,
    # never resolved in favour of either reading.
    liar = item(623, "Liczba goli", "powyżej 4.5", 1.67, {"total": "4.5"}, "-")
    assert parse_line(liar, "hockey", "1", T1, T2) is None


def test_a_side_without_a_code_is_read_from_the_text() -> None:
    # Basketball's per-team quarter totals carry code None (live 2026-09-29).
    q = item(
        200795,
        f"1. kwarta - {T2} liczba punktów",
        "poniżej 19.5",
        1.87,
        {"quarternr": "1", "total": "19.5"},
    )
    line = parse_line(q, "basketball", "1", T1, T2)
    assert line is not None
    assert (line.family, line.subject, line.period, line.side) == (
        "quarter_team_total",
        "T2",
        1,
        "UNDER",
    )


def test_a_team_market_whose_name_disagrees_with_its_id_is_dropped() -> None:
    # 658 is the first-named team's goals; a market name naming team2 under
    # that id means one of the two readings is wrong.
    wrong = item(658, f"{T2} - liczba goli", "powyżej 2.5", 1.64, {"total": "2.5"}, "+")
    assert parse_line(wrong, "hockey", "1", T1, T2) is None
    right = item(658, f"{T1} - liczba goli", "powyżej 2.5", 1.64, {"total": "2.5"}, "+")
    line = parse_line(right, "hockey", "1", T1, T2)
    assert line is not None and line.subject == "T1"


def test_handicap_uses_team1s_hcp_for_both_outcomes() -> None:
    a = item(604, "Handicap", f"{T1} (-3.5)", 5.0, {"hcp": "-3.5"}, "1")
    b = item(604, "Handicap", f"{T2} (3.5)", 1.14, {"hcp": "-3.5"}, "2")
    la, lb = (parse_line(x, "hockey", "1", T1, T2) for x in (a, b))
    assert la is not None and lb is not None
    assert (la.side, la.line, lb.side, lb.line) == ("T1", -3.5, "T2", -3.5)
    # An outcome whose own number breaks the convention is not guessed at.
    odd = item(604, "Handicap", f"{T2} (-3.5)", 1.14, {"hcp": "-3.5"}, "2")
    assert parse_line(odd, "hockey", "1", T1, T2) is None


def test_skipped_items() -> None:
    base = item(623, "Liczba goli", "powyżej 4.5", 1.67, {"total": "4.5"}, "+")
    assert parse_line({**base, "status": "block"}, "hockey", "1", T1, T2) is None
    assert parse_line({**base, "price": 1.0}, "hockey", "1", T1, T2) is None
    assert parse_line({**base, "tags": "price_boost,v2"}, "hockey", "1", T1, T2) is None
    # A three-way 1X2 (640) and a combo are not in the table.
    assert parse_line({**base, "marketId": 640}, "hockey", "1", T1, T2) is None
    assert parse_line({**base, "marketName": "A; B"}, "hockey", "1", T1, T2) is None
    # A period market without its period.
    period = item(
        649, "1. tercja - liczba goli", "Powyżej 1.5", 2.1, {"total": "1.5"}, "+"
    )
    assert parse_line(period, "hockey", "1", T1, T2) is None


def test_parse_event_keeps_only_lines_with_both_sides_quoted_once() -> None:
    items = [
        item(623, "Liczba goli", "poniżej 4.5", 2.05, {"total": "4.5"}, "-"),
        item(623, "Liczba goli", "powyżej 4.5", 1.67, {"total": "4.5"}, "+"),
        item(623, "Liczba goli", "powyżej 5.5", 2.5, {"total": "5.5"}, "+"),  # alone
        item(
            630,
            "Zwycięzca (z dogrywką i rzutami karnymi)",
            "1",
            1.33,
            None,
            "1",
            f"{T1} wygra mecz",
        ),
        item(
            630,
            "Zwycięzca (z dogrywką i rzutami karnymi)",
            "2",
            3.0,
            None,
            "2",
            f"{T2} wygra mecz",
        ),
        item(
            630,
            "Zwycięzca (z dogrywką i rzutami karnymi)",
            "2",
            3.1,
            None,
            "2",
            f"{T2} wygra mecz",
        ),  # T2 quoted twice: ambiguous pair
    ]
    lines = parse_event(items, "hockey", "1", T1, T2)
    assert sorted((ln.family, ln.side) for ln in lines) == [
        ("total", "OVER"),
        ("total", "UNDER"),
    ]


# --- results -----------------------------------------------------------------------

# HC Motor Ceske Budejovice U20 - HC Dukla Jihlava U20, 2026-09-28, AET: the
# overtime goal is in `current` and in no period, and there is no overtime key.
HOCKEY_AET = {
    "status": {"code": 110, "description": "AET", "type": "finished"},
    "winnerCode": 1,
    "homeScore": {
        "current": 4,
        "display": 4,
        "period1": 1,
        "period2": 2,
        "period3": 0,
        "normaltime": 3,
    },
    "awayScore": {
        "current": 3,
        "display": 3,
        "period1": 2,
        "period2": 0,
        "period3": 1,
        "normaltime": 3,
    },
}
# Golden State Valkyries - Dallas Wings, 2026-09-28.
BASKETBALL_ENDED = {
    "status": {"code": 100, "description": "Ended", "type": "finished"},
    "winnerCode": 1,
    "homeScore": {
        "current": 104,
        "period1": 21,
        "period2": 37,
        "period3": 27,
        "period4": 19,
        "normaltime": 104,
        "series": 1,
    },
    "awayScore": {
        "current": 80,
        "period1": 20,
        "period2": 11,
        "period3": 25,
        "period4": 24,
        "normaltime": 80,
        "series": 0,
    },
}
# USA U23 - Costa Rica U23, 2026-09-28.
VOLLEYBALL_ENDED = {
    "status": {"code": 100, "description": "Ended", "type": "finished"},
    "winnerCode": 1,
    "homeScore": {
        "current": 3,
        "period1": 25,
        "period2": 23,
        "period3": 25,
        "period4": 25,
    },
    "awayScore": {
        "current": 1,
        "period1": 16,
        "period2": 25,
        "period3": 13,
        "period4": 17,
    },
}


def test_hockey_overtime_goal_is_in_current_not_in_the_periods() -> None:
    r = build_result(HOCKEY_AET, HOCKEY, True)
    assert r is not None
    assert (r.t1_periods, r.t2_periods) == ((1, 2, 0), (2, 0, 1))
    assert (r.t1_full, r.t2_full, r.winner, r.overtime) == (4, 3, "T1", True)


def test_orientation_swaps_every_quantity() -> None:
    r = build_result(HOCKEY_AET, HOCKEY, False)
    assert r is not None
    assert (r.t1_periods, r.t1_full, r.winner) == ((2, 0, 1), 3, "T2")


def test_scores_that_do_not_add_up_are_refused() -> None:
    bad_normal = json.loads(json.dumps(BASKETBALL_ENDED))
    bad_normal["homeScore"]["normaltime"] = 103
    assert build_result(bad_normal, BASKETBALL, True) is None
    # Overtime from a score that was not level.
    uneven = json.loads(json.dumps(HOCKEY_AET))
    uneven["homeScore"]["period3"] = 1
    uneven["homeScore"]["normaltime"] = 4
    uneven["homeScore"]["current"] = 5
    assert build_result(uneven, HOCKEY, True) is None
    # A winner that contradicts the regulation score.
    liar = {**BASKETBALL_ENDED, "winnerCode": 2}
    assert build_result(liar, BASKETBALL, True) is None
    # A missing period.
    short = json.loads(json.dumps(BASKETBALL_ENDED))
    del short["homeScore"]["period4"], short["awayScore"]["period4"]
    assert build_result(short, BASKETBALL, True) is None
    # Volleyball sets won must be what Sofascore says the match score is.
    sets = json.loads(json.dumps(VOLLEYBALL_ENDED))
    sets["homeScore"]["current"] = 2
    assert build_result(sets, VOLLEYBALL, True) is None


def test_a_regulation_draw_grades_totals_but_not_the_winner() -> None:
    draw = {
        "status": {"type": "finished", "description": "Ended"},
        "winnerCode": 3,
        "homeScore": {"current": 2, "period1": 1, "period2": 1, "period3": 0},
        "awayScore": {"current": 2, "period1": 0, "period2": 1, "period3": 1},
    }
    r = build_result(draw, HOCKEY, True)
    assert r is not None and r.winner is None and not r.overtime
    winner = ShadowLine("1", 630, "winner", 0, "", None, "T1", 1.9)
    total = ShadowLine("1", 623, "total", 0, "", 3.5, "OVER", 1.9)
    assert actual_value(winner, r, HOCKEY) is None
    assert actual_value(total, r, HOCKEY) == 4.0


# Real overtime payloads from Sofascore team listings, 2026-09-29: Sofascore
# prints `overtime` separately and never as an extra period.
NHL_AP = {  # Vegas Golden Knights, event 14201583
    "status": {"type": "finished", "description": "AP"},
    "winnerCode": 1,
    "homeScore": {
        "current": 4,
        "display": 4,
        "period1": 0,
        "period2": 1,
        "period3": 2,
        "normaltime": 3,
        "overtime": 0,
        "penalties": 1,
    },
    "awayScore": {
        "current": 3,
        "display": 3,
        "period1": 1,
        "period2": 1,
        "period3": 1,
        "normaltime": 3,
        "overtime": 0,
        "penalties": 0,
    },
}
NHL_AET = {  # event 14201585
    "status": {"type": "finished", "description": "AET"},
    "winnerCode": 2,
    "homeScore": {
        "current": 2,
        "display": 2,
        "period1": 1,
        "period2": 1,
        "period3": 0,
        "normaltime": 2,
        "overtime": 0,
    },
    "awayScore": {
        "current": 3,
        "display": 3,
        "period1": 1,
        "period2": 1,
        "period3": 0,
        "normaltime": 2,
        "overtime": 1,
    },
}
WNBA_AET = {  # Golden State Valkyries, event 15953573
    "status": {"type": "finished", "description": "AET"},
    "winnerCode": 1,
    "homeScore": {
        "current": 90,
        "display": 90,
        "period1": 10,
        "period2": 27,
        "period3": 21,
        "period4": 19,
        "normaltime": 77,
        "overtime": 13,
    },
    "awayScore": {
        "current": 82,
        "display": 82,
        "period1": 24,
        "period2": 16,
        "period3": 21,
        "period4": 16,
        "normaltime": 77,
        "overtime": 5,
    },
}


def test_real_overtime_payloads() -> None:
    ap = build_result(NHL_AP, HOCKEY, True)
    assert ap is not None and ap.overtime and ap.winner == "T1"
    assert (sum(ap.t1_periods), sum(ap.t2_periods)) == (3, 3)
    aet = build_result(NHL_AET, HOCKEY, True)
    assert aet is not None and aet.overtime and aet.winner == "T2"
    wnba = build_result(WNBA_AET, BASKETBALL, True)
    assert wnba is not None and wnba.overtime and wnba.winner == "T1"
    assert (wnba.t1_full, wnba.t2_full) == (90, 82)
    # The full-game total counts overtime; Q4 does not grade after it.
    assert actual_value(line(753, "total", "OVER", 160.5), wnba, BASKETBALL) == 172.0
    assert actual_value(line(748, "h1_total", "OVER", 70.5), wnba, BASKETBALL) == 77.0
    assert (
        actual_value(
            line(788, "quarter_total", "OVER", 30.5, period=4), wnba, BASKETBALL
        )
        is None
    )


def test_current_must_equal_regulation_plus_the_printed_overtime() -> None:
    wrong = json.loads(json.dumps(WNBA_AET))
    wrong["homeScore"]["overtime"] = 12
    assert build_result(wrong, BASKETBALL, True) is None
    # Only a shootout's winner may carry the one extra goal.
    loser_plus_one = json.loads(json.dumps(NHL_AP))
    loser_plus_one["awayScore"]["current"] = 4
    loser_plus_one["homeScore"]["current"] = 3
    assert build_result(loser_plus_one, HOCKEY, True) is None
    # An overtime win whose score says the other side won.
    liar = {**WNBA_AET, "winnerCode": 2}
    assert build_result(liar, BASKETBALL, True) is None


# --- quantities and grading ---------------------------------------------------------


def line(
    market_id: int,
    family: str,
    side: str,
    value: float | None = None,
    period: int = 0,
    subject: str = "",
    odds: float = 1.9,
) -> ShadowLine:
    return ShadowLine("1", market_id, family, period, subject, value, side, odds)


def test_hockey_regulation_markets_exclude_the_overtime_goal() -> None:
    r = build_result(HOCKEY_AET, HOCKEY, True)
    assert r is not None
    assert actual_value(line(623, "total", "OVER", 6.5), r, HOCKEY) == 6.0
    assert actual_value(line(604, "handicap", "T1", -0.5), r, HOCKEY) == 0.0
    assert (
        actual_value(line(658, "team_total", "OVER", 2.5, subject="T1"), r, HOCKEY)
        == 3.0
    )
    # The winner includes overtime: team1 won it.
    assert (
        grade(
            line(630, "winner", "T1"),
            actual_value(line(630, "winner", "T1"), r, HOCKEY) or 0,
        )
        == "WIN"
    )
    # Hockey's third period is gradeable after overtime: overtime is its own period.
    assert (
        actual_value(line(649, "period_total", "OVER", 0.5, period=3), r, HOCKEY) == 1.0
    )


def test_basketball_q4_and_second_half_are_ungradeable_after_overtime() -> None:
    ot = {
        "status": {"type": "finished", "description": "AET"},
        "winnerCode": 2,
        "homeScore": {
            "current": 98,
            "period1": 20,
            "period2": 20,
            "period3": 25,
            "period4": 25,
            "normaltime": 90,
        },
        "awayScore": {
            "current": 101,
            "period1": 22,
            "period2": 18,
            "period3": 25,
            "period4": 25,
            "normaltime": 90,
        },
    }
    r = build_result(ot, BASKETBALL, True)
    assert r is not None and r.overtime
    assert actual_value(line(753, "total", "OVER", 180.5), r, BASKETBALL) == 199.0
    assert actual_value(line(748, "h1_total", "OVER", 80.5), r, BASKETBALL) == 80.0
    assert actual_value(line(233404, "h2_total", "OVER", 100.5), r, BASKETBALL) is None
    assert (
        actual_value(line(788, "quarter_total", "OVER", 40.5, period=4), r, BASKETBALL)
        is None
    )
    assert (
        actual_value(line(788, "quarter_total", "OVER", 40.5, period=3), r, BASKETBALL)
        == 50.0
    )
    # Without overtime the same lines grade.
    r2 = build_result(BASKETBALL_ENDED, BASKETBALL, True)
    assert r2 is not None
    assert actual_value(line(233404, "h2_total", "OVER", 90.5), r2, BASKETBALL) == 95.0
    assert actual_value(line(768, "handicap", "T1", -20.5), r2, BASKETBALL) == 24.0


def test_volleyball_quantities() -> None:
    r = build_result(VOLLEYBALL_ENDED, VOLLEYBALL, True)
    assert r is not None
    assert actual_value(line(230058, "sets_total", "OVER", 3.5), r, VOLLEYBALL) == 4.0
    assert actual_value(line(100082, "set_handicap", "T1", -1.5), r, VOLLEYBALL) == 2.0
    assert actual_value(line(745, "winner", "T1"), r, VOLLEYBALL) == 2.0
    assert (
        actual_value(line(230060, "points_total", "OVER", 180.5), r, VOLLEYBALL)
        == 169.0
    )
    assert (
        actual_value(
            line(782, "set_points_total", "OVER", 44.5, period=2), r, VOLLEYBALL
        )
        == 48.0
    )
    assert actual_value(line(744, "set_winner", "T2", period=2), r, VOLLEYBALL) == -2.0
    # A fifth set that was never played cannot be graded.
    assert actual_value(line(744, "set_winner", "T1", period=5), r, VOLLEYBALL) is None


def test_grade() -> None:
    assert grade(line(623, "total", "OVER", 4.5), 5) == "WIN"
    assert grade(line(623, "total", "UNDER", 4.5), 5) == "LOSS"
    assert grade(line(623, "total", "OVER", 5.0), 5) == "VOID"
    # team1 -1.5 wins by 2
    assert grade(line(604, "handicap", "T1", -1.5), 2) == "WIN"
    assert grade(line(604, "handicap", "T2", -1.5), 2) == "LOSS"
    # draw-no-bet level: stake back
    assert grade(line(662, "period_dnb", "T1", period=1), 0) == "VOID"


def test_settle_event_grades_both_sides_of_a_pair_or_neither() -> None:
    r = build_result(HOCKEY_AET, HOCKEY, True)
    assert r is not None
    snaps = [
        {
            "fetched_at_utc": "2026-09-28T15:00:00Z",
            "superbet_event_id": "9",
            "match_name": f"{T1}·{T2}",
            "team1": T1,
            "team2": T2,
            "kickoff_utc": "2026-09-28T16:00:00Z",
            "tournament": "Extraliga",
            "lines": [
                line(623, "total", "OVER", 5.5).as_dict(),
                line(623, "total", "UNDER", 5.5).as_dict(),
                line(623, "total", "OVER", 6.5).as_dict(),  # partner missing
            ],
        }
    ]
    ev = latest_pre_kickoff(snaps)["9"]
    rows, counts = settle_event(ev, r, HOCKEY)
    assert sorted((x["side"], x["outcome"]) for x in rows) == [
        ("OVER", "WIN"),
        ("UNDER", "LOSS"),
    ]
    assert counts["unpaired"] == 1
    assert rows[0]["overtime"] is True and rows[0]["fair_p"] == pytest.approx(0.5)


def test_a_price_taken_after_the_start_is_not_a_pre_match_price() -> None:
    def snap(at: str, odds: float) -> dict[str, Any]:
        ln = ShadowLine("9", 623, "total", 0, "", 5.5, "OVER", odds).as_dict()
        return {
            "fetched_at_utc": at,
            "superbet_event_id": "9",
            "match_name": "A·B",
            "team1": "A",
            "team2": "B",
            "kickoff_utc": "2026-09-28T16:00:00Z",
            "lines": [ln],
        }

    ev = latest_pre_kickoff(
        [snap("2026-09-28T15:30:00Z", 1.8), snap("2026-09-28T16:05:00Z", 3.0)]
    )["9"]
    assert [ln.odds for ln in ev.sides.values()] == [1.8]


def test_a_line_taken_down_before_the_start_is_not_graded() -> None:
    def snap(at: str, total: float) -> dict[str, Any]:
        lines = [
            ShadowLine("9", 623, "total", 0, "", total, side, 1.9).as_dict()
            for side in ("OVER", "UNDER")
        ]
        return {
            "fetched_at_utc": at,
            "superbet_event_id": "9",
            "match_name": "A·B",
            "team1": "A",
            "team2": "B",
            "kickoff_utc": "2026-09-28T16:00:00Z",
            "lines": lines,
        }

    # 08:00 the ladder is at 5.5; by 15:30 Superbet has moved it to 6.5.
    ev = latest_pre_kickoff(
        [snap("2026-09-28T08:00:00Z", 5.5), snap("2026-09-28T15:30:00Z", 6.5)]
    )["9"]
    assert {ln.line for ln in ev.sides.values()} == {6.5}
    r = build_result(HOCKEY_AET, HOCKEY, True)
    assert r is not None
    rows, _ = settle_event(ev, r, HOCKEY)
    assert {row["minutes_before_kickoff"] for row in rows} == {30}


def test_event_state() -> None:
    ko = datetime(2026, 9, 28, 16, tzinfo=UTC)
    at = ko + timedelta(hours=5)
    assert event_state(HOCKEY_AET, HOCKEY, ko, at) == "FINISHED"
    walkover = {"status": {"type": "finished", "description": "Walkover"}}
    assert event_state(walkover, HOCKEY, ko, at) == "UNUSUAL"
    # AET is not a volleyball description; anything unexpected is not graded.
    assert event_state(HOCKEY_AET, VOLLEYBALL, ko, at) == "UNUSUAL"
    late = {"status": {"type": "notstarted"}}
    assert event_state(late, HOCKEY, ko, at) == "PENDING"
    assert event_state(late, HOCKEY, ko, ko + timedelta(hours=49)) == "VOID"


# --- SHADOW (snapshot) ---------------------------------------------------------------

DATE = "2026-09-28"


class FakeSuperbet:
    def __init__(self, fail_board: bool = False, fail_event: str | None = None) -> None:
        self.fail_board, self.fail_event = fail_board, fail_event
        self.fetched: list[str] = []

    def events_by_date(
        self, start: datetime, end: datetime, offer_state: str
    ) -> list[dict]:
        if self.fail_board:
            raise RuntimeError("board down")
        assert offer_state == "prematch"
        return [
            {
                "sportId": 3,
                "eventId": 1,
                "matchName": f"{T1}·{T2}",
                "utcDate": "2026-09-28T16:00:00Z",
                "tournamentId": 7,
            },
            {
                "sportId": 3,
                "eventId": 2,
                "matchName": "A·B",
                "utcDate": "2026-09-28T10:00:00Z",
                "tournamentId": 7,
            },  # started
            {
                "sportId": 4,
                "eventId": 3,
                "matchName": "C·D",
                "utcDate": "2026-09-28T22:00:00Z",
                "tournamentId": 8,
            },  # far off
            {
                "sportId": 5,
                "eventId": 4,
                "matchName": "Legia·Lech",
                "utcDate": "2026-09-28T16:00:00Z",
                "tournamentId": 9,
            },  # football
            {
                "sportId": 157,
                "eventId": 5,
                "matchName": "E·F",
                "utcDate": "2026-09-28T16:00:00Z",
                "tournamentId": 9,
            },  # e-hockey
        ]

    def event_odds(self, event_id: str) -> dict[str, Any]:
        self.fetched.append(event_id)
        if event_id == self.fail_event:
            raise RuntimeError("event down")
        if event_id == "3":
            return {
                "odds": [
                    item(
                        753,
                        "Liczba punktów (z dogrywką)",
                        "poniżej 170.5",
                        1.85,
                        {"total": "170.5"},
                        "-",
                    ),
                    item(
                        753,
                        "Liczba punktów (z dogrywką)",
                        "powyżej 170.5",
                        1.85,
                        {"total": "170.5"},
                        "+",
                    ),
                ]
            }
        return {
            "odds": [
                item(623, "Liczba goli", "poniżej 5.5", 1.9, {"total": "5.5"}, "-"),
                item(623, "Liczba goli", "powyżej 5.5", 1.9, {"total": "5.5"}, "+"),
            ]
        }

    def _get_json(self, path: str) -> dict[str, Any]:
        return {
            "data": {"tournaments": [{"id": "7", "localNames": {"pl-PL": "Extraliga"}}]}
        }


def test_snapshot_writes_per_sport_and_ignores_other_sports(tmp_path: Path) -> None:
    sb = FakeSuperbet()
    at = datetime(2026, 9, 28, 14, tzinfo=UTC)
    result = run_shadow.snapshot(DATE, sb, str(tmp_path), at=at)  # type: ignore[arg-type]
    assert result["verdict"] == "OK"
    assert result["metrics"]["hockey"]["started"] == 1
    assert result["metrics"]["hockey"]["events_with_lines"] == 1
    # First sight of an event outside the horizon is still recorded, once.
    assert result["metrics"]["basketball"]["events_with_lines"] == 1
    assert sorted(sb.fetched) == ["1", "3"]
    hockey = tmp_path / "shadow" / "hockey" / DATE / "snapshots.jsonl"
    (rec,) = [json.loads(x) for x in hockey.read_text().splitlines()]
    assert rec["tournament"] == "Extraliga" and len(rec["lines"]) == 2
    # Second run: the far-off basketball game is not re-asked; hockey is.
    sb2 = FakeSuperbet()
    again = run_shadow.snapshot(DATE, sb2, str(tmp_path), at=at)  # type: ignore[arg-type]
    assert sb2.fetched == ["1"]
    assert again["metrics"]["basketball"]["out_of_horizon"] == 1
    assert len(hockey.read_text().splitlines()) == 2
    assert not (tmp_path / DATE).exists(), "never writes into the day's directory"


def test_next_days_early_games_are_snapshotted_into_that_day(tmp_path: Path) -> None:
    class LateGames(FakeSuperbet):
        def events_by_date(
            self, start: datetime, end: datetime, offer_state: str
        ) -> list[dict]:
            # The window must reach past midnight by the horizon.
            assert end - start == timedelta(days=1, hours=3)
            return [
                {
                    "sportId": 3,
                    "eventId": 1,
                    "matchName": f"{T1}·{T2}",
                    "utcDate": "2026-09-29T01:00:00Z",
                    "tournamentId": 7,
                },  # in horizon
                {
                    "sportId": 3,
                    "eventId": 6,
                    "matchName": "G·H",
                    "utcDate": "2026-09-29T09:00:00Z",
                    "tournamentId": 7,
                },  # too far
            ]

    sb = LateGames()
    at = datetime(2026, 9, 28, 23, tzinfo=UTC)
    result = run_shadow.snapshot(DATE, sb, str(tmp_path), at=at)  # type: ignore[arg-type]
    assert sb.fetched == ["1"]
    assert result["metrics"]["hockey"]["next_day_events_with_lines"] == 1
    assert result["metrics"]["hockey"]["events_on_board"] == 0
    nxt = tmp_path / "shadow" / "hockey" / "2026-09-29" / "snapshots.jsonl"
    assert json.loads(nxt.read_text())["superbet_event_id"] == "1"
    assert not (tmp_path / "shadow" / "hockey" / DATE / "snapshots.jsonl").exists()


def test_snapshot_verdicts(tmp_path: Path) -> None:
    at = datetime(2026, 9, 28, 14, tzinfo=UTC)
    partial = run_shadow.snapshot(
        DATE, FakeSuperbet(fail_event="1"), str(tmp_path), at=at
    )  # type: ignore[arg-type]
    assert partial["verdict"] == "PARTIAL"
    failed = run_shadow.snapshot(
        DATE, FakeSuperbet(fail_board=True), str(tmp_path), at=at
    )  # type: ignore[arg-type]
    assert failed["verdict"] == "FAILED"


# --- SHADOW_SETTLE --------------------------------------------------------------------


def sofa_event(
    home: str = T1, away: str = T2, status: dict | None = None
) -> dict[str, Any]:
    return {
        "id": 700,
        "startTimestamp": int(datetime(2026, 9, 28, 16, tzinfo=UTC).timestamp()),
        "homeTeam": {"name": home},
        "awayTeam": {"name": away},
        "tournament": {"name": "Extraliga"},
        **(status or {}),
    }


class FakeResolver:
    def __init__(
        self,
        event: dict[str, Any] | None,
        ambiguous: bool = False,
        breaker: bool = False,
    ) -> None:
        self.event, self.ambiguous, self.breaker = event, ambiguous, breaker
        self.calls: list[tuple[str, str]] = []

    def resolve_entity(
        self,
        sport: str,
        side: str,
        kickoff: datetime,
        opponent: str,
        *,
        board_side_a: str = "",
        board_side_b: str = "",
        record_miss: bool = True,
        check_orientation: bool = True,
    ) -> tuple:
        if self.breaker:
            raise CircuitOpenError("open")
        self.calls.append((sport, side))
        assert (board_side_a, board_side_b) == (T1, T2)
        # Settle looks up one game, not the team: it must never record a miss.
        assert record_miss is False
        # ...and reads the orientation itself, so a reversed listing is kept.
        assert check_orientation is False
        return (
            (1, self.event, self.ambiguous)
            if not self.ambiguous
            else (None, None, True)
        )


class FakeClient:
    def __init__(self, detail: dict[str, Any]) -> None:
        self.detail = detail
        self.asked: list[int] = []

    def event(self, eid: int) -> dict[str, Any]:
        self.asked.append(eid)
        return {"event": self.detail}


def write_snapshot(tmp_path: Path) -> None:
    lines = [
        line(623, "total", "OVER", 5.5).as_dict(),
        line(623, "total", "UNDER", 5.5).as_dict(),
        line(630, "winner", "T1").as_dict(),
        line(630, "winner", "T2").as_dict(),
    ]
    day = tmp_path / "shadow" / "hockey" / DATE
    day.mkdir(parents=True)
    (day / "snapshots.jsonl").write_text(
        json.dumps(
            {
                "fetched_at_utc": "2026-09-28T15:00:00Z",
                "superbet_event_id": "1",
                "match_name": f"{T1}·{T2}",
                "team1": T1,
                "team2": T2,
                "kickoff_utc": "2026-09-28T16:00:00Z",
                "tournament": "Extraliga",
                "lines": lines,
            }
        )
        + "\n"
    )


def run_settle(tmp_path: Path, resolver: Any, client: Any, hours_after: float) -> dict:
    at = datetime(2026, 9, 28, 16, tzinfo=UTC) + timedelta(hours=hours_after)
    return settle_shadow.settle(
        DATE, resolver, client, None, str(tmp_path), at, ("hockey",)
    )


def settled(tmp_path: Path) -> dict[str, Any]:
    path = tmp_path / "shadow" / "hockey" / DATE / "settled.json"
    return dict(json.loads(path.read_text())["events"])


def test_settle_grades_a_game_end_to_end(tmp_path: Path) -> None:
    write_snapshot(tmp_path)
    resolver = FakeResolver(sofa_event())
    client = FakeClient({**sofa_event(), **HOCKEY_AET})
    result = run_settle(tmp_path, resolver, client, 6)
    assert result["verdict"] == "OK"
    rec = settled(tmp_path)["1"]
    assert rec["state"] == "SETTLED" and rec["overtime"] is True
    assert resolver.calls == [("ice-hockey", T1)]
    assert client.asked == [700]
    outcomes = {(g["family"], g["side"]): g["outcome"] for g in rec["graded"]}
    # Regulation 3-3 -> 6 goals over 5.5; team1 won in overtime.
    assert outcomes == {
        ("total", "OVER"): "WIN",
        ("total", "UNDER"): "LOSS",
        ("winner", "T1"): "WIN",
        ("winner", "T2"): "LOSS",
    }
    # Settled is terminal: a rerun asks nothing.
    resolver2 = FakeResolver(sofa_event())
    again = run_settle(tmp_path, resolver2, FakeClient({}), 30)
    assert again["metrics"]["hockey"]["metrics"]["kept"] == 1 and resolver2.calls == []


def test_reversed_listing_is_graded_from_team1s_side(tmp_path: Path) -> None:
    write_snapshot(tmp_path)
    reversed_event = sofa_event(home=T2, away=T1)
    run_settle(
        tmp_path,
        FakeResolver(reversed_event),
        FakeClient({**reversed_event, **HOCKEY_AET}),
        6,
    )
    rec = settled(tmp_path)["1"]
    assert rec["home_is_team1"] is False
    # Home (team2 here) won in overtime.
    outcomes = {(g["family"], g["side"]): g["outcome"] for g in rec["graded"]}
    assert outcomes[("winner", "T2")] == "WIN"


def test_settle_states(tmp_path: Path) -> None:
    write_snapshot(tmp_path)
    assert (
        run_settle(tmp_path, FakeResolver(None), FakeClient({}), 1)["metrics"][
            "hockey"
        ]["metrics"]["too_early"]
        == 1
    )
    missing = run_settle(tmp_path, FakeResolver(None), FakeClient({}), 6)
    assert settled(tmp_path)["1"]["state"] == "NOT_ON_SOFASCORE"
    # Every game tried, none graded: not a clean day.
    assert missing["verdict"] == "PARTIAL"
    run_settle(tmp_path, FakeResolver(None, ambiguous=True), FakeClient({}), 6)
    assert settled(tmp_path)["1"]["state"] == "AMBIGUOUS"
    running = {**sofa_event(), "status": {"type": "inprogress", "description": "3rd"}}
    run_settle(tmp_path, FakeResolver(sofa_event()), FakeClient(running), 6)
    assert settled(tmp_path)["1"]["state"] == "PENDING"
    broken = json.loads(json.dumps({**sofa_event(), **HOCKEY_AET}))
    broken["homeScore"]["normaltime"] = 2
    run_settle(tmp_path, FakeResolver(sofa_event()), FakeClient(broken), 6)
    assert settled(tmp_path)["1"]["state"] == "DATA_MISMATCH"
    # Retryable for a week, then ours to give up on - never Superbet's void.
    run_settle(tmp_path, FakeResolver(None), FakeClient({}), 24 * 8)
    rec = settled(tmp_path)["1"]
    assert rec["state"] == "GAVE_UP" and rec["gave_up_on"] == "NOT_ON_SOFASCORE"


def test_a_name_that_reads_both_ways_grades_only_the_totals(tmp_path: Path) -> None:
    write_snapshot(tmp_path)
    same = sofa_event(home="X", away="X")
    run_settle(tmp_path, FakeResolver(same), FakeClient({**same, **HOCKEY_AET}), 6)
    rec = settled(tmp_path)["1"]
    # The total does not care which side is team1; the winner does.
    assert rec["state"] == "SETTLED" and rec["orientation_unclear"] is True
    assert {g["family"] for g in rec["graded"]} == {"total"}
    assert rec["needs_orientation"] == 2


def test_home_is_team1_needs_a_clear_margin() -> None:
    event = sofa_event(home="Dynamo Moskva", away="Dinamo Minsk")
    assert settle_shadow.home_is_team1(event, "Dynamo Moskva", "Dinamo Minsk") is True
    assert settle_shadow.home_is_team1(event, "Dinamo Minsk", "Dynamo Moskva") is False
    # Each board name sits inside both Sofascore names: no reading wins clearly.
    near = sofa_event(home="Lions Tigers", away="Tigers Lions")
    assert settle_shadow.home_is_team1(near, "Lions", "Tigers") is None


def test_an_ambiguous_team1_still_lets_team2_resolve(tmp_path: Path) -> None:
    class HalfAmbiguous(FakeResolver):
        def resolve_entity(self, sport: str, side: str, *a: Any, **k: Any) -> tuple:
            super().resolve_entity(sport, side, *a, **k)
            return (None, None, True) if side == T1 else (1, self.event, False)

    write_snapshot(tmp_path)
    resolver = HalfAmbiguous(sofa_event())
    run_settle(tmp_path, resolver, FakeClient({**sofa_event(), **HOCKEY_AET}), 6)
    assert [side for _, side in resolver.calls] == [T1, T2]
    assert settled(tmp_path)["1"]["state"] == "SETTLED"


def test_an_open_breaker_fails_the_stage_without_writing_a_grade(
    tmp_path: Path,
) -> None:
    write_snapshot(tmp_path)
    result = run_settle(tmp_path, FakeResolver(None, breaker=True), FakeClient({}), 6)
    assert result["verdict"] == "FAILED"
    assert settled(tmp_path) == {}


def test_no_snapshots_anywhere_is_failed_one_quiet_sport_is_not(tmp_path: Path) -> None:
    at = datetime(2026, 9, 28, 22, tzinfo=UTC)
    empty = settle_shadow.settle(
        DATE, FakeResolver(None), FakeClient({}), None, str(tmp_path), at
    )  # type: ignore[arg-type]
    assert empty["verdict"] == "FAILED"
    write_snapshot(tmp_path)
    one = settle_shadow.settle(  # type: ignore[arg-type]
        DATE,
        FakeResolver(sofa_event()),
        FakeClient({**sofa_event(), **HOCKEY_AET}),
        None,
        str(tmp_path),
        at,
    )
    assert one["verdict"] == "OK"
    assert one["metrics"]["volleyball"]["verdict"] == "NO_SNAPSHOTS"


# --- audit, pipeline, daily loop ----------------------------------------------------


def test_audit_reports_the_settled_game(tmp_path: Path) -> None:
    write_snapshot(tmp_path)
    run_settle(
        tmp_path,
        FakeResolver(sofa_event()),
        FakeClient({**sofa_event(), **HOCKEY_AET}),
        6,
    )
    text = "\n".join(
        audit_shadow.render(str(tmp_path), ["hockey", "basketball"], DATE, DATE)
    )
    assert "games: 1  SETTLED 1" in text
    # One side per line in section 2, so a line is one row there.
    assert "| total | 1 | 1 |" in text and "| winner | 1 | 1 |" in text
    assert "### 2b. fixed side" in text
    assert "## basketball" in text and "no settled game in range" in text
    # Priced at 15:00 for a 16:00 start: the fresh half of the price-age split.
    assert "| <= 60 min | 1 | 2 |" in text


def _pair(eid: int, fav_wins: bool, side_a: str = "T1") -> list[dict[str, Any]]:
    side_b = PARTNER[side_a]
    fav, dog = 1.5, 2.6
    return [
        {
            "superbet_event_id": str(eid),
            "family": "winner",
            "market_id": 630,
            "period": 0,
            "subject": "",
            "line": None,
            "side": side,
            "odds": odds,
            "partner_odds": partner,
            "fair_p": fair_probability(odds, partner),
            "outcome": "WIN" if won else "LOSS",
        }
        for side, odds, partner, won in (
            (side_a, fav, dog, fav_wins),
            (side_b, dog, fav, not fav_wins),
        )
    ]


def test_pooling_both_sides_hides_the_gap_one_side_per_line_shows_it() -> None:
    # 100 lines whose favourite (fair p ~0.63) won 90 times.
    rows = [r for i in range(100) for r in _pair(i, i < 90)]
    pooled = summarize(rows, "x")
    assert pooled is not None
    assert pooled.fair_p == pytest.approx(0.5) and pooled.hit == pytest.approx(0.5)
    fav = summarize(one_side_per_line(rows, "favourite"), "x")
    assert fav is not None and fav.sides == 100
    assert fav.hit == pytest.approx(0.9) and fav.hit - fav.fair_p > 0.2
    # The fixed side is T1 whatever its price: here T1 is the favourite.
    fixed = one_side_per_line(rows, "fixed")
    assert len(fixed) == 100 and {r["side"] for r in fixed} == {"T1"}
    # A total's fixed side is OVER even when UNDER is listed first.
    total = [
        dict(r, family="total", side=s)
        for r, s in zip(_pair(1, True), ("UNDER", "OVER"), strict=True)
    ]
    assert [r["side"] for r in one_side_per_line(total, "fixed")] == ["OVER"]


def test_audit_counts_a_game_rescheduled_across_midnight_once(tmp_path: Path) -> None:
    for day, state in (("2026-09-28", "PENDING"), ("2026-09-29", "SETTLED")):
        d = tmp_path / "shadow" / "hockey" / day
        d.mkdir(parents=True)
        (d / "settled.json").write_text(
            json.dumps({"events": {"9": {"state": state, "graded": []}}})
        )
    events = audit_shadow.load(str(tmp_path), "hockey", "2026-09-28", "2026-09-29")
    assert [e["state"] for e in events] == ["SETTLED"]


def test_stages_are_registered_and_never_in_the_daily_sequence() -> None:
    assert run_pipeline.STAGE_MODULES["SHADOW"] == "scripts.sofa.run_shadow"
    assert run_pipeline.STAGE_MODULES["SHADOW_SETTLE"] == "scripts.sofa.settle_shadow"
    daily = {stage for stage, _ in run_pipeline.DEFAULT_SEQUENCE}
    assert not daily & {"SHADOW", "SHADOW_SETTLE"}


def test_daily_plan() -> None:
    snapshot, morning, audit = shadow_daily.plan(DATE)
    assert snapshot[-2:] == ["--only", "SHADOW"]
    # The day, then the day before once more for its pending games.
    assert morning[:2] == [
        ["scripts/sofa/run_pipeline.py", "--date", DATE, "--only", "SHADOW_SETTLE"],
        [
            "scripts/sofa/run_pipeline.py",
            "--date",
            "2026-09-27",
            "--only",
            "SHADOW_SETTLE",
        ],
    ]
    # then each settled day's experimental coupons, after every settle
    assert [(c[0], c[2], c[-1]) for c in morning[2:-1]] == [
        ("scripts/sofa/settle_sport_coupon.py", d, sp)
        for d in (DATE, "2026-09-27")
        for sp in ("hockey", "basketball", "volleyball")
    ]
    # and last, the ledger for both settled days
    assert morning[-1] == [
        "scripts/sofa/record_results.py", "--from", "2026-09-27", "--to", DATE
    ]
    assert audit[0] == "scripts/sofa/audit_shadow.py"
    # On the first shadow day there is nothing before it to retry.
    _, first_day, _ = shadow_daily.plan(DATE, retry_before=False)
    assert {cmd[2] for cmd in first_day} == {DATE}


def test_has_snapshots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shadow_daily, "state_dir", lambda: tmp_path / "shadow")
    assert shadow_daily.has_snapshots(DATE) is False
    write_snapshot(tmp_path)
    assert shadow_daily.has_snapshots(DATE) is True


def test_market_tables_only_name_known_scopes() -> None:
    from bet.sofa.shadow import MARKETS

    for sport, table in MARKETS.items():
        for spec in table.values():
            assert spec.scope in ("full", "reg", "period", "h1", "h2", "sets")
            assert (spec.scope == "period") == (spec.period_key is not None)
            if spec.team is not None:
                assert spec.kind in ("team_total", "odd_even")
            if spec.kind == "team_total":
                assert spec.team is not None
            if spec.kind == "yes_no":
                assert sport == "volleyball" and spec.scope == "period"
            if spec.kind == "exact":
                assert spec.scope == "sets"
            if spec.scope in ("h1", "h2"):
                assert sport == "basketball"
            if spec.scope == "reg":
                assert SPORTS[sport].regulation_periods is not None


# --- RESOLVE's gates for the shadow sports ------------------------------------------


def _resolver() -> Any:
    from bet.sofa.config import SofaConfig
    from bet.sofa.resolve import SofaResolver

    return SofaResolver(SofaConfig(), None, None)  # type: ignore[arg-type]


def _womens_basketball_event() -> dict[str, Any]:
    return {
        "id": 17185011,
        "startTimestamp": int(datetime(2026, 9, 28, 2, tzinfo=UTC).timestamp()),
        "homeTeam": {"name": "Golden State Valkyries", "gender": "F"},
        "awayTeam": {"name": "Dallas Wings", "gender": "F"},
        "tournament": {"name": "WNBA", "category": {"name": "USA"}},
    }


@pytest.mark.parametrize("sport", ["basketball", "volleyball", "ice-hockey"])
def test_the_gender_gate_applies_to_every_team_sport(sport: str) -> None:
    ko = datetime(2026, 9, 28, 2, tzinfo=UTC)
    resolver = _resolver()
    womens = _womens_basketball_event()
    # Superbet's (K) side against Sofascore's women's teams: accepted.
    assert (
        resolver.match_quality(
            womens,
            ko,
            "dallas wings",
            sport=sport,
            superbet_side_a="Golden State Valkyries (K)",
            superbet_side_b="Dallas Wings (K)",
        )
        is not None
    )
    # The men's board name against the women's event: refused.
    assert (
        resolver.match_quality(
            womens,
            ko,
            "dallas wings",
            sport=sport,
            superbet_side_a="Golden State Valkyries",
            superbet_side_b="Dallas Wings",
        )
        is None
    )


def test_team_sports_match_within_six_hours_not_a_day() -> None:
    from bet.sofa.resolve import MATCH_WINDOW_S

    for slug in ("ice-hockey", "basketball", "volleyball"):
        assert MATCH_WINDOW_S[slug] == 6 * 3600
    # The same two hockey sides the next evening are a different game.
    event = _womens_basketball_event()
    tomorrow = datetime(2026, 9, 29, 2, tzinfo=UTC)
    assert (
        _resolver().match_quality(event, tomorrow, "dallas wings", sport="basketball")
        is None
    )


def test_the_shadow_sports_map_to_real_sofascore_slugs() -> None:
    assert {s.sofascore_slug for s in SPORTS.values()} == {
        "ice-hockey",
        "basketball",
        "volleyball",
    }
    # 157 / 70 are e-hockey / e-basketball on Superbet: simulations, never read.
    assert {s.superbet_id for s in SPORTS.values()} == {3, 4, 1}


def test_measure_mlb_asks_for_baseball_not_hockey() -> None:
    from bet.sofa.shadow import SPORT_BY_SUPERBET_ID
    from scripts.sofa.measure_mlb import BASEBALL_SPORT_ID

    # 3 is Superbet's ice hockey (checked 2026-09-29), which the script used to
    # measure under baseball's name.
    assert BASEBALL_SPORT_ID == 20
    assert SPORT_BY_SUPERBET_ID[3].key == "hockey"


def test_a_shootout_is_overtime_whether_or_not_current_counts_its_goal() -> None:
    base = {
        "status": {"type": "finished", "description": "AP"},
        "winnerCode": 2,
        "homeScore": {"period1": 1, "period2": 1, "period3": 0, "normaltime": 2},
        "awayScore": {"period1": 0, "period2": 1, "period3": 1, "normaltime": 2},
    }
    counted = json.loads(json.dumps(base))
    counted["homeScore"]["current"], counted["awayScore"]["current"] = 2, 3
    level = json.loads(json.dumps(base))
    level["homeScore"]["current"], level["awayScore"]["current"] = 2, 2
    for detail in (counted, level):
        r = build_result(detail, HOCKEY, True)
        assert r is not None and r.overtime and r.winner == "T2"
        # Regulation total is 4 either way; the winner comes from winnerCode.
        assert actual_value(line(623, "total", "OVER", 3.5), r, HOCKEY) == 4.0
        assert actual_value(line(630, "winner", "T2"), r, HOCKEY) == -1.0


# --- 2026-09-29 audit: fixes ------------------------------------------------------


def _snap(fetched: str, total_odds: float) -> dict[str, Any]:
    return {
        "fetched_at_utc": fetched,
        "superbet_event_id": "1",
        "match_name": f"{T1}·{T2}",
        "team1": T1,
        "team2": T2,
        "kickoff_utc": "2026-09-28T16:00:00Z",
        "tournament": "Extraliga",
        "lines": [
            line(623, "total", "OVER", 5.5, odds=total_odds).as_dict(),
            line(623, "total", "UNDER", 5.5, odds=total_odds).as_dict(),
        ],
    }


def _write_snaps(tmp_path: Path, snaps: list[dict[str, Any]]) -> None:
    day = tmp_path / "shadow" / "hockey" / DATE
    day.mkdir(parents=True, exist_ok=True)
    (day / "snapshots.jsonl").write_text("".join(json.dumps(s) + "\n" for s in snaps))


def _started_at(hour: int, minute: int) -> dict[str, Any]:
    return {
        **sofa_event(),
        "startTimestamp": int(
            datetime(2026, 9, 28, hour, minute, tzinfo=UTC).timestamp()
        ),
    }


def test_a_game_that_began_before_superbets_time_is_graded_at_the_earlier_price(
    tmp_path: Path,
) -> None:
    # Superbet said 16:00, Sofascore says it began 15:30: the 15:50 quote was
    # taken in play, so the 15:00 one is the pre-match price (football's
    # earlier-of-two-clocks rule).
    _write_snaps(
        tmp_path,
        [_snap("2026-09-28T15:00:00Z", 1.90), _snap("2026-09-28T15:50:00Z", 1.40)],
    )
    early = _started_at(15, 30)
    run_settle(tmp_path, FakeResolver(early), FakeClient({**early, **HOCKEY_AET}), 6)
    rec = settled(tmp_path)["1"]
    assert rec["state"] == "SETTLED"
    assert {g["odds"] for g in rec["graded"]} == {1.90}
    assert rec["started_before_superbet_min"] == 30
    assert rec["sofascore_start_utc"] == "2026-09-28T15:30:00Z"
    # The price's age runs to the real start (15:30), not Superbet's 16:00.
    assert {g["minutes_before_kickoff"] for g in rec["graded"]} == {30}
    assert rec["priced_sides_superbet_clock"] == 2 and rec["priced_sides"] == 2


def test_the_earlier_snapshot_may_hold_more_sides_than_the_later(
    tmp_path: Path,
) -> None:
    richer = _snap("2026-09-28T15:00:00Z", 1.90)
    richer["lines"] += [
        line(623, "total", "OVER", 6.5).as_dict(),
        line(623, "total", "UNDER", 6.5).as_dict(),
    ]
    _write_snaps(tmp_path, [richer, _snap("2026-09-28T15:50:00Z", 1.40)])
    early = _started_at(15, 30)
    run_settle(tmp_path, FakeResolver(early), FakeClient({**early, **HOCKEY_AET}), 6)
    rec = settled(tmp_path)["1"]
    assert rec["priced_sides_superbet_clock"] == 2 and rec["priced_sides"] == 4
    assert "in_play_sides_dropped" not in rec


def test_a_postponed_game_with_an_early_start_stays_pending(tmp_path: Path) -> None:
    # NO_PRE_START_PRICE is final, so it is only decided for a finished game.
    _write_snaps(tmp_path, [_snap("2026-09-28T15:50:00Z", 1.40)])
    early = {
        **_started_at(15, 30),
        "status": {"code": 60, "description": "Postponed", "type": "postponed"},
    }
    run_settle(tmp_path, FakeResolver(early), FakeClient(early), 6)
    assert settled(tmp_path)["1"]["state"] == "PENDING"


def test_every_price_taken_in_play_is_no_pre_start_price_and_final(
    tmp_path: Path,
) -> None:
    _write_snaps(tmp_path, [_snap("2026-09-28T15:50:00Z", 1.40)])
    early = _started_at(15, 30)
    client = FakeClient({**early, **HOCKEY_AET})
    run_settle(tmp_path, FakeResolver(early), client, 6)
    assert settled(tmp_path)["1"]["state"] == "NO_PRE_START_PRICE"
    # A fact about the game: not asked again.
    run_settle(tmp_path, FakeResolver(early), client, 7)
    assert client.asked == [700]


def test_latest_pre_kickoff_takes_the_earlier_clock() -> None:
    snaps = [_snap("2026-09-28T15:00:00Z", 1.90), _snap("2026-09-28T15:50:00Z", 1.40)]
    assert latest_pre_kickoff(snaps)["1"].sides  # Superbet's clock alone: 15:50
    later = latest_pre_kickoff(snaps)["1"]
    assert {ln.odds for ln in later.sides.values()} == {1.40}
    start = {"1": datetime(2026, 9, 28, 15, 30, tzinfo=UTC)}
    early = latest_pre_kickoff(snaps, start)["1"]
    assert {ln.odds for ln in early.sides.values()} == {1.90}
    # A Sofascore start after Superbet's changes nothing.
    late = {"1": datetime(2026, 9, 28, 17, tzinfo=UTC)}
    assert {ln.odds for ln in latest_pre_kickoff(snaps, late)["1"].sides.values()} == {
        1.40
    }


class EmptyClient(FakeClient):
    def event(self, eid: int) -> dict[str, Any]:
        self.asked.append(eid)
        return {}


def test_no_event_payload_is_an_error_never_the_listings_score(tmp_path: Path) -> None:
    write_snapshot(tmp_path)
    # The listing carries a finished score; /event answered nothing.
    listing = {**sofa_event(), **HOCKEY_AET}
    result = run_settle(tmp_path, FakeResolver(listing), EmptyClient({}), 6)
    rec = settled(tmp_path)["1"]
    assert rec["state"] == "ERROR" and "graded" not in rec
    assert result["verdict"] == "PARTIAL"
    assert result["metrics"]["hockey"]["metrics"]["errors"] == 1


def test_settled_now_counts_this_run_not_the_file(tmp_path: Path) -> None:
    write_snapshot(tmp_path)
    client = FakeClient({**sofa_event(), **HOCKEY_AET})
    run_settle(tmp_path, FakeResolver(sofa_event()), client, 6)
    again = run_settle(tmp_path, FakeResolver(sofa_event()), client, 7)
    m = again["metrics"]["hockey"]["metrics"]
    assert m["kept"] == 1 and m["settled_now"] == 0


def test_home_is_team1_survives_a_null_name() -> None:
    event = {"homeTeam": {"name": None}, "awayTeam": {"name": T2}}
    assert settle_shadow.home_is_team1(event, T1, T2) is None


def test_the_real_resolver_keeps_a_reversed_listing_only_when_asked() -> None:
    # RESOLVE (football) refuses a reversal - it would price the wrong team's
    # sample. SHADOW_SETTLE reads the orientation itself and must still find
    # the game, or a reversed game could never be graded (it was, before).
    ko = datetime(2026, 9, 28, 16, tzinfo=UTC)
    reversed_event = {
        "id": 1,
        "startTimestamp": int(ko.timestamp()),
        "homeTeam": {"name": T2},
        "awayTeam": {"name": T1},
        "tournament": {"name": "Extraliga", "category": {"name": "Czech Republic"}},
    }
    resolver = _resolver()
    kwargs: dict[str, Any] = {
        "sport": "ice-hockey",
        "superbet_side_a": T1,
        "superbet_side_b": T2,
    }
    opponent = settle_shadow.normalize_name(T2)
    assert resolver.match_quality(reversed_event, ko, opponent, **kwargs) is None
    assert (
        resolver.match_quality(
            reversed_event, ko, opponent, check_orientation=False, **kwargs
        )
        is not None
    )
    assert settle_shadow.home_is_team1(reversed_event, T1, T2) is False


def test_shadow_sports_read_one_page_of_past_games_only() -> None:
    from bet.sofa.resolve import (
        DEFAULT_LISTING_PAGES,
        LISTING_KINDS_BY_SPORT,
        LISTING_PAGES_BY_SPORT,
    )

    for slug in ("ice-hockey", "basketball", "volleyball"):
        assert LISTING_KINDS_BY_SPORT[slug] == ("last",)
        assert LISTING_PAGES_BY_SPORT[slug] == 1
    # Football and tennis unchanged.
    assert LISTING_KINDS_BY_SPORT["football"] == ("next", "last")
    assert LISTING_KINDS_BY_SPORT["tennis"] == ("last",)
    assert "football" not in LISTING_PAGES_BY_SPORT and DEFAULT_LISTING_PAGES == 3


def test_a_second_daily_loop_for_the_same_day_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os
    import subprocess
    import sys

    def fake_loop(date: str) -> subprocess.Popen[bytes]:
        # A live process whose command line reads like the loop's.
        return subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import time; time.sleep(30)",
                "scripts/sofa/shadow_daily.py",
                "--date",
                date,
            ]
        )

    pid_file = tmp_path / "daily.pid"
    assert shadow_daily.already_running(pid_file) is None  # no file
    pid_file.write_text("not a pid")
    assert shadow_daily.already_running(pid_file) is None
    pid_file.write_text(str(os.getpid()))
    assert shadow_daily.already_running(pid_file) is None  # ourselves
    live = fake_loop(DATE)
    other = subprocess.Popen(["sleep", "30"])
    try:
        pid_file.write_text(str(live.pid))
        assert shadow_daily.already_running(pid_file, DATE) == live.pid
        # The same loop's pid, but another day's file: not this day's loop.
        assert shadow_daily.already_running(pid_file, "2026-10-01") is None
        # A recycled pid of an unrelated process does not block (P1).
        pid_file.write_text(str(other.pid))
        assert shadow_daily.already_running(pid_file, DATE) is None
    finally:
        for proc in (live, other):
            proc.kill()
            proc.wait()
    pid_file.write_text(str(live.pid))
    assert shadow_daily.already_running(pid_file) is None  # dead pid

    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(shadow_daily, "REPO", Path("/"))
    state = shadow_daily.state_dir()
    state.mkdir(parents=True)
    blocker = fake_loop(DATE)
    try:
        (state / f"daily_{DATE}.pid").write_text(str(blocker.pid))
        monkeypatch.setattr("sys.argv", ["shadow_daily", "--date", DATE])
        called: list[Any] = []
        monkeypatch.setattr(shadow_daily, "loop", lambda *a, **k: called.append(a))
        assert shadow_daily.main() == 2 and not called
        assert (state / f"daily_{DATE}.pid").read_text() == str(blocker.pid)
    finally:
        blocker.kill()
        blocker.wait()


def test_each_snapshot_record_is_stamped_when_its_event_was_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ticks = iter(datetime(2026, 9, 28, 14, m, tzinfo=UTC) for m in range(0, 59))
    monkeypatch.setattr(run_shadow, "now", lambda: next(ticks))
    run_shadow.snapshot(DATE, FakeSuperbet(), str(tmp_path))  # type: ignore[arg-type]
    stamps = [
        json.loads(x)["fetched_at_utc"]
        for p in sorted((tmp_path / "shadow").glob("*/*/snapshots.jsonl"))
        for x in p.read_text().splitlines()
    ]
    assert stamps and len(set(stamps)) == len(stamps)
    assert all(s > "2026-09-28T14:00:00Z" for s in stamps)


def test_chain_starts_the_next_day_only_when_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(shadow_daily, "REPO", Path("/"))
    def fake_loop(*a: object, after_snapshots: object = None, **k: object) -> int:
        # cs2_daily.loop's contract: the hook runs once when the snapshots
        # end, and its failure is logged, never raised.
        if callable(after_snapshots):
            try:
                after_snapshots()
            except Exception:  # noqa: BLE001
                pass
        return 0

    monkeypatch.setattr(shadow_daily, "loop", fake_loop)
    spawned: list[str] = []

    def spawn(date: str) -> int:
        spawned.append(date)
        return 1

    monkeypatch.setattr("sys.argv", ["shadow_daily", "--date", DATE])
    assert shadow_daily.main(spawn) == 0 and spawned == []
    monkeypatch.setattr("sys.argv", ["shadow_daily", "--date", DATE, "--chain"])
    assert shadow_daily.main(spawn) == 0 and spawned == [DATE]
    assert shadow_daily.next_day("2026-09-30") == "2026-10-01"
    # The loop is over: its pid file is gone, so it blocks nothing.
    assert not (shadow_daily.state_dir() / f"daily_{DATE}.pid").exists()
    done = json.loads((shadow_daily.state_dir() / f"daily_{DATE}.done").read_text())
    assert done["exit"] == 0

    def broken(date: str) -> int:
        raise OSError("no fork")

    # A failed chain never changes the day's own exit code.
    assert shadow_daily.main(broken) == 0


def test_spawn_next_day_is_detached_into_its_own_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(shadow_daily, "REPO", tmp_path)
    monkeypatch.setattr(shadow_daily, "PYTHON", "echo")
    shadow_daily.state_dir().mkdir(parents=True)
    pid = shadow_daily.spawn_next_day(DATE)
    os.waitpid(pid, 0)
    log = (shadow_daily.state_dir() / "daily_2026-09-29.log").read_text()
    assert "scripts/sofa/shadow_daily.py --date 2026-09-29 --chain" in log


class _NullCache:
    def get_entity_miss(self, *a: Any) -> bool:
        return False

    def get_entity(self, *a: Any) -> None:
        return None

    def get_entity_events(self, *a: Any) -> None:
        return None

    def get_listing_miss(self, *a: Any) -> bool:
        return False

    def __getattr__(self, name: str) -> Any:  # every save_* is a no-op
        return lambda *a, **k: None


class _SearchClient:
    def __init__(self, listing: dict[str, Any]) -> None:
        self.searches: list[tuple[str, str | None]] = []
        self.listings: list[tuple[int, str, int]] = []
        self.listing = listing

    def search(self, q: str, sport: str | None = None) -> dict[str, Any]:
        self.searches.append((q, sport))
        slug = sport or "football"
        return {
            "results": [
                {
                    "type": "team",
                    "entity": {"id": 5, "name": "Hamar", "sport": {"slug": slug}},
                }
            ]
        }

    def entity_events(self, eid: int, kind: str, page: int) -> dict[str, Any]:
        self.listings.append((eid, kind, page))
        return {"events": [self.listing], "hasNextPage": True}


def _hamar_game(ko: datetime) -> dict[str, Any]:
    return {
        "id": 42,
        "startTimestamp": int(ko.timestamp()),
        "homeTeam": {"name": "Afturelding"},
        "awayTeam": {"name": "Hamar"},
        "tournament": {"name": "Mizunodeild", "category": {"name": "Iceland"}},
        "status": {"type": "finished", "description": "Ended"},
    }


def test_a_shadow_sport_searches_scoped_to_its_sport_and_one_page() -> None:
    from bet.sofa.config import SofaConfig
    from bet.sofa.resolve import SofaResolver

    ko = datetime(2026, 9, 29, 19, 30, tzinfo=UTC)
    client = _SearchClient(_hamar_game(ko))
    resolver = SofaResolver(SofaConfig(), client, _NullCache())  # type: ignore[arg-type]
    _, event, _ = resolver.resolve_entity(
        "volleyball",
        "Hamar",
        ko,
        "Afturelding",
        board_side_a="Afturelding",
        board_side_b="Hamar",
        record_miss=False,
        check_orientation=False,
    )
    assert event is not None and event["id"] == 42
    assert client.searches == [("hamar", "volleyball")]
    # events/last page 0 only, however many pages Sofascore says there are.
    assert client.listings == [(5, "last", 0)]


def test_football_search_stays_unscoped() -> None:
    from bet.sofa.config import SofaConfig
    from bet.sofa.resolve import SofaResolver

    ko = datetime(2026, 9, 29, 19, 30, tzinfo=UTC)
    client = _SearchClient(_hamar_game(ko))
    resolver = SofaResolver(SofaConfig(), client, _NullCache())  # type: ignore[arg-type]
    resolver.resolve_entity("football", "Hamar", ko, "Afturelding")
    assert client.searches == [("hamar", None)]
    assert {kind for _, kind, _ in client.listings} == {"next", "last"}


def test_client_search_appends_the_sport_only_when_given() -> None:
    from bet.sofa.client import SofascoreClient

    urls: list[str] = []
    client = SofascoreClient.__new__(SofascoreClient)
    client._execute = lambda url, *a, **k: urls.append(url)  # type: ignore[method-assign]
    client.search("praia clube")
    client.search("praia clube", sport="volleyball")
    assert urls == [
        "https://api.sofascore.com/api/v1/search/all?q=praia%20clube",
        "https://api.sofascore.com/api/v1/search/all?q=praia%20clube&sport=volleyball",
    ]


def _event(home: str, away: str, ko: datetime, gender: str = "M") -> dict[str, Any]:
    return {
        "id": 77,
        "startTimestamp": int(ko.timestamp()),
        "homeTeam": {"name": home, "gender": gender},
        "awayTeam": {"name": away, "gender": gender},
        "tournament": {"name": "Campeonato Mineiro", "category": {"name": "Brazil"}},
    }


@pytest.mark.parametrize(
    ("board", "home", "away", "gender", "minutes"),
    [
        # Live 2026-09-29: each was on Sofascore and refused by the 82 gate.
        (
            ("Praia Clube", "Minas TC"),
            "Praia Clube",
            "Itambé/Minas Tênis Clube",
            "M",
            0,
        ),
        (
            ("Milwaukee Panthers (K)", "Wisconsin Green Bay (K)"),
            "Milwaukee Panthers",
            "Green Bay Phoenix",
            "F",
            0,
        ),
        # The "(w)" marker alone cost the point: accepted at any gap in window.
        (
            ("Helios VS (K)", "Nyon (K)"),
            "Helios VS Basket",
            "Nyon Basket Féminin",
            "F",
            120,
        ),
    ],
)
def test_the_shadow_opponent_check_admits_sponsor_names_and_markers(
    board: tuple[str, str], home: str, away: str, gender: str, minutes: int
) -> None:
    ko = datetime(2026, 9, 29, 22, 30, tzinfo=UTC)
    event = _event(home, away, ko + timedelta(minutes=minutes), gender)
    resolver = _resolver()
    first = settle_shadow.normalize_name(board[0])
    kwargs: dict[str, Any] = {"superbet_side_a": board[0], "superbet_side_b": board[1]}
    for sport in ("volleyball", "basketball"):
        assert (
            resolver.match_quality(event, ko, first, sport=sport, **kwargs) is not None
            or resolver.match_quality(
                event, ko, settle_shadow.normalize_name(board[1]), sport=sport, **kwargs
            )
            is not None
        )
    # Football keeps RESOLVE's strict gate: a wrong pair prices the wrong sample.
    if board[0] == "Praia Clube":
        opp = settle_shadow.normalize_name(board[1])
        assert (
            resolver.match_quality(event, ko, opp, sport="football", **kwargs) is None
        )


def test_the_shadow_opponent_check_still_refuses() -> None:
    from bet.sofa.resolve import shadow_opponent_agrees

    n = settle_shadow.normalize_name
    # No shared word: a different game (the women's side of the other club).
    assert not shadow_opponent_agrees(n("Triglav Kranj"), n("ŽKK Cinkarna Celje"), 0)
    # A shared word only counts when both clocks agree within 15 minutes.
    assert shadow_opponent_agrees(n("Minas TC"), n("Itambé/Minas Tênis Clube"), 900)
    assert not shadow_opponent_agrees(n("Minas TC"), n("Itambé/Minas Tênis Clube"), 901)
    # Generic words never count.
    assert not shadow_opponent_agrees(n("Sporting Lisboa"), n("Sporting Braga"), 0)
    # Both sides of the event share the word: which one is the opponent is
    # unknown, so the game is refused.
    ko = datetime(2026, 9, 29, 18, tzinfo=UTC)
    derby = _event("Hapoel Tel Aviv", "Maccabi Tel Aviv", ko)
    assert (
        _resolver().match_quality(
            derby,
            ko,
            n("Tel Aviv Stars"),
            sport="basketball",
            superbet_side_a="Maccabi Tel Aviv",
            superbet_side_b="Tel Aviv Stars",
        )
        is None
    )


def test_virtual_games_never_resolve_for_a_shadow_sport() -> None:
    from bet.sofa.resolve import candidate_fits, is_virtual_event

    ko = datetime(2026, 9, 29, 19, tzinfo=UTC)
    real = _event("Maxima Roma", "U-Banca Transilvania Cluj-Napoca", ko)
    # Live 2026-09-29: a player-named e-team, caught by its category alone.
    virtual = {
        **_event(
            "Coviran Granada (eSport)", "U-BT Cluj-Napoca (Nerijus Jakubauskas)", ko
        ),
        "tournament": {
            "name": "Eurocup 2K/Virtual EuroCup - Group B",
            "category": {"name": "Virtual Basketball", "slug": "virtual-basketball"},
        },
    }
    cyber = _event("Cluj (Cyber)", "Budućnost (Cyber)", ko)
    assert not is_virtual_event(real)
    assert is_virtual_event(virtual) and is_virtual_event(cyber)
    resolver = _resolver()
    kwargs: dict[str, Any] = {
        "sport": "basketball",
        "superbet_side_a": "Maxima Roma",
        "superbet_side_b": "U BT Cluj",
    }
    assert resolver.match_quality(real, ko, "maxima roma", **kwargs) is not None
    for fake in (virtual, cyber):
        assert resolver.match_quality(fake, ko, "maxima roma", **kwargs) is None
    # A simulated side takes none of the three candidate places.
    for name in ("Cluj (Cyber)", "U-BT Cluj-Napoca (eSport)"):
        assert not candidate_fits(
            "u bt cluj", {"name": name, "gender": "M"}, "basketball"
        )
    assert candidate_fits(
        "u bt cluj",
        {"name": "U-Banca Transilvania Cluj-Napoca", "gender": "M"},
        "basketball",
    )


def test_a_cell_reads_only_what_its_data_carries() -> None:
    from bet.sofa.cs2 import FamilyStats

    def stats(games: int, fair: float, hit: float) -> FamilyStats:
        return FamilyStats("x", games, games, fair, hit, 0.2, 0.0, 0.05)

    assert audit_shadow.read_of(stats(10, 0.5, 0.9), 0.01, 30).startswith("too few")
    assert audit_shadow.read_of(stats(100, 0.50, 0.55), 0.04, 30) == "noise"
    assert audit_shadow.read_of(stats(100, 0.50, 0.60), 0.04, 3).startswith("lead")
    assert audit_shadow.read_of(stats(100, 0.50, 0.60), 0.04, 7) == "signal"


def test_the_gap_error_is_clustered_by_game() -> None:
    # Ten lines of ONE game that all won are one observation, not ten.
    one_game = [
        {"superbet_event_id": "1", "fair_p": 0.5, "outcome": "WIN"} for _ in range(10)
    ]
    assert audit_shadow.gap_se(one_game) is None
    spread = [
        {
            "superbet_event_id": str(i),
            "fair_p": 0.5,
            "outcome": "WIN" if i % 2 else "LOSS",
        }
        for i in range(100)
    ]
    se = audit_shadow.gap_se(spread)
    # Independent games: sqrt(p(1-p)/n) with the G/(G-1) correction.
    assert se is not None and se == pytest.approx(0.05 * (100 / 99) ** 0.5)
    # The same 100 outcomes, but ten correlated lines to a game (a game's
    # lines all win or all lose together): a wider error.
    ordered = sorted(spread, key=lambda r: r["outcome"])
    packed = [dict(r, superbet_event_id=str(i // 10)) for i, r in enumerate(ordered)]
    wide = audit_shadow.gap_se(packed)
    assert wide is not None and wide >= se


@pytest.mark.parametrize(
    ("board", "event"),
    [
        # Review 2026-09-29: the searched team confirmed itself through a word
        # both clubs of the board share, against a different opponent.
        (("Dynamo Moscow", "Spartak Moscow"), ("Dynamo Moscow", "Lokomotiv Yaroslavl")),
        (
            ("Hapoel Tel Aviv", "Maccabi Tel Aviv"),
            ("Hapoel Tel Aviv", "Hapoel Jerusalem"),
        ),
        (
            ("Metallurg Magnitogorsk", "Metallurg Novokuznetsk"),
            ("Metallurg Magnitogorsk", "Traktor Chelyabinsk"),
        ),
        # ...and a club-type word that two different clubs carry.
        (
            ("Maccabi Tel Aviv", "Hapoel Holon"),
            ("Maccabi Tel Aviv", "Hapoel Galil Elyon"),
        ),
    ],
)
def test_the_relaxed_gate_never_lets_the_searched_team_confirm_itself(
    board: tuple[str, str], event: tuple[str, str]
) -> None:
    ko = datetime(2026, 9, 29, 18, tzinfo=UTC)
    game = _event(event[0], event[1], ko)
    opponent = settle_shadow.normalize_name(board[1])
    for sport in ("ice-hockey", "basketball", "volleyball"):
        assert (
            _resolver().match_quality(
                game,
                ko,
                opponent,
                sport=sport,
                superbet_side_a=board[0],
                superbet_side_b=board[1],
            )
            is None
        )


def test_a_zero_error_reads_as_noise_not_signal() -> None:
    from bet.sofa.cs2 import FamilyStats

    flat = FamilyStats("x", 40, 80, 0.5, 0.5, 0.25, -0.05, 0.05)
    assert audit_shadow.read_of(flat, 0.0, 30) == "noise"
    # A real gap with no spread at all is not noise.
    sure = FamilyStats("x", 40, 40, 0.5, 1.0, 0.25, 0.9, 0.05)
    assert audit_shadow.read_of(sure, 0.0, 30) == "signal"


def test_the_clustered_error_is_centred_on_the_mean_gap() -> None:
    # Every game's one line won at fair p 0.5: the gap is +0.5 with NO spread.
    rows = [
        {"superbet_event_id": str(i), "fair_p": 0.5, "outcome": "WIN"}
        for i in range(50)
    ]
    assert audit_shadow.gap_se(rows) == pytest.approx(0.0)


def test_a_torn_snapshot_line_is_counted_not_fatal(tmp_path: Path) -> None:
    write_snapshot(tmp_path)
    path = tmp_path / "shadow" / "hockey" / DATE / "snapshots.jsonl"
    with path.open("a") as fh:
        fh.write('{"fetched_at_utc": "2026-09-28T15:30:00Z", "superbet_ev')  # torn
        fh.write("\n[1, 2]\n")
    result = run_settle(
        tmp_path,
        FakeResolver(sofa_event()),
        FakeClient({**sofa_event(), **HOCKEY_AET}),
        6,
    )
    m = result["metrics"]["hockey"]
    assert m["metrics"]["unreadable_snapshot_lines"] == 2
    assert settled(tmp_path)["1"]["state"] == "SETTLED"
    assert m["verdict"] == "PARTIAL"  # graded, but the file needs a look


def test_concurrent_snapshot_appends_keep_every_record_whole(tmp_path: Path) -> None:
    import threading

    def one(i: int) -> None:
        clock = datetime(2026, 9, 28, 9, i, tzinfo=UTC)
        run_shadow.snapshot(DATE, FakeSuperbet(), str(tmp_path), at=clock)  # type: ignore[arg-type]

    threads = [threading.Thread(target=one, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    for p in (tmp_path / "shadow").glob("*/*/snapshots.jsonl"):
        for raw in p.read_text().splitlines():
            json.loads(raw)  # every line parses


# --- player lines (hockey, basketball) -----------------------------------------


def _pitem(
    mid: int,
    market: str,
    player: str,
    side: str,
    total: float,
    price: float,
    code: str | None = None,
) -> dict[str, Any]:
    word = "powyżej" if side == "OVER" else "poniżej"
    return {
        "marketId": mid,
        "marketName": market,
        "name": f"{player} - {word} {total}",
        "info": f"{player} {word} {total} punktów (z dogrywką)",
        "code": code,
        "specifiers": {"player": player + " ", "total": str(total)},
        "status": "active",
        "price": price,
    }


def test_a_player_line_is_parsed_and_paired() -> None:
    m = "Zawodnik - liczba punktów + zbiórek (z dogrywką)"
    items = [
        _pitem(233572, m, "Astier, Pauline", "OVER", 11.5, 1.85),
        _pitem(233572, m, "Astier, Pauline", "UNDER", 11.5, 1.87),
        # Another player's single side: unpaired, dropped by parse_event.
        _pitem(233572, m, "Other, Guy", "OVER", 9.5, 1.9),
    ]
    lines = parse_event(items, "basketball", "e", "A", "B")
    assert {(ln.family, ln.subject, ln.line, ln.side) for ln in lines} == {
        ("player_pts_reb", "Astier, Pauline", 11.5, "OVER"),
        ("player_pts_reb", "Astier, Pauline", 11.5, "UNDER"),
    }


@pytest.mark.parametrize(
    "bad",
    [
        {"marketName": "Zawodnik - liczba punktów"},  # not the name the id carries
        {"specifiers": {"player": "Astier, Pauline", "total": "12.5"}},  # 11.5 in text
        {"name": "Somebody Else - powyżej 11.5"},  # the outcome names another player
        {"status": "block"},
        {"price": 1.0},
        {"tags": "price_boost"},
    ],
)
def test_a_player_line_that_does_not_read_twice_is_dropped(bad: dict[str, Any]) -> None:
    m = "Zawodnik - liczba punktów + zbiórek (z dogrywką)"
    item = {**_pitem(233572, m, "Astier, Pauline", "OVER", 11.5, 1.85), **bad}
    assert parse_line(item, "basketball", "e", "A", "B") is None


def test_the_hockey_code_is_not_read_as_a_direction() -> None:
    # Superbet's code on "Celne strzały zawodnika" is "6-" for an UNDER and
    # "6+" for an OVER on some lines and meaningless on others: text only.
    item = _pitem(
        230023,
        "Celne strzały zawodnika (z dogrywką)",
        "Adam Fox",
        "UNDER",
        1.5,
        1.6,
        "6+",
    )
    got = parse_line(item, "hockey", "e", "A", "B")
    assert (
        got is not None and got.side == "UNDER" and got.family == "player_shots_on_goal"
    )


def _box_lineups(
    home_points: list[int], away_points: list[int], key: str = "points"
) -> dict[str, Any]:
    def squad(values: list[int], tag: str) -> dict[str, Any]:
        return {
            "players": [
                {
                    "player": {"name": f"{tag} Player{i}"},
                    "statistics": {
                        "secondsPlayed": 600,
                        key: v,
                        "rebounds": 3,
                        "assists": 1,
                    },
                }
                for i, v in enumerate(values)
            ]
            + [{"player": {"name": f"{tag} Bench"}, "statistics": {}}]
        }

    return {"home": squad(home_points, "Home"), "away": squad(away_points, "Away")}


def _score_detail(
    home: int, away: int, description: str = "Ended", code: int = 1
) -> dict[str, Any]:
    return {
        "status": {"type": "finished", "description": description},
        "winnerCode": code,
        "homeScore": {"current": home},
        "awayScore": {"current": away},
    }


def test_the_player_box_must_add_up_to_the_score() -> None:
    from bet.sofa.shadow import build_player_box

    ok = build_player_box(
        _box_lineups([20, 30], [10, 15]), _score_detail(50, 25), BASKETBALL
    )
    assert ok is not None and ok.ok
    off = build_player_box(
        _box_lineups([20, 30], [10, 15]), _score_detail(52, 25), BASKETBALL
    )
    assert off is not None and not off.ok and "home points 50 vs score 52" in off.reason
    assert build_player_box(None, _score_detail(50, 25), BASKETBALL) is None
    # Hockey: a shootout's deciding goal may or may not be in current.
    for home_current in (3, 4):
        box = build_player_box(
            _box_lineups([1, 2], [3], key="goals"),
            _score_detail(home_current, 3, "AP", 1),
            HOCKEY,
        )
        assert box is not None and box.ok
    beyond = build_player_box(
        _box_lineups([1, 2], [3], key="goals"), _score_detail(5, 3, "AP", 1), HOCKEY
    )
    assert beyond is not None and not beyond.ok


def test_player_values_dnp_and_unmatched() -> None:
    from bet.sofa.shadow import build_player_box, player_value

    box = build_player_box(
        _box_lineups([20, 30], [10, 15]), _score_detail(50, 25), BASKETBALL
    )
    assert box is not None

    def ln(subject: str, mid: int = 233572) -> ShadowLine:
        return ShadowLine("e", mid, "x", 0, subject, 11.5, "OVER", 1.9)

    assert player_value(ln("Player1, Home"), box, BASKETBALL) == 33.0  # pts + reb
    assert (
        player_value(ln("Home Player0", 235217), box, BASKETBALL) == "NO_STAT"
    )  # blocks
    assert player_value(ln("Bench, Home"), box, BASKETBALL) == "DNP"
    assert player_value(ln("Nobody Atall"), box, BASKETBALL) == "UNMATCHED"


class LineupsClient(FakeClient):
    def __init__(self, detail: dict[str, Any], lineups: dict[str, Any] | None) -> None:
        super().__init__(detail)
        self.lineups = lineups
        self.lineups_asked: list[int] = []

    def event_lineups(self, eid: int) -> dict[str, Any] | None:
        self.lineups_asked.append(eid)
        return self.lineups


def test_player_lines_settle_end_to_end(tmp_path: Path) -> None:
    lines = [
        ShadowLine(
            "1", 236265, "player_points", 0, "Player0, Home", 0.5, "OVER", 2.1
        ).as_dict(),
        ShadowLine(
            "1", 236265, "player_points", 0, "Player0, Home", 0.5, "UNDER", 1.7
        ).as_dict(),
        ShadowLine(
            "1", 236265, "player_points", 0, "Bench, Home", 0.5, "OVER", 3.0
        ).as_dict(),
        ShadowLine(
            "1", 236265, "player_points", 0, "Bench, Home", 0.5, "UNDER", 1.35
        ).as_dict(),
    ]
    snap = {**_snap("2026-09-28T15:00:00Z", 1.9)}
    snap["lines"] = snap["lines"] + lines
    _write_snaps(tmp_path, [snap])
    # HOCKEY_AET: home 4 (1+2+0, OT goal), away 3.
    lineups = {
        "home": {
            "players": [
                {
                    "player": {"name": "Home Player0"},
                    "statistics": {"secondsPlayed": 1200, "goals": 4, "points": 5},
                },
                {
                    "player": {"name": "Home Bench"},
                    "statistics": {"secondsPlayed": 0, "goals": 0, "points": 0},
                },
            ]
        },
        "away": {
            "players": [
                {
                    "player": {"name": "Away One"},
                    "statistics": {"secondsPlayed": 1100, "goals": 3, "points": 3},
                }
            ]
        },
    }
    client = LineupsClient({**sofa_event(), **HOCKEY_AET}, lineups)
    run_settle(tmp_path, FakeResolver(sofa_event()), client, 6)
    rec = settled(tmp_path)["1"]
    assert rec["state"] == "SETTLED" and rec["player_box"] == "ok"
    got = {
        (g["subject"], g["side"]): g["outcome"]
        for g in rec["graded"]
        if g["family"] == "player_points"
    }
    assert got == {("Player0, Home", "OVER"): "WIN", ("Player0, Home", "UNDER"): "LOSS"}
    assert rec["player_dnp"] == 2  # the bench player's two sides: void, not graded
    assert client.lineups_asked == [700]


def test_a_box_that_does_not_add_up_grades_no_player_line(tmp_path: Path) -> None:
    snap = {**_snap("2026-09-28T15:00:00Z", 1.9)}
    snap["lines"] = snap["lines"] + [
        ShadowLine(
            "1", 236265, "player_points", 0, "Player0, Home", 0.5, s, 1.9
        ).as_dict()
        for s in ("OVER", "UNDER")
    ]
    _write_snaps(tmp_path, [snap])
    lineups = {
        "home": {
            "players": [
                {
                    "player": {"name": "Home Player0"},
                    "statistics": {"secondsPlayed": 1, "goals": 1},
                }
            ]
        },
        "away": {
            "players": [
                {
                    "player": {"name": "Away One"},
                    "statistics": {"secondsPlayed": 1, "goals": 3},
                }
            ]
        },
    }
    client = LineupsClient({**sofa_event(), **HOCKEY_AET}, lineups)
    run_settle(tmp_path, FakeResolver(sofa_event()), client, 6)
    rec = settled(tmp_path)["1"]
    assert rec["player_box"].startswith("home goals 1 vs score 4")
    assert rec["player_no_box"] == 2
    assert all(g["family"] != "player_points" for g in rec["graded"])
    # The team lines are still graded.
    assert any(g["family"] == "total" for g in rec["graded"])


def test_a_name_in_both_squads_is_nobodys_line() -> None:
    from bet.sofa.shadow import build_player_box, player_value

    lineups = {
        "home": {
            "players": [
                {
                    "player": {"name": "Jan Kowalski"},
                    "statistics": {"secondsPlayed": 9, "points": 25},
                }
            ]
        },
        "away": {
            "players": [
                {
                    "player": {"name": "Jan Kowalski"},
                    "statistics": {"secondsPlayed": 9, "points": 10},
                }
            ]
        },
    }
    box = build_player_box(lineups, _score_detail(25, 10), BASKETBALL)
    assert box is not None and box.ok  # the score still adds up
    line = ShadowLine(
        "e", 233565, "player_points", 0, "Kowalski, Jan", 20.5, "OVER", 1.9
    )
    assert player_value(line, box, BASKETBALL) == "UNMATCHED"


def test_a_malformed_player_entry_is_skipped_not_fatal() -> None:
    from bet.sofa.shadow import build_player_box

    lineups = {
        "home": {
            "players": [
                {"player": "oops"},
                {
                    "player": {"name": "A B"},
                    "statistics": {"secondsPlayed": 1, "points": 2},
                },
            ]
        },
        "away": {
            "players": [
                {
                    "player": {"name": "C D"},
                    "statistics": {"secondsPlayed": 1, "points": 1},
                }
            ]
        },
    }
    box = build_player_box(lineups, _score_detail(2, 1), BASKETBALL)
    assert box is not None and box.ok


def test_a_missing_box_is_asked_again_and_then_grades(tmp_path: Path) -> None:
    snap = {**_snap("2026-09-28T15:00:00Z", 1.9)}
    snap["lines"] = snap["lines"] + [
        ShadowLine(
            "1", 236265, "player_points", 0, "Player0, Home", 0.5, s, 1.9
        ).as_dict()
        for s in ("OVER", "UNDER")
    ]
    _write_snaps(tmp_path, [snap])
    first = LineupsClient({**sofa_event(), **HOCKEY_AET}, None)  # not published yet
    run_settle(tmp_path, FakeResolver(sofa_event()), first, 6)
    rec = settled(tmp_path)["1"]
    assert rec["state"] == "SETTLED" and rec["player_retry"] is True
    assert any(g["family"] == "total" for g in rec["graded"])
    lineups = {
        "home": {
            "players": [
                {
                    "player": {"name": "Home Player0"},
                    "statistics": {"secondsPlayed": 900, "goals": 4, "points": 4},
                }
            ]
        },
        "away": {
            "players": [
                {
                    "player": {"name": "Away One"},
                    "statistics": {"secondsPlayed": 900, "goals": 3, "points": 3},
                }
            ]
        },
    }
    later = LineupsClient({**sofa_event(), **HOCKEY_AET}, lineups)
    run_settle(tmp_path, FakeResolver(sofa_event()), later, 8)
    rec = settled(tmp_path)["1"]
    assert rec["player_retry"] is False
    assert {
        g["side"]: g["outcome"] for g in rec["graded"] if g["family"] == "player_points"
    } == {
        "OVER": "WIN",
        "UNDER": "LOSS",
    }
    # ...and once the box is in, the game is final: never asked a third time.
    third = LineupsClient({**sofa_event(), **HOCKEY_AET}, lineups)
    run_settle(tmp_path, FakeResolver(sofa_event()), third, 9)
    assert third.lineups_asked == []


def test_a_missing_box_stops_being_asked_after_the_give_up_window(
    tmp_path: Path,
) -> None:
    snap = {**_snap("2026-09-28T15:00:00Z", 1.9)}
    snap["lines"] = snap["lines"] + [
        ShadowLine(
            "1", 236265, "player_points", 0, "Player0, Home", 0.5, s, 1.9
        ).as_dict()
        for s in ("OVER", "UNDER")
    ]
    _write_snaps(tmp_path, [snap])
    run_settle(
        tmp_path,
        FakeResolver(sofa_event()),
        LineupsClient({**sofa_event(), **HOCKEY_AET}, None),
        6,
    )
    late = LineupsClient({**sofa_event(), **HOCKEY_AET}, None)
    run_settle(tmp_path, FakeResolver(sofa_event()), late, 24 * 8)
    assert late.lineups_asked == [] and settled(tmp_path)["1"]["state"] == "SETTLED"


def test_player_lines_grade_when_the_orientation_is_unclear() -> None:
    from bet.sofa.shadow import build_player_box

    ev = latest_pre_kickoff(
        [
            {
                **_snap("2026-09-28T15:00:00Z", 1.9),
                "lines": [
                    ShadowLine(
                        "1", 236265, "player_points", 0, "Player0, Home", 0.5, s, 1.9
                    ).as_dict()
                    for s in ("OVER", "UNDER")
                ],
            }
        ]
    )["1"]
    result = build_result(HOCKEY_AET, HOCKEY, True)
    assert result is not None
    box = build_player_box(
        {
            "home": {
                "players": [
                    {
                        "player": {"name": "Home Player0"},
                        "statistics": {"secondsPlayed": 9, "goals": 4, "points": 4},
                    }
                ]
            },
            "away": {
                "players": [
                    {
                        "player": {"name": "Away One"},
                        "statistics": {"secondsPlayed": 9, "goals": 3, "points": 3},
                    }
                ]
            },
        },
        HOCKEY_AET,
        HOCKEY,
    )
    rows, counts = settle_event(ev, result, HOCKEY, totals_only=True, box=box)
    assert {r["side"] for r in rows} == {"OVER", "UNDER"} and counts[
        "needs_orientation"
    ] == 0


class FailingClient(LineupsClient):
    def event(self, eid: int) -> dict[str, Any]:
        raise RuntimeError("HTTP 403")


def test_a_failed_player_retry_never_replaces_the_graded_game(tmp_path: Path) -> None:
    snap = {**_snap("2026-09-28T15:00:00Z", 1.9)}
    snap["lines"] = snap["lines"] + [
        ShadowLine(
            "1", 236265, "player_points", 0, "Player0, Home", 0.5, s, 1.9
        ).as_dict()
        for s in ("OVER", "UNDER")
    ]
    _write_snaps(tmp_path, [snap])
    run_settle(
        tmp_path,
        FakeResolver(sofa_event()),
        LineupsClient({**sofa_event(), **HOCKEY_AET}, None),
        6,
    )
    before = settled(tmp_path)["1"]
    assert before["state"] == "SETTLED" and before["player_retry"] and before["graded"]
    run_settle(tmp_path, FakeResolver(sofa_event()), FailingClient({}, None), 8)
    after = settled(tmp_path)["1"]
    assert after["state"] == "SETTLED" and after["graded"] == before["graded"]
    assert after["player_retry_last_error"] == "ERROR"
    # ...and a resolver that no longer finds the game changes nothing either.
    run_settle(tmp_path, FakeResolver(None), LineupsClient({}, None), 9)
    assert settled(tmp_path)["1"]["graded"] == before["graded"]


def test_a_snapshot_after_midnight_asks_for_the_next_mornings_games(
    tmp_path: Path,
) -> None:
    asked: list[tuple[datetime, datetime]] = []

    class Board(FakeSuperbet):
        def events_by_date(
            self, start: datetime, end: datetime, offer_state: str
        ) -> list[dict]:
            asked.append((start, end))
            return []

    late = datetime(2026, 9, 29, 4, 24, tzinfo=UTC)  # D+1 04:24Z of D = 09-28
    run_shadow.snapshot(DATE, Board(), str(tmp_path), at=late)  # type: ignore[arg-type]
    assert asked[-1][1] == late + timedelta(hours=run_shadow.DEFAULT_HORIZON_H)
    # During the day itself the window is the day plus the horizon, as before.
    run_shadow.snapshot(
        DATE, Board(), str(tmp_path), at=datetime(2026, 9, 28, 12, tzinfo=UTC)
    )  # type: ignore[arg-type]
    assert asked[-1][1] == datetime(2026, 9, 29, tzinfo=UTC) + timedelta(
        hours=run_shadow.DEFAULT_HORIZON_H
    )


# --- 2026-09-30: 1X2, parity, yes/no, exact score (shapes captured live) ----------

from bet.sofa.shadow import GameResult, SnapshotEvent  # noqa: E402

BB1, BB2 = "New Zealand Breakers", "Cairns Taipans"


def test_hockey_1x2_reads_code_and_token_and_needs_all_three() -> None:
    raw = [
        item(640, "Mecz", "1", 1.74, code="1", info=f"{T1} wygra mecz"),
        item(640, "Mecz", "X", 4.2, code="0", info="Remis w meczu"),
        item(640, "Mecz", "2", 3.9, code="2", info=f"{T2} wygra mecz"),
        item(660, "X.tercja - zwycięzca", "1.tercja - 1", 2.27, {"periodnr": "1"},
             code="1", info="Wygra 1.tercji"),
        item(660, "X.tercja - zwycięzca", "1.tercja - X", 2.7, {"periodnr": "1"},
             code="0", info="Remis w 1.tercji"),
    ]
    lines = parse_event(raw, "hockey", "1", T1, T2)
    assert sorted(ln.side for ln in lines) == ["DRAW", "T1", "T2"]  # period: no "2"
    assert {ln.family for ln in lines} == {"result_1x2"}
    # the code and the token must agree
    wrong = item(640, "Mecz", "1", 1.74, code="2")
    assert parse_line(wrong, "hockey", "1", T1, T2) is None


def test_basketball_second_half_1x2_names_the_teams_and_remis() -> None:
    raw = [
        item(233400, "2.Połowa - 1X2", BB1, 1.76, info=f"{BB1} wygra 2.połowę"),
        item(233400, "2.Połowa - 1X2", "Remis", 16.0, info="Remis w 2.połowie"),
        item(233400, "2.Połowa - 1X2", BB2, 2.2, info=f"{BB2} wygra 2.połowę"),
    ]
    sides = {ln.side: ln.odds for ln in parse_event(raw, "basketball", "1", BB1, BB2)}
    assert sides == {"T1": 1.76, "DRAW": 16.0, "T2": 2.2}


def test_parity_markets_and_the_team_they_name() -> None:
    raw = [
        item(775, "Nieparzysta/parzysta liczba punktów(z dogrywką)", "nieparzysta",
             1.77, code="1", info="Nieparzysta liczba punktów w meczu (z dogrywką)"),
        item(775, "Nieparzysta/parzysta liczba punktów(z dogrywką)", "parzysta",
             1.92, code="2", info="Parzysta liczba punktów w meczu (z dogrywką)"),
        item(230634, f"{BB1} liczba punktów nieparzysta/parzysta (z dogrywką)",
             "Nieparzysta", 1.87),
        item(230634, f"{BB1} liczba punktów nieparzysta/parzysta (z dogrywką)",
             "Parzysta", 1.82),
        # id says team1, the name says team2: dropped
        item(230634, f"{BB2} liczba punktów nieparzysta/parzysta (z dogrywką)",
             "Nieparzysta", 1.87),
    ]
    lines = parse_event(raw[:4], "basketball", "1", BB1, BB2)
    got = {(ln.family, ln.subject, ln.side) for ln in lines}
    assert got == {("odd_even", "", "ODD"), ("odd_even", "", "EVEN"),
                   ("team_odd_even", "T1", "ODD"), ("team_odd_even", "T1", "EVEN")}
    assert parse_line(raw[4], "basketball", "1", BB1, BB2) is None


def test_volleyball_exact_score_extra_points_and_parity() -> None:
    scores = ["3:0", "3:1", "3:2", "0:3", "1:3", "2:3"]
    raw = [item(785, "Dokładny wynik", s, 5.0 + i, code=s.replace(":", ""))
           for i, s in enumerate(scores)]
    assert len(parse_event(raw, "volleyball", "1", T1, T2)) == 6
    assert parse_event(raw[:5], "volleyball", "1", T1, T2) == []  # not whole
    bad = item(785, "Dokładny wynik", "3:1", 5.0, code="13")
    assert parse_line(bad, "volleyball", "1", T1, T2) is None
    q = "Czy 1. set zostanie rozstrzygnięty na dodatkowe punkty przewagi?"
    raw_yes = item(100077, q, "Tak", 6.4, {"setnr": "1"})
    yes = parse_line(raw_yes, "volleyball", "1", T1, T2)
    assert yes is not None and (yes.side, yes.period) == ("YES", 1)

    game = GameResult((25, 26, 23, 15), (20, 24, 25, 13), 3, 1, "T1", False)
    ex = ShadowLine("1", 785, "exact_sets", 0, "", None, "3:1", 5.0)
    assert grade(ex, actual_value(ex, game, VOLLEYBALL) or 0.0) == "WIN"
    ex30 = ShadowLine("1", 785, "exact_sets", 0, "", None, "3:0", 5.0)
    assert grade(ex30, actual_value(ex30, game, VOLLEYBALL) or 0.0) == "LOSS"
    extra = {p: ShadowLine("1", 100077, "set_extra_points", p, "", None, "YES", 6.0)
             for p in (1, 2)}
    assert grade(extra[1], actual_value(extra[1], game, VOLLEYBALL) or 0.0) == "LOSS"
    assert grade(extra[2], actual_value(extra[2], game, VOLLEYBALL) or 0.0) == "WIN"
    five = GameResult((25, 20, 25, 20, 16), (20, 25, 20, 25, 14), 3, 2, "T1", False)
    set5 = ShadowLine("1", 100077, "set_extra_points", 5, "", None, "YES", 6.0)
    assert actual_value(set5, five, VOLLEYBALL) == 1.0  # 16-14 in a set to 15
    par = ShadowLine("1", 781, "set_points_odd_even", 1, "", None, "ODD", 1.9)
    assert grade(par, actual_value(par, game, VOLLEYBALL) or 0.0) == "WIN"  # 45


def test_a_level_score_is_the_draws_win_in_a_1x2_never_a_void() -> None:
    draw = ShadowLine("1", 640, "result_1x2", 0, "", None, "DRAW", 4.2)
    home = ShadowLine("1", 640, "result_1x2", 0, "", None, "T1", 1.8)
    assert grade(draw, 0.0, three_way=True) == "WIN"
    assert grade(home, 0.0, three_way=True) == "LOSS"
    assert grade(home, 2.0, three_way=True) == "WIN"


def test_a_three_way_group_settles_devigged_over_all_three() -> None:
    ev = SnapshotEvent("1", f"{T1}·{T2}", T1, T2, "2026-09-29T17:00:00Z", None)
    for side, odds in (("T1", 1.8), ("DRAW", 4.2), ("T2", 3.9)):
        ln = ShadowLine("1", 640, "result_1x2", 0, "", None, side, odds)
        ev.sides[(*ln.key(), side)] = ln
        ev.fetched_at[(*ln.key(), side)] = "2026-09-29T16:30:00Z"
    game = GameResult((1, 1, 1), (1, 1, 1), 4, 3, "T1", True)  # 3-3, won in OT
    rows, _ = settle_event(ev, game, HOCKEY)
    by = {r["side"]: r for r in rows}
    assert by["DRAW"]["outcome"] == "WIN" and by["T1"]["outcome"] == "LOSS"
    assert sum(r["fair_p"] for r in rows) == pytest.approx(1.0)
    assert by["T1"]["overround"] == pytest.approx(1 / 1.8 + 1 / 4.2 + 1 / 3.9 - 1)
    assert "partner_odds" not in by["T1"] and len(by["T1"]["group_odds"]) == 3
    # one side missing: no price for the others
    del ev.sides[(640, 0, "", None, "DRAW")]
    rows, counts = settle_event(ev, game, HOCKEY)
    assert rows == [] and counts["unpaired"] == 2


def test_orientation_free_kinds_grade_without_orientation() -> None:
    ev = SnapshotEvent("1", f"{BB1}·{BB2}", BB1, BB2, "2026-09-29T17:00:00Z", None)
    for mid, fam, subj in ((775, "odd_even", ""), (230634, "team_odd_even", "T1")):
        for side in ("ODD", "EVEN"):
            ln = ShadowLine("1", mid, fam, 0, subj, None, side, 1.9)
            ev.sides[(*ln.key(), side)] = ln
            ev.fetched_at[(*ln.key(), side)] = "2026-09-29T16:30:00Z"
    game = GameResult((20, 20, 20, 21), (20, 20, 20, 20), 81, 80, "T1", False)
    rows, counts = settle_event(ev, game, BASKETBALL, totals_only=True)
    assert {r["family"] for r in rows} == {"odd_even"}
    assert counts["needs_orientation"] == 2
    assert {r["side"]: r["outcome"] for r in rows} == {"ODD": "WIN", "EVEN": "LOSS"}


def test_extra_points_in_the_deciding_set_of_a_best_of_three() -> None:
    bo3 = GameResult((25, 20, 16), (20, 25, 14), 2, 1, "T1", False)
    third = ShadowLine("1", 100077, "set_extra_points", 3, "", None, "YES", 6.0)
    assert actual_value(third, bo3, VOLLEYBALL) == 1.0  # 16-14 in a set to 15
    # the same score in the 3rd set of a best-of-5 is a set to 25: no extras
    bo5 = GameResult((25, 20, 16, 25), (20, 25, 14, 20), 3, 1, "T1", False)
    assert actual_value(third, bo5, VOLLEYBALL) == 0.0


# --- review 2026-10-01: miss reasons, D-2 settle, saved lineups ------------------


def _temp_cache(tmp_path: Path) -> Any:
    from bet.sofa.cache import SofaCache
    from bet.sofa.config import SofaConfig
    from bet.sofa.db import migrate

    tmp_path.mkdir(parents=True, exist_ok=True)
    db = str(tmp_path / "sofa.db")
    migrate(db)
    return SofaCache(SofaConfig(db_path=db))


class _MissClient:
    """Search answers per query; one listing for entity 5."""

    def __init__(self, results: dict[str, Any], listing: list[dict[str, Any]]):
        self.results, self.listing = results, listing
        self.requests = 0

    def search(self, q: str, sport: str | None = None) -> Any:
        self.requests += 1
        return self.results.get(q)

    def entity_events(self, eid: int, kind: str, page: int) -> dict[str, Any]:
        self.requests += 1
        return {"events": self.listing, "hasNextPage": False}


def _volley_game(home: str, away: str, ko: datetime) -> dict[str, Any]:
    return {
        "id": 77,
        "startTimestamp": int(ko.timestamp()),
        "homeTeam": {"name": home},
        "awayTeam": {"name": away},
        "tournament": {"name": "Liga", "category": {"name": "Iceland"}},
    }


def _explain(
    tmp_path: Path, results: dict[str, Any], listing: list[dict[str, Any]]
) -> tuple[Any, dict[str, Any], int]:
    from bet.sofa.config import SofaConfig
    from bet.sofa.resolve import SofaResolver
    from bet.sofa.shadow import SnapshotEvent

    ko = datetime(2026, 9, 29, 19, 30, tzinfo=UTC)
    client = _MissClient(results, listing)
    resolver = SofaResolver(SofaConfig(), client, _temp_cache(tmp_path))  # type: ignore[arg-type]
    ev = SnapshotEvent("9", "Hamar·Afturelding", "Hamar", "Afturelding",
                       "2026-09-29T19:30:00Z", "Liga")  # fmt: skip
    miss: dict[str, Any] = {}
    found = settle_shadow.find_event(resolver, VOLLEYBALL, ev, ko, miss)
    # The client is RESOLVE's own again afterwards.
    assert resolver.client is client
    return found, miss, client.requests


def _team(name: str) -> dict[str, Any]:
    return {"type": "team", "entity": {"id": 5, "name": name,
                                       "sport": {"slug": "volleyball"}}}  # fmt: skip


def test_a_miss_records_why_from_answers_already_paid_for(tmp_path: Path) -> None:
    ko = datetime(2026, 9, 29, 19, 30, tzinfo=UTC)
    # Nothing found for either side.
    found, miss, _ = _explain(tmp_path / "a", {}, [])
    assert found == "NOT_ON_SOFASCORE"
    assert miss["team1"]["reason"] == "NO_SEARCH_RESULT"
    assert miss["team2"]["reason"] == "NO_SEARCH_RESULT"
    # A search hit of another sport only: no candidate, its names kept empty.
    other = {"hamar": {"results": [{"type": "team", "entity": {
        "id": 5, "name": "Hamar", "sport": {"slug": "football"}}}]}}  # fmt: skip
    _, miss, _ = _explain(tmp_path / "b", other, [])
    assert miss["team1"]["reason"] == "NO_CANDIDATE"
    # The team found, its game listed, but against a name that does not agree.
    hit = {"hamar": {"results": [_team("Hamar")]}}
    wrong = [_volley_game("Hamar", "Somebody Else", ko + timedelta(hours=2))]
    _, miss, requests = _explain(tmp_path / "c", hit, wrong)
    assert miss["team1"] == {
        "reason": "OPPONENT_REFUSED",
        "in_window": ["Hamar - Somebody Else"],
        "search_teams": ["Hamar"],
    }
    assert miss["team2"]["reason"] == "NO_SEARCH_RESULT"
    # Explaining cost nothing: one search per side and the one listing.
    assert requests == 3
    # The game listed, but a day away.
    late = [_volley_game("Hamar", "Afturelding", ko + timedelta(hours=30))]
    _, miss, _ = _explain(tmp_path / "d", hit, late)
    assert miss["team1"] == {
        "reason": "NO_GAME_IN_WINDOW",
        "nearest_gap_h": 30.0,
        "search_teams": ["Hamar"],
    }
    # A women's game where the board names the men's side.
    women = [{**_volley_game("Hamar", "Afturelding", ko),
              "homeTeam": {"name": "Hamar", "gender": "F"}}]  # fmt: skip
    _, miss, _ = _explain(tmp_path / "e", hit, women)
    assert miss["team1"]["reason"] == "GENDER_REFUSED"


def test_a_miss_reason_reaches_the_settled_record(tmp_path: Path) -> None:
    from bet.sofa.config import SofaConfig
    from bet.sofa.resolve import SofaResolver

    write_snapshot(tmp_path)
    client = _MissClient({}, [])
    resolver = SofaResolver(SofaConfig(), client, _temp_cache(tmp_path))  # type: ignore[arg-type]
    run_settle(tmp_path, resolver, FakeClient({}), 6)
    rec = settled(tmp_path)["1"]
    assert rec["state"] == "NOT_ON_SOFASCORE"
    assert rec["miss"]["team1"]["reason"] == "NO_SEARCH_RESULT"


def test_daily_plan_settles_d_minus_2_so_a_postponed_game_can_void() -> None:
    from bet.sofa.shadow import VOID_AFTER

    _, morning, _ = shadow_daily.plan(DATE, retry_two_before=True)
    settles = [c[2] for c in morning if c[-1] == "SHADOW_SETTLE"]
    assert settles == [DATE, "2026-09-27", "2026-09-26"]
    assert ("scripts/sofa/settle_sport_coupon.py", "2026-09-26", "hockey") in {
        (c[0], c[2], c[-1]) for c in morning
    }
    assert morning[-1][1:] == ["--from", "2026-09-26", "--to", DATE]
    # D-2's 05:15Z settle is past VOID_AFTER even for a 23:59Z start; D-1's
    # is not, which is why D-2 is in the plan.
    latest_start = datetime(2026, 9, 26, 23, 59, tzinfo=UTC)
    d1_settle = datetime(2026, 9, 28, 5, 15, tzinfo=UTC)
    assert d1_settle - latest_start < VOID_AFTER
    assert d1_settle + timedelta(days=1) - latest_start > VOID_AFTER
    _, default, _ = shadow_daily.plan(DATE)
    assert "2026-09-26" not in {c[2] for c in default}


def test_settling_a_player_line_saves_the_lineups(tmp_path: Path) -> None:
    snap = {**_snap("2026-09-28T15:00:00Z", 1.9)}
    snap["lines"] = snap["lines"] + [
        ShadowLine(
            "1", 236265, "player_points", 0, "Player0, Home", 0.5, s, 1.9
        ).as_dict()
        for s in ("OVER", "UNDER")
    ]
    _write_snaps(tmp_path, [snap])
    lineups = {
        "home": {"players": [{"player": {"name": "Home Player0"},
                 "statistics": {"secondsPlayed": 1200, "goals": 4}}]},
        "away": {"players": [{"player": {"name": "Away One"},
                 "statistics": {"secondsPlayed": 1100, "goals": 3}}]},
    }  # fmt: skip
    cache = _temp_cache(tmp_path)
    client = LineupsClient({**sofa_event(), **HOCKEY_AET}, lineups)
    at = datetime(2026, 9, 28, 22, tzinfo=UTC)
    settle_shadow.settle(
        DATE, FakeResolver(sofa_event()), client, cache, str(tmp_path), at, ("hockey",)
    )
    assert settled(tmp_path)["1"]["state"] == "SETTLED"
    assert cache.get_event_lineups(700) == lineups
    # An empty answer is never saved as the fact "nothing published".
    empty_cache = _temp_cache(tmp_path / "empty")
    (tmp_path / "shadow" / "hockey" / DATE / "settled.json").unlink()
    settle_shadow.settle(
        DATE,
        FakeResolver(sofa_event()),
        LineupsClient({**sofa_event(), **HOCKEY_AET}, None),
        empty_cache,
        str(tmp_path),
        at,
        ("hockey",),
    )
    assert empty_cache.get_event_lineups(700) is None


def test_shadow_chains_d1_before_the_morning_and_its_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import timedelta

    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(shadow_daily, "REPO", Path("/"))
    t = {"now": datetime(2026, 10, 2, 4, 20, tzinfo=UTC)}
    events: list[str] = []
    fails = {"n": 1}

    def runner(cmd: list[str]) -> int:
        events.append(Path(cmd[0]).name + (f":{cmd[-1]}" if "--only" in cmd else ""))
        if cmd[-1] == "SHADOW_SETTLE" and fails["n"]:
            fails["n"] -= 1
            return 2
        return 0

    def sleep(s: float) -> None:
        t["now"] += timedelta(seconds=s)

    real_loop = shadow_daily.loop

    def timed_loop(*a: object, **k: object) -> int:
        return real_loop(  # type: ignore[arg-type]
            *a, clock=lambda: t["now"], sleep=sleep, runner=runner, **k
        )

    monkeypatch.setattr(shadow_daily, "loop", timed_loop)

    def spawn(date: str) -> int:
        events.append("spawn")
        return 1

    monkeypatch.setattr("sys.argv", ["shadow_daily", "--date", "2026-10-01", "--chain"])
    assert shadow_daily.main(spawn) == 0
    assert events.count("spawn") == 1
    first_settle = events.index("run_pipeline.py:SHADOW_SETTLE")
    assert events.index("spawn") < first_settle, "D+1 waited for the morning"
    assert events.count("run_pipeline.py:SHADOW_SETTLE") == 2, "one retry"


def test_an_event_that_stops_quoting_is_no_longer_graded_at_its_old_price(
    tmp_path: Path,
) -> None:
    # Review 2026-10-04: a fetch with no lines wrote nothing, so SETTLE graded
    # the last price on file however old (628-707 minutes on four games).
    at = datetime(2026, 9, 28, 14, tzinfo=UTC)
    run_shadow.snapshot(DATE, FakeSuperbet(), str(tmp_path), at=at)  # type: ignore[arg-type]

    class Emptied(FakeSuperbet):
        def event_odds(self, event_id: str) -> dict[str, Any]:
            self.fetched.append(event_id)
            return {"odds": []}

    later = at + timedelta(hours=1)
    res = run_shadow.snapshot(DATE, Emptied(), str(tmp_path), at=later)  # type: ignore[arg-type]
    assert res["metrics"]["hockey"]["emptied"] == 1
    hockey = tmp_path / "shadow" / "hockey" / DATE / "snapshots.jsonl"
    recs = [json.loads(x) for x in hockey.read_text().splitlines()]
    assert [len(r["lines"]) for r in recs] == [2, 0]
    events = latest_pre_kickoff(recs)
    assert not events["1"].sides, "the old price is no longer the last one"


def test_volleyball_takes_the_winner_from_the_sets_when_winner_code_says_draw() -> None:
    # Review 2026-10-04: finished volleyball details with winnerCode 3 and
    # sets that agree with `current` were refused (Weber State 0-3 shape).
    detail = {
        "winnerCode": 3,
        "homeScore": {"current": 0, "period1": 20, "period2": 22, "period3": 19},
        "awayScore": {"current": 3, "period1": 25, "period2": 25, "period3": 25},
    }
    r = build_result(detail, VOLLEYBALL, True)
    assert r is not None
    # sets that do not agree with `current` are still refused
    bad = {**detail, "awayScore": {**detail["awayScore"], "current": 2}}
    assert build_result(bad, VOLLEYBALL, True) is None
    # a 2-1 under code 3 may be an unfinished best-of-five: still refused
    two_one = {
        "winnerCode": 3,
        "homeScore": {"current": 1, "period1": 25, "period2": 20, "period3": 20},
        "awayScore": {"current": 2, "period1": 20, "period2": 25, "period3": 25},
    }
    assert build_result(two_one, VOLLEYBALL, True) is None


def test_an_emptied_event_is_still_settled_and_recut_at_sofascores_start() -> None:
    # Review round 2: settle_sport dropped events whose last record was empty,
    # before settle_one could re-cut at Sofascore's earlier start.
    src = Path(settle_shadow.__file__).read_text(encoding="utf-8")
    assert "del events[eid]" not in src
    recs = [
        {"fetched_at_utc": "2026-10-03T12:23:00Z", "superbet_event_id": "9",
         "match_name": "A·B", "team1": "A", "team2": "B",
         "kickoff_utc": "2026-10-03T13:30:00Z", "tournament": None,
         "lines": [{"superbet_event_id": "9", "family": "winner", "period": 0,
                    "market_id": 1, "subject": "", "side": "T1", "line": None,
                    "odds": 1.12}]},
        {"fetched_at_utc": "2026-10-03T12:40:00Z", "superbet_event_id": "9",
         "match_name": "A·B", "team1": "A", "team2": "B",
         "kickoff_utc": "2026-10-03T13:30:00Z", "tournament": None, "lines": []},
    ]
    assert not latest_pre_kickoff(recs)["9"].sides
    start = datetime(2026, 10, 3, 12, 30, tzinfo=UTC)
    assert latest_pre_kickoff(recs, {"9": start})["9"].sides
