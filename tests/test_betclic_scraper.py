"""Tests for Betclic market scraper — keyword-based detection."""
import pytest
from bet.scrapers.betclic import (
    BetclicMarketInfo,
    MARKET_DETECTION_RULES,
    parse_event_page,
)


class TestMarketDetection:
    """Test that has_X booleans are keyword-based, not tab-based."""

    def test_statistics_tab_without_keywords_gives_false(self):
        """Statystyki tab present but no stat keywords → all has_X = False."""
        info = BetclicMarketInfo(
            has_statistics_tab=True,
            tabs=["Statystyki", "Wynik", "Gole"],
            market_names=["Wynik meczu", "Gole Powyżej/Poniżej", "Handicap"],
            open_market_count=412,
        )
        # Simulate what parse_event_page does (manually apply detection)
        all_text = " ".join(info.market_names).lower()
        info.has_corners = "rożn" in all_text or "corner" in all_text
        info.has_cards = "kartek" in all_text or "kartk" in all_text or "czerwona" in all_text
        info.has_shots = any(
            ("strzał" in m.lower() or "celny" in m.lower()) and "zawodnika" not in m.lower()
            for m in info.market_names
        )
        info.has_fouls = "faul" in all_text

        assert info.has_corners is False
        assert info.has_cards is False
        assert info.has_shots is False
        assert info.has_fouls is False

    def test_corners_keyword_detected(self):
        """Market name containing 'rożn' → has_corners = True."""
        info = BetclicMarketInfo(
            has_statistics_tab=True,
            tabs=["Statystyki", "Wynik"],
            market_names=["Rzuty rożne Powyżej/Poniżej", "1. połowa - Rzuty rożne"],
        )
        all_text = " ".join(info.market_names).lower()
        info.has_corners = "rożn" in all_text or "corner" in all_text
        assert info.has_corners is True

    def test_player_shots_not_counted_as_team_shots(self):
        """'Liczba celnych strzałów zawodnika' is player-level, not team shots."""
        info = BetclicMarketInfo(
            has_statistics_tab=True,
            tabs=["Statystyki"],
            market_names=["Liczba celnych strzałów zawodnika (OPTA)"],
        )
        info.has_shots = any(
            ("strzał" in m.lower() or "celny" in m.lower()) and "zawodnika" not in m.lower()
            for m in info.market_names
        )
        assert info.has_shots is False

    def test_fouls_keyword_detected(self):
        """Market name containing 'faul' → has_fouls = True."""
        info = BetclicMarketInfo(
            has_statistics_tab=True,
            tabs=["Statystyki"],
            market_names=["Faule Powyżej/Poniżej"],
        )
        all_text = " ".join(info.market_names).lower()
        info.has_fouls = "faul" in all_text
        assert info.has_fouls is True


class TestIsMarketAvailable:
    """Test is_market_available() returns correct results."""

    def test_tab_present_no_keywords_returns_none(self):
        """Statystyki tab + no keywords → None (unconfirmed)."""
        info = BetclicMarketInfo(
            has_statistics_tab=True,
            tabs=["Statystyki", "Wynik", "Gole"],
            market_names=["Wynik meczu", "Gole Powyżej/Poniżej"],
            open_market_count=412,
        )
        available, note = info.is_market_available("corners_total")
        assert available is None
        assert "not confirmed" in note.lower()

    def test_tab_present_with_keywords_returns_true(self):
        """Statystyki tab + keyword in market_names → True."""
        info = BetclicMarketInfo(
            has_statistics_tab=True,
            tabs=["Statystyki", "Wynik"],
            market_names=["Rzuty rożne Powyżej/Poniżej", "Wynik meczu"],
            open_market_count=50,
        )
        available, note = info.is_market_available("corners_total")
        assert available is True
        assert "confirmed" in note.lower()

    def test_no_stats_tab_returns_false(self):
        """No Statystyki tab → False for stat markets."""
        info = BetclicMarketInfo(
            has_statistics_tab=False,
            tabs=["Wynik", "Gole"],
            market_names=["Wynik meczu"],
        )
        available, note = info.is_market_available("corners_total")
        assert available is False

    def test_goals_market_with_tab_and_keyword(self):
        """Gole tab + keyword → True."""
        info = BetclicMarketInfo(
            has_statistics_tab=False,
            tabs=["Wynik", "Gole"],
            market_names=["Gole Powyżej/Poniżej", "Oba zespoły strzelą gola"],
        )
        available, note = info.is_market_available("goals_total")
        assert available is True

    def test_bournemouth_scenario(self):
        """Real scenario: Bournemouth has 412 markets, Statystyki tab, but NO corners."""
        info = BetclicMarketInfo(
            has_statistics_tab=True,
            tabs=["MyCombi", "Top", "Wynik", "Strzelcy", "Gole",
                  "Metoda gola", "Wynik / Handicap", "Statystyki"],
            market_names=[
                "1 gol lub więcej", "1. połowa Wynik", "2 gole lub więcej",
                "2. połowa Wynik", "3 gole lub więcej", "Brak Gola",
                "Czerwona kartka", "Dokładny wynik", "Gole",
                "Gole Powyżej/Poniżej", "Handicap",
                "Którykolwiek zawodnik strzeli gola",
                "Liczba celnych strzałów zawodnika (OPTA)",
                "Liczba goli - Bournemouth", "Liczba goli - Manchester City",
                "Metoda gola", "Oba zespoły strzelą gola",
                "Oba zespoły strzelą gola lub Powyżej 2,5 gola w meczu",
                "Ostatni gol", "Pierwszy gol", "Podwójna Szansa", "Strzelec",
                "Wynik", "Wynik / Handicap",
                "Wynik meczu (z wyłączeniem dogrywki)",
                "Zawodnik strzeli gola lub zaliczy asystę",
                "Zawodnik strzeli gola lub zaliczy asystę + jego zmiennik",
            ],
            open_market_count=412,
        )
        # Corners not available
        avail_corners, _ = info.is_market_available("corners_total")
        assert avail_corners is not True  # None or False, never True

        # Fouls not available
        avail_fouls, _ = info.is_market_available("fouls")
        assert avail_fouls is not True

        # Team shots not available (only player-level)
        avail_shots, _ = info.is_market_available("shots_on_target")
        assert avail_shots is not True, "Player-level shots must not confirm team shots_on_target"

        # Goals ARE available
        avail_goals, _ = info.is_market_available("goals_total")
        assert avail_goals is True

        # Red card IS available ("Czerwona kartka" in market_names)
        avail_red, _ = info.is_market_available("red_card")
        assert avail_red is True
