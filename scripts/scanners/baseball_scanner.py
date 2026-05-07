"""Baseball scanner module."""
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


class BaseballScanner(BaseSportScanner):
    """Baseball-specific scanner.

    Note: In-season April–October. Off-season scans may find 0 events.
    """

    @property
    def sport_name(self) -> str:
        return "baseball"

    @property
    def scanner_group(self) -> str:
        return "baseball"

    @property
    def urls(self) -> list[str]:
        return [
            # FlashScore
            "https://www.flashscore.com/baseball/",
            # Betclic
            "https://www.betclic.pl/baseball-s14",
            # OddsPortal
            "https://www.oddsportal.com/baseball/",
            # Scores24
            "https://scores24.live/en/baseball",
            # Covers
            "https://www.covers.com/",
        ]

    @property
    def timeout_per_page(self) -> int:
        return 45

    @property
    def max_deep_links(self) -> int:
        return 10

    @property
    def required_stat_keys(self) -> list[str]:
        return ["runs", "hits", "errors", "strikeouts", "walks"]

    @property
    def min_expected_events(self) -> int:
        # In-season (April-October)
        return 5


register_scanner("baseball", BaseballScanner)
