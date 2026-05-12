"""Hockey scanner module."""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE.parent / "src"))

_CONFIG_PATH = BASE.parent / "config" / "scan_urls.json"
_FALLBACK_URLS = [
    # FlashScore
    "https://www.flashscore.com/hockey/",
    "https://www.flashscore.com/hockey/usa/nhl/",
    "https://www.flashscore.com/hockey/sweden/shl/",
    "https://www.flashscore.com/hockey/finland/liiga/",
    "https://www.flashscore.com/hockey/czech-republic/extraliga/",
    # Betclic
    "https://www.betclic.pl/hokej-na-lodzie-s13",
    # OddsPortal
    "https://www.oddsportal.com/hockey/",
    # Hockey-Reference
    "https://www.hockey-reference.com/",
    # Forebet
    "https://www.forebet.com/en/hockey/predictions-today",
    # Scores24
    "https://scores24.live/en/ice-hockey",
    # Covers (NHL)
    "https://www.covers.com/",
]

try:
    from .base_scanner import BaseSportScanner
    from . import register_scanner
except ImportError:
    from scanners.base_scanner import BaseSportScanner
    from scanners import register_scanner


class HockeyScanner(BaseSportScanner):
    """Hockey-specific scanner."""

    _cached_urls = None

    @property
    def sport_name(self) -> str:
        return "hockey"

    @property
    def scanner_group(self) -> str:
        return "hockey"

    @property
    def urls(self) -> list[str]:
        if HockeyScanner._cached_urls is None:
            HockeyScanner._cached_urls = self._load_config_urls()
        return HockeyScanner._cached_urls

    def _load_config_urls(self) -> list[str]:
        try:
            data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            urls = data.get("sports", {}).get("hockey", {}).get("urls", [])
            if urls:
                return urls
        except Exception:
            pass
        return list(_FALLBACK_URLS)

    @property
    def timeout_per_page(self) -> int:
        return 45

    @property
    def max_deep_links(self) -> int:
        return 15

    @property
    def required_stat_keys(self) -> list[str]:
        return ["goals", "shots", "powerplay_goals", "pim", "hits"]

    @property
    def min_expected_events(self) -> int:
        return 10

    def get_fallback_urls(self) -> list[str]:
        return [
            "https://www.sofascore.com/",
        ]


register_scanner("hockey", HockeyScanner)
