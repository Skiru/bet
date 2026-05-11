#!/usr/bin/env python3
"""Self-healing data enrichment agent — fetches missing team stats via Playwright.

When the deep analysis pipeline encounters teams/events with missing statistics,
this agent fetches data from internet sources (Flashscore first, Sofascore fallback),
parses sport-specific stats, and saves results to both DB and JSON stats cache.

Usage:
    python3 scripts/data_enrichment_agent.py --team "FC Barcelona" --sport football
    python3 scripts/data_enrichment_agent.py --batch betting/data/missing_teams.json
    python3 scripts/data_enrichment_agent.py --date 2026-05-08
"""

import argparse
import concurrent.futures
import json
import logging
import re
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from fetch_with_playwright import fetch  # noqa: E402

from bet.db.connection import get_db  # noqa: E402
from bet.db.models import TeamForm  # noqa: E402
from bet.db.repositories import SportRepo, StatsRepo, TeamRepo  # noqa: E402
from bet.stats.market_ranking import SPORT_STAT_KEYS  # noqa: E402

logger = logging.getLogger(__name__)

DATA_DIR = ROOT_DIR / "betting" / "data"
CACHE_DIR = DATA_DIR / "stats_cache"

# Per-sport expected stat value ranges for sanity checking parsed data
SPORT_VALUE_RANGES: dict[str, dict[str, tuple[float, float]]] = {
    "football": {
        "corners": (0, 20), "fouls": (0, 35), "yellow_cards": (0, 12),
        "red_cards": (0, 4), "shots": (0, 40), "shots_on_target": (0, 20),
        "possession": (20, 80), "goals": (0, 12), "offsides": (0, 15),
        "saves": (0, 15),
    },
    "basketball": {
        "points": (50, 180), "rebounds": (15, 70), "assists": (10, 45),
        "steals": (0, 20), "blocks": (0, 15), "turnovers": (0, 30),
        "fg_pct": (25, 65), "three_pct": (15, 55), "ft_pct": (50, 100),
    },
    "hockey": {
        "goals": (0, 12), "shots": (10, 60), "powerplay_goals": (0, 5),
        "pim": (0, 50), "hits": (10, 70), "blocks": (5, 35),
        "faceoff_pct": (30, 70),
    },
    "tennis": {
        "aces": (0, 40), "double_faults": (0, 15), "first_serve_pct": (40, 95),
        "break_points_won": (0, 15), "games_won": (0, 25), "sets_won": (0, 5),
        "total_games": (10, 80),
    },
    "volleyball": {
        "points": (0, 160), "aces": (0, 15), "blocks": (0, 20),
        "attack_pct": (20, 70), "sets_won": (0, 5), "total_points": (60, 250),
        "errors": (0, 30),
    },
}

# Rate-limit tracking per domain (thread-safe)
_last_request_time: dict[str, float] = {}
_rate_lock = threading.Lock()
_RATE_LIMIT_SECONDS = 1.5


# ---------------------------------------------------------------------------
# Slugify
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    """Convert team/player name to URL slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


# ---------------------------------------------------------------------------
# URL builders
# ---------------------------------------------------------------------------

# Sports where participants are individuals, not teams
_INDIVIDUAL_SPORTS = {"tennis"}

# Flashscore sport slug overrides (when URL path differs from internal sport name)
_FS_SPORT_SLUGS = {
}

# Sofascore sport slug overrides
_SS_SPORT_SLUGS = {
    "hockey": "ice-hockey",
}


def _build_flashscore_url(team_name: str, sport: str) -> str:
    """Build Flashscore URL from team/player name."""
    slug = _slugify(team_name)
    if sport in _INDIVIDUAL_SPORTS:
        return f"https://www.flashscore.com/player/{slug}/"
    return f"https://www.flashscore.com/team/{slug}/"


def _build_flashscore_search_url(team_name: str) -> str:
    """Build Flashscore search URL as fallback when direct slug fails."""
    from urllib.parse import quote
    return f"https://www.flashscore.com/?text={quote(team_name)}"


def _build_sofascore_url(team_name: str, sport: str) -> str:
    """Build Sofascore URL from team/player name (best-effort — ID unknown)."""
    slug = _slugify(team_name)
    ss_sport = _SS_SPORT_SLUGS.get(sport, sport)
    if sport in _INDIVIDUAL_SPORTS:
        return f"https://www.sofascore.com/player/{slug}/0"
    return f"https://www.sofascore.com/team/{ss_sport}/{slug}/0"


def _build_scores24_url(team_name: str, sport: str) -> str:
    """Build scores24.live URL as third-tier fallback."""
    slug = _slugify(team_name)
    sport_map = {
        "football": "football", "basketball": "basketball", "hockey": "ice-hockey",
        "volleyball": "volleyball", "tennis": "tennis",
    }
    s24_sport = sport_map.get(sport, sport)
    return f"https://scores24.live/en/{s24_sport}/team/{slug}"


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

def _rate_limit(domain: str) -> None:
    """Enforce per-domain rate limit (thread-safe)."""
    with _rate_lock:
        now = time.time()
        last = _last_request_time.get(domain, 0.0)
        wait = _RATE_LIMIT_SECONDS - (now - last)
        if wait > 0:
            time.sleep(wait)
        _last_request_time[domain] = time.time()


# ---------------------------------------------------------------------------
# HTML parsers
# ---------------------------------------------------------------------------

def _parse_flashscore_stats(html: str, sport: str) -> dict:
    """Extract L10 stats from Flashscore team page HTML.

    Uses regex patterns to extract statistical data from Flashscore's
    rendered HTML. Returns dict of stat_key -> list of match values.
    """
    stats: dict[str, list[float]] = {}
    stat_keys = SPORT_STAT_KEYS.get(sport, [])

    if not html or len(html) < 500:
        return stats

    # Cap HTML processing to 2MB to prevent catastrophic regex backtracking
    html = html[:2_000_000]

    # Flashscore renders stats in structured divs/tables.
    # Look for patterns like "Corners: 7" or stat values in table cells.
    for key in stat_keys:
        values = _extract_stat_values(html, key, sport)
        if values:
            stats[key] = values

    # Fallback: extract match scores from results list
    # Flashscore shows recent results with score patterns like "2 - 1", "3:1", etc.
    if not stats:
        score_key = _primary_score_key(sport)
        if score_key:
            scores = _extract_match_scores(html, sport)
            if scores:
                stats[score_key] = scores[:10]

    # Validate extracted values
    validated_stats = {}
    for key, vals in stats.items():
        clean = _validate_stat_values(vals, key, sport)
        if clean:
            validated_stats[key] = clean
    return validated_stats


def _primary_score_key(sport: str) -> str | None:
    """Return the primary scoring stat key for a sport."""
    return {
        "football": "goals", "basketball": "points", "hockey": "goals",
        "volleyball": "total_points",
        "tennis": "total_games",
    }.get(sport)


def _extract_match_scores(html: str, sport: str) -> list[float]:
    """Extract numeric scores from recent match results in HTML.

    Looks for score patterns: '2 - 1', '2:1', '(3-1)', final score divs.
    Returns list of total scores (sum of both sides per match).
    """
    scores: list[float] = []

    # Pattern: "X - Y" or "X:Y" score lines (common across Flashscore/Sofascore/scores24)
    score_matches = re.findall(
        r'(?:score|result|final)[^>]*>?\s*(\d+)\s*[-:]\s*(\d+)',
        html, re.IGNORECASE
    )
    for home, away in score_matches:
        try:
            total = float(home) + float(away)
            if total < 200:  # sanity: avoid matching IDs/dates
                scores.append(total)
        except ValueError:
            continue

    # Also try plain "N - N" patterns in content divs
    if not scores:
        plain_scores = re.findall(
            r'>(\d{1,3})\s*[-–:]\s*(\d{1,3})<',
            html,
        )
        for home, away in plain_scores:
            try:
                h, a = float(home), float(away)
                total = h + a
                # Filter by sport-appropriate ranges
                if sport in ("football", "hockey") and total <= 15:
                    scores.append(total)
                elif sport in ("basketball",) and 50 < total < 400:
                    scores.append(total)
                elif sport in ("volleyball", "tennis") and total <= 10:
                    scores.append(total)  # sets/games
                elif total <= 50:  # generic fallback
                    scores.append(total)
            except ValueError:
                continue

    return scores[:10]


def _extract_stat_values(html: str, stat_key: str, sport: str) -> list[float]:
    """Extract numeric values for a stat key from HTML."""
    values: list[float] = []

    # Map stat keys to common labels in HTML
    label_map = {
        "corners": r"(?:corners?|corner\s*kicks?)",
        "fouls": r"(?:fouls?|foul\s*committed)",
        "yellow_cards": r"(?:yellow\s*cards?|bookings?)",
        "red_cards": r"(?:red\s*cards?|sending\s*off)",
        "shots": r"(?:shots?|total\s*shots?)",
        "shots_on_target": r"(?:shots?\s*on\s*target|on\s*target)",
        "possession": r"(?:possession|ball\s*possession)",
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
        "games_won": r"(?:games?\s*won)",
        "sets_won": r"(?:sets?\s*won)",
        "total_games": r"(?:total\s*games?)",
        "hits": r"(?:hits?)",
        "pim": r"(?:pim|penalty\s*minutes?|penalties\s*in\s*minutes?)",
        "runs": r"(?:runs?)",
        "strikeouts": r"(?:strikeouts?|k|so)",
        "walks": r"(?:walks?|bb)",
        "total_runs": r"(?:total\s*runs?)",
        "home_runs": r"(?:home\s*runs?|hr)",
        "penalties": r"(?:penalties?|penalty)",
        "suspensions": r"(?:suspensions?|2min)",
        "total_goals": r"(?:total\s*goals?)",
        "attack_pct": r"(?:attack\s*%|attack\s*pct|attack\s*efficiency)",
        "total_points": r"(?:total\s*points?)",
        "errors": r"(?:errors?)",
        "frames_won": r"(?:frames?\s*won)",
        "centuries": r"(?:centuries?|century\s*breaks?)",
        "highest_break": r"(?:highest?\s*break)",
        "total_frames": r"(?:total\s*frames?)",
        "fifty_plus_breaks": r"(?:50\+?\s*breaks?|fifty\s*plus)",
        "legs_won": r"(?:legs?\s*won)",
        "checkout_pct": r"(?:checkout\s*%|checkout\s*pct)",
        "one_eighties": r"(?:180s?|one\s*eight(?:y|ies))",
        "avg_score": r"(?:avg\s*score|average\s*score|average)",
        "total_legs": r"(?:total\s*legs?)",
        "maps_won": r"(?:maps?\s*won)",
        "rounds_won": r"(?:rounds?\s*won)",
        "kills": r"(?:kills?)",
        "total_maps": r"(?:total\s*maps?)",
        "total_rounds": r"(?:total\s*rounds?)",
        "break_points_won": r"(?:break\s*points?\s*won|bp\s*won)",
        "first_serve_pct": r"(?:1st\s*serve\s*%|first\s*serve\s*%)",
        "fg_pct": r"(?:fg\s*%|field\s*goal\s*%)",
        "three_pct": r"(?:3pt\s*%|three\s*point\s*%|3p%)",
        "ft_pct": r"(?:ft\s*%|free\s*throw\s*%)",
        "faceoff_pct": r"(?:faceoff\s*%|fo%|face\s*off)",
        "powerplay_goals": r"(?:powerplay\s*goals?|pp\s*goals?|ppg)",
        "points_per_set": r"(?:points?\s*per\s*set)",
        "total_sets": r"(?:total\s*sets?)",
        "takedowns": r"(?:takedowns?|td)",
        "sig_strikes": r"(?:sig\.?\s*strikes?|significant\s*strikes?)",
        "submission_attempts": r"(?:submission\s*attempts?|sub\s*att)",
        "rounds": r"(?:rounds?)",
        "control_time": r"(?:control\s*time|ctrl\s*time)",
        "break_points": r"(?:break\s*points?|bp)",
        "heat_points": r"(?:heat\s*points?)",
        "heat_wins": r"(?:heat\s*wins?)",
    }

    pattern = label_map.get(stat_key, re.escape(stat_key.replace("_", " ")))

    # Pattern 1: "Label: value" or "Label value" in text
    matches = re.findall(
        pattern + r"[:\s]*(\d+(?:\.\d+)?)",
        html,
        re.IGNORECASE,
    )
    for m in matches:
        try:
            values.append(float(m))
        except ValueError:
            continue

    # Pattern 2: Table cells with stat name and values in adjacent cells
    cell_pattern = (
        r"(?:<td[^>]*>.*?" + pattern + r".*?</td>\s*<td[^>]*>\s*(\d+(?:\.\d+)?)\s*</td>)"
    )
    cell_matches = re.findall(cell_pattern, html, re.IGNORECASE | re.DOTALL)
    for m in cell_matches:
        try:
            v = float(m)
            if v not in values:
                values.append(v)
        except ValueError:
            continue

    # Pattern 3: Flashscore stat rows in divs (rendered by JS)
    # e.g., <div class="stat__category">Corners</div> ... <div class="stat__homeValue">7</div>
    div_pattern = (
        r'class="[^"]*stat[^"]*"[^>]*>.*?' + pattern
        + r'.*?(\d+(?:\.\d+)?)\s*</(?:div|span)>'
    )
    div_matches = re.findall(div_pattern, html, re.IGNORECASE | re.DOTALL)
    for m in div_matches:
        try:
            v = float(m)
            if v not in values:
                values.append(v)
        except ValueError:
            continue

    # Pattern 4: data-* attributes containing stat values
    data_pattern = r'data-(?:' + stat_key + r'|stat)[^=]*=[\"\'](\d+(?:\.\d+)?)[\"\'"]'
    data_matches = re.findall(data_pattern, html, re.IGNORECASE)
    for m in data_matches:
        try:
            v = float(m)
            if v not in values:
                values.append(v)
        except ValueError:
            continue

    # Deduplicate, validate range, and keep last 10
    validated = _validate_stat_values(values, stat_key, sport)
    return validated[:10]


def _validate_stat_values(values: list[float], stat_key: str, sport: str) -> list[float]:
    """Filter out values outside expected ranges for a sport+stat combination."""
    ranges = SPORT_VALUE_RANGES.get(sport, {})
    bounds = ranges.get(stat_key)
    if not bounds:
        return values  # No validation available for this stat
    lo, hi = bounds
    filtered = [v for v in values if lo <= v <= hi]
    if len(filtered) < len(values):
        logger.warning(
            "Filtered %d/%d %s %s values outside range [%.1f, %.1f]",
            len(values) - len(filtered), len(values), sport, stat_key, lo, hi,
        )
    return filtered


def _parse_sofascore_stats(html: str, sport: str) -> dict:
    """Extract stats from Sofascore HTML (fallback parser).

    Sofascore uses React-rendered HTML with JSON-LD blocks, data-testid
    attributes, and embedded JSON in script tags. This parser tries
    multiple extraction strategies specific to Sofascore's structure.
    """
    stats: dict[str, list[float]] = {}
    stat_keys = SPORT_STAT_KEYS.get(sport, [])

    if not html or len(html) < 200:
        return stats

    # Strategy 1: Extract JSON from <script> tags containing statistics data
    # Sofascore embeds structured data in script tags (JSON-LD or __NEXT_DATA__)
    script_blocks = re.findall(
        r'<script[^>]*>\s*({.*?"statistics".*?})\s*</script>',
        html[:500_000], re.DOTALL | re.IGNORECASE,  # Cap regex scan to 500KB
    )
    if not script_blocks:
        # Try __NEXT_DATA__ pattern — limit to first 2MB to avoid catastrophic backtracking
        next_data = re.findall(
            r'<script[^>]*id="__NEXT_DATA__"[^>]*>\s*({.*?})\s*</script>',
            html[:2_000_000], re.DOTALL,
        )
        script_blocks.extend(next_data)

    for block in script_blocks[:5]:  # Process at most 5 script blocks
        if len(block) > 1_000_000:  # Skip blocks > 1MB — likely not statistics
            continue
        try:
            data = json.loads(block)
            _extract_sofascore_json_stats(data, stat_keys, stats)
        except (json.JSONDecodeError, TypeError):
            continue

    # Strategy 2: Parse data-testid attributes (React-rendered stat cells)
    # Sofascore uses patterns like: <div data-testid="cell">8</div>
    for key in stat_keys:
        if key in stats:
            continue
        label_map = {
            "corners": r"corner", "fouls": r"foul", "yellow_cards": r"yellow",
            "red_cards": r"red", "shots": r"shot", "shots_on_target": r"on.?target",
            "possession": r"possession", "goals": r"goal", "offsides": r"offside",
            "saves": r"save", "points": r"point", "rebounds": r"rebound",
            "assists": r"assist", "aces": r"ace", "blocks": r"block",
            "total_games": r"game", "total_points": r"total.?point",
            "hits": r"hit", "pim": r"penal",
        }
        label_re = label_map.get(key, re.escape(key.replace("_", " ")))

        # data-testid rows: label cell followed by value cell
        testid_pattern = (
            r'data-testid="[^"]*"[^>]*>[^<]*'
            + label_re
            + r'[^<]*<.*?>(\d+(?:\.\d+)?)\s*</'
        )
        testid_matches = re.findall(testid_pattern, html, re.IGNORECASE | re.DOTALL)
        for m in testid_matches:
            try:
                stats.setdefault(key, []).append(float(m))
            except ValueError:
                continue

    # Strategy 3: Generic stat label + value extraction (non-Flashscore-specific)
    # Sofascore renders "StatName  value" in React Box/Text components
    for key in stat_keys:
        if key in stats:
            continue
        label_map = {
            "corners": r"(?:corners?|corner\s*kicks?)",
            "fouls": r"(?:fouls?)", "yellow_cards": r"(?:yellow\s*cards?)",
            "shots": r"(?:shots?|total\s*shots?)",
            "possession": r"(?:possession)", "goals": r"(?:goals?)",
            "points": r"(?:points?|pts)", "rebounds": r"(?:rebounds?|reb)",
            "assists": r"(?:assists?|ast)", "aces": r"(?:aces?)",
            "blocks": r"(?:blocks?|blk)", "total_games": r"(?:total\s*games?)",
            "total_points": r"(?:total\s*points?)",
        }
        pattern = label_map.get(key, re.escape(key.replace("_", " ")))

        # Look for: <Text/span/div>Label</...><Text/span/div>Value</...>
        generic_pattern = (
            r'>[^<]*' + pattern + r'[^<]*</[^>]+>\s*'
            r'(?:<[^>]+>\s*)*?(\d+(?:\.\d+)?)\s*</'
        )
        generic_matches = re.findall(generic_pattern, html, re.IGNORECASE | re.DOTALL)
        for m in generic_matches:
            try:
                v = float(m)
                stats.setdefault(key, []).append(v)
            except ValueError:
                continue

    # Strategy 4: JSON-LD structured data blocks
    jsonld_blocks = re.findall(
        r'<script\s+type="application/ld\+json"[^>]*>\s*({.*?})\s*</script>',
        html[:500_000], re.DOTALL,
    )
    for block in jsonld_blocks[:10]:  # Cap to 10 JSON-LD blocks
        if len(block) > 500_000:
            continue
        try:
            data = json.loads(block)
            _extract_sofascore_json_stats(data, stat_keys, stats)
        except (json.JSONDecodeError, TypeError):
            continue

    # Keep last 10 values per key (no value-based dedup — same stat value
    # can legitimately occur in multiple matches, e.g., 7 corners twice)
    for key in stats:
        stats[key] = stats[key][:10]

    # Validate extracted values
    validated_stats = {}
    for key, vals in stats.items():
        clean = _validate_stat_values(vals, key, sport)
        if clean:
            validated_stats[key] = clean
    return validated_stats


def _extract_sofascore_json_stats(
    data: dict | list, stat_keys: list[str], stats: dict[str, list[float]],
    _depth: int = 0,
) -> None:
    """Recursively extract stat values from parsed Sofascore JSON data."""
    if _depth > 20:
        return
    # Safety: stop if we already have enough data per key (prevent runaway on huge JSON)
    if all(len(stats.get(k, [])) >= 20 for k in stat_keys if k in stats) and stats:
        return
    if isinstance(data, list):
        for item in data[:200]:  # Cap list iteration to prevent memory issues on huge arrays
            if isinstance(item, (dict, list)):
                _extract_sofascore_json_stats(item, stat_keys, stats, _depth + 1)
        return
    if not isinstance(data, dict):
        return

    # Check if this dict has a "name"/"key" + "value" pattern
    name = data.get("name") or data.get("key") or data.get("statisticName") or ""
    value = data.get("value")
    if value is None:
        value = data.get("home")
    if value is None:
        value = data.get("away")
    if isinstance(name, str) and value is not None:
        name_lower = name.lower().replace(" ", "_").replace("-", "_")
        for key in stat_keys:
            if key in name_lower or name_lower in key:
                try:
                    stats.setdefault(key, []).append(float(value))
                except (ValueError, TypeError):
                    pass
                break

    # Check "groups" pattern (Sofascore statistics API format)
    for group in data.get("groups", []):
        if isinstance(group, dict):
            for item in group.get("statisticsItems", []):
                if isinstance(item, dict):
                    item_name = (item.get("name") or "").lower().replace(" ", "_")
                    for key in stat_keys:
                        if key in item_name or item_name in key:
                            for side in ("home", "away", "value", "homeValue", "awayValue"):
                                val = item.get(side)
                                if val is not None:
                                    try:
                                        stats.setdefault(key, []).append(float(str(val).rstrip("%")))
                                    except (ValueError, TypeError):
                                        pass
                            break

    # Recurse into nested dicts (skip "groups" — already processed above)
    for k, v in data.items():
        if k == "groups":
            continue
        if isinstance(v, (dict, list)):
            _extract_sofascore_json_stats(v, stat_keys, stats, _depth + 1)


# ---------------------------------------------------------------------------
# Deep extraction — structured data from Flashscore HTML
# ---------------------------------------------------------------------------

def _parse_flashscore_deep(html: str, sport: str) -> dict:
    """Extract deep structured data from Flashscore team/match page HTML.

    Returns:
        {
            "recent_form": [{"date": "...", "opponent": "...", "result": "W/L/D",
                             "score": "2-1", "competition": "...", "venue": "H/A"}],
            "h2h_meetings": [{"date": "...", "score": "...", "competition": "...",
                              "stats": {"corners": 8, "fouls": 22}}],
            "injuries": [{"player": "...", "status": "OUT/DOUBTFUL", "since": "..."}],
            "stats_per_match": {"corners": [7,8,5,9,6], "fouls": [...]}
        }
    """
    result = {
        "recent_form": [],
        "h2h_meetings": [],
        "injuries": [],
        "stats_per_match": {},
    }

    if not html or len(html) < 500:
        return result

    # --- Recent form ---
    # Flashscore renders recent results with patterns like:
    # "W 2-1 vs Opponent (League)" or structured divs
    form_patterns = [
        # "result W/L/D score opponent" patterns
        re.compile(
            r'(?:class="[^"]*(?:form|result|match)[^"]*"[^>]*>.*?)?'
            r'([WLD])\s*(\d{1,3})\s*[-:–]\s*(\d{1,3})\s+'
            r'(?:vs\.?\s+)?([A-Z][A-Za-z\s\.\'-]{2,30})',
            re.IGNORECASE | re.DOTALL,
        ),
        # Date + score patterns: "DD.MM. Home 2-1 Away"
        re.compile(
            r'(\d{2}\.\d{2}\.?\d{0,4})\s+'
            r'([A-Z][A-Za-z\s\.\'-]{2,30})\s+'
            r'(\d{1,3})\s*[-:–]\s*(\d{1,3})\s+'
            r'([A-Z][A-Za-z\s\.\'-]{2,30})',
            re.IGNORECASE,
        ),
    ]

    for pat in form_patterns:
        for m in pat.finditer(html):
            groups = m.groups()
            if len(groups) == 4:
                # W/L/D pattern
                entry = {
                    "result": groups[0].upper(),
                    "score": f"{groups[1]}-{groups[2]}",
                    "opponent": groups[3].strip(),
                    "date": "",
                    "competition": "",
                    "venue": "",
                }
                result["recent_form"].append(entry)
            elif len(groups) == 5:
                # Date + teams pattern
                entry = {
                    "date": groups[0],
                    "opponent": groups[4].strip(),
                    "score": f"{groups[2]}-{groups[3]}",
                    "result": "",
                    "competition": "",
                    "venue": "",
                }
                result["recent_form"].append(entry)
        if result["recent_form"]:
            break

    # Limit to last 10
    result["recent_form"] = result["recent_form"][:10]

    # --- H2H meetings ---
    # Look for H2H section markers
    h2h_section = re.search(
        r'(?:h2h|head.to.head|direct.meetings)(.*?)(?:standings|statistics|$)',
        html, re.IGNORECASE | re.DOTALL,
    )
    if h2h_section:
        h2h_html = h2h_section.group(1)[:5000]  # limit search scope
        h2h_matches = re.findall(
            r'(\d{2}\.\d{2}\.\d{2,4})\s*.*?'
            r'(\d{1,3})\s*[-:–]\s*(\d{1,3})',
            h2h_html,
        )
        for date_str, score_h, score_a in h2h_matches[:10]:
            meeting = {
                "date": date_str,
                "score": f"{score_h}-{score_a}",
                "competition": "",
                "stats": {},
            }
            result["h2h_meetings"].append(meeting)

    # --- Injuries ---
    # Look for injury markers in the HTML
    injury_patterns = [
        re.compile(
            r'(?:class="[^"]*injur[^"]*"[^>]*>.*?)'
            r'([A-Z][A-Za-z\s\.\'-]{2,30})\s*'
            r'(?:[-–]\s*)?(OUT|Doubtful|Questionable|Day-to-day|Injured|Suspended)',
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            r'(OUT|Doubtful|Questionable|Injured|Suspended)\s*[-–:]\s*'
            r'([A-Z][A-Za-z\s\.\'-]{2,30})',
            re.IGNORECASE,
        ),
    ]
    for pat in injury_patterns:
        for m in pat.finditer(html):
            groups = m.groups()
            if len(groups) == 2:
                player = groups[0].strip() if groups[0][0].isupper() else groups[1].strip()
                status = groups[1].strip() if groups[0][0].isupper() else groups[0].strip()
                result["injuries"].append({
                    "player": player,
                    "status": status.upper(),
                    "since": "",
                })
    # Deduplicate injuries by player name
    seen_players = set()
    unique_injuries = []
    for inj in result["injuries"]:
        if inj["player"] not in seen_players:
            seen_players.add(inj["player"])
            unique_injuries.append(inj)
    result["injuries"] = unique_injuries[:20]

    # --- Stats per match ---
    stat_keys = SPORT_STAT_KEYS.get(sport, [])
    for key in stat_keys:
        values = _extract_stat_values(html, key, sport)
        if values:
            result["stats_per_match"][key] = values[:10]

    # Fallback: extract match scores if no stat keys found
    if not result["stats_per_match"]:
        score_key = _primary_score_key(sport)
        if score_key:
            scores = _extract_match_scores(html, sport)
            if scores:
                result["stats_per_match"][score_key] = scores[:10]

    return result


# ---------------------------------------------------------------------------
# Deep extraction — Sofascore API (public, no key needed)
# ---------------------------------------------------------------------------

_SOFASCORE_API_BASE = "https://api.sofascore.com/api/v1"
_SOFASCORE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.sofascore.com/",
}
_SOFASCORE_SPORT_MAP = {
    "football": "football",
    "basketball": "basketball",
    "hockey": "ice-hockey",
    "tennis": "tennis",
    "volleyball": "volleyball",
}


def _sofascore_request(url: str, max_retries: int = 3) -> dict | None:
    """Make a Sofascore API request with exponential backoff retry."""
    import urllib.request
    import urllib.error

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=_SOFASCORE_HEADERS)
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = (2 ** attempt) * 1.5
                logger.warning("Sofascore rate limited, waiting %.1fs (attempt %d/%d)",
                               wait, attempt + 1, max_retries)
                time.sleep(wait)
            elif e.code in (403, 404):
                logger.debug("Sofascore %d for %s", e.code, url)
                return None
            else:
                logger.warning("Sofascore HTTP %d for %s", e.code, url)
                return None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            logger.debug("Sofascore request error: %s", e)
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                return None
    return None


def _fetch_sofascore_deep(team_name: str, sport: str) -> dict:
    """Fetch deep structured data from Sofascore public API.

    Returns same structure as _parse_flashscore_deep.
    """
    result = {
        "recent_form": [],
        "h2h_meetings": [],
        "injuries": [],
        "stats_per_match": {},
    }

    ss_sport = _SOFASCORE_SPORT_MAP.get(sport, sport)

    # Step 1: Search for team
    from urllib.parse import quote
    search_url = f"{_SOFASCORE_API_BASE}/search/all?q={quote(team_name)}&page=0"
    _rate_limit("sofascore.com")
    search_data = _sofascore_request(search_url)
    if not search_data:
        return result

    # Find team ID from search results
    team_id = None
    teams = search_data.get("teams", [])
    for t in teams:
        t_sport = t.get("sport", {}).get("slug", "")
        if t_sport == ss_sport:
            team_id = t.get("id")
            break
    # Fallback: take first team result
    if not team_id and teams:
        team_id = teams[0].get("id")

    if not team_id:
        logger.debug("Sofascore: team not found for '%s' (%s)", team_name, sport)
        return result

    # Step 2: Get last events
    events_url = f"{_SOFASCORE_API_BASE}/team/{team_id}/events/last/0"
    _rate_limit("sofascore.com")
    events_data = _sofascore_request(events_url)
    if not events_data:
        return result

    events = events_data.get("events", [])[:10]

    # Step 3: Extract form + per-event stats
    for event in events:
        home_team = event.get("homeTeam", {})
        away_team = event.get("awayTeam", {})
        home_name = home_team.get("name", "")
        away_name = away_team.get("name", "")
        home_score = event.get("homeScore", {})
        away_score = event.get("awayScore", {})

        is_home = home_name.lower() == team_name.lower() or home_team.get("id") == team_id
        opponent = away_name if is_home else home_name
        h_score = home_score.get("current", home_score.get("display", ""))
        a_score = away_score.get("current", away_score.get("display", ""))

        # Determine result
        result_str = ""
        try:
            hs, as_ = int(h_score), int(a_score)
            if is_home:
                result_str = "W" if hs > as_ else ("L" if hs < as_ else "D")
            else:
                result_str = "W" if as_ > hs else ("L" if as_ < hs else "D")
        except (ValueError, TypeError):
            pass

        tournament = event.get("tournament", {})
        comp_name = tournament.get("name", "")
        start_ts = event.get("startTimestamp", 0)
        date_str = ""
        if start_ts:
            try:
                date_str = datetime.fromtimestamp(start_ts, tz=timezone.utc).strftime("%Y-%m-%d")
            except (ValueError, TypeError, OSError):
                pass

        form_entry = {
            "date": date_str,
            "opponent": opponent,
            "result": result_str,
            "score": f"{h_score}-{a_score}" if h_score != "" and a_score != "" else "",
            "competition": comp_name,
            "venue": "H" if is_home else "A",
        }
        result["recent_form"].append(form_entry)

        # Step 4: Get per-event statistics
        event_id = event.get("id")
        if event_id:
            stats_url = f"{_SOFASCORE_API_BASE}/event/{event_id}/statistics"
            _rate_limit("sofascore.com")
            stats_data = _sofascore_request(stats_url)
            if stats_data:
                _extract_sofascore_event_stats(
                    stats_data, is_home, result["stats_per_match"]
                )

    return result


def _extract_sofascore_event_stats(
    stats_data: dict, is_home: bool, stats_per_match: dict
) -> None:
    """Extract per-match stat values from Sofascore event statistics response."""
    # Sofascore stats structure: {"statistics": [{"period": "ALL", "groups": [...]}]}
    stat_name_map = {
        "corner kicks": "corners",
        "corners": "corners",
        "fouls": "fouls",
        "yellow cards": "yellow_cards",
        "red cards": "red_cards",
        "total shots": "shots",
        "shots on target": "shots_on_target",
        "shots off target": "shots",
        "ball possession": "possession",
        "offsides": "offsides",
        "goalkeeper saves": "saves",
        "free kicks": "free_kicks",
        "total passes": "passes",
        "tackles": "tackles",
        "blocked shots": "blocked_shots",
        "points": "points",
        "rebounds": "rebounds",
        "assists": "assists",
        "steals": "steals",
        "blocks": "blocks",
        "turnovers": "turnovers",
        "aces": "aces",
        "double faults": "double_faults",
        "break points won": "break_points_won",
        "hits": "hits",
        "penalty minutes": "pim",
        "faceoffs won": "faceoffs_won",
    }

    for period_group in stats_data.get("statistics", []):
        if period_group.get("period") != "ALL":
            continue
        for group in period_group.get("groups", []):
            for item in group.get("statisticsItems", []):
                stat_name = item.get("name", "").lower()
                mapped_key = stat_name_map.get(stat_name)
                if not mapped_key:
                    continue
                home_val = item.get("home", "")
                away_val = item.get("away", "")
                try:
                    val = float(str(home_val).rstrip("%")) if is_home else float(str(away_val).rstrip("%"))
                    stats_per_match.setdefault(mapped_key, []).append(val)
                except (ValueError, TypeError):
                    pass


# ---------------------------------------------------------------------------
# Deep extraction — ESPN API (free, unlimited)
# ---------------------------------------------------------------------------

def _fetch_espn_deep(team_name: str, sport: str) -> dict:
    """Fetch deep structured data from ESPN API.

    Uses existing ESPNStatsClient and ESPN hidden API for:
    - Game logs with per-match stat breakdowns
    - Team injuries
    - Standings

    Returns same structure as _parse_flashscore_deep.
    """
    import urllib.request
    import urllib.error

    result = {
        "recent_form": [],
        "h2h_meetings": [],
        "injuries": [],
        "stats_per_match": {},
    }

    # ESPN sport/league mappings
    espn_sport_map = {
        "football": ("soccer", ""),
        "basketball": ("basketball", "nba"),
        "hockey": ("hockey", "nhl"),
        "tennis": ("tennis", ""),
        "volleyball": ("volleyball", ""),
    }
    espn_sport, espn_league = espn_sport_map.get(sport, (sport, ""))
    if not espn_sport:
        return result

    # Step 1: Search for team via ESPN API
    from urllib.parse import quote
    search_url = f"https://site.api.espn.com/apis/site/v2/sports/{espn_sport}/{espn_league}/teams?limit=100"
    try:
        req = urllib.request.Request(search_url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            teams_data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.debug("ESPN team search error: %s", e)
        return result

    # Find team ID
    team_id = None
    team_lower = team_name.lower()
    for group in teams_data.get("sports", [{}]):
        for league in group.get("leagues", [{}]):
            for t in league.get("teams", []):
                team_info = t.get("team", t)
                names = [
                    team_info.get("displayName", "").lower(),
                    team_info.get("shortDisplayName", "").lower(),
                    team_info.get("name", "").lower(),
                    team_info.get("abbreviation", "").lower(),
                ]
                if any(team_lower in n or n in team_lower for n in names if n):
                    team_id = team_info.get("id")
                    break

    if not team_id:
        logger.debug("ESPN: team not found for '%s' (%s)", team_name, sport)
        return result

    # Step 2: Get team schedule/results
    if espn_league:
        schedule_url = (
            f"https://site.api.espn.com/apis/site/v2/sports/{espn_sport}/{espn_league}"
            f"/teams/{team_id}/schedule"
        )
    else:
        schedule_url = (
            f"https://site.api.espn.com/apis/site/v2/sports/{espn_sport}"
            f"/teams/{team_id}/schedule"
        )

    try:
        req = urllib.request.Request(schedule_url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            schedule_data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.debug("ESPN schedule error: %s", e)
        schedule_data = {}

    # Extract recent form from schedule events
    events = schedule_data.get("events", [])
    # Filter finished games, take last 10
    finished_events = [
        ev for ev in events
        if ev.get("competitions", [{}])[0].get("status", {}).get("type", {}).get("state") == "post"
    ]
    for ev in finished_events[-10:]:
        comps = ev.get("competitions", [{}])
        if not comps:
            continue
        comp = comps[0]
        competitors = comp.get("competitors", [])
        if len(competitors) < 2:
            continue

        is_home = False
        opponent = ""
        h_score = ""
        a_score = ""
        for c in competitors:
            c_id = c.get("id", "")
            if str(c_id) == str(team_id):
                is_home = c.get("homeAway") == "home"
                h_score = c.get("score", "")
            else:
                opponent = c.get("team", {}).get("displayName", "")
                a_score = c.get("score", "")

        # Swap scores if our team is away
        if not is_home:
            h_score, a_score = a_score, h_score

        result_str = ""
        try:
            hs, as_ = int(h_score), int(a_score)
            if is_home:
                result_str = "W" if hs > as_ else ("L" if hs < as_ else "D")
            else:
                result_str = "W" if as_ > hs else ("L" if as_ < hs else "D")
        except (ValueError, TypeError):
            pass

        date_str = ev.get("date", "")[:10]
        comp_name = ev.get("name", "")

        result["recent_form"].append({
            "date": date_str,
            "opponent": opponent,
            "result": result_str,
            "score": f"{h_score}-{a_score}",
            "competition": comp_name,
            "venue": "H" if is_home else "A",
        })

    # Step 3: Get injuries
    if espn_league:
        injuries_url = (
            f"https://site.api.espn.com/apis/site/v2/sports/{espn_sport}/{espn_league}"
            f"/teams/{team_id}/injuries"
        )
    else:
        injuries_url = (
            f"https://site.api.espn.com/apis/site/v2/sports/{espn_sport}"
            f"/teams/{team_id}/injuries"
        )
    try:
        req = urllib.request.Request(injuries_url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            injuries_data = json.loads(resp.read().decode("utf-8"))
        for item in injuries_data.get("items", []):
            athlete = item.get("athlete", {})
            player_name = athlete.get("displayName", "")
            status = item.get("status", "")
            date_of = item.get("date", "")
            if player_name:
                mapped_status = "OUT" if status.lower() in ("out", "injured reserve") else "DOUBTFUL"
                result["injuries"].append({
                    "player": player_name,
                    "status": mapped_status,
                    "since": date_of[:10] if date_of else "",
                })
    except Exception as e:
        logger.debug("ESPN injuries error: %s", e)

    return result


# ---------------------------------------------------------------------------
# Enrichment completeness validation
# ---------------------------------------------------------------------------

def _compute_enrichment_quality(deep_data: dict, sport: str) -> dict:
    """Compute a quality score (0-100) for enriched data completeness.

    Checks:
    - recent_form: has L10 matches with actual results (30 pts)
    - stats_per_match: at least 2 stat keys with per-match values (30 pts)
    - h2h_meetings: has H2H data (20 pts)
    - injuries: has injury data (10 pts)
    - competition context: form entries have competition info (10 pts)
    """
    score = 0
    details = {}

    # Recent form (0-30)
    form = deep_data.get("recent_form", [])
    form_with_results = [f for f in form if f.get("result")]
    if len(form_with_results) >= 8:
        score += 30
        details["recent_form"] = "excellent"
    elif len(form_with_results) >= 5:
        score += 20
        details["recent_form"] = "good"
    elif len(form_with_results) >= 3:
        score += 10
        details["recent_form"] = "partial"
    else:
        details["recent_form"] = "missing"

    # Stats per match (0-30)
    spm = deep_data.get("stats_per_match", {})
    keys_with_data = sum(1 for v in spm.values() if len(v) >= 3)
    if keys_with_data >= 4:
        score += 30
        details["stats_per_match"] = f"excellent ({keys_with_data} keys)"
    elif keys_with_data >= 2:
        score += 20
        details["stats_per_match"] = f"good ({keys_with_data} keys)"
    elif keys_with_data >= 1:
        score += 10
        details["stats_per_match"] = f"partial ({keys_with_data} keys)"
    else:
        details["stats_per_match"] = "missing"

    # H2H (0-20)
    h2h = deep_data.get("h2h_meetings", [])
    if len(h2h) >= 3:
        score += 20
        details["h2h"] = f"good ({len(h2h)} meetings)"
    elif len(h2h) >= 1:
        score += 10
        details["h2h"] = f"partial ({len(h2h)} meetings)"
    else:
        details["h2h"] = "missing"

    # Injuries (0-10)
    injuries = deep_data.get("injuries", [])
    if injuries:
        score += 10
        details["injuries"] = f"{len(injuries)} players"
    else:
        details["injuries"] = "not available"

    # Competition context (0-10)
    form_with_comp = [f for f in form if f.get("competition")]
    if len(form_with_comp) >= 3:
        score += 10
        details["competition_context"] = "present"
    else:
        details["competition_context"] = "missing"

    return {"score": score, "details": details}


# ---------------------------------------------------------------------------
# Deep data save helper
# ---------------------------------------------------------------------------

def _save_deep_data(
    team_name: str, sport: str, deep_data: dict, source: str
) -> None:
    """Save deep extraction data to cache and DB."""
    # Save stats_per_match via existing save functions
    stats = deep_data.get("stats_per_match", {})
    if stats:
        _save_to_cache(team_name, sport, stats, source)
        _save_to_db(team_name, sport, stats, f"deep-{source}")

    # Save deep data JSON to separate cache file
    slug = _slugify(team_name)
    deep_dir = CACHE_DIR / sport / "deep"
    deep_dir.mkdir(parents=True, exist_ok=True)
    deep_path = deep_dir / f"{slug}.json"

    deep_cache = {
        "team": team_name,
        "sport": sport,
        "source": source,
        "recent_form": deep_data.get("recent_form", []),
        "h2h_meetings": deep_data.get("h2h_meetings", []),
        "injuries": deep_data.get("injuries", []),
        "stats_per_match_keys": list(stats.keys()),
        "enriched_at": _now_iso(),
    }
    deep_path.write_text(
        json.dumps(deep_cache, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Saved deep data: %s (%s via %s)", team_name, sport, source)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_avg(values: list) -> float | None:
    nums = [v for v in values if isinstance(v, (int, float))]
    if not nums:
        return None
    return round(sum(nums) / len(nums), 2)


def _compute_trend(l10_values: list[float], l5_values: list[float]) -> str:
    """Determine trend: rising, falling, or stable."""
    l10_avg = _safe_avg(l10_values)
    l5_avg = _safe_avg(l5_values)
    if l10_avg is None or l5_avg is None:
        return "stable"
    diff = l5_avg - l10_avg
    if abs(diff) < 0.3:
        return "stable"
    return "rising" if diff > 0 else "falling"


# ---------------------------------------------------------------------------
# Save functions
# ---------------------------------------------------------------------------

def _save_to_cache(team_name: str, sport: str, stats: dict, source: str) -> None:
    """Save stats to JSON cache file for backward compatibility."""
    slug = _slugify(team_name)
    sport_dir = CACHE_DIR / sport
    sport_dir.mkdir(parents=True, exist_ok=True)
    cache_path = sport_dir / f"{slug}.json"

    # Load existing cache if present
    existing = {}
    if cache_path.exists():
        try:
            existing = json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}

    # Build form data
    form_data = {}
    for stat_key, values in stats.items():
        l10 = values[:10]
        l5 = values[:5] if len(values) >= 5 else values
        form_data[stat_key] = {
            "l10_avg": _safe_avg(l10),
            "l5_avg": _safe_avg(l5),
        }

    l10_matches = []
    if stats:
        # Build per-match dicts from parallel value lists
        max_matches = max(len(v) for v in stats.values())
        for i in range(min(max_matches, 10)):
            match_stats = {}
            for key, vals in stats.items():
                if i < len(vals):
                    match_stats[key] = vals[i]
            if match_stats:
                l10_matches.append(match_stats)

    # Merge sources
    sources = existing.get("sources", [])
    if source not in sources:
        sources.append(source)
    if "enrichment-agent" not in sources:
        sources.append("enrichment-agent")

    cache_data = {
        "team": team_name,
        "sport": sport,
        "sources": sources,
        "form": {
            "l10_avg": {k: v["l10_avg"] for k, v in form_data.items()},
            "l5_avg": {k: v["l5_avg"] for k, v in form_data.items()},
            "l10_matches": l10_matches,
        },
        "enriched_at": _now_iso(),
    }

    cache_path.write_text(
        json.dumps(cache_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Saved cache: %s", cache_path)


def _save_to_db(team_name: str, sport: str, stats: dict, source: str) -> None:
    """Save stats to SQLite DB via StatsRepo.save_team_form()."""
    try:
        with get_db() as conn:
            sport_repo = SportRepo(conn)
            team_repo = TeamRepo(conn)
            stats_repo = StatsRepo(conn)

            sport_obj = sport_repo.get_by_name(sport)
            if not sport_obj:
                # Auto-create sport entry if missing
                from bet.db.schema import init_db
                init_db(conn)
                sport_repo.seed_defaults()
                conn.commit()
                sport_obj = sport_repo.get_by_name(sport)
                if not sport_obj:
                    logger.warning("Sport '%s' not found in DB even after seeding", sport)
                    return

            team = team_repo.find_or_create(team_name, sport_obj.id)

            for stat_key, values in stats.items():
                l10 = values[:10]
                l5 = values[:5] if len(values) >= 5 else values
                trend = _compute_trend(l10, l5)

                form = TeamForm(
                    id=None,
                    team_id=team.id,
                    sport_id=sport_obj.id,
                    stat_key=stat_key,
                    l10_values=l10,
                    l5_values=l5,
                    l10_avg=_safe_avg(l10),
                    l5_avg=_safe_avg(l5),
                    h2h_values=[],
                    h2h_opponent_id=None,
                    trend=trend,
                    updated_at=_now_iso(),
                    source=source,
                )
                stats_repo.save_team_form(form)

            conn.commit()
            logger.info("Saved to DB: %s (%s) — %d stat keys", team_name, sport, len(stats))
    except Exception as exc:
        logger.error("DB save failed for %s: %s", team_name, exc)


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------

def _try_flashscore(team_name: str, sport: str) -> tuple[dict, str | None]:
    """Fetch stats from Flashscore. Returns (stats_dict, error_or_None)."""
    url = _build_flashscore_url(team_name, sport)
    _rate_limit("flashscore.com")
    try:
        html = fetch(url, save_snapshot=False)
        if html is None:
            return {}, "CAPTCHA or empty response from Flashscore"
        stats = _parse_flashscore_stats(html, sport)
        if stats:
            return stats, None
        # Direct slug failed — try search as fallback
        search_url = _build_flashscore_search_url(team_name)
        _rate_limit("flashscore.com")
        search_html = fetch(search_url, save_snapshot=False)
        if search_html:
            stats = _parse_flashscore_stats(search_html, sport)
        return stats, None if stats else "No stats parsed from Flashscore"
    except Exception as exc:
        return {}, f"Flashscore fetch error: {exc}"


def _try_sofascore(team_name: str, sport: str) -> tuple[dict, str | None]:
    """Fetch stats from Sofascore (fallback). Returns (stats_dict, error_or_None)."""
    url = _build_sofascore_url(team_name, sport)
    _rate_limit("sofascore.com")
    try:
        html = fetch(url, save_snapshot=False)
        if html is None:
            return {}, "CAPTCHA or empty response from Sofascore"
        stats = _parse_sofascore_stats(html, sport)
        return stats, None
    except Exception as exc:
        return {}, f"Sofascore fetch error: {exc}"


def _try_scores24(team_name: str, sport: str) -> tuple[dict, str | None]:
    """Fetch stats from scores24.live (third-tier fallback). Returns (stats_dict, error_or_None)."""
    url = _build_scores24_url(team_name, sport)
    _rate_limit("scores24.live")
    try:
        html = fetch(url, save_snapshot=False)
        if html is None:
            return {}, "Empty response from scores24"
        # scores24 uses same stat label patterns as Flashscore
        stats = _parse_flashscore_stats(html, sport)
        return stats, None
    except Exception as exc:
        return {}, f"scores24 fetch error: {exc}"


# ---------------------------------------------------------------------------
# Core enrichment functions
# ---------------------------------------------------------------------------

def enrich_team(team_name: str, sport: str, max_retries: int = 2) -> dict:
    """Fetch and save stats for a single team.

    Returns: {
        "team": team_name,
        "sport": sport,
        "status": "enriched" | "partial" | "failed",
        "stats_found": {"corners": 8.5, ...},
        "source": "flashscore" | "sofascore",
        "error": None | "description"
    }
    """
    result = {
        "team": team_name,
        "sport": sport,
        "status": "failed",
        "stats_found": {},
        "source": None,
        "error": None,
    }

    stat_keys = SPORT_STAT_KEYS.get(sport, [])
    if not stat_keys:
        result["error"] = f"No stat keys defined for sport: {sport}"
        return result

    errors = []

    # Try Flashscore first (most reliable)
    for attempt in range(1, max_retries + 1):
        stats, err = _try_flashscore(team_name, sport)
        if stats:
            source = "flashscore"
            result["source"] = source
            # Determine status
            found_keys = set(stats.keys())
            expected_keys = set(stat_keys)
            if found_keys >= expected_keys:
                result["status"] = "enriched"
            elif found_keys:
                result["status"] = "partial"
            else:
                continue  # retry

            result["stats_found"] = {
                k: _safe_avg(v) for k, v in stats.items() if v
            }

            # Save to both cache and DB
            _save_to_cache(team_name, sport, stats, source)
            _save_to_db(team_name, sport, stats, "enrichment-agent")
            return result

        if err:
            errors.append(err)
        if attempt < max_retries:
            time.sleep(1.0)

    # Fallback: try Sofascore
    for attempt in range(1, max_retries + 1):
        stats, err = _try_sofascore(team_name, sport)
        if stats:
            source = "sofascore"
            result["source"] = source
            found_keys = set(stats.keys())
            if found_keys:
                result["status"] = "partial" if found_keys < set(stat_keys) else "enriched"
            result["stats_found"] = {
                k: _safe_avg(v) for k, v in stats.items() if v
            }

            _save_to_cache(team_name, sport, stats, source)
            _save_to_db(team_name, sport, stats, "enrichment-agent")
            return result

        if err:
            errors.append(err)
        if attempt < max_retries:
            time.sleep(1.0)

    # Third fallback: try scores24.live
    stats, err = _try_scores24(team_name, sport)
    if stats:
        source = "scores24"
        result["source"] = source
        found_keys = set(stats.keys())
        if found_keys:
            result["status"] = "partial" if found_keys < set(stat_keys) else "enriched"
        result["stats_found"] = {
            k: _safe_avg(v) for k, v in stats.items() if v
        }
        _save_to_cache(team_name, sport, stats, source)
        _save_to_db(team_name, sport, stats, "enrichment-agent")
        return result
    if err:
        errors.append(err)

    # L7: Web research agent — last resort for missing data
    try:
        from web_research_agent import research_missing_data

        for data_type in ("form", "injuries"):
            l7_result = research_missing_data(
                team1=team_name, sport=sport, data_type=data_type,
            )
            if l7_result.get("data") and not l7_result.get("error"):
                result["status"] = "partial"
                result["source"] = f"web-research-{data_type}"
                logger.info("L7 web research found %s data for %s", data_type, team_name)
                break
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("L7 web research failed for %s: %s", team_name, exc)

    if result["status"] != "failed":
        return result

    result["error"] = "; ".join(errors) if errors else "No data found from any source"
    return result


def enrich_team_deep(team_name: str, sport: str) -> dict:
    """Run deep extraction for a team from multiple sources.

    Tries sources in order of data quality and speed:
    1. Sofascore API (structured, fast, rich stats)
    2. ESPN API (free, unlimited, good for injuries/schedule)
    3. Flashscore deep parse (Playwright-based, slowest)

    Returns deep data dict with quality score.
    """
    deep_result = {
        "team": team_name,
        "sport": sport,
        "deep_data": None,
        "source": None,
        "quality_score": 0,
    }

    best_data = None
    best_score = 0
    best_source = None

    # Source 1: Sofascore API
    try:
        ss_data = _fetch_sofascore_deep(team_name, sport)
        ss_quality = _compute_enrichment_quality(ss_data, sport)
        if ss_quality["score"] > best_score:
            best_data = ss_data
            best_score = ss_quality["score"]
            best_source = "sofascore-api"
            logger.info("Sofascore deep: %s (%s) quality=%d",
                        team_name, sport, ss_quality["score"])
    except Exception as e:
        logger.warning("Sofascore deep failed for %s: %s", team_name, e)

    # Source 2: ESPN API (always try — free and has injuries)
    try:
        espn_data = _fetch_espn_deep(team_name, sport)
        espn_quality = _compute_enrichment_quality(espn_data, sport)
        if espn_quality["score"] > best_score:
            best_data = espn_data
            best_score = espn_quality["score"]
            best_source = "espn-api"
            logger.info("ESPN deep: %s (%s) quality=%d",
                        team_name, sport, espn_quality["score"])
        # Merge injury data from ESPN even if Sofascore had better stats
        elif best_data and espn_data.get("injuries") and not best_data.get("injuries"):
            best_data["injuries"] = espn_data["injuries"]
            logger.info("ESPN injuries merged for %s", team_name)
    except Exception as e:
        logger.warning("ESPN deep failed for %s: %s", team_name, e)

    # Source 3: Flashscore deep parse (only if we don't have good data yet)
    if best_score < 40:
        try:
            url = _build_flashscore_url(team_name, sport)
            _rate_limit("flashscore.com")
            html = fetch(url, save_snapshot=False)
            if html:
                fs_data = _parse_flashscore_deep(html, sport)
                fs_quality = _compute_enrichment_quality(fs_data, sport)
                if fs_quality["score"] > best_score:
                    best_data = fs_data
                    best_score = fs_quality["score"]
                    best_source = "flashscore-deep"
                    logger.info("Flashscore deep: %s (%s) quality=%d",
                                team_name, sport, fs_quality["score"])
        except Exception as e:
            logger.warning("Flashscore deep failed for %s: %s", team_name, e)

    if best_data and best_source:
        _save_deep_data(team_name, sport, best_data, best_source)
        deep_result["deep_data"] = best_data
        deep_result["source"] = best_source
        deep_result["quality_score"] = best_score
    else:
        logger.warning("No deep data found for %s (%s)", team_name, sport)

    return deep_result


def enrich_h2h(team_a: str, team_b: str, sport: str) -> dict:
    """Fetch H2H stats between two teams.

    Returns: {
        "team_a": ..., "team_b": ...,
        "status": "enriched" | "failed",
        "meetings_found": 5,
        "h2h_stats": {...}
    }
    """
    result = {
        "team_a": team_a,
        "team_b": team_b,
        "sport": sport,
        "status": "failed",
        "meetings_found": 0,
        "h2h_stats": {},
        "error": None,
    }

    # Build H2H URL — Flashscore pattern
    slug_a = _slugify(team_a)
    slug_b = _slugify(team_b)
    url = f"https://www.flashscore.com/h2h/{slug_a}/{slug_b}/"
    _rate_limit("flashscore.com")

    try:
        html = fetch(url, save_snapshot=False)
        if html is None:
            result["error"] = "CAPTCHA or empty response for H2H page"
            return result

        # Parse H2H data
        stats = _parse_flashscore_stats(html, sport)
        if stats:
            result["status"] = "enriched"
            result["h2h_stats"] = {
                k: _safe_avg(v) for k, v in stats.items() if v
            }
            # Count meetings from data density
            if stats:
                max_vals = max(len(v) for v in stats.values())
                result["meetings_found"] = max_vals

            # Save H2H to DB
            _save_h2h_to_db(team_a, team_b, sport, stats)
        else:
            result["error"] = "No H2H stats parsed from page"

    except Exception as exc:
        result["error"] = f"H2H fetch error: {exc}"

    return result


def _save_h2h_to_db(
    team_a: str, team_b: str, sport: str, stats: dict
) -> None:
    """Save H2H stats to DB."""
    try:
        with get_db() as conn:
            sport_repo = SportRepo(conn)
            team_repo = TeamRepo(conn)
            stats_repo = StatsRepo(conn)

            sport_obj = sport_repo.get_by_name(sport)
            if not sport_obj:
                return

            t_a = team_repo.find_or_create(team_a, sport_obj.id)
            t_b = team_repo.find_or_create(team_b, sport_obj.id)

            for stat_key, values in stats.items():
                form = TeamForm(
                    id=None,
                    team_id=t_a.id,
                    sport_id=sport_obj.id,
                    stat_key=stat_key,
                    l10_values=[],
                    l5_values=[],
                    l10_avg=None,
                    l5_avg=None,
                    h2h_values=values[:10],
                    h2h_opponent_id=t_b.id,
                    trend="stable",
                    updated_at=_now_iso(),
                    source="enrichment-agent",
                )
                stats_repo.save_team_form(form)

            logger.info("Saved H2H to DB: %s vs %s (%s)", team_a, team_b, sport)
    except Exception as exc:
        logger.error("H2H DB save failed: %s", exc)


def batch_enrich(teams: list[dict], max_workers: int = 4) -> list[dict]:
    """Enrich multiple teams in parallel.

    Input: [{"team": "FC Barcelona", "sport": "football", "missing": ["corners", "fouls"]}]
    Returns: list of enrich_team results
    """
    results = []

    # Use ThreadPoolExecutor but respect rate limits via _rate_limit()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for entry in teams:
            team_name = entry.get("team", "")
            sport = entry.get("sport", "")
            if not team_name or not sport:
                results.append({
                    "team": team_name,
                    "sport": sport,
                    "status": "failed",
                    "stats_found": {},
                    "source": None,
                    "error": "Missing team name or sport",
                })
                continue
            fut = executor.submit(enrich_team, team_name, sport)
            futures[fut] = entry

        for fut in concurrent.futures.as_completed(futures):
            try:
                res = fut.result()
                results.append(res)
            except Exception as exc:
                entry = futures[fut]
                results.append({
                    "team": entry.get("team", ""),
                    "sport": entry.get("sport", ""),
                    "status": "failed",
                    "stats_found": {},
                    "source": None,
                    "error": str(exc),
                })

    return results


# ---------------------------------------------------------------------------
# Auto-detect missing teams from shortlist
# ---------------------------------------------------------------------------

def _detect_missing_from_shortlist(date_str: str) -> list[dict]:
    """Scan shortlist for candidates with missing stats cache."""
    # Try both date formats: YYYY-MM-DD (pipeline) and YYYYMMDD (legacy)
    shortlist_path = DATA_DIR / f"{date_str}_s2_shortlist.json"
    if not shortlist_path.exists():
        shortlist_path = DATA_DIR / f"{date_str.replace('-', '')}_s2_shortlist.json"
    if not shortlist_path.exists():
        logger.warning("Shortlist not found: %s", shortlist_path)
        return []

    try:
        data = json.loads(shortlist_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to read shortlist: %s", exc)
        return []

    candidates = data.get("candidates", [])
    missing = []

    for c in candidates:
        sport = c.get("sport", "")
        stat_keys = SPORT_STAT_KEYS.get(sport, [])
        if not stat_keys:
            continue

        for team_field in ("home_team", "away_team", "home", "away", "team_a", "team_b"):
            team_name = c.get(team_field, "")
            if not team_name:
                continue

            slug = _slugify(team_name)
            cache_path = CACHE_DIR / sport / f"{slug}.json"
            if not cache_path.exists():
                missing.append({
                    "team": team_name,
                    "sport": sport,
                    "missing": stat_keys,
                })

    # Deduplicate by (team, sport)
    seen = set()
    deduped = []
    for entry in missing:
        key = (entry["team"], entry["sport"])
        if key not in seen:
            seen.add(key)
            deduped.append(entry)

    return deduped


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    from agent_output import AgentOutput

    parser = argparse.ArgumentParser(
        description="Self-healing data enrichment agent"
    )
    parser.add_argument("--team", help="Single team name to enrich")
    parser.add_argument("--sport", help="Sport for --team mode")
    parser.add_argument("--batch", help="Path to JSON file with teams to enrich")
    parser.add_argument("--date", help="Auto-detect missing teams from shortlist (YYYY-MM-DD)")
    parser.add_argument("--h2h", nargs=2, metavar=("TEAM_A", "TEAM_B"), help="Fetch H2H stats")
    parser.add_argument("--workers", type=int, default=4, help="Max parallel workers")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    parser.add_argument("--stop-on-error", action="store_true", help="Stop on first critical error")
    args = parser.parse_args()

    out = AgentOutput("s2_enrich", verbose=args.verbose, stop_on_error=args.stop_on_error)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if args.team:
        if not args.sport:
            out.error("--sport required with --team", recoverable=False)
            out.summary(verdict="FAILED", metrics={"error": "--sport required with --team"})
            sys.exit(1)
        result = enrich_team(args.team, args.sport)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        out.summary(verdict="OK" if result.get("status") == "enriched" else "PARTIAL",
                     metrics={"team": args.team, "sport": args.sport, "status": result.get("status", "?")})

    elif args.h2h:
        if not args.sport:
            out.error("--sport required with --h2h", recoverable=False)
            out.summary(verdict="FAILED", metrics={"error": "--sport required with --h2h"})
            sys.exit(1)
        result = enrich_h2h(args.h2h[0], args.h2h[1], args.sport)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        out.summary(verdict="OK", metrics={"h2h": f"{args.h2h[0]} vs {args.h2h[1]}", "sport": args.sport})

    elif args.batch:
        batch_path = Path(args.batch)
        if not batch_path.exists():
            out.error(f"Batch file not found: {batch_path}", recoverable=False)
            out.summary(verdict="FAILED", metrics={"error": f"Batch file not found: {batch_path}"})
            sys.exit(1)
        try:
            teams = json.loads(batch_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            out.error(f"Failed to read batch file: {exc}", recoverable=False)
            out.summary(verdict="FAILED", metrics={"error": str(exc)})
            sys.exit(1)
        results = batch_enrich(teams, max_workers=args.workers)
        print(json.dumps(results, indent=2, ensure_ascii=False))

        enriched = sum(1 for r in results if r.get("status") == "enriched")
        partial = sum(1 for r in results if r.get("status") == "partial")
        failed = sum(1 for r in results if r.get("status") == "failed")
        out.summary(verdict="OK" if enriched > 0 else "PARTIAL",
                     metrics={"enriched": enriched, "partial": partial, "failed": failed, "total": len(results)})

    elif args.date:
        # V5: Input contract pre-check (warning-only, never blocks)
        _contract = AgentOutput.validate_input_contract("s2_5_enrich", args.date)
        if _contract["status"] != "OK":
            for _w in _contract.get("warnings", []):
                out.warning(f"Input contract: {_w}")
            for _m in _contract.get("missing", []):
                out.warning(f"Missing input: {_m}")

        missing = _detect_missing_from_shortlist(args.date)
        if not missing:
            out.summary(verdict="OK", metrics={"missing": 0, "message": f"No missing teams for {args.date}"})
            sys.exit(0)
        if args.verbose:
            out.event("missing_detected", count=len(missing))
        else:
            print(f"Found {len(missing)} teams with missing stats", file=sys.stderr)
        results = batch_enrich(missing, max_workers=args.workers)
        print(json.dumps(results, indent=2, ensure_ascii=False))

        enriched = sum(1 for r in results if r.get("status") == "enriched")
        partial = sum(1 for r in results if r.get("status") == "partial")
        failed = sum(1 for r in results if r.get("status") == "failed")
        out.summary(verdict="OK" if enriched > 0 else "PARTIAL",
                     metrics={"enriched": enriched, "partial": partial, "failed": failed, "total": len(results)})

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
