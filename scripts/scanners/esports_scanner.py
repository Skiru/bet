"""Esports scanner module."""
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


class EsportsScanner(BaseSportScanner):
    """Esports-specific scanner (CS2, LoL, Dota2, etc.)."""

    @property
    def sport_name(self) -> str:
        return "esports"

    @property
    def scanner_group(self) -> str:
        return "esports"

    @property
    def urls(self) -> list[str]:
        return [
            # FlashScore
            "https://www.flashscore.com/esports/",
            "https://www.flashscore.com/esports/counter-strike/",
            # Betclic
            "https://www.betclic.pl/esport-s46",
            # BetExplorer
            "https://www.betexplorer.com/esports/",
            # HLTV (CS2)
            "https://www.hltv.org/matches",
            # GosuGamers
            "https://www.gosugamers.net/",
            # Scores24
            "https://scores24.live/en/csgo",
        ]

    @property
    def timeout_per_page(self) -> int:
        return 60

    @property
    def max_deep_links(self) -> int:
        return 10

    @property
    def required_stat_keys(self) -> list[str]:
        return ["maps_won", "rounds_won", "kills"]

    @property
    def min_expected_events(self) -> int:
        return 5


register_scanner("esports", EsportsScanner)
