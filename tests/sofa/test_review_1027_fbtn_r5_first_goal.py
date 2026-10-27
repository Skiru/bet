"""Review 2026-10-27 R5: the first goal's split under NB goals.

football_incidents.first_goal_probs split P(someone scores) by
lh / (lh + la), exact for Poisson goals only. The goals are NB (gamma-mixed
Poisson); with ``exact`` (epochs.first_goal_nb_exact) the split is the race of
the two mixed processes. Off is byte-identical to the old formula.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import numpy as np
import pytest

from bet.sofa import epochs
from bet.sofa.football_incidents import (
    FG_AWAY,
    FG_HOME,
    FG_NONE,
    FIRST_GOAL,
    IncidentPricing,
    first_goal_probs,
)
from tests.sofa.test_football_incident_markets import CFG, _forecast, _rates, _sheet

R = 7.586


def _monte_carlo(lh: float, la: float, r: float, n: int, seed: int
                 ) -> tuple[float, float, float]:
    """Each side's rate drawn from Gamma(r, mean / r), first goal times
    exponential; a time past 1 (the match) is no goal."""
    rng = np.random.default_rng(seed)
    a = rng.gamma(r, lh / r, n)
    b = rng.gamma(r, la / r, n)
    ta = rng.exponential(1.0 / a)
    tb = rng.exponential(1.0 / b)
    home = float(np.mean((ta < tb) & (ta < 1.0)))
    away = float(np.mean((tb < ta) & (tb < 1.0)))
    return home, away, 1.0 - home - away


@pytest.mark.parametrize("lh,la", [(1.8, 0.8), (2.6, 0.5), (1.0, 1.0),
                                   (0.3, 2.9), (1.4, 1.1)])
def test_exact_matches_monte_carlo(lh: float, la: float) -> None:
    p = first_goal_probs(lh, la, R, exact=True)
    home, away, none = _monte_carlo(lh, la, R, 1_000_000, seed=1027)
    assert p[FG_HOME] == pytest.approx(home, abs=2e-3)
    assert p[FG_AWAY] == pytest.approx(away, abs=2e-3)
    assert p[FG_NONE] == pytest.approx(none, abs=2e-3)
    assert sum(p.values()) == pytest.approx(1.0, abs=1e-12)


def test_the_ratio_overstates_the_favourite() -> None:
    old = first_goal_probs(1.8, 0.8, R)
    new = first_goal_probs(1.8, 0.8, R, exact=True)
    assert old[FG_HOME] == pytest.approx(0.628, abs=5e-4)
    assert new[FG_HOME] == pytest.approx(0.621, abs=5e-4)
    assert new[FG_NONE] == old[FG_NONE]
    # equal means: the race is symmetric, the ratio is right
    eq = first_goal_probs(1.2, 1.2, R, exact=True)
    assert eq[FG_HOME] == pytest.approx(eq[FG_AWAY], abs=1e-12)


def test_large_r_tends_to_poisson() -> None:
    poisson = first_goal_probs(1.7, 0.9, 1e7)
    nb = first_goal_probs(1.7, 0.9, 1e7, exact=True)
    assert nb[FG_HOME] == pytest.approx(poisson[FG_HOME], abs=1e-6)


@pytest.mark.parametrize("lh,la", [(1.5, 1.1), (0.4, 2.8), (2.9, 0.3)])
def test_off_is_the_old_formula_byte_for_byte(lh: float, la: float) -> None:
    p0h = math.exp(R * math.log(R / (R + lh)))
    p0a = math.exp(R * math.log(R / (R + la)))
    none = p0h * p0a
    want = {FG_HOME: (1 - none) * lh / (lh + la),
            FG_AWAY: (1 - none) * la / (lh + la), FG_NONE: none}
    assert first_goal_probs(lh, la, R) == want
    assert first_goal_probs(lh, la, R, exact=False) == want


def test_exact_validates_like_the_old() -> None:
    with pytest.raises(ValueError):
        first_goal_probs(0.0, 1.0, R, exact=True)
    with pytest.raises(ValueError):
        first_goal_probs(1.0, 1.0, 0.0, exact=True)


def test_sheet_reads_the_pricing_flag() -> None:
    fc = _forecast()
    off = {(r["subject"]): r for r in _sheet(IncidentPricing(_rates(), CFG), fc)
           if r["market"] == FIRST_GOAL}
    on = {(r["subject"]): r for r in
          _sheet(IncidentPricing(_rates(), CFG, nb_exact=True), fc)
          if r["market"] == FIRST_GOAL}
    home = fc.centre("goals_for", "side_a")
    away = fc.centre("goals_for", "side_b")
    assert home is not None and away is not None
    want_off = first_goal_probs(home[0], away[0], CFG.nb_r)
    want_on = first_goal_probs(home[0], away[0], CFG.nb_r, exact=True)
    assert off[FG_HOME]["p_central"] == round(want_off[FG_HOME], 4)
    assert on[FG_HOME]["p_central"] == round(want_on[FG_HOME], 4)
    assert on[FG_NONE]["p_central"] == off[FG_NONE]["p_central"]
    # the default pricing is the switch off
    assert IncidentPricing(_rates(), CFG).nb_exact is False


def test_switch_reads_the_day_and_the_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "FIRST_GOAL_NB_EXACT_FROM_UTC", None)
    assert not epochs.first_goal_nb_exact("2026-10-28",
                                          datetime(2026, 10, 28, 6, tzinfo=UTC))
    monkeypatch.setattr(epochs, "FIRST_GOAL_NB_EXACT_FROM_UTC",
                        datetime(2026, 10, 28, tzinfo=UTC))
    assert epochs.first_goal_nb_exact("2026-10-28",
                                      datetime(2026, 10, 28, 6, tzinfo=UTC))
    assert not epochs.first_goal_nb_exact("2026-10-27",
                                          datetime(2026, 10, 28, 6, tzinfo=UTC))
    assert not epochs.first_goal_nb_exact("2026-10-28",
                                          datetime(2026, 10, 27, 22, tzinfo=UTC))
