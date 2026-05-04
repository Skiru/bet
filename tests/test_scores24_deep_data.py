"""Tests for _extract_scores24_deep_data in generate_market_matrix."""
import pytest
from scripts.generate_market_matrix import _extract_scores24_deep_data


def _make_item(odds=None, h2h=None, form_home=None, form_away=None, trends=None,
               url="https://scores24.live/en/tennis/m-30-04-2026-test"):
    item = {"source_url": url, "home": "A", "away": "B"}
    if odds is not None:
        item["odds"] = odds
    if h2h is not None:
        item["h2h"] = h2h
    if form_home is not None:
        item["form_home"] = form_home
    if form_away is not None:
        item["form_away"] = form_away
    if trends is not None:
        item["trends"] = trends
    return item


class TestExtractScores24DeepData:
    def test_returns_none_for_empty_lookup(self):
        assert _extract_scores24_deep_data("a|b", {}) is None

    def test_returns_none_for_missing_key(self):
        assert _extract_scores24_deep_data("a|b", {"c|d": []}) is None

    def test_returns_none_when_no_scores24_items(self):
        items = [{"source_url": "https://flashscore.com/match/123", "home": "A", "away": "B"}]
        assert _extract_scores24_deep_data("a|b", {"a|b": items}) is None

    def test_returns_none_for_item_with_raw_string(self):
        items = [{"source_url": "https://scores24.live/en/tennis/m-30-04-2026-t", "raw": "some text"}]
        assert _extract_scores24_deep_data("a|b", {"a|b": items}) is None

    def test_happy_path_moneyline_odds(self):
        items = [_make_item(odds={"w1": 1.50, "w2": 2.80, "x": 3.40})]
        result = _extract_scores24_deep_data("a|b", {"a|b": items})
        assert result is not None
        odds_mkts = result["odds_markets"]
        assert len(odds_mkts) == 3
        markets = {m["market"] for m in odds_mkts}
        assert markets == {"ML:Home", "1X2:Draw", "ML:Away"}
        home_mkt = next(m for m in odds_mkts if m["market"] == "ML:Home")
        assert home_mkt["best_odds"] == 1.50
        assert home_mkt["source"] == "scores24"

    def test_totals_extraction(self):
        odds = {"total_lines": [{"direction": "over", "line": 22.5, "odds": 1.85}]}
        items = [_make_item(odds=odds)]
        result = _extract_scores24_deep_data("a|b", {"a|b": items})
        assert result is not None
        assert len(result["odds_markets"]) == 1
        m = result["odds_markets"][0]
        assert m["market"] == "Over 22.5"
        assert m["point"] == 22.5
        assert m["best_odds"] == 1.85

    def test_handicap_extraction(self):
        odds = {"handicap_lines": [{"line": "-1.5", "odds": 1.90}]}
        items = [_make_item(odds=odds)]
        result = _extract_scores24_deep_data("a|b", {"a|b": items})
        assert result is not None
        assert len(result["odds_markets"]) == 1
        assert result["odds_markets"][0]["market"] == "HC -1.5"

    def test_trends_extraction(self):
        trends = [{"category": "Totals", "description": "Over 2.5 in 6/7",
                   "bet_name": "Over 2.5 Goals", "odds": 1.90,
                   "hit_count": 6, "sample_size": 7, "hit_rate": 0.857}]
        items = [_make_item(trends=trends)]
        result = _extract_scores24_deep_data("a|b", {"a|b": items})
        assert result is not None
        assert len(result["trend_markets"]) == 1
        t = result["trend_markets"][0]
        assert t["market"] == "Over 2.5 Goals"
        assert t["safety_score"] == 0.86
        assert t["hit_count"] == 6
        assert t["trend_odds"] == 1.90

    def test_h2h_and_form_extraction(self):
        h2h = {"home_wins": 3, "away_wins": 1, "matches": [{"date": "2026-01-01"}]}
        form_h = [{"date": "2026-04-25", "result": "W"}]
        form_a = [{"date": "2026-04-24", "result": "L"}]
        items = [_make_item(odds={"w1": 1.50}, h2h=h2h, form_home=form_h, form_away=form_a)]
        result = _extract_scores24_deep_data("a|b", {"a|b": items})
        assert result["h2h"]["home_wins"] == 3
        assert result["form"]["home"][0]["result"] == "W"
        assert result["form"]["away"][0]["result"] == "L"

    def test_rejects_odds_outside_bounds(self):
        odds = {"w1": 0.50, "w2": 100.0, "x": 1.00}  # all out of 1.01-50.0
        items = [_make_item(odds=odds)]
        # No valid odds + no trends = None
        assert _extract_scores24_deep_data("a|b", {"a|b": items}) is None

    def test_handles_string_odds_gracefully(self):
        """M1 fix: string odds should not crash."""
        odds = {"w1": "1.50", "total_lines": [{"direction": "over", "line": 22.5, "odds": "1.85"}],
                "handicap_lines": [{"line": "-1.5", "odds": "2.10"}]}
        items = [_make_item(odds=odds)]
        # Should return None since string odds fail isinstance check
        assert _extract_scores24_deep_data("a|b", {"a|b": items}) is None

    def test_handles_string_trend_odds(self):
        """m1 fix: string trend_odds should not crash."""
        trends = [{"category": "T", "bet_name": "O2.5", "odds": "bad",
                   "hit_count": 5, "sample_size": 8, "hit_rate": 0.625}]
        items = [_make_item(trends=trends)]
        result = _extract_scores24_deep_data("a|b", {"a|b": items})
        assert result is not None
        assert result["trend_markets"][0]["trend_odds"] is None

    def test_empty_h2h_not_attached(self):
        """H2H with no matches/wins should not be attached."""
        items = [_make_item(odds={"w1": 2.0}, h2h={})]
        result = _extract_scores24_deep_data("a|b", {"a|b": items})
        assert result is not None
        assert result["h2h"] is None

    def test_mixed_scores24_and_other_items(self):
        """Only scores24 items should be processed."""
        items = [
            {"source_url": "https://flashscore.com/match/1", "home": "A", "away": "B"},
            _make_item(odds={"w1": 1.80, "w2": 2.10}),
        ]
        result = _extract_scores24_deep_data("a|b", {"a|b": items})
        assert result is not None
        assert len(result["odds_markets"]) == 2
