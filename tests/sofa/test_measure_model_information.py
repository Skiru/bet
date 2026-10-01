"""scripts/sofa/measure_model_information.py - the combination test.

b must come out near 0 for a model that is noise around the price, clearly
positive for a model that knows something the price does not, and the
bootstrap must resample games, not lines.
"""

import math
import random

from scripts.sofa.measure_model_information import bootstrap_b, fit


def _rows(informative: bool, n_games: int = 300, seed: int = 1):
    rng = random.Random(seed)
    rows = []
    for g in range(n_games):
        truth = rng.uniform(-1.5, 1.5)
        price_logit = truth + rng.gauss(0, 0.6)
        model_logit = (truth if informative else price_logit) + rng.gauss(0, 0.4)
        for _ in range(3):  # three lines of one game share its truth
            y = 1.0 if rng.random() < 1 / (1 + math.exp(-truth)) else 0.0
            rows.append({"game": g, "p_model": 1 / (1 + math.exp(-model_logit)),
                         "p_price": 1 / (1 + math.exp(-price_logit)), "y": y})
    return rows


def test_a_model_that_knows_the_truth_gets_a_positive_b():
    b, lo, hi = bootstrap_b(_rows(True), n=200)
    assert lo > 0 and b > 0.3


def test_noise_around_the_price_gets_no_b():
    _, lo, hi = bootstrap_b(_rows(False), n=200)
    assert lo < 0 < hi or abs(lo) < 0.2


def test_the_price_alone_fits_c_near_one():
    rows = _rows(False, seed=3)
    a, b, c = fit(rows)
    assert 0.5 < c + b < 1.5
