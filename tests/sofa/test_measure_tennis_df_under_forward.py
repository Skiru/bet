"""T-TENNIS-DF-UNDER-FORWARD: the frozen rule's verdict (scripts/sofa/
measure_tennis_df_under_forward.py), judged only at the required n."""

from __future__ import annotations

from scripts.sofa.measure_tennis_df_under_forward import frozen_verdict


def test_no_verdict_below_the_required_n() -> None:
    assert frozen_verdict(399, 200, 0.05, 0.20) is None
    assert frozen_verdict(500, 119, 0.05, 0.20) is None


def test_the_frozen_rule_at_the_required_n() -> None:
    assert frozen_verdict(400, 120, 0.001, 0.20) == "PASSED"
    assert frozen_verdict(400, 120, -0.30, 0.019) == "FAILED"
    # 2026-11-05: 500 legs / 129 matches, ROI -1.6% [-15.9, +12.5]
    assert frozen_verdict(500, 129, -0.159, 0.125) == "NOT_PASSED"
