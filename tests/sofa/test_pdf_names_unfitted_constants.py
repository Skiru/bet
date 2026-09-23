"""The PDF is the coupon, so it must carry UNFITTED_CONSTANTS (2026-09-23).

Every sheet row said it and the page the operator stakes from said it zero
times - which is stripping it by omission.
"""

import sys

from scripts.sofa.build_coupon_pdf import unfitted_constants


def test_the_constants_of_printed_rows_are_collected():
    rows = [
        {"sofascore_event_id": 1, "market": "m", "subject": "a", "line": 4.5,
         "direction": "OVER",
         "notes": ["UNFITTED_CONSTANTS: K_PRICE, K_TENNIS_LADDER_CENTRE"]},
        {"sofascore_event_id": 2, "market": "m", "subject": "b", "line": 4.5,
         "direction": "OVER", "notes": ["UNFITTED_CONSTANTS: SOMETHING_ELSE"]},
    ]
    printed = {(1, "m", "a", 4.5, "OVER")}
    assert unfitted_constants(rows, printed) == ["K_PRICE", "K_TENNIS_LADDER_CENTRE"]


def test_the_page_renders_them():
    import inspect

    import scripts.sofa.build_coupon_pdf as pdf

    src = inspect.getsource(pdf.main)
    assert "unfitted_constants(sheet_rows, printed)" in src
    assert "UNFITTED_CONSTANTS:" in src
    assert sys.modules["scripts.sofa.build_coupon_pdf"] is pdf
