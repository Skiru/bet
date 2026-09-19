"""A rung quoted on one side only has no price to check the model against.

`market_p` is what `bar_probability` shrinks the sample toward and what `edge`
is measured against. When only one side of a rung is quoted there is nothing
to devig, so `market_p` is None, `p_bar` falls back to the raw model at w=1,
and `bar_is_unreachable` returns False without testing anything. The row is
then selected by the model alone.

On the 2026-09-19 coupon that was 71 of 520 rows, at a median surplus of 4.95
against 0.24 for the anchored rows and median odds of 12.0 against 3.10 — the
signature of a missing check, not of an edge.
"""

from __future__ import annotations

from bet.sofa.engine import bar_is_unreachable, bar_probability


def test_bar_probability_has_no_price_to_shrink_toward() -> None:
    """Documents the mechanism this rule exists to refuse."""
    p_bar, _ = bar_probability(
        p_central=0.30, hits=3, n=10, p_low_val=0.30, market_p=None
    )
    assert p_bar == 0.30, "with no anchor the model is used raw, at weight 1"

    anchored, _ = bar_probability(
        p_central=0.30, hits=3, n=10, p_low_val=0.30, market_p=0.10
    )
    assert anchored < 0.30, "an anchored row is pulled toward the price"


def test_the_unreachable_guard_cannot_fire_without_an_anchor() -> None:
    """So the guard that refuses impossible rows is inert for exactly these."""
    assert bar_is_unreachable(offered_odds=1.07, market_p=0.95, n=10) is True
    assert bar_is_unreachable(offered_odds=1.07, market_p=None, n=10) is False


def test_run_sheet_withholds_value_when_market_p_is_none() -> None:
    """The rule itself, read off the source.

    run_sheet is a script, not an importable unit with a seam at this point,
    so this asserts the branch exists and precedes the ladder gate — the same
    shape as the NO_LADDER_CHECK rule it sits next to.
    """
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2] / "scripts" / "sofa" / "run_sheet.py"
    ).read_text()
    assert "NO_PRICE_ANCHOR" in src
    assert 'if m_p is None:' in src
    anchor_at = src.index("NO_PRICE_ANCHOR")
    ladder_at = src.index("NO_LADDER_CHECK")
    assert anchor_at < ladder_at, "the anchor gate must be checked first"
    # and it must set LEAN, never VALUE
    window = src[src.index("if m_p is None:") : anchor_at]
    assert 'verdict = "LEAN"' in window


def test_a_derived_joint_needs_the_market_marginals_to_be_value() -> None:
    """The same rule on the derived path, which has its own verdict block.

    `both_over_*` and `handicap_*` are built in derived.py, not run_sheet, so
    the NO_PRICE_ANCHOR gate above does not reach them. Their equivalent is
    `p_marginal`: the joint priced off the market's own per-side marginals
    with our measured dependence. When the per-side ladders are not quoted at
    that line, p_marginal is None — and the check was skipped rather than
    failed, which let the row through as VALUE.

    On 2026-09-19 that was 23 rows at a median price of 12.0, every one of
    them also carrying ONE_SIDED_LADDER, and with no per-side sample in the
    artifacts that could have checked them either.
    """
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2] / "src" / "bet" / "sofa" / "derived.py"
    ).read_text()
    assert "NO_MARKET_MARGINAL_CHECK" in src
    guard_at = src.index("if p_marginal is None:")
    disagree_at = src.index("MARGINAL_DISAGREEMENT")
    assert guard_at < disagree_at, "the None case must be refused before the compare"
    window = src[guard_at:disagree_at]
    assert 'verdict = "LEAN"' in window
