"""Count stretch: the supremacy term of a football count centre outside
GAME_STATE (switch ``epochs.FOOTBALL_COUNT_STRETCH_FROM_UTC``, off while
None).

GAME_STATE (bet.sofa.game_state) multiplies corners_for, shots_for,
cards_points_for and fouls_for by exp(beta x s). The other count markets
SHEET prices carry the same mismatch compression with no term: a favourite's
half corners, second-half shots and shots on target come out too low, its
goalkeeper's saves and goal kicks too high (the outsider's the other way),
and a lopsided match's shots on target / saves total a shade too low. With
the switch on, the centre of a market of COUNT_STRETCH_MARKETS is

    side  : centre x exp(beta x s [+ beta2 x s^2])   s = the side's expected
                                                      goal difference
    total : centre x exp(g1 x |s| + g2 x s^2)          s = the home side's

(bet.sofa.supremacy_stretch, the goals stretch's arithmetic), applied after
GAME_STATE and the venue prior, on the blended or sample-only centre, in
SHEET and in the cache replay (calibrate_from_cache --count-stretch). The
coefficients are fitted by ``scripts/sofa/fit_count_stretch.py`` (Poisson
pseudo-likelihood, offset log centre, rows of the mature rating book from
2026-01-01) into config/sofa_count_stretch.json; COUNT_STRETCH_TERMS says
how many terms each market was measured to need. Single coefficients only:
per season phase was never better for a count (h_phase, 2026-10-17).

Measured 2026-10-17 (history replay of SHEET's count centre with the B15
correction and the installed GAME_STATE; NB log-loss new - old, match
bootstrap; walk-forward from 2025-08, pre-2026 fit tested on 2026, fit
2026-H1 tested from 2026-07, and the per-line bucket curve after it):
walk-forward NB log-loss below zero on all 16; after the bucket curve both
out-of-sample checks (pre-2026 fit -> 2026, 2026-H1 fit -> 2026-07..) below
zero on all 16, e.g. corners_1h_for walk-forward -0.0109 [-0.0124, -0.0095],
after the curve -0.0059 [-0.0069, -0.0050]. The raw NB of a fixed fit is not
significant for shots_1h_for (pre-2026 fit, -0.0000 [-0.0014, +0.0014]) and
offsides_for (2026-H1 fit, -0.0002 [-0.0005, +0.0000]); offsides_1h_for was
left out for failing the after-curve 2026-H1 check (-0.0003 [-0.0007,
+0.0001]). Not here: cards, fouls, tackles (no robust gain or worse out of
sample), corners_for / shots_for (GAME_STATE's beta is enough), the corners
/ shots / offsides totals (the bucket curve absorbs it). Evidence: EVIDENCE.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from bet.sofa import supremacy_stretch as ss

CONFIG_FILE = "sofa_count_stretch.json"
EVIDENCE = "docs/sofa/evidence/count_stretch_2026-10-17.md"
SIDE_MARKETS: tuple[str, ...] = (
    "corners_1h_for", "corners_2h_for", "shots_1h_for", "shots_2h_for",
    "shots_on_target_for", "shots_on_target_1h_for", "shots_on_target_2h_for",
    "offsides_for", "saves_for", "saves_1h_for", "throw_ins_for",
    "goal_kicks_for")
TOTAL_MARKETS: tuple[str, ...] = (
    "shots_on_target_total", "saves_total", "saves_1h_total", "throw_ins_total")
COUNT_STRETCH_MARKETS: tuple[str, ...] = SIDE_MARKETS + TOTAL_MARKETS
# The measured form: 1 = s (a side) / |s| (a total, g2 written 0), 2 = s +
# s^2 / |s| + s^2 (chosen where the s^2 term was better out of sample with
# the interval below zero).
COUNT_STRETCH_TERMS: Mapping[str, int] = {
    **{m: 1 for m in COUNT_STRETCH_MARKETS},
    "throw_ins_for": 2, "throw_ins_total": 2,
}
COUNT_STRETCH_UNFITTED = ss.STRETCH_UNFITTED
SPEC = ss.StretchSpec("count-stretch", SIDE_MARKETS, TOTAL_MARKETS,
                      phased=False, side_quadratic=True)


def is_total(market: str) -> bool:
    return market in TOTAL_MARKETS


class CountStretchTable(ss.StretchTable):
    SPEC = SPEC


def parse_table(data: Mapping[str, Any], path: str | None = None) -> CountStretchTable:
    single, phased = ss.parse_cells(SPEC, data, path)
    return CountStretchTable(single, path, phased)


def load_table(path: Path | None = None) -> CountStretchTable:
    """The fitted table. Missing or malformed raises: with the switch on a
    silent identity would claim a rule the sheet did not use."""
    data, where = ss.read_file(CONFIG_FILE, path)
    return parse_table(data, where)
