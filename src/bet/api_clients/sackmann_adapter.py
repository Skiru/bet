"""Sackmann adapter — wraps the existing TennisSackmannScraper into BaseAPIClient.

Provides aggregated serve/return statistics from Jeff Sackmann's open-source
tennis match CSVs (GitHub). Data is yearly aggregates (not per-match).

Data source: https://github.com/JeffSackmann/tennis_atp (ATP)
             https://github.com/JeffSackmann/tennis_wta (WTA)
"""

import csv
import io
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone

import requests

from .base_client import BaseAPIClient, APIError, CACHE_DIR
from .rate_limiter import RateLimiter
from bet.models.normalized import NormalizedFixture, NormalizedMatchStats
from bet.scrapers.constants import SACKMANN_ATP_URL, SACKMANN_WTA_URL

logger = logging.getLogger(__name__)


class SackmannClient(BaseAPIClient):
    """Adapter wrapping Jeff Sackmann's GitHub tennis match CSVs.

    Returns aggregated season stats per player: aces, DFs, 1st serve %,
    1st/2nd win %, BP saved/faced, win-loss record, surface splits.
    """

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="sackmann",
            base_url="https://raw.githubusercontent.com/JeffSackmann",
            rate_limiter=rate_limiter,
        )
        self._player_stats_cache: dict[str, dict] = {}  # "player_lower" → stats
        self._last_match_rows: dict[str, tuple] = {}  # fixture_id → (row_dict, is_winner)

    # ─── BaseAPIClient overrides ─────────────────────────────────────

    def _load_api_key(self) -> str:
        """No API key needed — public GitHub CSVs."""
        return "sackmann-no-key"

    def is_available(self) -> bool:
        return True

    def _build_headers(self) -> dict:
        return {"Accept": "text/csv", "User-Agent": "bet-pipeline/1.0"}

    def get_fixtures(self, date: str) -> list:
        """Not applicable — Sackmann provides season aggregates."""
        return []

    def get_fixture_stats(self, fixture_id: str) -> NormalizedMatchStats | None:
        """Return per-match stats from the cache (populated by get_team_last_fixtures)."""
        entry = self._last_match_rows.get(fixture_id)
        if not entry:
            return None
        row, is_winner = entry
        prefix = "w_" if is_winner else "l_"
        player_name = row.get("winner_name" if is_winner else "loser_name", "")
        opponent = row.get("loser_name" if is_winner else "winner_name", "")

        svpt = self._safe_int(row.get(f"{prefix}svpt"))
        first_in = self._safe_int(row.get(f"{prefix}1stIn"))
        first_won = self._safe_int(row.get(f"{prefix}1stWon"))
        second_won = self._safe_int(row.get(f"{prefix}2ndWon"))
        bp_saved = self._safe_int(row.get(f"{prefix}bpSaved"))
        bp_faced = self._safe_int(row.get(f"{prefix}bpFaced"))
        aces = self._safe_int(row.get(f"{prefix}ace"))
        dfs = self._safe_int(row.get(f"{prefix}df"))

        if not svpt:
            return None

        second_serves = svpt - first_in if svpt > first_in else 0
        stats = {
            "aces": aces,
            "double_faults": dfs,
            "first_serve_pct": round(first_in / svpt * 100, 1) if svpt else 0,
            "first_serve_win_pct": round(first_won / first_in * 100, 1) if first_in else 0,
            "second_serve_win_pct": round(second_won / second_serves * 100, 1) if second_serves else 0,
            "break_points_saved": bp_saved,
            "break_points_faced": bp_faced,
            "break_points_saved_pct": round(bp_saved / bp_faced * 100, 1) if bp_faced else 0,
            "surface": row.get("surface", ""),
            "round": row.get("round", ""),
            "result": "W" if is_winner else "L",
        }

        return NormalizedMatchStats(
            fixture_id=fixture_id,
            source="sackmann",
            sport="tennis",
            home_team=player_name,
            away_team=opponent,
            date=self._format_date(row.get("tourney_date", "")),
            stats=stats,
        )

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list[dict]:
        """Get H2H from Sackmann CSV data."""
        year = str(datetime.now().year)
        h2h_matches = []

        for tour in ("ATP", "WTA"):
            rows = self._fetch_csv(tour, year)
            if not rows:
                continue

            p1_norm = team1_id.lower().replace(" ", "").replace("-", "")
            p2_norm = team2_id.lower().replace(" ", "").replace("-", "")

            for row in rows:
                winner = (row.get("winner_name", "") or "").lower().replace(" ", "").replace("-", "")
                loser = (row.get("loser_name", "") or "").lower().replace(" ", "").replace("-", "")

                if (winner == p1_norm and loser == p2_norm) or (winner == p2_norm and loser == p1_norm):
                    h2h_matches.append({
                        "date": row.get("tourney_date", ""),
                        "tournament": row.get("tourney_name", ""),
                        "surface": row.get("surface", ""),
                        "winner": row.get("winner_name", ""),
                        "loser": row.get("loser_name", ""),
                        "score": row.get("score", ""),
                        "round": row.get("round", ""),
                    })
                    if len(h2h_matches) >= last_n:
                        break
            if h2h_matches:
                break

        return h2h_matches

    def resolve_team_id(self, team_name: str, **kwargs) -> str | None:
        """For tennis, player name is the ID."""
        return team_name if team_name else None

    def get_team_last_fixtures(self, team_id: str, last_n: int = 10) -> list[NormalizedFixture]:
        """Return last N matches for a player from current year CSV."""
        year = str(datetime.now().year)
        player_norm = team_id.lower().replace(" ", "").replace("-", "")
        matches = []

        for tour in ("ATP", "WTA"):
            rows = self._fetch_csv(tour, year)
            if not rows:
                continue

            for row in rows:
                winner = (row.get("winner_name", "") or "").lower().replace(" ", "").replace("-", "")
                loser = (row.get("loser_name", "") or "").lower().replace(" ", "").replace("-", "")

                if winner == player_norm or loser == player_norm:
                    fixture_id = f"sack_{row.get('tourney_date', '')}_{row.get('match_num', '')}"
                    is_winner = winner == player_norm
                    opp = row.get("loser_name" if is_winner else "winner_name", "")

                    matches.append((row.get("tourney_date", ""), NormalizedFixture(
                        fixture_id=fixture_id,
                        source="sackmann",
                        sport="tennis",
                        competition=row.get("tourney_name", ""),
                        home_team=team_id,
                        away_team=opp,
                        kickoff=self._format_date(row.get("tourney_date", "")),
                        status="FT",
                    ), row, is_winner))

            if matches:
                break

        # Sort by date descending and take last_n
        matches.sort(key=lambda x: x[0], reverse=True)
        self._last_match_rows = {m[1].fixture_id: (m[2], m[3]) for m in matches[:last_n]}
        return [m[1] for m in matches[:last_n]]

    def get_player_season_stats(self, player_name: str, year: str | None = None) -> NormalizedMatchStats | None:
        """Get aggregated season stats for a player.

        This is the primary method for the enrichment pipeline.
        Returns a single NormalizedMatchStats with averaged/summed serve stats.
        """
        if year is None:
            year = str(datetime.now().year)

        player_norm = player_name.lower().replace(" ", "").replace("-", "")

        # Check cache
        cache_key = f"sackmann/season/{player_norm}_{year}"
        cached = self._check_cache(cache_key, ttl_hours=12)
        if cached:
            return NormalizedMatchStats(
                fixture_id=f"sack_season_{player_norm}_{year}",
                source="sackmann",
                sport="tennis",
                home_team=player_name,
                away_team="season_aggregate",
                date=year,
                stats=cached,
            )

        # Fetch and aggregate
        for tour in ("ATP", "WTA"):
            rows = self._fetch_csv(tour, year)
            if not rows:
                continue

            # Aggregate stats for this player
            agg = self._aggregate_player_stats(rows, player_norm)
            if agg:
                self._save_to_cache(cache_key, agg)
                return NormalizedMatchStats(
                    fixture_id=f"sack_season_{player_norm}_{year}",
                    source="sackmann",
                    sport="tennis",
                    home_team=player_name,
                    away_team="season_aggregate",
                    date=year,
                    stats=agg,
                )

        return None

    # ─── CSV fetching ────────────────────────────────────────────────

    def _fetch_csv(self, tour: str, year: str) -> list[dict]:
        """Fetch and parse Sackmann CSV for a tour/year. Cached 12h."""
        cache_key = f"sackmann/csv/{tour.lower()}_{year}"
        cached = self._check_cache(cache_key, ttl_hours=12)
        if cached and isinstance(cached, list):
            return cached

        url = SACKMANN_WTA_URL.format(year=year) if tour.upper() == "WTA" else SACKMANN_ATP_URL.format(year=year)

        try:
            time.sleep(0.3)
            resp = requests.get(url, headers=self._build_headers(), timeout=30)
            if resp.status_code != 200:
                logger.debug(f"[sackmann] HTTP {resp.status_code} for {url}")
                return []
            reader = csv.DictReader(io.StringIO(resp.text))
            rows = list(reader)
            # Cache the CSV data
            self._save_to_cache(cache_key, rows)
            return rows
        except Exception as e:
            logger.debug(f"[sackmann] Failed to fetch CSV: {e}")
            return []

    def _aggregate_player_stats(self, rows: list[dict], player_norm: str) -> dict | None:
        """Aggregate stats for a player across all their matches."""
        wins = 0
        losses = 0
        total_aces = 0
        total_dfs = 0
        total_svpt = 0
        total_first_in = 0
        total_first_won = 0
        total_second_won = 0
        total_bp_saved = 0
        total_bp_faced = 0
        surface_record: dict[str, dict] = defaultdict(lambda: {"wins": 0, "losses": 0})
        match_count = 0

        for row in rows:
            winner = (row.get("winner_name", "") or "").lower().replace(" ", "").replace("-", "")
            loser = (row.get("loser_name", "") or "").lower().replace(" ", "").replace("-", "")
            surface = (row.get("surface", "") or "").lower()

            if winner == player_norm:
                wins += 1
                surface_record[surface]["wins"] += 1
                prefix = "w_"
            elif loser == player_norm:
                losses += 1
                surface_record[surface]["losses"] += 1
                prefix = "l_"
            else:
                continue

            match_count += 1
            total_aces += self._safe_int(row.get(f"{prefix}ace"))
            total_dfs += self._safe_int(row.get(f"{prefix}df"))
            total_svpt += self._safe_int(row.get(f"{prefix}svpt"))
            total_first_in += self._safe_int(row.get(f"{prefix}1stIn"))
            total_first_won += self._safe_int(row.get(f"{prefix}1stWon"))
            total_second_won += self._safe_int(row.get(f"{prefix}2ndWon"))
            total_bp_saved += self._safe_int(row.get(f"{prefix}bpSaved"))
            total_bp_faced += self._safe_int(row.get(f"{prefix}bpFaced"))

        if match_count == 0:
            return None

        second_serves = total_svpt - total_first_in if total_svpt > total_first_in else 0

        stats = {
            "matches_played": match_count,
            "wins": wins,
            "losses": losses,
            "win_pct": round(wins / match_count * 100, 1),
            "aces": total_aces,
            "double_faults": total_dfs,
            "aces_per_match": round(total_aces / match_count, 1),
            "dfs_per_match": round(total_dfs / match_count, 1),
            "first_serve_pct": round(total_first_in / total_svpt * 100, 1) if total_svpt else 0,
            "first_serve_win_pct": round(total_first_won / total_first_in * 100, 1) if total_first_in else 0,
            "second_serve_win_pct": round(total_second_won / second_serves * 100, 1) if second_serves else 0,
            "break_points_saved": total_bp_saved,
            "break_points_faced": total_bp_faced,
            "break_points_saved_pct": round(total_bp_saved / total_bp_faced * 100, 1) if total_bp_faced else 0,
            "surface_record": dict(surface_record),
        }

        return stats

    # ─── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _format_date(date_str: str) -> str:
        """Convert '20260115' → '2026-01-15'."""
        if date_str and len(date_str) == 8 and date_str.isdigit():
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        return date_str

    @staticmethod
    def _safe_int(val) -> int:
        """Safely convert to int, defaulting to 0."""
        if val is None or val == "":
            return 0
        try:
            return int(val)
        except (ValueError, TypeError):
            return 0

    def _save_to_cache(self, cache_key: str, data) -> None:
        """Save data to stats_cache."""
        import json
        self._validate_cache_key(cache_key)
        cache_file = CACHE_DIR / f"{cache_key}.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(data, default=str), encoding="utf-8")
