"""Basketball scanner module."""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE.parent / "src"))

try:
    from .base_scanner import BaseSportScanner
    from . import register_scanner
except ImportError:
    from scanners.base_scanner import BaseSportScanner
    from scanners import register_scanner


class BasketballScanner(BaseSportScanner):
    """Basketball-specific scanner — Tier 1 sport."""

    @property
    def sport_name(self) -> str:
        return "basketball"

    @property
    def scanner_group(self) -> str:
        return "basketball"

    @property
    def urls(self) -> list[str]:
        return [
            # FlashScore
            "https://www.flashscore.com/basketball/",
            "https://www.flashscore.com/basketball/usa/nba/",
            "https://www.flashscore.com/basketball/europe/euroleague/",
            "https://www.flashscore.com/basketball/europe/eurocup/",
            "https://www.flashscore.com/basketball/europe/champions-league/",
            "https://www.flashscore.com/basketball/spain/acb/",
            "https://www.flashscore.com/basketball/germany/bundesliga/",
            "https://www.flashscore.com/basketball/france/lnb/",
            "https://www.flashscore.com/basketball/italy/lega-a/",
            "https://www.flashscore.com/basketball/greece/basket-league/",
            "https://www.flashscore.com/basketball/poland/",
            "https://www.flashscore.com/basketball/poland/basket-liga/",
            "https://www.flashscore.com/basketball/poland/plk/",
            "https://www.flashscore.com/basketball/poland/1-liga/",
            "https://www.flashscore.com/basketball/turkey/bsl/",
            # Betclic
            "https://www.betclic.pl/koszykowka-s4",
            # OddsPortal
            "https://www.oddsportal.com/basketball/",
            # BetExplorer
            "https://www.betexplorer.com/basketball/",
            # Basketball-Reference
            "https://www.basketball-reference.com/",
            # Forebet
            "https://www.forebet.com/en/basketball/predictions-today",
            # Scores24
            "https://scores24.live/en/basketball",
            # Covers + TeamRankings
            "https://www.covers.com/",
            "https://www.teamrankings.com/",
        ]

    @property
    def timeout_per_page(self) -> int:
        return 45

    @property
    def max_deep_links(self) -> int:
        return 20

    @property
    def required_stat_keys(self) -> list[str]:
        return ["points", "rebounds", "assists", "steals", "blocks", "turnovers"]

    @property
    def min_expected_events(self) -> int:
        return 20

    def get_fallback_urls(self) -> list[str]:
        return [
            "https://www.flashscore.com/basketball/poland/basket-liga-women/",
        ]


register_scanner("basketball", BasketballScanner)
