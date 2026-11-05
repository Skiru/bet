"""NCAA men's basketball is played in two halves (2026-11-05 coverage review,
docs/sofa/evidence/pokrycie_sportow_2026-11-05.md): Sofascore publishes two
periods (labelled "1st quarter" / "2nd quarter") adding up to `normaltime`, and
build_result refused every such game as DATA_MISMATCH for not being four
quarters - 136 NCAA D-I games of 10-22..11-04, 0 graded. SHADOW_SETTLE
(allow_final_only) now reads them as halves: h1 / h2 = one period each, no
quarter; the history readers (default) and four-quarter leagues are unchanged,
and a real payload defect is still refused."""

from __future__ import annotations

from typing import Any

from bet.sofa import sport_day as sd
from bet.sofa.score_model import BB_HALVES_COMPETITIONS
from bet.sofa.shadow import SPORTS, ShadowLine, actual_value, build_result

BASKETBALL, HOCKEY = SPORTS["basketball"], SPORTS["hockey"]
NCAA_D1 = 33651
DATE = "2026-11-01"


def _event(home: list[int], away: list[int], code: int, *,
           unique_id: int = NCAA_D1, current: tuple[int, int] | None = None,
           nt: tuple[int, int] | None = None, description: str = "Ended",
           **extra: Any) -> dict[str, Any]:
    h_cur, a_cur = current or (sum(home), sum(away))
    h_nt, a_nt = nt or (sum(home), sum(away))
    h: dict[str, Any] = {"current": h_cur, "display": h_cur, "normaltime": h_nt}
    a: dict[str, Any] = {"current": a_cur, "display": a_cur, "normaltime": a_nt}
    for i, (x, y) in enumerate(zip(home, away, strict=True), start=1):
        h[f"period{i}"], a[f"period{i}"] = x, y
    labels = {"current": "Score", "period1": "1st quarter",
              "period2": "2nd quarter", "period3": "3rd quarter",
              "period4": "4th quarter", "overtime": "Overtime"}
    return {"status": {"type": "finished", "description": description},
            "winnerCode": code, "homeScore": h, "awayScore": a,
            "periods": labels, "defaultPeriodCount": 4,
            "tournament": {"name": "NCAA Men's Division I, Regular season",
                           "uniqueTournament": {"id": unique_id}}, **extra}


def _line(market_id: int, family: str, side: str, value: float | None = None,
          period: int = 0, subject: str = "") -> ShadowLine:
    return ShadowLine("1", market_id, family, period, subject, value, side, 1.9)


def test_ncaa_two_halves_grade_halves_and_full_game_never_quarters() -> None:
    # 16759340 of 2026-11-01: 31+43 = 74, 35+37 = 72, normaltime 74 / 72.
    assert NCAA_D1 in BB_HALVES_COMPETITIONS
    detail = _event([31, 43], [35, 37], 1)
    assert build_result(detail, BASKETBALL, True) is None  # history: unchanged
    r = build_result(detail, BASKETBALL, True, allow_final_only=True)
    assert r is not None and r.halves and not r.final_only and not r.overtime
    assert (r.t1_full, r.t2_full, r.winner) == (74, 72, "T1")
    assert actual_value(_line(753, "total", "OVER", 140.5), r, BASKETBALL) == 146.0
    assert actual_value(_line(768, "handicap", "T1", -1.5), r, BASKETBALL) == 2.0
    assert actual_value(_line(777, "result_1x2", "T1"), r, BASKETBALL) == 2.0
    # a half is one period, not the sum of the first two
    assert actual_value(_line(748, "h1_total", "OVER", 65.5), r, BASKETBALL) == 66.0
    assert actual_value(_line(773, "h1_handicap", "T1", 2.5), r, BASKETBALL) == -4.0
    assert actual_value(_line(233404, "h2_total", "OVER", 79.5), r, BASKETBALL) == 80.0
    assert actual_value(_line(233806, "h2_team_total", "OVER", 40.5,
                              subject="T1"), r, BASKETBALL) == 43.0
    # no quarter can be told from two halves
    for q in (1, 2, 3, 4):
        assert actual_value(_line(788, "quarter_total", "OVER", 35.5, period=q),
                            r, BASKETBALL) is None


def test_ncaa_halves_orientation_swaps() -> None:
    r = build_result(_event([34, 23], [37, 35], 2), BASKETBALL, False,
                     allow_final_only=True)
    assert r is not None and r.halves and r.winner == "T1"
    assert (r.t1_full, r.t2_full) == (72, 57)
    assert actual_value(_line(748, "h1_total", "OVER", 70.5), r, BASKETBALL) == 71.0
    assert actual_value(_line(233405, "h2_handicap", "T1", -10.5),
                        r, BASKETBALL) == 12.0


def test_ncaa_halves_with_overtime_keep_the_second_half_on_regulation() -> None:
    # Overtime after a level regulation: the full game counts it, h2 does not.
    detail = _event([35, 35], [30, 40], 1, current=(78, 74),
                    nt=(70, 70), description="AET")
    detail["homeScore"]["overtime"], detail["awayScore"]["overtime"] = 8, 4
    r = build_result(detail, BASKETBALL, True, allow_final_only=True)
    assert r is not None and r.halves and r.overtime and r.winner == "T1"
    assert actual_value(_line(753, "total", "OVER", 150.5), r, BASKETBALL) == 152.0
    assert actual_value(_line(233404, "h2_total", "OVER", 74.5), r, BASKETBALL) == 75.0
    assert actual_value(_line(777, "result_1x2", "T1"), r, BASKETBALL) == 0.0


def test_ncaa_halves_still_refuse_a_real_payload_defect() -> None:
    for detail in (
        _event([31, 43], [35, 37], 1, nt=(70, 72)),        # halves != normaltime
        _event([31, 43], [35, 37], 2),                     # winner disagrees
        _event([31, 43], [35, 37], 1, current=(80, 72)),   # past regulation, not level
        _event([31, 43, 10], [35, 37, 9], 1),              # three periods
    ):
        assert build_result(detail, BASKETBALL, True, allow_final_only=True) is None


def test_two_periods_outside_a_halves_competition_stay_refused() -> None:
    # A quarter league with two periods published is unfinished data, not halves.
    detail = _event([31, 43], [35, 37], 1, unique_id=1520)
    assert build_result(detail, BASKETBALL, True, allow_final_only=True) is None
    no_tournament = _event([31, 43], [35, 37], 1)
    del no_tournament["tournament"]
    assert build_result(no_tournament, BASKETBALL, True,
                        allow_final_only=True) is None
    # hockey never reads halves
    assert build_result(_event([1, 2], [0, 1], 1), HOCKEY, True,
                        allow_final_only=True) is None


def test_four_quarter_ncaa_game_is_read_as_quarters() -> None:
    r = build_result(_event([20, 18, 15, 21], [17, 19, 16, 20], 1),
                     BASKETBALL, True, allow_final_only=True)
    assert r is not None and not r.halves
    assert actual_value(_line(748, "h1_total", "OVER", 70.5), r, BASKETBALL) == 74.0


def test_a_stored_halves_event_grades_coupon_legs_by_half() -> None:
    # As SHADOW_SETTLE writes it (settle_shadow: score_source "halves"), read
    # back by the coupon's grader (sport_day.grade_legs).
    ev = {"state": "SETTLED", "t1_periods": [31, 43], "t2_periods": [35, 37],
          "t1_full": 74, "t2_full": 72, "overtime": False, "winner": "T1",
          "score_source": "halves"}
    base = {"superbet_event_id": "7", "period": 0, "subject": "", "odds": 1.8,
            "kickoff_utc": "2026-11-01T23:00:00Z"}
    legs = [{**base, "market_id": 748, "family": "h1_total", "line": 65.5,
             "side": "OVER"},
            {**base, "market_id": 233404, "family": "h2_total", "line": 79.5,
             "side": "UNDER"},
            {**base, "market_id": 788, "family": "quarter_total", "line": 35.5,
             "side": "OVER", "period": 1}]
    graded = sd.grade_legs({"sport": "basketball", "date": DATE, "legs": legs},
                           {DATE: {"events": {"7": ev}}})
    assert [g["outcome"] for g in graded] == ["WIN", "LOSS", "UNGRADEABLE"]
