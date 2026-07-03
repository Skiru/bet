from bet.pipeline.odds_optional_analysis_contracts import (
    OddsStatus,
    derive_bettable_status,
    derive_odds_status,
    derive_pricing_tier,
)


def test_provider_odds_without_human_superbet_quote_are_only_partially_priced() -> None:
    status = derive_odds_status(
        has_human_odds=False,
        provider_odds_present=True,
        line_source_status="EXACT_PROVIDER_LINE",
    )
    assert status == OddsStatus.PARTIALLY_PRICED
    assert derive_pricing_tier(status).value == "PARTIALLY_PRICED_ANALYTICAL"


def test_unknown_line_keeps_analysis_but_not_price_readiness() -> None:
    status = derive_odds_status(
        has_human_odds=False,
        provider_odds_present=True,
        line_source_status="LINE_REQUIRES_OPERATOR_CHECK",
    )
    assert status == OddsStatus.UNPRICED
    assert derive_bettable_status(odds_status=status, has_human_odds=False).value == "NOT_BETTABLE_ANALYSIS_ONLY"


def test_exact_human_quote_is_only_path_to_priced_status() -> None:
    status = derive_odds_status(
        has_human_odds=True,
        provider_odds_present=True,
        line_source_status="EXACT_PROVIDER_LINE",
    )
    assert status == OddsStatus.PRICED
