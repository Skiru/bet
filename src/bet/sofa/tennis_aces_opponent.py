"""A tennis player's aces centre corrected for today's returner
(epochs.TENNIS_ACES_OPPONENT_FROM_UTC).

Until this switch an aces row was priced from the server's own sample alone:
his last matches' aces on a comparable surface and format, shrunk toward the
tier prior (bet.sofa.tennis_prior). Who stands on the other side of the net
never entered, though an ace is as much the returner's miss as the server's
hit - the same server meets a big returner and a weak one in one week.

The correction multiplies the centre by the returner's factor: how many aces
his own opponents served against him, shrunk with K toward the same tier prior
the centre is shrunk toward, over that prior

    f(R) = ((sum conceded_R + K x prior) / (n_R + K)) / prior

so an average returner reads 1.0, and a short or empty sample of his reads
close to 1.0. `conceded_R` is the returner's sample's `against` (SAMPLES:
the aces his opponent served in each of his matches; the replay: total minus
own of his `aces` history) - his matches on the fixture's surface and format,
as his own sample is scoped.

  * `aces_for` (and the per-set `aces_set1_for` / `aces_set2_for`): centre x
    f(the other side). The per-set rows read the full-match factor - an ace
    rate per point does not depend on the set.
  * `aces_total` (and the per-set totals): the pooled-total centre x
    (c_A f(B) + c_B f(A)) / (c_A + c_B), c the sides' own shrunk centres - the
    share of each server's aces moved by the other's return, so the total
    moves only by what the two corrections add up to.

Double faults are NOT corrected: measured worse (the returner barely touches a
fault) - docs/sofa/evidence/tennis_aces_opponent_2026-10-17.md.

No tier prior (best-of-five, unknown tier or surface) or a returner without
MIN_RETURNER_VALUES values: no correction - the row is priced as before and
says so in a note.
"""

from __future__ import annotations

from collections.abc import Sequence

# The markets the correction applies to.
ACES_SIDE_MARKETS = frozenset({"aces_for", "aces_set1_for", "aces_set2_for"})
ACES_TOTAL_MARKETS = frozenset({"aces_total", "aces_set1_total", "aces_set2_total"})
ACES_MARKETS = ACES_SIDE_MARKETS | ACES_TOTAL_MARKETS

# The prior is the tier prior of the full-match quantity whatever the row's
# scope: the factor is a ratio, so its reference must be the quantity the
# conceded sample counts (full-match aces).
PRIOR_MARKET = "aces_for"

# A returner sample shorter than this gives no factor (the server's own sample
# is held to SHEET's min_sample, 5, the same bar).
MIN_RETURNER_VALUES = 5

NOTE = "TENNIS_ACES_OPPONENT"


def returner_factor(
    conceded: Sequence[float], prior: float | None, k: float
) -> float | None:
    """f(R): the returner's conceded aces shrunk toward `prior` with `k`, over
    `prior`. None when there is no prior or too few values."""
    if prior is None or prior <= 0.0 or len(conceded) < MIN_RETURNER_VALUES:
        return None
    n = len(conceded)
    return ((sum(conceded) + k * prior) / (n + k)) / prior


def shrunk(values: Sequence[float], prior: float, k: float) -> float:
    """A side's own centre for the total's weights: its sample mean shrunk
    toward `prior` with `k` (SHEET's K_CENTRE shrink)."""
    n = len(values)
    return (sum(values) + k * prior) / (n + k)


def total_multiplier(
    centre_a: float, centre_b: float, f_a: float, f_b: float
) -> float:
    """(c_A f(B) + c_B f(A)) / (c_A + c_B): A serves into B's return and B into
    A's. 1.0 when both sides' centres are zero."""
    whole = centre_a + centre_b
    if whole <= 0.0:
        return 1.0
    return (centre_a * f_b + centre_b * f_a) / whole


def describe(multiplier: float, before: float, after: float, detail: str) -> str:
    """The row note: what moved the centre and by how much."""
    return (f"{NOTE}: centre {after:.2f} = {before:.2f} x {multiplier:.3f} "
            f"({detail}; epochs.TENNIS_ACES_OPPONENT)")
