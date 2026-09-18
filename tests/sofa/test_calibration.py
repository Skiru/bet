"""The calibration path — measured from the cache, applied by the sheet.

`config/sofa_market_reliability.json` was `{}` for the life of this pipeline,
not because the measurement is hard but because the only route to it went
through a provider that has been refusing connections. Every row therefore
shipped with an uncorrected `p_central`, and the coupon inherited it: on
2026-09-18 every coupon row sat above the devigged market price with nothing
measured to say whether that was edge or error.
"""

import json
from pathlib import Path

import pytest

from scripts.sofa.run_sheet import get_calibration_correction


class TestCorrectionLookup:
    def test_a_measured_bucket_is_used(self) -> None:
        reliability = {
            "goals_total": {
                "0.2-0.3": {"correction": 0.0352, "n": 76745, "status": "MEASURED"}
            }
        }
        assert get_calibration_correction(
            reliability, "goals_total", 0.25
        ) == pytest.approx(0.0352)

    def test_a_thin_market_falls_back_to_the_pooled_curve(self) -> None:
        """Zero is not the neutral answer it looks like.

        A market with too few rows of its own used to get exactly zero, which
        asserts the estimator is calibrated there while the pooled measurement
        — 1.5M rows — says it is not.
        """
        reliability = {
            "offsides_for": {
                "0.2-0.3": {"correction": 0.0, "n": 12, "status": "TOO_FEW_ROWS"}
            },
            "_pooled": {
                "0.2-0.3": {"correction": 0.0236, "n": 175934, "status": "MEASURED"}
            },
        }
        assert get_calibration_correction(
            reliability, "offsides_for", 0.25
        ) == pytest.approx(0.0236)

    def test_an_unknown_market_still_gets_the_pooled_correction(self) -> None:
        reliability = {
            "_pooled": {
                "0.3-0.4": {"correction": 0.0243, "n": 137011, "status": "MEASURED"}
            }
        }
        assert get_calibration_correction(
            reliability, "something_new", 0.35
        ) == pytest.approx(0.0243)

    def test_an_empty_curve_corrects_nothing(self) -> None:
        assert get_calibration_correction({}, "goals_total", 0.25) == 0.0

    def test_a_negative_correction_cannot_become_a_discount(self) -> None:
        """The engine may raise the bar. It may never lower it.

        A hand-edited or mis-fitted file must not be able to turn a measured
        underconfidence into a reason to bet more.
        """
        reliability = {
            "goals_total": {
                "0.7-0.8": {"correction": -0.05, "n": 99999, "status": "MEASURED"}
            }
        }
        assert get_calibration_correction(reliability, "goals_total", 0.75) == 0.0


class TestShippedCurve:
    """Guards on the file the engine actually reads."""

    def _curve(self) -> dict:
        path = Path("config/sofa_market_reliability.json")
        if not path.exists():
            pytest.skip("reliability curve not generated in this checkout")
        return json.loads(path.read_text(encoding="utf-8"))

    def test_the_curve_is_not_empty(self) -> None:
        curve = self._curve()
        markets = [k for k in curve if not k.startswith("_")]
        assert markets, "an empty curve silently ships an uncorrected model"

    def test_a_pooled_fallback_exists(self) -> None:
        assert "_pooled" in self._curve()

    def test_no_correction_is_negative(self) -> None:
        for market, entry in self._curve().items():
            if market.startswith("_doc"):
                continue
            if not isinstance(entry, dict):
                continue
            for bucket, value in entry.items():
                if isinstance(value, dict) and "correction" in value:
                    assert value["correction"] >= 0.0, f"{market} {bucket}"

    def test_corrections_concentrate_below_the_middle(self) -> None:
        """Measured shape: overconfident low, underconfident high.

        The estimator overstates small probabilities and understates large
        ones, antisymmetrically — it must, since OVER and UNDER of one rung are
        complements. Since only overconfidence is corrected, every non-zero
        correction in the pooled curve has to sit in the lower half. A curve
        that corrected the top half would mean the sign had been inverted.
        """
        pooled = self._curve().get("_pooled", {})
        for bucket, value in pooled.items():
            if value.get("correction", 0.0) > 0:
                assert float(bucket.split("-")[0]) < 0.5, bucket
