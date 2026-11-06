"""Games handicap read off the tennis point model's simulations
(docs/sofa/evidence/tennis_handicap_point_model_2026-11-06.md). SHEET reads
the per-set handicap through bet.sofa.tennis_point_sheet under
epochs.TENNIS_HANDICAP_POINT_MODEL; the full-match ``handicap_games`` is
measurement only (it failed the calibration rule on the hold-out).

``bet.sofa.tennis_point_model.MarketSim`` already holds, per simulated match,
every player's games per set; a handicap is a function of them:

  * ``handicap_games``: "X (L)" wins when X's games minus the opponent's games
    over the match, plus L, is above zero (the pipeline's tennis_score
    convention: a deciding 10-point match tiebreak is one game);
  * ``handicap_games_won_set1`` / ``_set2``: the same margin inside set 1 / 2
    (conditional on the set being played - in best of three set 2 always is).

A line landing exactly is a push (VOID); the probability is then the win
share of the decided simulations, which is what a de-vigged two-way price
describes. Superbet's lines are half lines, so no push happens there.
"""

from __future__ import annotations

from typing import Final

import numpy as np
import numpy.typing as npt

from bet.sofa.tennis_point_model import MarketSim

HANDICAP_MARKETS: Final[dict[str, int]] = {
    "handicap_games": 0,
    "handicap_games_won_set1": 1,
    "handicap_games_won_set2": 2,
}


def margins(ms: MarketSim, market: str, side: int) -> tuple[
        npt.NDArray[np.int64], npt.NDArray[np.bool_]] | None:
    """(the subject's game margin per simulation, the simulations in which
    the market is decided) or None for a market this module does not read.
    side 0 = home / 1 = away (the history's orientation)."""
    scope = HANDICAP_MARKETS.get(market)
    if scope is None or side not in (0, 1):
        return None
    games = ms.sim.games  # [S, 3, 2]
    if scope == 0:
        own = games[:, :, side].sum(axis=1)
        opp = games[:, :, 1 - side].sum(axis=1)
        played = np.ones(len(own), dtype=bool)
    else:
        own = games[:, scope - 1, side]
        opp = games[:, scope - 1, 1 - side]
        played = ms.sim.sets_played >= scope
    return np.asarray(own - opp, dtype=np.int64), played


def p_handicap(ms: MarketSim, market: str, side: int, line: float) -> float | None:
    """P("subject (line)" wins | decided), None when not readable."""
    found = margins(ms, market, side)
    if found is None:
        return None
    margin, played = found
    value = margin + line
    decided = played & (value != 0)
    if not decided.any():
        return None
    return float((value[decided] > 0).mean())


def mean_sd(ms: MarketSim, market: str, side: int) -> tuple[float, float] | None:
    """Mean and sd of the subject's margin (where the market is decided by a
    played set) - the centre of a line ladder."""
    found = margins(ms, market, side)
    if found is None:
        return None
    margin, played = found
    if not played.any():
        return None
    m = margin[played].astype(np.float64)
    return float(m.mean()), float(m.std())
