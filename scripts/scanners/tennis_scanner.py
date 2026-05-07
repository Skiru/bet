"""Tennis scanner module."""
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


class TennisScanner(BaseSportScanner):
    """Tennis-specific scanner — Tier 1 sport."""

    @property
    def sport_name(self) -> str:
        return "tennis"

    @property
    def scanner_group(self) -> str:
        return "tennis"

    @property
    def urls(self) -> list[str]:
        return [
            # FlashScore
            "https://www.flashscore.com/tennis/",
            "https://www.flashscore.com/tennis/atp-singles/",
            "https://www.flashscore.com/tennis/wta-singles/",
            "https://www.flashscore.com/tennis/atp-doubles/",
            # Betclic
            "https://www.betclic.pl/tenis-s2",
            # OddsPortal
            "https://www.oddsportal.com/tennis/",
            # TennisExplorer
            "https://www.tennisexplorer.com/",
            "https://www.tennisexplorer.com/matches/",
            # TennisAbstract
            "https://www.tennisabstract.com/reports/atp_elo_ratings.html",
            "https://www.tennisabstract.com/reports/wta_elo_ratings.html",
            # ATP Tour
            "https://www.atptour.com/en/scores/current",
            # Forebet
            "https://www.forebet.com/en/tennis/predictions-today",
            # Scores24
            "https://scores24.live/en/tennis",
        ]

    @property
    def timeout_per_page(self) -> int:
        return 45

    @property
    def max_deep_links(self) -> int:
        return 20

    @property
    def required_stat_keys(self) -> list[str]:
        return ["aces", "double_faults", "first_serve_pct", "break_points_won", "games_won"]

    @property
    def min_expected_events(self) -> int:
        return 30

    def get_fallback_urls(self) -> list[str]:
        return [
            "https://www.sofascore.com/",
        ]


register_scanner("tennis", TennisScanner)
