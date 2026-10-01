"""Football player props are priced from a negative binomial - measured
2026-10-01: the normal claimed 0.243 on assists 0.5 OVER, realised 0.081."""

from __future__ import annotations

from bet.sofa.engine import (
    calc_p_central_nb_raw,
    predictive_sd,
    uses_negative_binomial,
    winning_boundary,
)


def test_measured_player_metrics_use_the_nb() -> None:
    for m in ("player_assists_for", "player_shots_on_target_for", "player_shots_for"):
        assert uses_negative_binomial(m)


def test_a_low_mean_prop_over_is_not_inflated() -> None:
    # mean 0.2 over n=10 with sd 0.42: at most the Poisson-like mass above 0.
    sd = predictive_sd(0.42**2, 0.2, 10)
    p = calc_p_central_nb_raw(0.2, sd, winning_boundary(0.5, "OVER"), "OVER")
    assert p <= 0.2


def test_woodwork_is_not_a_team_shots_market() -> None:
    from bet.sofa.market_mapper import classify_market

    assert classify_market("Liczba strzałów w obramowanie bramki") is None
    assert classify_market("Liczba strzałów Legia Warszawa") == (
        "shots_for",
        "legia warszawa",
    )
