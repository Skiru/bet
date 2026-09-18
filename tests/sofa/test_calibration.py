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

    def test_no_correction_is_large_enough_to_be_doing_the_model_s_job(
        self,
    ) -> None:
        """The curve trims a residual; it must never carry the estimate.

        This replaced an assertion that every non-zero correction sits below
        p = 0.5. That held while the estimator was badly miscalibrated low —
        corrections of 0.0196-0.0243 across 0.1-0.4 and nothing above — and it
        stopped holding once F41/F44 landed. The measured curve is now near
        calibrated on both sides (largest pooled correction 0.0108, most
        buckets exactly zero), and small residuals of either sign are what a
        well-fitted model looks like, not a sign inversion.

        What is worth pinning is the magnitude. A correction is a trim: if one
        ever grew past a few points of probability, the curve would be
        substituting for an estimator that needs fixing, and everything
        downstream would rest on the fit rather than on the sample.
        """
        curve = self._curve()

        # Pooled: the estimator across everything. This one has to be small,
        # or the model is wrong in a way no per-market trim can excuse.
        pooled = curve.get("_pooled", {})
        pooled_largest = max(
            (float(v.get("correction", 0.0)) for v in pooled.values()),
            default=0.0,
        )
        assert pooled_largest <= 0.02, f"pooled correction {pooled_largest}"

        # Per market and per direction the residual is genuinely larger, and
        # naming the ceiling is the point. Once the direction layer landed
        # (F48) the largest are games_total|OVER at 0.1548/0.1499 on n=643/722
        # and goals_for|OVER at 0.1315 on n=31,681 — real, well-evidenced
        # biases that the pooled curve cancelled to nothing because OVER and
        # UNDER are exact complements. Those are markets to distrust, not
        # curve noise, and if any ever passes this bound the estimator has
        # drifted somewhere new.
        largest = 0.0
        where = ""
        for market, buckets in curve.items():
            if not isinstance(buckets, dict):
                continue
            for bucket, value in buckets.items():
                if not isinstance(value, dict):
                    continue
                correction = float(value.get("correction", 0.0))
                if correction > largest:
                    largest, where = correction, f"{market} {bucket}"
        assert largest <= 0.20, f"{where} corrects by {largest}"
