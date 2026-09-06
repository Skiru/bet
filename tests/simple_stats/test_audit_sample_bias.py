"""The sample-bias guard: does a market's sample measure what the book settles?

The failure this catches is the one that hides best. ``p_low``, ``p_central``,
the shrink and the ladder gates are all internally consistent with a sample
that counts the wrong thing, so a definition mismatch reads as bad luck for as
long as nobody subtracts the sample's mean from what actually happened.
``cards_total`` counted yellows while Superbet counted reds too, and it took a
hand audit of one slip to find it.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "simple" / "audit_sample_bias.py"


def _module():
    spec = importlib.util.spec_from_file_location("audit_sample_bias", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def audit():
    return _module()


class TestReport:
    def test_a_centred_market_passes(self, audit) -> None:
        # Noise around zero, no drift.
        deltas = {"corners_total": [0.5, -0.5, 0.4, -0.4, 0.1, -0.1] * 8}
        rows, drifted = audit.report(deltas, {"corners_total"})
        assert drifted == []
        assert rows[0]["n"] == 48

    def test_a_market_that_always_lands_above_its_sample_fails(self, audit) -> None:
        # Every fixture comes in half a card over what the sample said: this is
        # the shape of a yellow-only sample against a book counting reds.
        deltas = {"cards_total": [0.5, 0.6, 0.4, 0.5, 0.6, 0.4] * 8}
        _, drifted = audit.report(deltas, {"cards_total"})
        assert [r["market"] for r in drifted] == ["cards_total"]
        assert drifted[0]["z"] > audit.MAX_ABS_Z

    def test_a_thin_market_is_reported_and_never_failed_on(self, audit) -> None:
        # Below the floor the SE is too wide for |z| > 3 to mean anything, and
        # a newly added market must not block every run until it has history.
        deltas = {"breaks_total": [0.5] * (audit.MIN_FIXTURES - 1)}
        rows, drifted = audit.report(deltas, {"breaks_total"})
        assert drifted == []
        assert rows[0]["n"] == audit.MIN_FIXTURES - 1

    def test_drift_in_a_market_the_book_does_not_price_is_reported_not_failed(
        self, audit
    ) -> None:
        # The live ``cards_total`` case: really drifted, really unbettable,
        # because every card line Superbet posts now maps to cards_points_*.
        deltas = {"cards_total": [0.5, 0.6, 0.4, 0.5, 0.6, 0.4] * 8}
        rows, drifted = audit.report(deltas, {"cards_points_total"})
        assert drifted == []
        assert rows[0]["priced"] is False
        assert abs(rows[0]["z"]) > audit.MAX_ABS_Z

    def test_priced_none_means_check_everything(self, audit) -> None:
        # No offer artifact on disk: fail closed rather than silently pass a
        # drifted market because nothing said it was bettable.
        deltas = {"cards_total": [0.5, 0.6, 0.4, 0.5, 0.6, 0.4] * 8}
        _, drifted = audit.report(deltas, None)
        assert [r["market"] for r in drifted] == ["cards_total"]


class TestPricedMarkets:
    def test_only_the_newest_slates_define_what_is_bettable(self, audit, tmp_path) -> None:
        # Superbet's card lines mapped to cards_total until 2026-09-02 and to
        # cards_points_total from 09-03. A set built from all history would
        # keep failing on a mapping that was fixed a week ago.
        def write(date: str, market: str) -> None:
            run = tmp_path / date
            run.mkdir()
            (run / f"{date}_superbet_offer.json").write_text(
                '{"events": [{"lines": [{"market": "%s"}]}]}' % market,
                encoding="utf-8",
            )
        write("2026-09-01", "cards_total")
        write("2026-09-05", "cards_points_total")
        write("2026-09-06", "cards_points_total")
        assert audit.priced_markets(tmp_path) == {"cards_points_total"}


class TestAgainstTheRealRepository:
    def test_no_bettable_market_has_drifted(self) -> None:
        """The assertion that makes this a guard rather than a report."""
        if not (ROOT / "runs" / "_backtest_actuals.json").exists():
            pytest.skip("no settled slates on disk")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--check"],
            capture_output=True, text=True, timeout=900,
        )
        assert result.returncode == 0, result.stdout + result.stderr
