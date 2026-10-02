"""A tennis p already pulled onto the price takes no reliability correction
(measured 2026-10-02: it made Brier worse on both event-id halves); a
sample-based row keeps it."""

from __future__ import annotations

from scripts.sofa.run_sheet import row_correction

RELIABILITY = {
    "games_total|OVER": {
        "0.7-0.8": {"status": "MEASURED", "correction": 0.09, "n": 4000}
    }
}


def test_a_price_anchored_row_is_not_corrected() -> None:
    assert row_correction(RELIABILITY, "games_total", 0.75, "OVER", True) == 0.0


def test_a_sample_based_row_keeps_its_correction() -> None:
    assert row_correction(RELIABILITY, "games_total", 0.75, "OVER", False) > 0.0
