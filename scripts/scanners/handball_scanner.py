"""Handball scanner module."""
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


class HandballScanner(BaseSportScanner):
    """Handball-specific scanner."""

    @property
    def sport_name(self) -> str:
        return "handball"

    @property
    def scanner_group(self) -> str:
        return "handball"

    @property
    def urls(self) -> list[str]:
        return [
            # FlashScore
            "https://www.flashscore.com/handball/",
            "https://www.flashscore.com/handball/poland/",
            "https://www.flashscore.com/handball/poland/superliga/",
            "https://www.flashscore.com/handball/poland/superliga-women/",
            "https://www.flashscore.com/handball/europe/champions-league/",
            "https://www.flashscore.com/handball/germany/bundesliga/",
            "https://www.flashscore.com/handball/france/starligue/",
            "https://www.flashscore.com/handball/spain/liga-asobal/",
            "https://www.flashscore.com/handball/denmark/handboldligaen/",
            # Betclic
            "https://www.betclic.pl/pilka-reczna-s3",
            # OddsPortal
            "https://www.oddsportal.com/handball/",
            # BetExplorer
            "https://www.betexplorer.com/handball/",
            # Forebet
            "https://www.forebet.com/en/handball/predictions-today",
            # Scores24
            "https://scores24.live/en/handball",
        ]

    @property
    def timeout_per_page(self) -> int:
        return 45

    @property
    def max_deep_links(self) -> int:
        return 10

    @property
    def required_stat_keys(self) -> list[str]:
        return ["goals", "saves", "turnovers", "total_goals"]

    @property
    def min_expected_events(self) -> int:
        return 10

    def get_fallback_urls(self) -> list[str]:
        return [
            "https://www.sofascore.com/",
        ]


register_scanner("handball", HandballScanner)
