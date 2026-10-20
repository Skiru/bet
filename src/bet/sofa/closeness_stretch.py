"""Closeness stretch: the match-closeness term of a football count centre
(switch ``epochs.FOOTBALL_CLOSENESS_STRETCH_FROM_UTC``, off while None).

GAME_STATE (bet.sofa.game_state) and the count stretch
(bet.sofa.count_stretch) move a count centre with the SIGN of the expected
goal difference s: the favourite's corners and shots up, its bookings down.
Neither says anything about how CLOSE the match is expected to be, and the
literature says bookings are not monotone in the score: they peak in a
close match and fall once it is decided (Buraimo, Forrest & Simmons 2010:
"as the lead becomes decisive both teams become less likely to attract
sanctions"); a lopsided match carries more shots in total (the outsider
defends deep, the favourite keeps shooting). With the switch on, the centre
of a market of CLOSENESS_MARKETS is

    centre x exp(g1 x |s| + g2 x s^2),   s = the home side's expected goal
                                         difference (|s| and s^2 are the
                                         same for both sides)

applied after GAME_STATE, the venue prior and the count stretch (a side
market keeps GAME_STATE's beta x s: g is fitted on top of the live centre),
on the blended or sample-only centre, in SHEET and in the cache replay
(calibrate_from_cache --closeness-stretch). The arithmetic and the file
grammar are bet.sofa.supremacy_stretch's total form; the coefficients are
fitted by ``scripts/sofa/fit_closeness_stretch.py`` (Poisson
pseudo-likelihood, offset log of the live centre, rows of the mature rating
book from 2026-01-01) into config/sofa_closeness_stretch.json.

Measured 2026-10-21 (history replay of SHEET's count centre, walk-forward
monthly from 2026-01 on rows from 2025-08, NB log-loss with the installed
per-competition alpha, match bootstrap; two fixed splits - fit 2025-08..12
-> test 2026, fit 2026-H1 -> test 2026-07..10-19 - through the installed
curves at Superbet's quoted lines, also on the legs at a curve >= 0.70):
cards_points_for and cards_points_total (|s| + s^2: the s^2 term better than
|s| alone walk-forward, -6.9 / -11.2 x1e-4 with the interval below zero),
shots_total and shots_1h_total (|s|) better walk-forward with the interval
below zero and not worse after the curve. Not here: fouls (better before
2026-08, worse from it: the H1 fit significantly worse on 2026-07..),
corners_total (no gain after the curve), corners_1h_total (worse after the
curve), the side corners / shots / shots on target / offsides (no gain;
GAME_STATE or the count stretch is enough), shots_on_target_total (already
carries |s| in the count stretch), offsides_total (zero). Dispersion as a
function of |s| was measured too and is NOT here: better in NB log-loss on
the side shots / shots on target / offsides / corners, worse through the
installed curves on the legs at >= 0.70. Evidence: EVIDENCE.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from bet.sofa import supremacy_stretch as ss

CONFIG_FILE = "sofa_closeness_stretch.json"
EVIDENCE = "docs/sofa/evidence/football_closeness_stretch_2026-10-21.md"
# Every market reads exp(g1 |s| + g2 s^2) - the supremacy stretch's total
# form - whether it is a side or a total: the closeness of a match is the same
# number for both sides.
SIDE_COUNT_MARKETS: tuple[str, ...] = ("cards_points_for",)
TOTAL_COUNT_MARKETS: tuple[str, ...] = (
    "cards_points_total", "shots_total", "shots_1h_total")
CLOSENESS_MARKETS: tuple[str, ...] = SIDE_COUNT_MARKETS + TOTAL_COUNT_MARKETS
# The measured form: 1 = |s| (g2 written 0), 2 = |s| + s^2 (chosen where the
# s^2 term was better out of sample with the interval below zero).
CLOSENESS_TERMS: Mapping[str, int] = {
    **{m: 1 for m in CLOSENESS_MARKETS},
    "cards_points_for": 2, "cards_points_total": 2}
CLOSENESS_UNFITTED = ss.STRETCH_UNFITTED
SPEC = ss.StretchSpec("closeness-stretch", (), CLOSENESS_MARKETS,
                      phased=False, side_quadratic=False)


def supremacy(forecast: Any) -> float | None:
    """The s the term reads: the home side's (|s| and s^2 are even), None
    when the goals rating gives no centre."""
    return ss.stretch_supremacy(forecast, None, True)


class ClosenessStretchTable(ss.StretchTable):
    SPEC = SPEC


def parse_table(data: Mapping[str, Any],
                path: str | None = None) -> ClosenessStretchTable:
    single, phased = ss.parse_cells(SPEC, data, path)
    return ClosenessStretchTable(single, path, phased)


def load_table(path: Path | None = None) -> ClosenessStretchTable:
    """The fitted table. Missing or malformed raises: with the switch on a
    silent identity would claim a rule the sheet did not use."""
    data, where = ss.read_file(CONFIG_FILE, path)
    return parse_table(data, where)
