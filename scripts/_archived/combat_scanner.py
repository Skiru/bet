"""Combat (MMA) scanner module."""
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


class CombatScanner(BaseSportScanner):
    """MMA/Combat-specific scanner.

    Note: UFC events are not daily — min_expected_events is low.
    """

    @property
    def sport_name(self) -> str:
        return "mma"

    @property
    def scanner_group(self) -> str:
        return "combat"

    @property
    def urls(self) -> list[str]:
        return [
            # FlashScore
            "https://www.flashscore.com/mma/",
            "https://www.flashscore.com/mma/ufc/",
            # Betclic
            "https://www.betclic.pl/mma-s38",
            # Scores24
            "https://scores24.live/en/mma",
        ]

    @property
    def timeout_per_page(self) -> int:
        return 45

    @property
    def max_deep_links(self) -> int:
        return 5

    @property
    def required_stat_keys(self) -> list[str]:
        return ["takedowns", "sig_strikes", "submission_attempts"]

    @property
    def min_expected_events(self) -> int:
        # UFC events are not daily
        return 1


register_scanner("combat", CombatScanner)
