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
import json
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
    def test_check_agrees_with_the_config_on_disk(self) -> None:
        """The live audit and ``config/sample_drift.json`` must tell one story.

        This replaces ``test_no_bettable_market_has_drifted``, which asserted
        ``--check`` exits 0 and had been failing since ``cards_points_*`` was
        measured. That assertion was not wrong so much as unsatisfiable by any
        code change: whether a market's sample drifts is a property of the
        *slates on disk*, not of this repository, and the drift is real --
        ``cards_points_total`` runs 0.55 low over 266 settled fixtures
        (z=+3.86), ``cards_points_for`` 0.28 over 525 (z=+3.84), and project
        memory records the cause as competition mix rather than a transcription
        fault. Nothing in ``src/`` can make that exit 0, so as a guard it could
        only ever be silenced or left red, and left red it would have been the
        one permanently failing test in the suite -- which is how a suite stops
        being read.

        What the repository *can* guarantee, and what actually protects money,
        is that the drift is never silent: ``config/sample_drift.json`` records
        it and ``test_sample_drift_reaches_the_artifacts.py`` asserts it reaches
        the forecast card and every coupon row. So the invariant here becomes
        agreement between the measurement and the config built from it.

        It can fail in both directions, which is the point. A market that
        starts drifting and is not in the config fails. A market that stops
        drifting -- because the sample definition was fixed, or the mix of
        slates changed -- also fails, and must, because the caveats downstream
        would then be warning about an error that is gone.
        """
        if not (ROOT / "runs" / "_backtest_actuals.json").exists():
            pytest.skip("no settled slates on disk")
        config_path = ROOT / "config" / "sample_drift.json"
        if not config_path.exists():
            pytest.skip("config/sample_drift.json not built yet")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        recorded = {
            market
            for market, entry in (config.get("markets") or {}).items()
            if entry.get("drifted") is True
        }
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--check"],
            capture_output=True, text=True, timeout=900,
        )
        # The drifted markets are the ones --check names on stderr, one per
        # line as "  <market>: ...". Parsed rather than re-derived so this
        # tests the script's own verdict and not a copy of its arithmetic.
        live = {
            line.strip().split(":")[0]
            for line in result.stderr.splitlines()
            if line.startswith("  ") and ":" in line
        }
        assert live == recorded, (
            f"the live audit and config/sample_drift.json disagree about which "
            f"markets drift: only live {sorted(live - recorded)}, only in "
            f"config {sorted(recorded - live)}. Re-run "
            f"`python3 scripts/simple/audit_sample_bias.py --write`, and if a "
            f"market has stopped drifting check the caveats it was raising."
        )
        expected_exit = 1 if recorded else 0
        assert result.returncode == expected_exit, (
            f"--check exited {result.returncode}, expected {expected_exit} for "
            f"{len(recorded)} drifted market(s)\n{result.stdout}{result.stderr}"
        )


class TestTheWrittenConfig:
    def test_write_is_deterministic(self, tmp_path) -> None:
        """Two passes over the same slates must produce identical bytes.

        A wall-clock stamp in the document would break this, which is why
        ``_measured_over`` is derived from the slate dates instead. Without it
        every regeneration shows as a diff and the config stops being
        reviewable.
        """
        if not (ROOT / "runs" / "_backtest_actuals.json").exists():
            pytest.skip("no settled slates on disk")
        first, second = tmp_path / "a.json", tmp_path / "b.json"
        for out in (first, second):
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--write", "--out", str(out)],
                capture_output=True, text=True, timeout=900,
            )
            assert out.exists(), result.stdout + result.stderr
        assert first.read_bytes() == second.read_bytes()

    def test_every_market_records_the_side_the_drift_flatters(
        self, audit
    ) -> None:
        """``overstated_side`` follows the sign of ``delta``, every time.

        Written into the config so no consumer re-derives it. A positive delta
        is *actual above sample*, i.e. a sample running low, which inflates
        UNDER.
        """
        rows = [
            {"market": "high", "n": 100, "delta": 0.5, "se": 0.1, "z": 5.0,
             "priced": True},
            {"market": "low", "n": 100, "delta": -0.5, "se": 0.1, "z": -5.0,
             "priced": True},
        ]
        markets = audit.document(rows, {"2026-09-01"})["markets"]
        assert markets["high"]["overstated_side"] == "UNDER"
        assert markets["low"]["overstated_side"] == "OVER"

    def test_a_market_the_book_does_not_price_is_recorded_but_not_drifted(
        self, audit
    ) -> None:
        """``cards_total`` is the live case: real drift, unreachable by a bet.

        It has to appear -- a reader must be able to tell "checked, drifts,
        cannot be bet" from "never checked" -- and it must not raise a caveat,
        because a warning about a market Superbet does not post would train the
        operator to ignore the ones that matter.
        """
        rows = [
            {"market": "unpriced", "n": 300, "delta": 0.42, "se": 0.11,
             "z": 3.78, "priced": False},
        ]
        entry = audit.document(rows, {"2026-09-01"})["markets"]["unpriced"]
        assert entry["priced"] is False
        assert entry["drifted"] is False

    def test_a_thin_market_is_recorded_but_not_drifted(self, audit) -> None:
        """Below ``MIN_FIXTURES`` the SE is too wide for |z| to mean anything."""
        rows = [
            {"market": "thin", "n": 5, "delta": 3.0, "se": 0.2, "z": 15.0,
             "priced": True},
        ]
        entry = audit.document(rows, {"2026-09-01"})["markets"]["thin"]
        assert entry["fixtures"] == 5
        assert entry["drifted"] is False
