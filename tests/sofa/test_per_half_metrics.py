"""F43 — per-half counting metrics read the period Sofascore actually keys.

`/statistics` has always been keyed by period ("1ST", "2ND", "ALL") and
`extract_flat_statistics` has always preserved that, but `extract_metric` read
"ALL" unconditionally. Every per-half counting market Superbet prices —
"1. polowa - liczba rzutow roznych" on 92 fixtures of the 2026-09-18 board,
plus ~100 per-team forms — went to unmapped_markets.
"""

from __future__ import annotations

from bet.sofa.contracts import GapReason
from bet.sofa.market_mapper import classify_market, get_mechanism_family
from bet.sofa.metrics import FOOTBALL_METRICS, extract_metric

# Live-verified shape, from event 16950627 pulled through the bridge on
# 2026-09-18: cornerKicks ALL=(5,7), 1ST=(2,2), 2ND=(3,5).
STATS = {
    "ALL": {"cornerKicks": (5.0, 7.0), "fouls": (8.0, 11.0)},
    "1ST": {"cornerKicks": (2.0, 2.0), "fouls": (3.0, 5.0)},
    "2ND": {"cornerKicks": (3.0, 5.0), "fouls": (5.0, 6.0)},
}
LISTING = {"homeScore": {"current": 1}, "awayScore": {"current": 2}}


def _get(metric: str, stats: dict, is_home: bool = True) -> float | GapReason:
    return extract_metric(metric, "football", stats, None, LISTING, is_home)


def test_each_half_reads_its_own_period() -> None:
    assert _get("corners_1h_total", STATS) == 4.0
    assert _get("corners_2h_total", STATS) == 8.0
    assert _get("corners_total", STATS) == 12.0
    assert _get("corners_1h_for", STATS, is_home=True) == 2.0
    assert _get("corners_2h_for", STATS, is_home=False) == 5.0
    assert _get("fouls_1h_total", STATS) == 8.0


def test_the_halves_add_up_to_the_match() -> None:
    for whole, first, second in (
        ("corners_total", "corners_1h_total", "corners_2h_total"),
        ("corners_for", "corners_1h_for", "corners_2h_for"),
    ):
        for is_home in (True, False):
            assert _get(whole, STATS, is_home) == (
                _get(first, STATS, is_home) + _get(second, STATS, is_home)
            )


def test_a_half_that_disagrees_with_the_match_is_refused() -> None:
    """1-2% of cached events carry halves that do not sum; which figure is
    wrong is unknowable, so the observation goes, not a guess."""
    broken = {
        "ALL": {"cornerKicks": (4.0, 2.0)},
        "1ST": {"cornerKicks": (4.0, 0.0)},
        "2ND": {"cornerKicks": (1.0, 2.0)},  # home: 4 + 1 != 4
    }
    assert _get("corners_1h_total", broken) == GapReason.INTERNAL_INCONSISTENT
    assert _get("corners_2h_for", broken) == GapReason.INTERNAL_INCONSISTENT
    # The match-level metric is untouched: the event keeps its ALL sample.
    assert _get("corners_total", broken) == 6.0


def test_a_missing_half_is_missing_data_not_a_nil_half() -> None:
    only_all = {"ALL": {"cornerKicks": (5.0, 7.0)}}
    assert _get("corners_1h_total", only_all) == GapReason.NO_STATISTICS
    assert _get("corners_total", only_all) == 12.0


def test_a_half_without_its_counterpart_is_still_read() -> None:
    """The consistency check needs both halves; one alone is not a fault."""
    partial = {
        "ALL": {"cornerKicks": (5.0, 7.0)},
        "1ST": {"cornerKicks": (2.0, 2.0)},
    }
    assert _get("corners_1h_total", partial) == 4.0


def test_every_declared_period_is_one_sofascore_actually_sends() -> None:
    for name, spec in FOOTBALL_METRICS.items():
        assert spec.get("period", "ALL") in {"ALL", "1ST", "2ND"}, name


def test_a_half_is_a_scope_not_a_mechanism() -> None:
    """Otherwise first-half corners and match corners reach one coupon as if
    they were independent evidence."""
    assert get_mechanism_family("corners_1h_for") == get_mechanism_family("corners_for")
    assert get_mechanism_family("corners_2h_total") == get_mechanism_family(
        "corners_total"
    )
    assert get_mechanism_family("fouls_1h_for") == get_mechanism_family("fouls_for")
    assert get_mechanism_family("shots_on_target_1h_total") == get_mechanism_family(
        "shots_on_target_total"
    )


def test_superbet_names_for_both_spacings_and_both_scopes() -> None:
    """Superbet writes the half with and without the space after the dot, and
    puts no dash before the metric on the per-team form (the F38 trap)."""
    assert classify_market("1. połowa - liczba rzutów rożnych") == (
        "corners_1h_total",
        "",
    )
    assert classify_market("1.połowa - liczba rzutów rożnych") == (
        "corners_1h_total",
        "",
    )
    assert classify_market("2. połowa - liczba rzutów rożnych") == (
        "corners_2h_total",
        "",
    )
    assert classify_market("1. połowa - Brentford liczba rzutów rożnych") == (
        "corners_1h_for",
        "brentford",
    )
    assert classify_market("2. połowa - Śląsk Wrocław liczba rzutów rożnych") == (
        "corners_2h_for",
        "slask wroclaw",
    )
    # The whole-match forms must not be captured by the half patterns.
    assert classify_market("Liczba rzutów rożnych") == ("corners_total", "")
    assert classify_market("Brentford - liczba rzutów rożnych") == (
        "corners_for",
        "brentford",
    )


def test_cards_per_half_are_deliberately_absent() -> None:
    """cards_points comes from /incidents, and a second-yellow dismissal whose
    first yellow was in the other half is a modelling question, not a period
    key. If this ever gains an answer, delete the test with the metric."""
    assert "cards_points_1h_total" not in FOOTBALL_METRICS
    assert classify_market("1. połowa - liczba kartek") is None
