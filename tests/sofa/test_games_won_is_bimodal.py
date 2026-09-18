"""F49 — a bell curve over a distribution with a wall in the middle.

`games_won_for` is the market Superbet quotes at 11.5, and in a best-of-three
a player who wins in straight sets has won at least twelve games. So the
quantity has a loser mode spread over 0-11 and a winner mode stacked on 12+,
with a trough at exactly the line. Integrating a normal across that trough
overstates UNDER, and it did so in the live coupon on nine rows at once.
"""

from __future__ import annotations

import collections
import json
from pathlib import Path

import pytest

from bet.sofa.engine import (
    EMPIRICAL_FREQUENCY_METRICS,
    calc_p_central_raw,
    p_empirical_raw,
    predictive_sd,
    support_floor_for,
    uses_empirical_frequency,
    winning_boundary,
)

REPO = Path(__file__).resolve().parents[2]


def test_games_won_is_priced_from_its_own_frequency() -> None:
    assert uses_empirical_frequency("games_won_for")
    assert "games_won_for" in EMPIRICAL_FREQUENCY_METRICS


def test_the_match_total_is_not_switched_with_it() -> None:
    """games_total is the sum of both players and has no wall at twelve."""
    assert not uses_empirical_frequency("games_total")
    assert not uses_empirical_frequency("aces_for")


def test_the_normal_overstates_the_trough_that_the_sample_knows_is_empty() -> None:
    """A player who won 12, 13, 6, 12, 5, 12, 13, 4, 12, 6 games.

    Six wins, four losses, and not one match at eleven. The sample says
    P(UNDER 11.5) = 0.40 exactly; the normal, fitted to mean 9.5 with a wide
    sd, smears mass across the gap and says far more.
    """
    sample = [12.0, 13.0, 6.0, 12.0, 5.0, 12.0, 13.0, 4.0, 12.0, 6.0]
    n = len(sample)
    mean = sum(sample) / n
    sd = (sum((v - mean) ** 2 for v in sample) / (n - 1)) ** 0.5
    boundary = winning_boundary(11.5, "UNDER")

    hits = sum(1 for v in sample if v < boundary)
    empirical = p_empirical_raw(hits, n)
    normal = calc_p_central_raw(
        mean,
        predictive_sd(sd**2, mean, n),
        boundary,
        "UNDER",
        support_floor_for("games_won_for"),
    )
    assert empirical == pytest.approx(0.4)
    assert normal > empirical
    assert sum(1 for v in sample if v == 11.0) == 0


def test_the_shape_is_really_bimodal_in_the_shipped_samples() -> None:
    """Not a story about tennis — a property of the day's own artifact."""
    path = REPO / "runs/sofa/2026-09-18/03_samples.json"
    if not path.exists():
        pytest.skip("no sample artifact in this checkout")
    counts: collections.Counter[int] = collections.Counter()
    for fixture in json.loads(path.read_text(encoding="utf-8")):
        metric = fixture["metrics"].get("games_won_for")
        if not metric:
            continue
        for side in ("side_a", "side_b"):
            for obs in metric.get(side) or []:
                counts[int(obs["value"])] += 1
    if sum(counts.values()) < 200:
        pytest.skip("too few observations to characterise the shape")

    # The wall: twelve is the most common value by a wide margin, and eleven —
    # the value just under the line — is rare.
    assert counts[12] == max(counts.values())
    assert counts[12] > 3 * counts[11]


def test_an_all_or_nothing_sample_is_still_refused() -> None:
    """The empirical estimator hands outside_model_resolution a 0 or a 1, and
    that is the whole point of taking it unclamped."""
    from bet.sofa.engine import outside_model_resolution

    assert outside_model_resolution(p_empirical_raw(0, 10))
    assert outside_model_resolution(p_empirical_raw(10, 10))
    assert not outside_model_resolution(p_empirical_raw(4, 10))
