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
        # Core keys reliably produced by ESPN API + enrichment pipeline
        # aces/double_faults/first_serve_pct come from ESPN match stats (partial coverage)
        # games_won/sets_won/total_games come from ESPN linescores (high coverage)
        return ["games_won", "sets_won", "total_games"]

    @property
    def desired_stat_keys(self) -> list[str]:
        """Extended keys — present when ESPN has detailed match stats."""
        return ["aces", "double_faults", "first_serve_pct", "break_points_won"]

    @property
    def min_expected_events(self) -> int:
        return 30

    def get_fallback_urls(self) -> list[str]:
        return [
            "https://www.sofascore.com/",
        ]


    def validate_event(self, event: dict) -> dict:
        """Tennis-specific event validation with stat-presence reporting."""
        result = {"valid": True, "warnings": []}

        required = set(self.required_stat_keys)
        desired = set(self.desired_stat_keys)
        present = set()

        stats = event.get("stats", {})
        for key in required | desired:
            if key in event or key in stats:
                present.add(key)

        missing_required = required - present
        missing_desired = desired - present

        if missing_required:
            result["warnings"].append(
                f"missing_required_stats: {sorted(missing_required)}"
            )
            # Still valid — stats come from enrichment, not scan
        if missing_desired:
            result["warnings"].append(
                f"missing_desired_stats: {sorted(missing_desired)}"
            )

        result["stat_coverage"] = len(present) / max(len(required | desired), 1)
        result["stats_present"] = sorted(present)

        # Surface is important for tennis
        if not event.get("surface"):
            result["warnings"].append("missing_surface")

        return result


register_scanner("tennis", TennisScanner)
