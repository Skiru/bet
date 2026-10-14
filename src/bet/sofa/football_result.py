"""Football double chance ("Podwójna szansa") from the pure rating - audit D1.

Behind ``epochs.FOOTBALL_RESULT_MARKETS_FROM_UTC``
(``epochs.football_result_markets``); off (None, the default), nothing here
is reached and OFFER / SAMPLES / SHEET / CONFIDENCE are what they were.
Plan and measurement: docs/sofa/evidence/football_result_phase_2026-10-13.md,
"Decyzja i plan implementacji (DC; DNB czeka)". DNB is NOT here.

Shape. Superbet posts the full-match double chance as one market "Podwójna
szansa" with three selections "1X" / "X2" / "12", and the match result as
"Mecz" with "1" / "X" / "2" (tests/sofa/golden/offer_mappable_items.json,
Villarreal - Napoli: 1.35 / 1.66 / 1.26 and 2.15 / 3.60 / 3.05). One DC
selection and the 1X2 outcome it leaves out are complementary, so they are
read as ONE two-sided rung and the ladder margin (``confidence.overround``)
judges it like every other leg:

    market  ``double_chance``
    subject the selection, "1X" / "X2" / "12"
    line    0.5
    OVER    the selection wins ("Podwójna szansa" price)
    UNDER   it loses = the left-out 1X2 outcome ("Mecz" "2" / "1" / "X")

Without a "Mecz" price the rung is one-sided (no overround; CONFIDENCE never
prints a one-sided leg without a history curve). A "Mecz" price with no DC
selection beside it is no DC offer and is dropped (``offer.OfferFetcher``).
The halves ("1.połowa - podwójna szansa") and every combination ("Podwójna
szansa & ...") are other questions and stay unmapped.

Price. ``p_central`` of the OVER row is P(selection) from independent
negative-binomial goals of the two sides on the PURE rating centres
(``FootballForecast.centre("goals_for", side)``, never the sample blend -
measured C2: the blend over-states 15-18 pp), one dispersion ``r`` from
``config/sofa_football_result.json`` (measured on the history, not written
by a fit script - so every row names it in UNFITTED_CONSTANTS). Only the
OVER (the DC selection itself) is priced: its UNDER is a single 1X2 outcome,
which did not meet the registered threshold. No season-phase term (measured
-0.00005 a match, left for the refit). An UNLINKED fixture carries
CROSS_LEAGUE_UNLINKED like every football row (CONFIDENCE refuses it); a
fixture the rating gives no goals centre for has no row.

Confidence. No curve is installed: ``double_chance`` is a rating-only market
(``tennis_winner.RATING_ONLY_MARKETS``), read from its own curve or not at
all (``confidence.OWN_CURVE_ONLY``), so under line evidence it reads its own
settled Superbet lines - NO_LINE_EVIDENCE until a p bucket holds
MIN_EVIDENCE_BUCKET lines of MIN_EVIDENCE_GAMES games.

Settlement. Superbet settles football result markets on regular time (90
minutes plus added time): the selection is graded on the 90-minute score
(``metrics.regulation_score``: ``normaltime`` after extra time or a
shootout), as goals are (``metrics.double_chance_value``).
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from bet.sofa.config import config_path
from bet.sofa.market_mapper import fold

F64 = NDArray[np.float64]

DOUBLE_CHANCE = "double_chance"
DC_LINE = 0.5
SELECTIONS = ("1X", "X2", "12")
# The 1X2 outcome each DC selection leaves out (its complement).
LEFT_OUT = {"1X": "2", "X2": "1", "12": "X"}
_DC_BY_LEFT_OUT = {v: k for k, v in LEFT_OUT.items()}
# The sheet note a DC row carries, and the row marker's field.
RESULT_NOTE = "FOOTBALL_RESULT_MARKETS"
RESULT_RULE_FIELD = "result_rule"
# The dispersion is measured, not produced by a fit script (CLAUDE.md:
# never strip UNFITTED_CONSTANTS).
UNFITTED_CONSTANTS = ("FOOTBALL_RESULT_NB_R",)
CONFIG_FILE = "sofa_football_result.json"
KMAX = 12  # goals per side 0..KMAX; the truncated tail is < 1e-6

_DC_MARKET = "podwojna szansa"
_RESULT_MARKET = "mecz"


# --- OFFER --------------------------------------------------------------------


def classify_result(
    market_name: str | None, selection_name: str | None,
) -> tuple[str, str, float, str] | None:
    """(double_chance, selection, 0.5, OVER / UNDER) for one odd of the
    full-match "Podwójna szansa" (OVER) or "Mecz" (the UNDER of the DC
    selection that leaves its outcome out), or None.

    Only the bare market names: halves, "Mecz & ...", "Podwójna szansa &
    ...", "1. połowa/mecz - podwójna szansa" are other questions."""
    folded = fold(market_name)
    selection = str(selection_name or "").strip().upper()
    if folded == _DC_MARKET and selection in SELECTIONS:
        return (DOUBLE_CHANCE, selection, DC_LINE, "OVER")
    if folded == _RESULT_MARKET and selection in _DC_BY_LEFT_OUT:
        return (DOUBLE_CHANCE, _DC_BY_LEFT_OUT[selection], DC_LINE, "UNDER")
    return None


def is_result_market(market_name: str | None) -> bool:
    return fold(market_name) in (_DC_MARKET, _RESULT_MARKET)


# --- the score grid (ported from scripts/sofa/measure_football_result_model) ---


def count_pmf(lam: F64, r: F64 | float | None, kmax: int = KMAX) -> F64:
    """(N, kmax+1) pmf of a count with mean `lam`: Poisson when `r` is None,
    else NB with variance lam + lam^2 / r. By the recursion
    p(k+1) = p(k) (k + r) / (k + 1) * lam / (r + lam), renormalised over
    0..kmax. The same arithmetic as the measurement's ``count_pmf``."""
    lam = np.maximum(np.asarray(lam, dtype=np.float64), 1e-9)
    out = np.empty((len(lam), kmax + 1))
    if r is None:
        out[:, 0] = np.exp(-lam)
        for k in range(kmax):
            out[:, k + 1] = out[:, k] * lam / (k + 1)
    else:
        rr = np.asarray(r, dtype=np.float64)
        q = lam / (rr + lam)
        out[:, 0] = np.exp(rr * np.log(rr / (rr + lam)))
        for k in range(kmax):
            out[:, k + 1] = out[:, k] * (k + rr) / (k + 1) * q
    normalised: F64 = out / out.sum(axis=1, keepdims=True)
    return normalised


def score_grid(pa: F64, pb: F64) -> F64:
    """(N, K, K) joint of independent home / away goals."""
    grid: F64 = pa[:, :, None] * pb[:, None, :]
    return grid


def market_probs(grid: F64) -> F64:
    """(N, 3) home win / draw / away win of a score grid (the ``res`` of the
    measurement's ``market_probs``)."""
    k = grid.shape[1]
    i = np.arange(k)[:, None]
    j = np.arange(k)[None, :]
    home = grid[:, i > j].sum(axis=1)
    away = grid[:, i < j].sum(axis=1)
    draw = grid[:, i == j].sum(axis=1)
    res: F64 = np.stack([home, draw, away], axis=1)
    return res


def result_probs(lh: float, la: float, r: float) -> dict[str, float]:
    """P of every 1X2 outcome and DC selection for expected home goals `lh`
    and away goals `la`, NB with dispersion `r` per side, independent sides.
    1X + X2 + 12 = 2."""
    if not (math.isfinite(lh) and math.isfinite(la) and lh > 0 and la > 0):
        raise ValueError(f"goal means must be positive, got {lh!r}, {la!r}")
    if not (math.isfinite(r) and r > 0):
        raise ValueError(f"NB dispersion r must be positive, got {r!r}")
    pa = count_pmf(np.array([lh]), r)
    pb = count_pmf(np.array([la]), r)
    home, draw, away = (float(x) for x in market_probs(score_grid(pa, pb))[0])
    return {
        "1": home, "X": draw, "2": away,
        "1X": home + draw, "X2": draw + away, "12": home + away,
    }


# --- settlement -----------------------------------------------------------------


def selection_holds(selection: str, home_goals: float, away_goals: float) -> bool:
    """Does the DC selection win on this score?"""
    if selection not in SELECTIONS:
        raise ValueError(f"not a double-chance selection: {selection!r}")
    outcome = "1" if home_goals > away_goals else (
        "X" if home_goals == away_goals else "2")
    return outcome != LEFT_OUT[selection]


# --- config ---------------------------------------------------------------------


@dataclass(frozen=True)
class ResultConfig:
    nb_r: float
    source: str


def load_config(path: Path | str | None = None) -> ResultConfig:
    """The NB dispersion of the result model. A missing or malformed file
    raises (SHEET exits 2 rather than price a model nobody measured)."""
    p = Path(path) if path is not None else config_path(CONFIG_FILE)
    doc: Mapping[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    raw = doc.get("nb_r")
    if not isinstance(raw, int | float) or isinstance(raw, bool) or raw <= 0:
        raise ValueError(f"{p}: nb_r must be a positive number, got {raw!r}")
    return ResultConfig(nb_r=float(raw), source=str(doc.get("source") or ""))


def dc_note(selection: str, p: float, lh: float, la: float, r: float) -> str:
    return (
        f"{RESULT_NOTE}: double chance {selection} p {p:.4f} from NB goals "
        f"(r {r:g}) on the pure rating centres home {lh:.3f} / away {la:.3f} "
        "(FootballForecast.centre goals_for); no sample, no price - no curve "
        "installed, the confidence is the market's own Superbet lines "
        "(epochs.FOOTBALL_RESULT_MARKETS)"
    )
