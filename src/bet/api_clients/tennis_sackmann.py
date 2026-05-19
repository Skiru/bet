"""Tennis serve stats from Jeff Sackmann's open-source ATP data.

Source: https://github.com/JeffSackmann/tennis_atp (public domain)
Data: Match-level CSV with serve/return statistics for ATP tour.

Caches parsed CSVs locally. Updates at most once per day.
Writes to team_form with source='sackmann'.
"""

import csv
import io
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from curl_cffi import requests as c_requests
except ImportError:
    c_requests = None

CACHE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "betting" / "data" / "sackmann_cache"
GITHUB_RAW = "https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master"

# Key stat columns from sackmann CSVs
STAT_COLUMNS = {
    "w_ace": "aces",
    "w_df": "double_faults",
    "w_1stIn": "first_serves_in",
    "w_1stWon": "first_serve_won",
    "w_2ndWon": "second_serve_won",
    "w_bpSaved": "break_points_saved",
    "w_bpFaced": "break_points_faced",
}


@dataclass
class PlayerServeStats:
    """Aggregated serve stats for a player (last N matches)."""
    name: str
    matches: int = 0
    aces_avg: float = 0.0
    double_faults_avg: float = 0.0
    first_serve_pct: float = 0.0
    first_serve_won_pct: float = 0.0
    break_points_saved_pct: float = 0.0
    recent_matches: list = field(default_factory=list)


class SackmannTennisClient:
    """Fetch and parse Jeff Sackmann's ATP match data for serve statistics."""

    def __init__(self):
        if c_requests is None:
            raise ImportError("curl_cffi required for SackmannTennisClient")
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._data_cache: dict[int, list[dict]] = {}

    def _get_year_data(self, year: int) -> list[dict]:
        """Fetch or load cached year CSV."""
        if year in self._data_cache:
            return self._data_cache[year]

        cache_file = CACHE_DIR / f"atp_matches_{year}.csv"

        # Check if cache is fresh (< 24h old)
        if cache_file.exists():
            age_hours = (time.time() - cache_file.stat().st_mtime) / 3600
            if age_hours < 24:
                return self._parse_csv(cache_file.read_text(encoding="utf-8"))

        # Fetch from GitHub
        url = f"{GITHUB_RAW}/atp_matches_{year}.csv"
        try:
            resp = c_requests.get(url, impersonate="chrome110", timeout=30)
            if resp.status_code != 200:
                logger.warning(f"Sackmann {year} CSV: HTTP {resp.status_code}")
                # Use stale cache if available
                if cache_file.exists():
                    return self._parse_csv(cache_file.read_text(encoding="utf-8"))
                return []

            cache_file.write_text(resp.text, encoding="utf-8")
            data = self._parse_csv(resp.text)
            self._data_cache[year] = data
            logger.info(f"Sackmann: loaded {len(data)} matches for {year}")
            return data

        except Exception as e:
            logger.warning(f"Sackmann fetch failed for {year}: {e}")
            if cache_file.exists():
                return self._parse_csv(cache_file.read_text(encoding="utf-8"))
            return []

    def _parse_csv(self, text: str) -> list[dict]:
        """Parse CSV text into list of match dicts."""
        reader = csv.DictReader(io.StringIO(text))
        return list(reader)

    def get_player_stats(self, player_name: str, n_matches: int = 10) -> PlayerServeStats | None:
        """Get serve stats for a player from their last N matches.

        Args:
            player_name: Player name (e.g., "Carlos Alcaraz", "Novak Djokovic")
            n_matches: Number of recent matches to aggregate

        Returns:
            PlayerServeStats or None if player not found.
        """
        import datetime
        current_year = datetime.date.today().year

        # Search current year and previous year
        all_matches = []
        for year in [current_year, current_year - 1]:
            data = self._get_year_data(year)
            for row in data:
                # Check if player is winner or loser
                winner = row.get("winner_name", "")
                loser = row.get("loser_name", "")
                if player_name.lower() in winner.lower():
                    all_matches.append(self._extract_winner_stats(row))
                elif player_name.lower() in loser.lower():
                    all_matches.append(self._extract_loser_stats(row))

        if not all_matches:
            return None

        # Take last N matches (most recent first — CSV is chronological)
        recent = all_matches[-n_matches:]

        # Aggregate
        stats = PlayerServeStats(name=player_name, matches=len(recent))
        if not recent:
            return stats

        stats.aces_avg = sum(m.get("aces", 0) for m in recent) / len(recent)
        stats.double_faults_avg = sum(m.get("double_faults", 0) for m in recent) / len(recent)

        first_in_total = sum(m.get("first_serves_in", 0) for m in recent)
        sv_points_total = sum(m.get("sv_points", 0) for m in recent)
        if sv_points_total > 0:
            stats.first_serve_pct = round(first_in_total / sv_points_total * 100, 1)

        first_won = sum(m.get("first_serve_won", 0) for m in recent)
        if first_in_total > 0:
            stats.first_serve_won_pct = round(first_won / first_in_total * 100, 1)

        bp_saved = sum(m.get("bp_saved", 0) for m in recent)
        bp_faced = sum(m.get("bp_faced", 0) for m in recent)
        if bp_faced > 0:
            stats.break_points_saved_pct = round(bp_saved / bp_faced * 100, 1)

        stats.recent_matches = recent
        return stats

    def _extract_winner_stats(self, row: dict) -> dict:
        """Extract serve stats for the winner."""
        return {
            "aces": self._safe_int(row.get("w_ace")),
            "double_faults": self._safe_int(row.get("w_df")),
            "first_serves_in": self._safe_int(row.get("w_1stIn")),
            "first_serve_won": self._safe_int(row.get("w_1stWon")),
            "sv_points": self._safe_int(row.get("w_svpt")),
            "bp_saved": self._safe_int(row.get("w_bpSaved")),
            "bp_faced": self._safe_int(row.get("w_bpFaced")),
        }

    def _extract_loser_stats(self, row: dict) -> dict:
        """Extract serve stats for the loser."""
        return {
            "aces": self._safe_int(row.get("l_ace")),
            "double_faults": self._safe_int(row.get("l_df")),
            "first_serves_in": self._safe_int(row.get("l_1stIn")),
            "first_serve_won": self._safe_int(row.get("l_1stWon")),
            "sv_points": self._safe_int(row.get("l_svpt")),
            "bp_saved": self._safe_int(row.get("l_bpSaved")),
            "bp_faced": self._safe_int(row.get("l_bpFaced")),
        }

    @staticmethod
    def _safe_int(val) -> int:
        try:
            return int(val) if val else 0
        except (ValueError, TypeError):
            return 0
