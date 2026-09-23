"""One lost leg loses a slip, even if another leg is still unsettled.

2026-09-22: the Accrington slip had a leg LOSS in 07_settled.json and was
reported as unsettled, so section 7c's ROI read -17.7% instead of about -34%.
"""

from scripts.sofa.audit_settlement import slip_status


def test_a_lost_leg_decides_before_an_unsettled_one():
    assert slip_status(["LOSS", None]) == "NIE WESZŁO"
    assert slip_status([None, "LOSS"]) == "NIE WESZŁO"


def test_unsettled_only_when_nothing_has_lost():
    assert slip_status(["WIN", None]) == "NIEROZLICZONY"
    assert slip_status(["WIN", "PUSH"]) == "NIEROZLICZONY"


def test_every_leg_won():
    assert slip_status(["WIN", "WIN"]) == "WESZŁO"


def test_the_pdf_singles_are_graded_at_their_printed_odds():
    """2026-09-23's PDF printed 216 singles and no builder; section 7c
    graded builders only and would have said nothing about that page."""
    from scripts.sofa.audit_settlement import settle_singles

    singles = [
        {"sofascore_event_id": 1, "market": "m", "subject": "a", "line": 4.5,
         "direction": "OVER", "confidence": 0.8, "offered_odds": 1.40},
        {"sofascore_event_id": 2, "market": "m", "subject": None, "line": 2.5,
         "direction": "UNDER", "confidence": 0.7, "offered_odds": 1.50},
        {"sofascore_event_id": 3, "market": "m", "subject": "c", "line": 1.5,
         "direction": "OVER", "confidence": 0.75, "offered_odds": 1.30},
    ]
    by_key = {
        (1, "m", "a", 4.5, "OVER"): {"outcome": "WIN"},
        (2, "m", "", 2.5, "UNDER"): {"outcome": "LOSS"},
    }
    res = settle_singles(singles, by_key)
    assert (res["won"], res["lost"], res["unsettled"]) == (1, 1, 1)
    assert abs(res["units"] - (0.40 - 1.0)) < 1e-12


def test_section_7_does_not_call_the_value_singles_the_coupon():
    """CLAUDE.md: 06_coupon.json is not the coupon, the PDF is."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[2]
           / "scripts/sofa/audit_settlement.py").read_text(encoding="utf-8")
    assert "Kupon — co faktycznie poszło na typ" not in src
    assert "Brak pliku kuponu." not in src
