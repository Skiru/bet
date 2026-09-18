"""F45 — the tennis serve markets Superbet prices and sofa could not read.

Of 197 tennis fixtures on the 2026-09-18 board, the offer mapped only games,
sets and the two bare serve counts. Everything else about the serve went to
unmapped_markets: "Liczba asow + podwojnych bledow" and its per-player form,
the per-set aces / double faults / combined markets, and the whole
who-takes-more family ("Najwiecej asow serwisowych", "Najwiecej asow +
podwojnych bledow", and their per-set versions).
"""

from __future__ import annotations

from bet.sofa.contracts import GapReason
from bet.sofa.market_mapper import (
    DERIVED_BASE_TO_SIDE_METRIC,
    classify_derived_market,
    classify_market,
    get_mechanism_family,
)
from bet.sofa.metrics import TENNIS_METRICS, extract_metric

# Shape taken from the cache: /statistics carries the serve keys per set.
STATS = {
    "ALL": {"aces": (9.0, 5.0), "doubleFaults": (3.0, 4.0), "gamesWon": (13.0, 11.0)},
    "1ST": {"aces": (4.0, 2.0), "doubleFaults": (1.0, 2.0)},
    "2ND": {"aces": (3.0, 2.0), "doubleFaults": (1.0, 1.0)},
    "3RD": {"aces": (2.0, 1.0), "doubleFaults": (1.0, 1.0)},
}


def _get(metric: str, stats: dict = STATS, is_home: bool = True) -> float | GapReason:
    return extract_metric(metric, "tennis", stats, None, {}, is_home)


# --------------------------------------------------------------------------
# aces + double faults is one quantity, not two rows added up
# --------------------------------------------------------------------------


def test_serve_points_is_the_sum_of_both_serve_outcomes() -> None:
    assert _get("serve_points_total") == 21.0  # 9 + 5 + 3 + 4
    assert _get("serve_points_for", is_home=True) == 12.0  # 9 + 3
    assert _get("serve_points_for", is_home=False) == 9.0  # 5 + 4


def test_serve_points_equals_aces_plus_double_faults_on_every_scope() -> None:
    for combined, ace, fault in (
        ("serve_points_total", "aces_total", "double_faults_total"),
        ("serve_points_for", "aces_for", "double_faults_for"),
        ("serve_points_set1_total", "aces_set1_total", "double_faults_set1_total"),
        ("serve_points_set1_for", "aces_set1_for", "double_faults_set1_for"),
        ("serve_points_set2_total", "aces_set2_total", "double_faults_set2_total"),
        ("serve_points_set2_for", "aces_set2_for", "double_faults_set2_for"),
    ):
        for is_home in (True, False):
            assert _get(combined, is_home=is_home) == (
                _get(ace, is_home=is_home) + _get(fault, is_home=is_home)
            ), combined


def test_half_a_sum_is_not_a_smaller_sum() -> None:
    """One key present and the other missing must refuse, not fabricate."""
    only_aces = {"ALL": {"aces": (9.0, 5.0)}}
    assert _get("serve_points_total", only_aces) == GapReason.STAT_KEY_ABSENT
    assert _get("serve_points_for", only_aces) == GapReason.STAT_KEY_ABSENT
    assert _get("aces_total", only_aces) == 14.0


# --------------------------------------------------------------------------
# per set
# --------------------------------------------------------------------------


def test_each_set_reads_its_own_period() -> None:
    assert _get("aces_set1_total") == 6.0
    assert _get("aces_set2_total") == 5.0
    assert _get("aces_total") == 14.0  # includes the third set
    assert _get("double_faults_set1_for", is_home=False) == 2.0
    assert _get("serve_points_set2_for", is_home=True) == 4.0


def test_sets_do_not_have_to_add_up_to_the_match() -> None:
    """The football halves check must not reach tennis.

    1ST + 2ND == ALL only when the match went two sets; 434 of the 1,992
    cached tennis events reach a third. Applying the football guard here would
    refuse every three-set match — and this fixture is one.
    """
    assert _get("aces_set1_total") + _get("aces_set2_total") != _get("aces_total")
    assert isinstance(_get("aces_set1_total"), float)
    for name, spec in TENNIS_METRICS.items():
        assert "period_complement" not in spec, name


def test_a_set_never_played_is_missing_data_not_a_nil_set() -> None:
    two_setter = {
        "ALL": {"aces": (6.0, 4.0), "doubleFaults": (2.0, 3.0)},
        "1ST": {"aces": (4.0, 2.0), "doubleFaults": (1.0, 2.0)},
        "2ND": {"aces": (2.0, 2.0), "doubleFaults": (1.0, 1.0)},
    }
    assert _get("aces_set1_total", two_setter) == 6.0
    # No third set is declared as a metric, but a genuinely absent period is
    # NO_STATISTICS wherever one is asked for.
    assert extract_metric(
        "aces_set2_total", "tennis", {"ALL": two_setter["ALL"]}, None, {}, True
    ) == GapReason.NO_STATISTICS


# --------------------------------------------------------------------------
# the names Superbet actually sends
# --------------------------------------------------------------------------


def test_match_level_serve_market_names() -> None:
    assert classify_market("Liczba asów + podwójnych błędów") == (
        "serve_points_total",
        "",
    )
    assert classify_market("Liczba asów") == ("aces_total", "")
    assert classify_market("Liczba podwójnych błędów") == ("double_faults_total", "")


def test_per_set_market_names_both_spacings() -> None:
    assert classify_market("1. set - liczba asów") == ("aces_set1_total", "")
    assert classify_market("1.set - liczba asów") == ("aces_set1_total", "")
    assert classify_market("2. set - liczba podwójnych błędów") == (
        "double_faults_set2_total",
        "",
    )
    assert classify_market("1. set - liczba asów + podwójnych błędów") == (
        "serve_points_set1_total",
        "",
    )


def test_per_player_names_with_and_without_the_dash() -> None:
    """Superbet writes "Quevedo liczba asow" but "Quevedo - liczba podwojnych
    bledow", on one screen. The F38 trap, twice."""
    assert classify_market("1. set - Kaitlin Quevedo liczba asów") == (
        "aces_set1_for",
        "kaitlin quevedo",
    )
    assert classify_market("1. set - Kaitlin Quevedo - liczba podwójnych błędów") == (
        "double_faults_set1_for",
        "kaitlin quevedo",
    )
    assert classify_market("2. set - Teodora Kostovic liczba asów + podwójnych błędów") == (
        "serve_points_set2_for",
        "teodora kostovic",
    )
    assert classify_market("Kaitlin Quevedo liczba asów + podwójnych błędów") == (
        "serve_points_for",
        "kaitlin quevedo",
    )
    # The set-scoped patterns must not swallow the plain per-player forms.
    assert classify_market("Jiri Lehecka liczba asów") == ("aces_for", "jiri lehecka")


def test_who_takes_more_family() -> None:
    def most(name: str) -> tuple | None:
        return classify_derived_market(name, "Ben Shelton", None)

    assert most("Najwięcej asów serwisowych") == ("most_aces", "ben shelton", 0.0, "OVER")
    assert most("Najwięcej podwójnych błędów") == (
        "most_double_faults",
        "ben shelton",
        0.0,
        "OVER",
    )
    assert most("Najwięcej asów + podwójnych błędów") == (
        "most_serve_points",
        "ben shelton",
        0.0,
        "OVER",
    )
    assert most("1. set - najwięcej asów") == (
        "most_aces_set1",
        "ben shelton",
        0.0,
        "OVER",
    )
    assert most("2. set - najwięcej podwójnych błędów") == (
        "most_double_faults_set2",
        "ben shelton",
        0.0,
        "OVER",
    )
    # The football scope works through the same rule, with its own spelling.
    assert most("1. połowa - najwięcej rzutów rożnych") == (
        "most_corners_1h",
        "ben shelton",
        0.0,
        "OVER",
    )


def test_a_scoped_market_we_cannot_sample_stays_unmapped() -> None:
    """Better visible in unmapped_markets than a row with no sample behind it."""
    assert "games_set1_for" not in TENNIS_METRICS
    assert classify_derived_market("1. set - najwięcej gemów", "Ben Shelton", None) is None


# --------------------------------------------------------------------------
# families
# --------------------------------------------------------------------------


def test_every_serve_market_is_one_mechanism() -> None:
    """Aces, double faults and their sum are what happened on serve, said
    three ways. A fixture must not spend three coupon slots saying it."""
    for market in (
        "aces_for",
        "aces_total",
        "double_faults_for",
        "serve_points_for",
        "serve_points_total",
        "aces_set1_for",
        "double_faults_set2_total",
        "serve_points_set1_for",
        "most_aces",
        "most_serve_points",
        "most_aces_set1",
        "most_double_faults_set2",
    ):
        assert get_mechanism_family(market) == "tennis_serve", market


def test_serve_is_not_the_same_mechanism_as_length() -> None:
    assert get_mechanism_family("games_won_for") == "tennis_length"
    assert get_mechanism_family("aces_for") != get_mechanism_family("games_won_for")


def test_every_derived_serve_base_knows_its_side_metric() -> None:
    for base in ("aces", "double_faults", "serve_points"):
        side = DERIVED_BASE_TO_SIDE_METRIC[base]
        assert side in TENNIS_METRICS, side


# --------------------------------------------------------------------------
# the line Superbet quotes on a scoped market
# --------------------------------------------------------------------------


def test_a_set_scoped_line_carries_its_set_number() -> None:
    """Superbet sends specialBetValue as "1-4.5" on a set-scoped market.

    `float("1-4.5")` raises, and on the 2026-09-18 board *every* per-set aces,
    double-faults and combined rung landed in unmapped_markets as
    "unparseable line". The market name classified fine; the rung died one
    step later.
    """
    from bet.sofa.offer import parse_line

    assert parse_line("4.5", "aces_total") == 4.5
    assert parse_line(3.5, "aces_total") == 3.5
    assert parse_line("1-1.5", "aces_set1_total") == 1.5
    assert parse_line("2-6.5", "serve_points_set2_total") == 6.5
    assert parse_line("1-10.5", "serve_points_set1_for") == 10.5
    assert parse_line("2-4.5", "double_faults_set2_for") == 4.5


def test_a_prefix_that_disagrees_with_its_market_is_refused() -> None:
    """A set-1 price on a set-2 ladder is worse than no rung at all."""
    import pytest

    from bet.sofa.offer import parse_line

    with pytest.raises(ValueError, match="disagrees"):
        parse_line("1-4.5", "aces_set2_total")
    with pytest.raises(ValueError, match="disagrees"):
        parse_line("2-4.5", "aces_set1_for")
    with pytest.raises(ValueError, match="unexpected scope prefix"):
        parse_line("1-2.5", "aces_total")
    with pytest.raises(ValueError, match="unparseable"):
        parse_line("nonsense", "aces_total")


def test_the_football_half_scope_uses_the_same_rule() -> None:
    from bet.sofa.offer import parse_line

    assert parse_line("1-3.5", "corners_1h_total") == 3.5
    assert parse_line("2-3.5", "corners_2h_for") == 3.5
