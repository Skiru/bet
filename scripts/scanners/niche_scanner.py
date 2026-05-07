"""Niche sports scanner module (snooker + darts + speedway)."""
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


class NicheScanner(BaseSportScanner):
    """Multi-sport scanner for snooker, darts, and speedway.

    Tags each result with correct sport based on URL patterns.
    Note: All three sports are sparse — events not guaranteed daily.
    Speedway is seasonal (April–October).
    """

    @property
    def sport_name(self) -> str:
        return "snooker"  # primary

    @property
    def scanner_group(self) -> str:
        return "niche"

    @property
    def urls(self) -> list[str]:
        return [
            # Snooker
            "https://www.flashscore.com/snooker/",
            "https://www.betclic.pl/snooker-s19",
            "https://www.betexplorer.com/snooker/",
            "https://cuetracker.net/",
            "https://scores24.live/en/snooker",
            # Darts
            "https://www.flashscore.com/darts/",
            "https://www.flashscore.com/darts/pdc/",
            "https://www.betclic.pl/rzutki-s11",
            "https://www.betexplorer.com/darts/",
            "https://dartsorakel.com/",
            "https://scores24.live/en/darts",
            # Speedway (seasonal: April–October)
            "https://www.betclic.pl/zuzel-s36",
            "https://www.betexplorer.com/speedway/",
            "https://speedwayekstraliga.pl/",
            "https://sportowefakty.wp.pl/zuzel",
        ]

    @property
    def timeout_per_page(self) -> int:
        # dartsorakel is rate-limited
        return 60

    @property
    def max_deep_links(self) -> int:
        return 5

    @property
    def required_stat_keys(self) -> list[str]:
        return ["frames_won", "century_breaks"]

    @property
    def min_expected_events(self) -> int:
        # Very sparse — not all sports active daily
        return 1

    def _parse_url(self, url: str, html: str) -> list[dict]:
        """Parse and tag results with correct sport based on URL."""
        events = super()._parse_url(url, html)
        sport = self._detect_sport_from_url(url)
        for event in events:
            event["sport"] = sport
        return events

    def _detect_sport_from_url(self, url: str) -> str:
        """Detect sport from URL pattern."""
        url_lower = url.lower()
        darts_patterns = ["darts", "rzutki", "dartsorakel"]
        speedway_patterns = ["zuzel", "speedway", "speedwayekstraliga"]
        for pattern in darts_patterns:
            if pattern in url_lower:
                return "darts"
        for pattern in speedway_patterns:
            if pattern in url_lower:
                return "speedway"
        return "snooker"


register_scanner("niche", NicheScanner)
