"""Flashscore scraper — multi-sport stats via curl_cffi.

Covers all 5 core sports (football, basketball, tennis, hockey, volleyball).
Uses native Flashscore search endpoint + results page parsing.

Each sport has its own subclass registered in the scraper registry.
"""
from __future__ import annotations

import json
import logging
import math
import re
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import text

from bet.scrapers.base import BaseScraper, ScraperError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# curl_cffi — optional dependency
# ---------------------------------------------------------------------------
try:
    from curl_cffi import requests as c_requests
except ImportError:
    c_requests = None

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SPORT_IDS_FS = {
    "football": 1,
    "tennis": 2,
    "basketball": 3,
    "hockey": 4,
    "volleyball": 12,
}

SPORT_STAT_KEYS: dict[str, list[str]] = {
    "football": [
        "corners", "fouls", "yellow_cards", "shots_on_target",
        "shots_off_target", "ball_possession",
    ],
    "tennis": ["aces", "double_faults", "win_1st_serve", "break_points_saved"],
    "basketball": ["2_pointers", "3_pointers", "free_throws", "rebounds", "turnovers"],
    "volleyball": ["aces", "blocks", "errors"],
    "hockey": ["shots_on_goal", "penalties_in_minutes", "power_play_goals"],
}

from bet.stats.value_ranges import SPORT_VALUE_RANGES

_INDIVIDUAL_SPORTS = {"tennis"}

# In-process rate limiter
_rate_lock = threading.Lock()
_last_request_time: dict[str, float] = {}
_FS_RATE_LIMIT_SECONDS = 1.5

# Regex label mapping for stat extraction
_LABEL_MAP: dict[str, str] = {
    "corners": r"(?:corners?|corner\s*kicks?)",
    "fouls": r"(?:fouls?|foul\s*committed)",
    "yellow_cards": r"(?:yellow\s*cards?|bookings?)",
    "red_cards": r"(?:red\s*cards?|sending\s*off)",
    "shots": r"(?:shots?|total\s*shots?)",
    "shots_on_target": r"(?:shots?\s*on\s*target|on\s*target)",
    "shots_off_target": r"(?:shots?\s*off\s*target|off\s*target)",
    "ball_possession": r"(?:possession|ball\s*possession)",
    "goals": r"(?:goals?|score)",
    "offsides": r"(?:offsides?)",
    "saves": r"(?:saves?|goalkeeper\s*saves?)",
    "points": r"(?:points?|total\s*points?|pts)",
    "rebounds": r"(?:rebounds?|reb)",
    "assists": r"(?:assists?|ast)",
    "steals": r"(?:steals?|stl)",
    "blocks": r"(?:blocks?|blk)",
    "turnovers": r"(?:turnovers?|tov)",
    "aces": r"(?:aces?)",
    "double_faults": r"(?:double\s*faults?|df)",
    "win_1st_serve": r"(?:1st\s*serve\s*%|first\s*serve\s*%|win\s*1st\s*serve)",
    "break_points_saved": r"(?:break\s*points?\s*saved|bp\s*saved)",
    "shots_on_goal": r"(?:shots?\s*on\s*goal|sog)",
    "penalties_in_minutes": r"(?:pim|penalty\s*minutes?|penalties\s*in\s*minutes?)",
    "power_play_goals": r"(?:powerplay\s*goals?|pp\s*goals?|ppg)",
    "2_pointers": r"(?:2\s*pointers?|2pt|two\s*pointers?)",
    "3_pointers": r"(?:3\s*pointers?|3pt|three\s*pointers?)",
    "free_throws": r"(?:free\s*throws?|ft)",
    "errors": r"(?:errors?)",
    "total_points": r"(?:total\s*points?)",
}


# ---------------------------------------------------------------------------
# Parsing helpers (ported from scripts/flashscore_enricher.py)
# ---------------------------------------------------------------------------

def _fs_rate_limit(domain: str = "flashscore.com") -> None:
    with _rate_lock:
        now = time.time()
        last = _last_request_time.get(domain, 0.0)
        wait = _FS_RATE_LIMIT_SECONDS - (now - last)
        if wait > 0:
            time.sleep(wait)
        _last_request_time[domain] = time.time()


def _primary_score_key(sport: str) -> str | None:
    """Return the game-total scoring stat key for HTML regex fallback.

    NOTE: _extract_match_scores sums home+away (game total), so we store under
    game_total_* keys to avoid polluting team-level stats (points, goals).
    Team-specific data comes from the feed parser or ESPN/API sources.
    """
    return {
        "football": "game_total_goals",
        "basketball": "game_total_points",
        "hockey": "game_total_goals",
        "volleyball": "total_points",
        "tennis": "total_games",
    }.get(sport)


def _validate_stat_values(values: list[float], stat_key: str, sport: str) -> list[float]:
    ranges = SPORT_VALUE_RANGES.get(sport, {})
    bounds = ranges.get(stat_key)
    if not bounds:
        return values
    lo, hi = bounds
    filtered = [v for v in values if lo <= v <= hi]
    if len(filtered) < len(values):
        logger.debug(
            "Filtered %d/%d %s %s values outside range [%.1f, %.1f]",
            len(values) - len(filtered), len(values), sport, stat_key, lo, hi,
        )
    return filtered


def _extract_stat_values(html: str, stat_key: str, sport: str) -> list[float]:
    values: list[float] = []
    pattern = _LABEL_MAP.get(stat_key, re.escape(stat_key.replace("_", " ")))

    # Pattern 1: "Label: value" or "Label value"
    matches = re.findall(pattern + r"[:\s]*(\d+(?:\.\d+)?)", html, re.IGNORECASE)
    for m in matches:
        try:
            values.append(float(m))
        except ValueError:
            continue

    # Pattern 2: Table cells
    cell_pattern = (
        r"(?:<td[^>]*>.*?" + pattern + r".*?</td>\s*<td[^>]*>\s*(\d+(?:\.\d+)?)\s*</td>)"
    )
    for m in re.findall(cell_pattern, html, re.IGNORECASE | re.DOTALL):
        try:
            v = float(m)
            if v not in values:
                values.append(v)
        except ValueError:
            continue

    # Pattern 3: Flashscore stat divs
    div_pattern = (
        r'class="[^"]*stat[^"]*"[^>]*>.*?' + pattern
        + r'.*?(\d+(?:\.\d+)?)\s*</(?:div|span)>'
    )
    for m in re.findall(div_pattern, html, re.IGNORECASE | re.DOTALL):
        try:
            v = float(m)
            if v not in values:
                values.append(v)
        except ValueError:
            continue

    # Pattern 4: data-* attributes
    data_pattern = r'data-(?:' + stat_key + r'|stat)[^=]*=[\"\'](\d+(?:\.\d+)?)[\"\'"]'
    for m in re.findall(data_pattern, html, re.IGNORECASE):
        try:
            v = float(m)
            if v not in values:
                values.append(v)
        except ValueError:
            continue

    validated = _validate_stat_values(values, stat_key, sport)
    return validated[:10]


def _extract_match_scores(html: str, sport: str) -> list[float]:
    scores: list[float] = []

    score_matches = re.findall(
        r'(?:score|result|final)[^>]*>?\s*(\d+)\s*[-:]\s*(\d+)',
        html, re.IGNORECASE,
    )
    for home, away in score_matches:
        try:
            total = float(home) + float(away)
            if total < 200:
                scores.append(total)
        except ValueError:
            continue

    if not scores:
        plain_scores = re.findall(r'>(\d{1,3})\s*[-–:]\s*(\d{1,3})<', html)
        for home, away in plain_scores:
            try:
                h, a = float(home), float(away)
                total = h + a
                if sport in ("football", "hockey") and total <= 15:
                    scores.append(total)
                elif sport == "basketball" and 50 < total < 400:
                    scores.append(total)
                elif sport in ("volleyball", "tennis") and total <= 10:
                    scores.append(total)
                elif total <= 50:
                    scores.append(total)
            except ValueError:
                continue

    return scores[:10]


def _parse_flashscore_stats(html: str, sport: str) -> dict[str, list[float]]:
    stats: dict[str, list[float]] = {}
    stat_keys = SPORT_STAT_KEYS.get(sport, [])

    if not html or len(html) < 500:
        return stats

    html = html[:2_000_000]

    for key in stat_keys:
        values = _extract_stat_values(html, key, sport)
        if values:
            stats[key] = values

    if not stats:
        score_key = _primary_score_key(sport)
        if score_key:
            scores = _extract_match_scores(html, sport)
            if scores:
                stats[score_key] = scores[:10]

    validated_stats = {}
    for key, vals in stats.items():
        clean = _validate_stat_values(vals, key, sport)
        if clean:
            validated_stats[key] = clean
    return validated_stats


# ---------------------------------------------------------------------------
# Flashscore API helpers
# ---------------------------------------------------------------------------

def _get_flashscore_entity(team_name: str, sport: str) -> tuple[str | None, str | None, str | None]:
    """Resolve Flashscore entity via native search endpoint."""
    if c_requests is None:
        logger.warning("curl_cffi not installed — cannot use Flashscore scraper")
        return None, None, None

    sid = SPORT_IDS_FS.get(sport, 1)
    from urllib.parse import quote
    url = f"https://s.flashscore.com/search/?q={quote(team_name)}&l=1&sid={sid}&pid=1&f=1;1"
    headers = {"x-fsign": "SW9D1eZo"}

    try:
        resp = c_requests.get(url, impersonate="chrome110", headers=headers, timeout=10)
        if resp.status_code == 200:
            txt = resp.text
            start = txt.find("({") + 1
            end = txt.rfind("})") + 1
            if start > 0 and end > 0:
                data = json.loads(txt[start:end])
                for r in data.get("results", []):
                    if r.get("type") == "participants":
                        entity_type = "player" if r.get("participant_type_id") == 2 else "team"
                        return entity_type, r.get("url"), r.get("id")
    except Exception as e:
        logger.warning("Flashscore search failed for %s: %s", team_name, e)
    return None, None, None


def _try_flashscore(team_name: str, sport: str) -> tuple[dict[str, list[float]], str | None]:
    """Fetch stats from Flashscore. Returns (stats_dict, error_or_None)."""
    if c_requests is None:
        return {}, "curl_cffi not installed"

    entity_type, slug, entity_id = _get_flashscore_entity(team_name, sport)
    if not slug or not entity_id:
        return {}, f"Could not find entity via Flashscore Search for '{team_name}'"

    url = f"https://www.flashscore.com/{entity_type}/{slug}/{entity_id}/results/"
    _fs_rate_limit("flashscore.com")

    try:
        resp = c_requests.get(url, impersonate="chrome110", timeout=15)
        if resp.status_code != 200:
            return {}, f"Flashscore returned status {resp.status_code}"

        html = resp.text
        if len(html) < 500 or "just a moment" in html.lower():
            return {}, "Blocked by JavaScript challenge barrier"

        stats = _parse_flashscore_stats(html, sport)
        if stats:
            return stats, None
        return {}, "No stats parsed from Flashscore HTML"
    except Exception as exc:
        return {}, f"Flashscore fetch error: {exc}"


# ---------------------------------------------------------------------------
# Scraper class
# ---------------------------------------------------------------------------

class FlashscoreScraper(BaseScraper):
    """Multi-sport Flashscore scraper using curl_cffi browser impersonation.

    Subclassed per sport for registry compatibility.
    """

    sport = ""  # set by subclass
    source_name = "flashscore"
    _request_delay = (1.5, 3.0)

    def fetch_team_stats(self, team_name: str) -> tuple[dict[str, list[float]], str | None]:
        """Public API: fetch stat series for a single team.

        Returns (stats_dict, error_or_None). Does NOT write to DB.
        """
        return _try_flashscore(team_name, self.sport)

    def scrape_team_season_stats(self, competition: str, season: str, *,
                                max_teams: int = 0,
                                team_list: list[str] | None = None) -> int:
        """Fetch stats for known teams in this sport from Flashscore.

        Args:
            max_teams: If >0, limit to this many teams (for testing).
            team_list: If provided, use these team names instead of DB lookup.
        """
        if c_requests is None:
            raise ScraperError("curl_cffi is required for Flashscore scraper")

        try:
            with self._get_session() as session:
                sport_id = self._find_or_create_sport(session, self.sport)
                comp_id = self._find_or_create_competition(
                    session, sport_id, competition or f"Flashscore-{self.sport}",
                    "", season,
                )

                if team_list:
                    # Explicit team list — skip DB lookup
                    team_names = list(team_list)
                    db_count = len(team_names)
                else:
                    # DB lookup — scoped by competition or fixture-linked teams
                    if competition:
                        rows = session.execute(
                            text("""
                                SELECT DISTINCT t.name FROM teams t
                                JOIN fixtures f ON (f.home_team_id = t.id OR f.away_team_id = t.id)
                                JOIN competitions c ON f.competition_id = c.id
                                WHERE t.sport_id = :sid AND c.name LIKE :comp
                            """),
                            {"sid": sport_id, "comp": f"%{competition}%"},
                        ).fetchall()
                    else:
                        rows = session.execute(
                            text("""
                                SELECT DISTINCT t.name FROM teams t
                                WHERE t.sport_id = :sid
                                AND length(t.name) >= 3
                                AND EXISTS (
                                    SELECT 1 FROM fixtures f
                                    WHERE f.home_team_id = t.id OR f.away_team_id = t.id
                                )
                            """),
                            {"sid": sport_id},
                        ).fetchall()

                    db_count = len(rows)
                    if not rows:
                        logger.warning("No teams in DB for sport=%s — cannot scrape Flashscore", self.sport)
                        return 0

                    # Python-side filtering for garbage names
                    team_names = []
                    for (name,) in rows:
                        if len(name) < 3:
                            continue
                        digit_ratio = sum(c.isdigit() or c == '.' for c in name) / max(len(name), 1)
                        if digit_ratio > 0.4:
                            continue
                        team_names.append(name)

                    if not team_names:
                        logger.warning("No valid team names after filtering for sport=%s", self.sport)
                        return 0

                if max_teams > 0:
                    team_names = team_names[:max_teams]

                logger.info(
                    "[%s] Flashscore: %d teams to fetch (from %d source rows)",
                    self.sport, len(team_names), db_count,
                )

                accum: dict[str, list[float]] = defaultdict(list)

                with self._track_run(session, f"team_stats/{competition}/{season}") as counts:
                    success = 0
                    for i, team_name in enumerate(team_names, 1):
                        logger.info(
                            "[%s] Flashscore %d/%d: %s",
                            self.sport, i, len(team_names), team_name,
                        )
                        stats, err = _try_flashscore(team_name, self.sport)
                        if err:
                            logger.warning("  ✗ %s: %s", team_name, err)
                            continue

                        success += 1
                        counts["scraped"] += 1
                        for stat_key, values in stats.items():
                            if values:
                                avg = sum(values) / len(values)
                                accum[stat_key].append(avg)

                    logger.info(
                        "[%s] Flashscore team stats: %d/%d teams succeeded, %d stat keys",
                        self.sport, success, len(team_names), len(accum),
                    )

                    inserted = self._upsert_league_profiles(session, comp_id, season, accum)
                    counts["inserted"] = inserted

                session.commit()
                return inserted

        except ScraperError:
            raise
        except Exception as e:
            raise ScraperError(f"Flashscore team stats error ({self.sport}): {e}") from e

    def scrape_player_season_stats(self, competition: str, season: str) -> int:
        """Flashscore results page does not provide per-player season stats."""
        return 0


# ---------------------------------------------------------------------------
# Per-sport subclasses (for registry compatibility)
# ---------------------------------------------------------------------------

class FootballFlashscoreScraper(FlashscoreScraper):
    sport = "football"


class BasketballFlashscoreScraper(FlashscoreScraper):
    sport = "basketball"


class TennisFlashscoreScraper(FlashscoreScraper):
    sport = "tennis"


class HockeyFlashscoreScraper(FlashscoreScraper):
    sport = "hockey"


class VolleyballFlashscoreScraper(FlashscoreScraper):
    sport = "volleyball"
