"""A basketball / hockey game Sofascore published with its final score and no
period (2026-10-12 audit of 2026-10-11): 18 of 22 basketball DATA_MISMATCH -
Australian NBL, Bulgarian NBL, Serie B, Austrian and Greek women's leagues -
had `current` and `winnerCode` and no `period1..4`; build_result refused them
whole, so even a full-game winner / total printed on the coupon never graded.
SHADOW_SETTLE now grades the full game (and regulation, where it can be
told) from the final score; every period market stays ungradeable, and the
history readers (default allow_final_only=False) see nothing new."""

from __future__ import annotations

from typing import Any

from bet.sofa import sport_day as sd
from bet.sofa.shadow import SPORTS, ShadowLine, actual_value, build_result, grade

BASKETBALL, HOCKEY = SPORTS["basketball"], SPORTS["hockey"]
DATE = "2026-10-11"


def _event(h: int, a: int, code: int, description: str = "Ended",
           nt: tuple[int, int] | None = None, **extra: Any) -> dict[str, Any]:
    home: dict[str, Any] = {"current": h, "display": h}
    away: dict[str, Any] = {"current": a, "display": a}
    if nt is not None:
        home["normaltime"], away["normaltime"] = nt
    return {"status": {"type": "finished", "description": description},
            "winnerCode": code, "homeScore": home, "awayScore": away,
            "defaultPeriodCount": 4, **extra}


def _line(market_id: int, family: str, side: str, value: float | None = None,
          period: int = 0, subject: str = "") -> ShadowLine:
    return ShadowLine("1", market_id, family, period, subject, value, side, 1.9)


def test_final_only_grades_the_full_game_and_nothing_by_period() -> None:
    # 16465734 UBSC Graz - Klosterneuburg, 10-11: Ended, 102-94, no periods.
    detail = _event(102, 94, 1)
    assert build_result(detail, BASKETBALL, True) is None  # history: unchanged
    r = build_result(detail, BASKETBALL, True, allow_final_only=True)
    assert r is not None and r.final_only and r.winner == "T1"
    assert r.reg_score == (102, 94) and not r.overtime
    win = _line(759, "winner", "T1")
    assert grade(win, actual_value(win, r, BASKETBALL) or 0) == "WIN"
    assert actual_value(_line(753, "total", "OVER", 190.5), r, BASKETBALL) == 196.0
    assert actual_value(_line(768, "handicap", "T1", -5.5), r, BASKETBALL) == 8.0
    assert actual_value(_line(776, "team_total", "OVER", 90.5, subject="T2"),
                        r, BASKETBALL) == 94.0
    # regulation 1x2: nothing says the game went past regulation
    assert actual_value(_line(777, "result_1x2", "T1"), r, BASKETBALL) == 8.0
    # every period / half market: unknown, never 0
    for mid, fam, per in ((788, "quarter_total", 4), (748, "h1_total", 0),
                          (233404, "h2_total", 0)):
        assert actual_value(_line(mid, fam, "OVER", 40.5, period=per),
                            r, BASKETBALL) is None


def test_final_only_regulation_comes_from_normaltime_and_orientation_swaps() -> None:
    # 16624629 Amyntas - Olympiacos (women), 10-11: normaltime printed, 60-68.
    r = build_result(_event(60, 68, 2, nt=(60, 68)), BASKETBALL, False,
                     allow_final_only=True)
    assert r is not None and r.winner == "T1"  # away won, away is team1
    assert (r.t1_full, r.t2_full, r.reg_score) == (68, 60, (68, 60))
    hcp = _line(768, "handicap", "T1", 23.5)
    assert actual_value(hcp, r, BASKETBALL) == 8.0


def test_final_only_after_overtime_grades_the_full_game_but_not_regulation() -> None:
    aet = build_result(_event(98, 92, 1, "AET"), BASKETBALL, True,
                       allow_final_only=True)
    assert aet is not None and aet.overtime and aet.reg_score is None
    assert actual_value(_line(753, "total", "OVER", 180.5), aet, BASKETBALL) == 190.0
    assert actual_value(_line(777, "result_1x2", "T1"), aet, BASKETBALL) is None
    told = build_result(_event(98, 92, 1, "AET", nt=(88, 88)), BASKETBALL, True,
                        allow_final_only=True)
    assert told is not None and told.reg_score == (88, 88)
    # overtime is played only from a level regulation score
    assert build_result(_event(98, 92, 1, "AET", nt=(90, 88)), BASKETBALL, True,
                        allow_final_only=True) is None


def test_final_only_refuses_a_score_that_does_not_agree_with_the_winner() -> None:
    for detail in (
        _event(63, 65, 1),                  # home "won" with fewer points
        _event(80, 80, 1),                  # level, no shootout
        _event(80, 70, 3),                  # a draw that is not level
        _event(80, 70, 7),                  # no winner code
        _event(80, 70, 1, nt=(81, 70)),     # regulation above the final
        {**_event(80, 70, 1), "isAwarded": True},
    ):
        assert build_result(detail, BASKETBALL, True, allow_final_only=True) is None
    # periods on one side only is still the old refusal, not final_only
    half = _event(80, 70, 1)
    half["homeScore"]["period1"] = 20
    assert build_result(half, BASKETBALL, True, allow_final_only=True) is None


def test_final_only_hockey_shootout_keeps_sofascores_winner() -> None:
    r = build_result(_event(3, 3, 2, "AP", nt=(3, 3)), HOCKEY, True,
                     allow_final_only=True)
    assert r is not None and r.winner == "T2" and r.reg_score == (3, 3)
    assert actual_value(_line(623, "total", "OVER", 5.5), r, HOCKEY) == 6.0


def test_a_stored_final_only_event_grades_coupon_legs_from_its_full_score() -> None:
    # As SHADOW_SETTLE writes it (settle_shadow: score_source / t1_reg / t2_reg),
    # read back by the coupon's grader (sport_day.grade_legs).
    ev = {"state": "SETTLED", "t1_periods": [], "t2_periods": [],
          "t1_full": 102, "t2_full": 94, "overtime": False, "winner": "T1",
          "score_source": "final_only", "t1_reg": 102, "t2_reg": 94}
    base = {"superbet_event_id": "7", "period": 0, "subject": "", "odds": 1.6,
            "kickoff_utc": "2026-10-11T17:00:00Z"}
    legs = [{**base, "market_id": 759, "family": "winner", "line": None, "side": "T1"},
            {**base, "market_id": 753, "family": "total", "line": 199.5,
             "side": "OVER"},
            {**base, "market_id": 788, "family": "quarter_total", "line": 40.5,
             "side": "OVER", "period": 4}]
    graded = sd.grade_legs({"sport": "basketball", "date": DATE, "legs": legs},
                           {DATE: {"events": {"7": ev}}})
    assert [g["outcome"] for g in graded] == ["WIN", "LOSS", "UNGRADEABLE"]
