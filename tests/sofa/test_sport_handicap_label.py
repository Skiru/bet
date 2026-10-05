"""A measured sport's handicap prints as the side's own (2026-10-05 verifier).

The leg's `line` is team 1's handicap; SETTLE grades it so. The PDF printed
"Herlev Eagles -1.5 T2" @1.30 where Superbet's outcome was "Herlev Eagles
(1.5)" - the label named a different bet from the one priced and graded.
"""

from __future__ import annotations

from bet.sofa import coupon_sports as cs
from bet.sofa import leg_relations as lr


def _leg(line: float | None, side: str, family: str = "handicap",
         sport: str = "hockey") -> dict[str, object]:
    return {"sport": sport, "family": family, "market": family, "line": line,
            "side": side, "direction": side}


def test_t2_handicap_is_the_opposite_of_team1s_line() -> None:
    # Sonderjyske - Herlev, 10-05: line -1.5 (Sonderjyske -1.5 @3.15), T2 @1.30
    assert cs.display_line(_leg(-1.5, "T2")) == "+1.5"
    # Rodovre - Esbjerg: line -0.5, T2 @1.27 = "Esbjerg Energy (0.5)"
    assert cs.display_line(_leg(-0.5, "T2")) == "+0.5"


def test_t1_handicap_keeps_its_line_signed() -> None:
    # Ceske Budejovice +1.5 (T1) printed right before and after
    assert cs.display_line(_leg(1.5, "T1")) == "+1.5"
    assert cs.display_line(_leg(-2.5, "T1")) == "-2.5"


def test_every_measured_handicap_family_and_cs2() -> None:
    assert cs.display_line(_leg(-3.5, "T2", "points_handicap", "basketball")) == "+3.5"
    assert cs.display_line(_leg(1.5, "T2", "maps_handicap", "cs2")) == "-1.5"
    assert cs.display_line(_leg(-1.5, "T2", "period_handicap")) == "+1.5"


def test_totals_and_sheet_legs_are_unchanged() -> None:
    assert cs.display_line(_leg(5.5, "OVER", "total")) == "5.5"
    football = {"market": "handicap_corners", "line": -1.5, "direction": "T2"}
    assert cs.display_line(football) == "-1.5"
    assert cs.display_line(_leg(None, "T1", "winner")) == ""


def test_ladder_rung_carries_the_sport_for_the_label() -> None:
    ref = lr.leg_ref({"sport": "hockey", "family": "handicap", "line": -1.5,
                      "side": "T2"})
    assert ref["sport"] == "hockey"
    assert cs.display_line(ref) == "+1.5"
