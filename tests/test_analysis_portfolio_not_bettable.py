import json
from pathlib import Path


RUN_ROOT = Path("tests/fixtures/pipeline_runs/FULL_DAY_SESSION_20260703_SUPERBET_ANALYSIS_FIRST_V18_1")


def test_analysis_portfolios_remain_non_bettable() -> None:
    portfolios = json.loads((RUN_ROOT / "12_analysis_portfolio_drafts.json").read_text(encoding="utf-8")).get("analysis_portfolios") or []
    assert portfolios
    assert any(
        entry.get("pricing_tier") == "UNPRICED_DEEP_ANALYTICAL"
        for portfolio in portfolios
        for entry in portfolio.get("entries") or []
    )
    for portfolio in portfolios:
        assert portfolio.get("bettable") is False
        assert portfolio.get("final_coupon_allowed") is False
        assert portfolio.get("combined_odds") is None
