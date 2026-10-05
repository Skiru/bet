"""F2.2 (2026-10-05): the tennis NB variance fix waits behind
epochs.MODEL_FIXES_FROM_UTC, which stays None until the next refit."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from bet.sofa import epochs
from bet.sofa.engine import (
    TENNIS_DISPERSION_SCALED_METRICS,
    predictive_sd,
    sheet_predictive_sd,
)


def test_model_fixes_are_disabled_on_the_live_day() -> None:
    # Never mid-day: the 10-05 curves were fitted without the fixes. The
    # operator sets the constant with the next refit, between days.
    assert epochs.MODEL_FIXES_FROM_UTC is None
    assert not epochs.model_fixes_enabled()


def test_model_fixes_read_the_wall_clock_not_sofa_now(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed = datetime(2026, 10, 7, 2, 0, tzinfo=UTC)
    monkeypatch.setattr(epochs, "MODEL_FIXES_FROM_UTC", installed)
    # A refit replay freezes timeutil.now() in the past; the estimator the new
    # curves describe must still be the fixed one.
    monkeypatch.setenv("SOFA_NOW", "2026-09-20T10:00:00Z")
    assert epochs.model_fixes_enabled(datetime(2026, 10, 7, 3, 0, tzinfo=UTC))
    assert not epochs.model_fixes_enabled(datetime(2026, 10, 6, 23, 0, tzinfo=UTC))


def test_tennis_spread_stays_raw_while_the_fixes_are_off() -> None:
    # aces_for: sample mean 4, variance 9, centre moved to 3 by the tier prior.
    raw = predictive_sd(9.0, 4.0, 10)
    assert sheet_predictive_sd("aces_for", "tennis", 4.0, 9.0, 10, 3.0) == raw


def test_tennis_spread_moves_with_the_centre_once_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        epochs, "MODEL_FIXES_FROM_UTC", datetime(2026, 1, 1, tzinfo=UTC)
    )
    scaled = sheet_predictive_sd("aces_for", "tennis", 4.0, 9.0, 10, 3.0)
    assert scaled == pytest.approx(predictive_sd(9.0 * 0.75, 3.0, 10))
    # The dispersion index var/mean is what is kept, as for football.
    assert scaled == pytest.approx(
        sheet_predictive_sd("aces_for", "football", 4.0, 9.0, 10, 3.0))
    # games_total measured mixed on the bet lines: left as it is.
    assert "games_total" not in TENNIS_DISPERSION_SCALED_METRICS
    assert sheet_predictive_sd("games_total", "tennis", 22.0, 16.0, 10, 21.0) == (
        predictive_sd(16.0, 22.0, 10))
