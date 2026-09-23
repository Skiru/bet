"""Per-set serve counts are priced from a negative binomial (2026-09-23).

Replayed over 10,229 cached tennis events (scripts/sofa/measure_per_set_nb.py):
the normal put ~+8 pp on every per-set OVER. Fernandez aces_set1_for OVER 0.5
at a sample mean of 1.2 was staked at 0.779; at sample means 1.0-1.4 the
normal claimed 0.776, the NB 0.623, and 0.610 happened.
"""

from bet.sofa.engine import (
    calc_p_central_nb_raw,
    predictive_sd,
    uses_negative_binomial,
    winning_boundary,
)


def test_the_measured_metrics_are_listed_and_the_failed_one_is_not():
    for m in ("aces_set1_for", "aces_set2_for", "double_faults_set1_for",
              "double_faults_set2_for", "serve_points_set2_for"):
        assert uses_negative_binomial(m), m
    # One half came out positive (+0.00107): it does not clear the bar.
    assert not uses_negative_binomial("serve_points_set1_for")


def test_the_fernandez_rung_comes_down_to_what_happened():
    values = [4.0, 0.0, 1.0, 2.0, 1.0, 0.0, 0.0, 1.0, 2.0, 1.0]
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    sd = predictive_sd(var, mean, len(values), apply_poisson_floor=True)
    p = calc_p_central_nb_raw(mean, sd, winning_boundary(0.5, "OVER"), "OVER")
    assert 0.55 < p < 0.70, p
