"""Tennis Abstract adapter — scrapes tennisabstract.com for detailed player stats.

Provides per-match serve/return statistics: aces, double faults, 1st serve %,
1st/2nd serve win %, break points saved/faced, hold %, break %, tiebreak records.

Data source: https://www.tennisabstract.com (no API key required, rate-limited).
Inspired by TheCommishDeuce/tennisabstract scraping approach.
"""

import ast
import io
import logging
import re
import time

import requests
from bs4 import BeautifulSoup

from .base_client import BaseAPIClient, APIError, APINotFoundError, CACHE_DIR
from .rate_limiter import RateLimiter
from bet.models.normalized import NormalizedFixture, NormalizedMatchStats

logger = logging.getLogger(__name__)

BASE_URL = "https://www.tennisabstract.com"
REQUEST_DELAY = 0.6  # polite scraping delay


class TennisAbstractClient(BaseAPIClient):
    """Scrapes tennisabstract.com for ATP/WTA player match stats."""

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="tennis-abstract",
            base_url=BASE_URL,
            rate_limiter=rate_limiter,
        )
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        self._last_matches_cache: dict[str, tuple[dict, str]] = {}

    # ─── BaseAPIClient overrides ─────────────────────────────────────

    def _load_api_key(self) -> str:
        """No API key needed — public website."""
        return "tennis-abstract-no-key"

    def is_available(self) -> bool:
        return True

    def _build_headers(self) -> dict:
        return dict(self._session.headers)

    def get_fixtures(self, date: str) -> list:
        """Not applicable — Tennis Abstract doesn't provide fixture lists."""
        return []

    def get_fixture_stats(self, fixture_id: str) -> NormalizedMatchStats | None:
        """Return stats for a fixture from the internal cache (populated by get_team_last_fixtures)."""
        cached = self._last_matches_cache.get(fixture_id)
        if not cached:
            return None
        match, player_name = cached
        return self._match_to_normalized(match, player_name)

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list[dict]:
        """Get H2H match history between two players."""
        matches = self._fetch_player_matches(team1_id)
        if matches is None:
            return []

        # Filter for matches against opponent — FUZZY MATCHING
        h2h_matches = []
        for m in matches:
            opp = m.get("opp", "")
            if self._fuzzy_opponent_match(opp, team2_id):
                h2h_matches.append(m)
            if len(h2h_matches) >= last_n:
                break

        return h2h_matches

    def _fuzzy_opponent_match(self, opp_name: str, target_name: str) -> bool:
        """Fuzzy match opponent name (handles abbreviations, diacritics)."""
        opp_norm = self._normalize_name(opp_name)
        target_norm = self._normalize_name(target_name)
        
        if opp_norm == target_norm:
            return True
        
        # Try rapidfuzz
        try:
            from rapidfuzz import fuzz
            if fuzz.ratio(opp_norm, target_norm) >= 85:
                return True
            if fuzz.token_sort_ratio(opp_norm, target_norm) >= 85:
                return True
        except ImportError:
            pass
        
        # Last-name fallback
        opp_parts = opp_name.strip().split()
        target_parts = target_name.strip().split()
        if opp_parts and target_parts:
            opp_last = self._normalize_name(opp_parts[-1])
            target_last = self._normalize_name(target_parts[-1])
            if len(opp_last) > 3 and opp_last == target_last:
                return True
        
        return False

    def resolve_team_id(self, team_name: str, **kwargs) -> str | None:
        """For tennis, team_name IS the player name — return as-is."""
        return team_name if team_name else None

    def get_team_last_fixtures(self, team_id: str, last_n: int = 10) -> list[NormalizedFixture]:
        """Fetch last N matches for a player from Tennis Abstract."""
        matches = self._fetch_player_matches(team_id)
        if not matches:
            return []

        fixtures = []
        for m in matches[:last_n]:
            fixture_id = f"ta_{team_id}_{m.get('date', '')}_{m.get('opp', '')}"
            # Store raw stats in a stash for get_fixture_stats_from_match
            nf = NormalizedFixture(
                fixture_id=fixture_id,
                source="tennis-abstract",
                sport="tennis",
                competition=m.get("tourn", ""),
                home_team=team_id,
                away_team=m.get("opp", ""),
                kickoff=m.get("date", ""),
                status="FT",
            )
            fixtures.append(nf)

        # Cache match data for fixture_stats lookup
        self._last_matches_cache = {
            f"ta_{team_id}_{m.get('date', '')}_{m.get('opp', '')}": (m, team_id)
            for m in matches[:last_n]
        }
        return fixtures

    def get_fixture_stats_for_player(self, player_name: str, last_n: int = 10) -> list[NormalizedMatchStats]:
        """Convenience: fetch player matches and return NormalizedMatchStats directly.

        This is the primary method used by the enrichment pipeline.
        """
        matches = self._fetch_player_matches(player_name)
        if not matches:
            return []

        stats_list = []
        for m in matches[:last_n]:
            stats = self._match_to_normalized(m, player_name)
            if stats:
                stats_list.append(stats)
        return stats_list

    # ─── Scraping logic ──────────────────────────────────────────────

    def _fetch_player_matches(self, player_name: str) -> list[dict] | None:
        """Fetch all match data for a player from Tennis Abstract."""
        # Check cache first
        cache_key = f"tennis-abstract/player/{self._url_name(player_name)}"
        cached = self._check_cache(cache_key, ttl_hours=6)
        if cached:
            return cached.get("matches")

        player_url_name = self._url_name(player_name)
        all_matches = []

        # Try HTML page first (classic player page)
        try:
            url = f"{BASE_URL}/cgi-bin/player-classic.cgi?p={player_url_name}"
            response = self._make_scrape_request(url)
            if response and response.status_code == 200:
                matches = self._parse_matches_from_html(response.text)
                if matches:
                    all_matches.extend(matches)
                    logger.info(f"[tennis-abstract] Found {len(matches)} matches in HTML for {player_name}")
        except Exception as e:
            logger.debug(f"[tennis-abstract] HTML page failed for {player_name}: {e}")

        # Fallback: try JS files
        if not all_matches:
            for suffix in ["", "Career"]:
                try:
                    url = f"{BASE_URL}/jsmatches/{player_url_name}{suffix}.js"
                    response = self._make_scrape_request(url)
                    if response and response.status_code == 200:
                        matches = self._parse_matches_from_js(response.text)
                        if matches:
                            all_matches.extend(matches)
                            logger.info(f"[tennis-abstract] Found {len(matches)} matches in JS for {player_name}")
                            break
                except Exception as e:
                    logger.debug(f"[tennis-abstract] JS file failed for {player_name}: {e}")

        if not all_matches:
            logger.info(f"[tennis-abstract] No matches found for {player_name}")
            return None

        # Parse into structured dicts
        parsed = self._create_match_dicts(all_matches)

        # Cache result
        self._save_to_cache(cache_key, {"matches": parsed})

        return parsed

    def _make_scrape_request(self, url: str, retries: int = 2) -> requests.Response | None:
        """Make HTTP request with rate limiting and retry."""
        for attempt in range(retries):
            try:
                time.sleep(REQUEST_DELAY)
                response = self._session.get(url, timeout=15)
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                return response
            except requests.RequestException as e:
                if attempt == retries - 1:
                    logger.debug(f"[tennis-abstract] Request failed: {url}: {e}")
                    return None
                time.sleep(REQUEST_DELAY * (attempt + 1))
        return None

    def _parse_matches_from_html(self, html_content: str) -> list | None:
        """Extract match data array from HTML player page (var matchmx = [...])."""
        try:
            start_marker = "var matchmx = ["
            start_pos = html_content.find(start_marker)
            if start_pos == -1:
                return None

            start_pos += len(start_marker) - 1  # include the '['
            end_marker = "];"
            end_pos = html_content.find(end_marker, start_pos)
            if end_pos == -1:
                return None

            matches_str = html_content[start_pos : end_pos + 1]
            # Replace JS nulls with Python None
            matches_str = matches_str.replace("null", "None")
            return ast.literal_eval(matches_str)
        except Exception as e:
            logger.debug(f"[tennis-abstract] HTML parse error: {e}")
            return None

    def _parse_matches_from_js(self, js_content: str) -> list | None:
        """Parse match data from JavaScript file (matchmx = [...])."""
        try:
            if "matchmx = [" not in js_content:
                return None
            matches_str = js_content.split("matchmx = [")[1].split("];")[0]
            matches_str = "[" + matches_str + "]"
            matches_str = matches_str.replace("null", "None")
            return ast.literal_eval(matches_str)
        except Exception as e:
            logger.debug(f"[tennis-abstract] JS parse error: {e}")
            return None

    def _create_match_dicts(self, raw_matches: list) -> list[dict]:
        """Convert raw match arrays to structured dicts."""
        # Column mapping from Tennis Abstract's array format
        COLUMNS = {
            0: "date", 1: "tourn", 2: "surf", 3: "level", 4: "wl",
            8: "round", 9: "score", 11: "opp", 12: "orank",
            21: "aces", 22: "dfs", 23: "pts", 24: "firsts",
            25: "fwon", 26: "swon", 27: "games",
            28: "saved", 29: "chances",
            30: "oaces", 31: "odfs", 32: "opts", 33: "ofirsts",
            34: "ofwon", 35: "oswon", 36: "ogames",
            37: "osaved", 38: "ochances",
        }

        results = []
        for match_row in raw_matches:
            if not isinstance(match_row, (list, tuple)):
                continue
            if len(match_row) < 12:
                continue

            m = {}
            for idx, key in COLUMNS.items():
                if idx < len(match_row):
                    m[key] = match_row[idx]
                else:
                    m[key] = None

            # Format date: "20260515" → "2026-05-15"
            date_raw = m.get("date", "")
            if date_raw and isinstance(date_raw, (str, int)):
                ds = str(date_raw)
                if len(ds) == 8 and ds.isdigit():
                    m["date"] = f"{ds[:4]}-{ds[4:6]}-{ds[6:8]}"

            # Skip walkovers
            score = m.get("score", "")
            if score in ("W/O", "", None):
                continue

            results.append(m)

        # Sort by date descending (most recent first)
        results.sort(key=lambda x: x.get("date", ""), reverse=True)
        return results

    def _match_to_normalized(self, match: dict, player_name: str) -> NormalizedMatchStats | None:
        """Convert a single match dict to NormalizedMatchStats with computed serve stats."""
        pts = self._safe_int(match.get("pts"))
        aces = self._safe_int(match.get("aces"))
        dfs = self._safe_int(match.get("dfs"))
        firsts = self._safe_int(match.get("firsts"))
        fwon = self._safe_int(match.get("fwon"))
        swon = self._safe_int(match.get("swon"))
        games = self._safe_int(match.get("games"))
        saved = self._safe_int(match.get("saved"))
        chances = self._safe_int(match.get("chances"))
        ogames = self._safe_int(match.get("ogames"))
        osaved = self._safe_int(match.get("osaved"))
        ochances = self._safe_int(match.get("ochances"))

        # If no serve data, skip this match
        if not pts:
            return None

        # Compute percentages
        second_serves = pts - firsts if pts and firsts else 0
        stats = {
            "aces": aces or 0,
            "double_faults": dfs or 0,
            "first_serve_pct": round(firsts / pts * 100, 1) if pts else 0,
            "first_serve_win_pct": round(fwon / firsts * 100, 1) if firsts else 0,
            "second_serve_win_pct": round(swon / second_serves * 100, 1) if second_serves else 0,
            "break_points_saved": saved or 0,
            "break_points_faced": chances or 0,
            "break_points_saved_pct": round(saved / chances * 100, 1) if chances else 0,
            "hold_pct": round((1 - (chances - saved) / games) * 100, 1) if games else 0,
            "break_pct": round((ochances - osaved) / ogames * 100, 1) if ogames else 0,
            "service_games": games or 0,
            "return_games": ogames or 0,
            "surface": match.get("surf", ""),
            "round": match.get("round", ""),
            "result": match.get("wl", ""),
            "opponent_rank": self._safe_int(match.get("orank")) or 0,
        }

        return NormalizedMatchStats(
            fixture_id=f"ta_{player_name}_{match.get('date', '')}_{match.get('opp', '')}",
            source="tennis-abstract",
            sport="tennis",
            home_team=player_name,
            away_team=match.get("opp", ""),
            date=match.get("date", ""),
            stats=stats,
        )

    # ─── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _url_name(player_name: str) -> str:
        """Convert player name to URL format (remove spaces, special chars, transliterate diacritics).
        
        Tennis Abstract uses ASCII-only names without spaces:
        - "Vit Kopřiva" → "VitKopriva"  
        - "Jiří Lehečka" → "JiriLehecka"
        - "Carlos Alcaraz" → "CarlosAlcaraz"
        """
        import unicodedata
        # Transliterate diacritics to ASCII (ř→r, á→a, č→c, etc.)
        nfkd = unicodedata.normalize("NFKD", player_name)
        ascii_name = nfkd.encode("ascii", "ignore").decode("ascii")
        # Remove spaces, hyphens, apostrophes
        return ascii_name.replace(" ", "").replace("-", "").replace("'", "")

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normalize player name for comparison."""
        return name.lower().replace(" ", "").replace("-", "").replace("'", "")

    @staticmethod
    def _safe_int(val) -> int | None:
        """Safely convert value to int."""
        if val is None or val == "":
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    def _save_to_cache(self, cache_key: str, data: dict) -> None:
        """Save data to stats_cache with last_updated for BaseAPIClient compatibility."""
        import json
        from pathlib import Path
        from datetime import datetime, timezone
        self._validate_cache_key(cache_key)
        cache_file = CACHE_DIR / f"{cache_key}.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        data["last_updated"] = datetime.now(timezone.utc).isoformat()
        cache_file.write_text(json.dumps(data, default=str), encoding="utf-8")
