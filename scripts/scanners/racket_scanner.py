"""Racket sports scanner module (table_tennis + padel)."""
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


class RacketScanner(BaseSportScanner):
    """Multi-sport scanner for table tennis and padel.

    Tags each result with correct sport based on URL patterns.
    """

    @property
    def sport_name(self) -> str:
        return "table_tennis"  # primary

    @property
    def scanner_group(self) -> str:
        return "racket"

    @property
    def urls(self) -> list[str]:
        return [
            # Table tennis
            "https://www.flashscore.com/table-tennis/",
            "https://www.betclic.pl/tenis-stolowy-s10",
            "https://www.betexplorer.com/table-tennis/",
            "https://scores24.live/en/table-tennis",
            # Padel
            "https://www.sofascore.com/padel",
            "https://www.betclic.pl/padel-s48",
            "https://www.betexplorer.com/padel/",
            "https://www.premierpadel.com/",
        ]

    @property
    def timeout_per_page(self) -> int:
        return 45

    @property
    def max_deep_links(self) -> int:
        return 5

    @property
    def required_stat_keys(self) -> list[str]:
        return ["sets_won", "points_per_set"]

    @property
    def min_expected_events(self) -> int:
        # Combined across both sports
        return 5

    def _parse_url(self, url: str, html: str) -> list[dict]:
        """Parse and tag results with correct sport based on URL."""
        events = super()._parse_url(url, html)
        sport = self._detect_sport_from_url(url)
        for event in events:
            event["sport"] = sport
        return events

    def _detect_sport_from_url(self, url: str) -> str:
        """Detect sport from URL pattern."""
        padel_patterns = ["padel", "premierpadel"]
        url_lower = url.lower()
        for pattern in padel_patterns:
            if pattern in url_lower:
                return "padel"
        return "table_tennis"


register_scanner("racket", RacketScanner)
