from __future__ import annotations

from bet.odds_merge import events_match, merge_event_odds


def test_merge_event_odds_preserves_markets_for_same_bookmaker():
    left = {
        "home_team": "Team A",
        "away_team": "Team B",
        "commence_time": "2026-06-26T18:00:00Z",
        "_odds_source": "oddspapi",
        "bookmakers": [
            {
                "key": "superbet_pl",
                "markets": [{"key": "h2h", "outcomes": [{"name": "Team A", "price": 1.91}]}],
            }
        ],
    }
    right = {
        "home_team": "Team A",
        "away_team": "Team B",
        "commence_time": "2026-06-26T18:20:00Z",
        "_odds_source": "oddspapi",
        "bookmakers": [
            {
                "key": "Superbet PL",
                "markets": [{"key": "over_under", "outcomes": [{"name": "Over 2.5", "price": 2.05, "point": 2.5}]}],
            }
        ],
    }

    merged = merge_event_odds(left, right)

    assert [market["key"] for market in merged["bookmakers"][0]["markets"]] == ["h2h", "totals"]
    assert merged["_source_provenance"] == ["oddspapi"]


def test_events_match_does_not_match_different_hours_even_with_same_teams():
    left = {"home_team": "Team A", "away_team": "Team B", "commence_time": "2026-06-26T18:00:00Z"}
    right = {"home_team": "Team A", "away_team": "Team B", "commence_time": "2026-06-26T21:00:00Z"}

    assert not events_match(left, right)
