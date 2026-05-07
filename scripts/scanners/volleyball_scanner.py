"""Volleyball scanner module."""
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


class VolleyballScanner(BaseSportScanner):
    """Volleyball-specific scanner — Tier 1 sport."""

    @property
    def sport_name(self) -> str:
        return "volleyball"

    @property
    def scanner_group(self) -> str:
        return "volleyball"

    @property
    def urls(self) -> list[str]:
        return [
            # FlashScore
            "https://www.flashscore.com/volleyball/",
            "https://www.flashscore.com/volleyball/poland/",
            "https://www.flashscore.com/volleyball/poland/plusliga/",
            "https://www.flashscore.com/volleyball/poland/i-liga/",
            "https://www.flashscore.com/volleyball/poland/tauron-liga-women/",
            "https://www.flashscore.com/volleyball/poland/i-liga-women/",
            "https://www.flashscore.com/volleyball/italy/superlega/",
            "https://www.flashscore.com/volleyball/france/ligue-a/",
            "https://www.flashscore.com/volleyball/turkey/efeler-ligi/",
            "https://www.flashscore.com/volleyball/germany/bundesliga/",
            "https://www.flashscore.com/volleyball/europe/champions-league/",
            "https://www.flashscore.com/volleyball/brazil/superliga/",
            # Betclic
            "https://www.betclic.pl/siatkowka-s18",
            # OddsPortal
            "https://www.oddsportal.com/volleyball/",
            # BetExplorer
            "https://www.betexplorer.com/volleyball/",
            # Forebet
            "https://www.forebet.com/en/volleyball/predictions-today",
            # Scores24
            "https://scores24.live/en/volleyball",
        ]

    @property
    def timeout_per_page(self) -> int:
        return 45

    @property
    def max_deep_links(self) -> int:
        return 15

    @property
    def required_stat_keys(self) -> list[str]:
        return ["points", "aces", "blocks", "attack_pct", "sets_won"]

    @property
    def min_expected_events(self) -> int:
        return 15

    def get_fallback_urls(self) -> list[str]:
        return [
            "https://www.sofascore.com/",
        ]


register_scanner("volleyball", VolleyballScanner)
