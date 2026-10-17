"""Goals stretch: the supremacy term of a football goals centre (switch
``epochs.FOOTBALL_GOALS_STRETCH_FROM_UTC``, off while None).

SHEET's goals centre is the rating blended with the shrunk sample - and both
halves pull a mismatch toward the middle: the favourite's own goals come out
too low and the outsider's too high (history replay 2025-08..2026-10, s >= 1:
y - centre +0.26 goals_for, -0.13 at s < -1), and a lopsided match's total
too low (+0.36 at |s| >= 1.5) while an even one's is a shade high. With the
switch on, the centre of a market of GOALS_STRETCH_MARKETS is

    side  (goals_for, goals_1h_for, goals_2h_for):
        centre x exp(beta_m x s),             s = the side's expected goal
                                              difference
    total (goals_total, goals_1h_total, goals_2h_total):
        centre x exp(g1_m x |s| + g2_m x s^2), s = the home side's

where s comes from the rating's own goals book as of the match
(``FootballForecast.supremacy``, the covariate of bet.sofa.game_state; the
opponent reads -s, a total's terms are even in s) clamped at
game_state.MAX_SUPREMACY, and the coefficients are fitted on the history
(``fit_terms``: Poisson pseudo-likelihood, log link, offset log centre) by
``scripts/sofa/fit_goals_stretch.py`` into config/sofa_goals_stretch.json.

Rule goals_stretch_v2 (2026-10-17): a market may carry one coefficient set
per season phase (``by_phase``; bet.sofa.season_phase's labels, a match with
no phase ``none`` - the phase SHEET and the replay already read for the
season-phase term). The slope is phase dependent: goals_for fitted before
2026 early 0.018, mid 0.056, late 0.064, final 0.063 (one value 0.071; a
match with no phase reads the single set - its own set, 0.082, was worse,
raw NB per-phase minus single +0.00018 [+0.00011, +0.00025]); the halves
only early differs (goals_1h_for 0.145 vs 0.167,
goals_2h_for 0.100 vs 0.128); the totals stay single (per phase measured no
better). A phase the table lacks reads the market's single set, else the
centre is left as it is. The arithmetic and the file grammar are
bet.sofa.supremacy_stretch's, shared with the count and player stretches.

A market absent from the file, or a fixture with no goals rating, keeps its
centre byte for byte. Measured 2026-10-17 on the history replay
(walk-forward, NB log-loss new - old, match bootstrap): goals_for -0.0010
[-0.0012, -0.0008], goals_1h_for -0.0074 [-0.0078, -0.0070], goals_2h_for
-0.0048 [-0.0052, -0.0045], goals_total -0.0011 [-0.0013, -0.0009],
goals_1h_total -0.0018 [-0.0021, -0.0016], goals_2h_total -0.0014 [-0.0017,
-0.0013] (the totals with |s| alone; the s^2 term's own figures are in the
evidence file). Evidence: EVIDENCE.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from bet.sofa import supremacy_stretch as ss

CONFIG_FILE = "sofa_goals_stretch.json"
EVIDENCE = "docs/sofa/evidence/goals_stretch_2026-10-17.md"
SIDE_MARKETS: tuple[str, ...] = ("goals_for", "goals_1h_for", "goals_2h_for")
TOTAL_MARKETS: tuple[str, ...] = (
    "goals_total", "goals_1h_total", "goals_2h_total")
GOALS_STRETCH_MARKETS: tuple[str, ...] = SIDE_MARKETS + TOTAL_MARKETS
GOALS_STRETCH_UNFITTED = ss.STRETCH_UNFITTED
MAX_ABS_COEFFICIENT = ss.MAX_ABS_COEFFICIENT
SPEC = ss.StretchSpec("goals-stretch", SIDE_MARKETS, TOTAL_MARKETS, phased=True)


class _Supremacy(Protocol):
    def supremacy(self, side: str) -> float | None: ...


def is_total(market: str) -> bool:
    return market in TOTAL_MARKETS


def features(market: str, supremacy: float) -> tuple[float, ...]:
    """The market's covariates of the clamped s: (s,) for a side market,
    (|s|, s^2) for a total."""
    x = ss.features(is_total(market), supremacy)
    return x if is_total(market) else x[:1]


def stretch_supremacy(forecast: _Supremacy, market: str,
                      side: str | None) -> float | None:
    """The s a market's term reads: the side's own for a side market (None
    without a side), the home side's for a total; None when the goals rating
    gives no centre."""
    return ss.stretch_supremacy(forecast, side, is_total(market))


class GoalsStretchTable(ss.StretchTable):
    SPEC = SPEC


def parse_table(data: Mapping[str, Any], path: str | None = None) -> GoalsStretchTable:
    single, phased = ss.parse_cells(SPEC, data, path)
    return GoalsStretchTable(single, path, phased)


def load_table(path: Path | None = None) -> GoalsStretchTable:
    """The fitted table. Missing or malformed raises: with the switch on a
    silent identity would claim a rule the sheet did not use."""
    data, where = ss.read_file(CONFIG_FILE, path)
    return parse_table(data, where)


def fit_terms(
    market: str, centres: Sequence[float], supremacy: Sequence[float],
    y: Sequence[float], iterations: int = 60,
) -> tuple[float, ...]:
    """The coefficients maximising sum(y x b.x - c x exp(b.x)) (Poisson
    pseudo-likelihood with offset log c: consistent for the mean whatever the
    count's dispersion), x = features(market, s): beta for a side, (g1, g2)
    for a total. Zeros when the Hessian is singular."""
    total = is_total(market)
    return ss.fit_terms(total, centres, supremacy, y, 2 if total else 1,
                        iterations)
