"""A derived joint reads its history curve only from
epochs.DERIVED_CURVES_FROM_UTC (off): until then CONFIDENCE and
fit_line_evidence read it through its settled Superbet lines alone."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from bet.sofa import epochs
from bet.sofa.confidence import Calibration


def test_the_switch_is_off_and_asks_day_and_clock(monkeypatch) -> None:
    assert not epochs.derived_curves("2099-01-01")
    at = datetime(2026, 10, 9, 6, tzinfo=UTC)
    monkeypatch.setattr(epochs, "DERIVED_CURVES_FROM_UTC", at)
    assert epochs.derived_curves("2026-10-09", at)
    assert not epochs.derived_curves("2026-10-08", at)
    assert not epochs.derived_curves("2026-10-09", at.replace(hour=5))


def test_a_fitted_derived_key_is_served_by_the_calibration(tmp_path: Path) -> None:
    path = tmp_path / "cal.json"
    path.write_text(json.dumps({"by_market_direction": {"handicap_games|OVER": {
        "0.800-0.825": {"n": 900, "realised": 0.81, "realised_lo95": 0.79}}}}),
        encoding="utf-8")
    hit = Calibration.load(path).realised("handicap_games", 0.81, "tennis", "OVER")
    assert hit is not None and hit[0] == 0.79


def test_a_derived_market_without_its_own_curve_reads_no_pool() -> None:
    """Review 2026-10-07: with the derived-curves switch on, a derived key with
    no own bucket fell to the sport pool, which holds count markets only."""
    from bet.sofa.confidence import Calibration

    cal = Calibration.load()
    assert cal.realised("both_over_shots", 0.80, "football", "OVER", None) is None
    assert cal.realised("handicap_games", 0.80, "tennis", "OVER", None) is None
