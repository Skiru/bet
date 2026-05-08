"""Tests for odds evaluator (extracted from orchestrator)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from odds_evaluator import _convert_espn_odds_to_decimal


# ---------------------------------------------------------------------------
# American odds → decimal conversion
# ---------------------------------------------------------------------------


def test_convert_positive_american_odds():
    """+150 → 2.50."""
    result = _convert_espn_odds_to_decimal({
        "moneyline": {"home": "+150"},
    })
    assert result["moneyline"]["home"] == 2.5


def test_convert_negative_american_odds():
    """-200 → 1.50."""
    result = _convert_espn_odds_to_decimal({
        "moneyline": {"home": "-200"},
    })
    assert result["moneyline"]["home"] == 1.5


def test_convert_espn_moneyline():
    """Full moneyline dict with home/away/draw."""
    result = _convert_espn_odds_to_decimal({
        "moneyline": {"home": "-150", "away": "+130", "draw": "+250"},
    })
    ml = result["moneyline"]
    assert "home" in ml
    assert "away" in ml
    assert "draw" in ml
    # -150 → 1 + 100/150 = 1.667
    assert abs(ml["home"] - 1.667) < 0.01
    # +130 → 1 + 130/100 = 2.30
    assert ml["away"] == 2.3
    # +250 → 1 + 250/100 = 3.50
    assert ml["draw"] == 3.5


def test_convert_espn_total():
    """Total with over/under."""
    result = _convert_espn_odds_to_decimal({
        "total": {"line": "2.5", "over_odds": "-110", "under_odds": "+100"},
    })
    total = result["total"]
    assert total["line"] == "2.5"
    # -110 → 1 + 100/110 ≈ 1.909
    assert abs(total["over"] - 1.909) < 0.01
    # +100 → 1 + 100/100 = 2.0
    assert total["under"] == 2.0


def test_convert_espn_spread():
    """Spread with home/away."""
    result = _convert_espn_odds_to_decimal({
        "spread": {
            "home_line": "-3.5", "away_line": "+3.5",
            "home_odds": "-110", "away_odds": "-110",
        },
    })
    spread = result["spread"]
    assert spread["home_line"] == "-3.5"
    assert spread["away_line"] == "+3.5"
    # -110 → 1 + 100/110 ≈ 1.909
    assert abs(spread["home"] - 1.909) < 0.01
    assert abs(spread["away"] - 1.909) < 0.01
