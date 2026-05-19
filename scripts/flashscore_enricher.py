"""Standalone Flashscore enrichment helpers.

This module is intentionally self-contained so it can be reused from other
scripts without importing the heavier enrichment agent or DB layer.

Primary entrypoints:
- `_get_flashscore_entity(team_name, sport)` resolves the native Flashscore
    participant slug and numeric entity id.
- `_try_flashscore(team_name, sport)` fetches the results page via `curl_cffi`
    and returns parsed stat series as `(stats_dict, error_or_none)`.
- `_parse_flashscore_deep(html, sport)` extracts structured context from a page
    that has already been fetched.
"""

import json
import logging
import re
import threading
import time

logger = logging.getLogger(__name__)

__all__ = [
        "SPORT_IDS_FS",
        "SPORT_STAT_KEYS",
        "SPORT_VALUE_RANGES",
        "_get_flashscore_entity",
        "_parse_flashscore_deep",
        "_parse_flashscore_stats",
        "_try_flashscore",
]

_INDIVIDUAL_SPORTS = {"tennis"}
_RATE_LIMIT_SECONDS = 1.5
_last_request_time: dict[str, float] = {}
_rate_lock = threading.Lock()

from bet.stats.value_ranges import SPORT_VALUE_RANGES


def _rate_limit(domain: str) -> None:
    """Apply a simple in-process domain rate limit."""
    with _rate_lock:
        now = time.time()
        last = _last_request_time.get(domain, 0.0)
        wait = _RATE_LIMIT_SECONDS - (now - last)
        if wait > 0:
            time.sleep(wait)
        _last_request_time[domain] = time.time()

SPORT_STAT_KEYS = {
    "football": [
        "corners", "fouls", "yellow_cards", "shots_on_target", 
        "shots_off_target", "ball_possession"
    ],
    "tennis": ["aces", "double_faults", "win_1st_serve", "break_points_saved"],
    "basketball": ["2_pointers", "3_pointers", "free_throws", "rebounds", "turnovers"],
    "volleyball": ["aces", "blocks", "errors"],
    "hockey": ["shots_on_goal", "penalties_in_minutes", "power_play_goals"]
}

def _slugify(name: str) -> str:
    """Convert team/player name to URL slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")

def _build_flashscore_url(team_name: str, sport: str) -> str:
    """Build Flashscore URL from team/player name."""
    slug = _slugify(team_name)
    if sport in _INDIVIDUAL_SPORTS:
        return f"https://www.flashscore.com/player/{slug}/"
    return f"https://www.flashscore.com/team/{slug}/"

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

    # Pattern: "X - Y" or "X:Y" score lines (common across Flashscore/scores24)
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


# curl_cffi for native browser fingerprinting
from curl_cffi import requests as c_requests

SPORT_IDS_FS = {
    "football": 1,
    "tennis": 2,
    "basketball": 3,
    "hockey": 4,
    "volleyball": 12 
}

# Standard browser headers for Flashscore (bypasses Cloudflare with chrome131 impersonation)
_FS_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.flashscore.com/",
}
_FS_IMPERSONATE = "chrome131"

def _get_flashscore_entity(team_name: str, sport: str) -> tuple:
    """Resolve Flashscore entity metadata via the native search endpoint."""
    sid = SPORT_IDS_FS.get(sport, 1)
    url = f"https://s.flashscore.com/search/?q={c_requests.utils.quote(team_name)}&l=1&sid={sid}&pid=1&f=1;1"
    headers = {"x-fsign": "SW9D1eZo"}
    
    try:
        resp = c_requests.get(url, impersonate=_FS_IMPERSONATE, headers=headers, timeout=10)
        if resp.status_code == 200:
            text = resp.text
            start = text.find('({') + 1
            end = text.rfind('})') + 1
            if start > 0 and end > 0:
                data = json.loads(text[start:end])
                for r in data.get('results', []):
                    if r.get('type') == 'participants':
                        entity_type = "player" if r.get('participant_type_id') == 2 else "team"
                        return entity_type, r.get('url'), r.get('id')
    except Exception as e:
        logger.warning(f"Flashscore search failed for {team_name}: {e}")
    return None, None, None

def _try_flashscore(team_name: str, sport: str) -> tuple:
    """Fetch stats from Flashscore using curl_cffi. Returns (stats_dict, error_or_None).
    
    Thread-safe: uses curl_cffi only (no Playwright, no asyncio).
    Parses embedded feed data from /results/ page for reliable score extraction.
    """
    # Tennis player pages (/player/{slug}/) consistently 404 on Flashscore.
    # Use Tennis Abstract + Sackmann instead (dedicated tennis sources).
    if sport in _INDIVIDUAL_SPORTS:
        return {}, f"Flashscore skipped for {sport} (use tennis-abstract/sackmann)"

    entity_type, slug, entity_id = _get_flashscore_entity(team_name, sport)
    if not slug or not entity_id:
        return {}, "Could not find team ID via Flashscore Search"
    
    errors = []

    # Fetch /results/ page
    url = f"https://www.flashscore.com/{entity_type}/{slug}/{entity_id}/results/"
    _rate_limit("flashscore.com")
    
    try:
        resp = c_requests.get(url, impersonate=_FS_IMPERSONATE, headers=_FS_HEADERS, timeout=15)
        if resp.status_code != 200:
            return {}, f"Flashscore results returned status {resp.status_code}"
        html = resp.text
        if len(html) < 500 or "just a moment" in html.lower():
            return {}, "Blocked by JavaScript challenge barrier"
    except Exception as exc:
        return {}, f"Flashscore results fetch error: {exc}"
    
    # Parse embedded feed data (much more reliable than HTML regex)
    stats = _parse_embedded_feed(html, sport, entity_id)
    if stats:
        return stats, None
    
    # Fallback: HTML regex parsing (less reliable)
    stats = _parse_flashscore_stats(html, sport)
    if stats:
        return stats, None
    
    return {}, "No stats parsed from Flashscore HTML"


def _parse_embedded_feed(html: str, sport: str, team_entity_id: str) -> dict[str, list[float]] | None:
    """Parse Flashscore embedded feed data from HTML for reliable score extraction.
    
    The HTML embeds match results in a feed format:
    ~AA÷{event_id}¬AD÷{timestamp}¬...AG÷{home_score}¬AH÷{away_score}¬
    BA÷{p1_home}¬BB÷{p1_away}¬BC÷{p2_home}¬BD÷{p2_away}¬...
    
    PY÷{entity_id} identifies "our" team (team we searched for).
    """
    if "~AA÷" not in html:
        return None
    
    matches_raw = html.split("~AA÷")[1:]
    if not matches_raw:
        return None
    
    # Parse up to 10 most recent finished matches
    our_scores: list[float] = []
    opp_scores: list[float] = []
    total_scores: list[float] = []
    period_scores: dict[str, list[float]] = {}  # "p1", "p2", "p3", "p4" → values
    
    for match_block in matches_raw[:15]:
        fields = {}
        for field in match_block.split("¬"):
            if "÷" in field:
                key, _, val = field.partition("÷")
                fields[key] = val
        
        # Check match is finished (AB÷3 = finished)
        status = fields.get("AB", "")
        if status != "3":
            continue
        
        # Get scores
        home_score_str = fields.get("AG", "")
        away_score_str = fields.get("AH", fields.get("AU", ""))
        if not home_score_str or not away_score_str:
            continue
        
        try:
            home_score = float(home_score_str)
            away_score = float(away_score_str)
        except (ValueError, TypeError):
            continue
        
        total = home_score + away_score
        total_scores.append(total)
        
        # Determine if we're home or away (PY÷ = home entity ID, PX÷ = away entity ID)
        if fields.get("PY") == team_entity_id:
            our_scores.append(home_score)
            opp_scores.append(away_score)
        elif fields.get("PX") == team_entity_id:
            our_scores.append(away_score)
            opp_scores.append(home_score)
        else:
            # Can't determine, use home as default
            our_scores.append(home_score)
            opp_scores.append(away_score)
        
        # Period/quarter scores: BA/BB=p1, BC/BD=p2, BE/BF=p3, BG/BH=p4
        period_keys = [("BA", "BB"), ("BC", "BD"), ("BE", "BF"), ("BG", "BH")]
        for i, (h_key, a_key) in enumerate(period_keys, 1):
            h_val = fields.get(h_key, "")
            a_val = fields.get(a_key, "")
            if h_val and a_val:
                try:
                    p_total = float(h_val) + float(a_val)
                    period_key = f"p{i}"
                    if period_key not in period_scores:
                        period_scores[period_key] = []
                    period_scores[period_key].append(p_total)
                except (ValueError, TypeError):
                    pass
        
        if len(total_scores) >= 10:
            break
    
    if not total_scores:
        return None
    
    # Build stats dict based on sport
    stats: dict[str, list[float]] = {}
    
    if sport == "football":
        stats["goals"] = total_scores
        # First half goals from period 1
        if "p1" in period_scores:
            stats["goals_1st_half"] = period_scores["p1"]
    elif sport == "basketball":
        stats["points"] = total_scores
        # Quarter totals
        for pk, pv in period_scores.items():
            stats[f"points_{pk}"] = pv
    elif sport == "hockey":
        stats["goals"] = total_scores
        if "p1" in period_scores:
            stats["goals_p1"] = period_scores["p1"]
        if "p2" in period_scores:
            stats["goals_p2"] = period_scores["p2"]
        if "p3" in period_scores:
            stats["goals_p3"] = period_scores["p3"]
    elif sport == "volleyball":
        stats["total_points"] = total_scores
        for pk, pv in period_scores.items():
            stats[f"set_{pk}_points"] = pv
    else:
        score_key = _primary_score_key(sport) or "total_score"
        stats[score_key] = total_scores
    
    # Validate all values
    validated = {}
    for key, vals in stats.items():
        clean = _validate_stat_values(vals, key, sport)
        if clean:
            validated[key] = clean
        elif vals:
            # If no validator exists for this key (period scores), keep raw
            validated[key] = vals[:10]
    
    if validated:
        logger.info(f"[flashscore-feed] Parsed {len(total_scores)} matches, {len(validated)} stat keys")
    return validated if validated else None


def _extract_match_ids(html: str) -> list[str]:
    """Extract Flashscore match/event IDs from results page HTML."""
    # Flashscore uses data-id or id attributes for match rows
    # Pattern: id="g_1_XXXXXXXX" or data-id="XXXXXXXX"
    ids = re.findall(r'id="g_\d+_([A-Za-z0-9]{8,})"', html)
    if not ids:
        # Alternative pattern
        ids = re.findall(r'data-id="([A-Za-z0-9]{8,})"', html)
    return ids[:10]  # Max 10 matches


def _fetch_match_statistics(match_ids: list[str], sport: str) -> dict[str, list[float]]:
    """Fetch per-match statistics from Flashscore match detail API.
    
    Flashscore exposes match stats via internal API:
    https://d.flashscore.com/x/feed/d_st_{match_id}
    """
    stats: dict[str, list[float]] = {}
    stat_keys = SPORT_STAT_KEYS.get(sport, [])
    
    for match_id in match_ids:
        _rate_limit("flashscore.com")
        url = f"https://d.flashscore.com/x/feed/d_st_{match_id}"
        headers = {
            **_FS_HEADERS,
            "x-fsign": "SW9D1eZo",
        }
        try:
            resp = c_requests.get(url, impersonate=_FS_IMPERSONATE, headers=headers, timeout=10)
            if resp.status_code != 200:
                continue
            text = resp.text
            # Parse Flashscore stat feed format:
            # Lines like: "SA÷stat_name¬SE÷home_value¬SF÷away_value¬"
            # or "SE÷Corner Kicks¬SF÷7¬SG÷5¬"
            _parse_stat_feed(text, sport, stat_keys, stats)
        except Exception:
            continue
    
    return stats


def _parse_stat_feed(text: str, sport: str, stat_keys: list[str], stats: dict[str, list[float]]) -> None:
    """Parse Flashscore stat feed text into stats dict.
    
    Feed format uses delimiters: ÷ (separator), ¬ (field end)
    Lines contain stat category name + home/away values.
    """
    # Flashscore stat feed key mapping
    feed_label_map = {
        "corner kicks": "corners",
        "corners": "corners",
        "fouls": "fouls",
        "yellow cards": "yellow_cards",
        "red cards": "red_cards",
        "shots on target": "shots_on_target",
        "shots off target": "shots_off_target",
        "total shots": "shots",
        "ball possession": "ball_possession",
        "offsides": "offsides",
        "goalkeeper saves": "saves",
        "free kicks": "free_kicks",
        "blocked shots": "blocked_shots",
        # Basketball
        "rebounds": "rebounds",
        "assists": "assists",
        "steals": "steals",
        "turnovers": "turnovers",
        "2 pointers": "2_pointers",
        "3 pointers": "3_pointers",
        "free throws": "free_throws",
        # Hockey
        "shots on goal": "shots_on_goal",
        "penalty minutes": "penalties_in_minutes",
        "power play goals": "power_play_goals",
        "hits": "hits",
        "blocked shots": "blocks",
        "faceoffs won": "faceoffs_won",
    }
    
    # Parse lines — format: "SA÷Category Name¬SE÷value1¬SF÷value2¬"
    # Split by stat separators
    sections = text.split("~")
    for section in sections:
        if "÷" not in section:
            continue
        fields = section.split("¬")
        category = ""
        home_val = None
        away_val = None
        for field in fields:
            if "÷" not in field:
                continue
            key, _, value = field.partition("÷")
            if key == "SA":
                category = value.lower().strip()
            elif key == "SE":
                try:
                    home_val = float(value.replace("%", ""))
                except (ValueError, TypeError):
                    pass
            elif key == "SF":
                try:
                    away_val = float(value.replace("%", ""))
                except (ValueError, TypeError):
                    pass
        
        if category and home_val is not None:
            mapped_key = feed_label_map.get(category, "")
            if mapped_key and mapped_key in stat_keys:
                if mapped_key not in stats:
                    stats[mapped_key] = []
                stats[mapped_key].append(home_val)
                if away_val is not None:
                    stats[mapped_key].append(away_val)
