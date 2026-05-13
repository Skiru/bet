#!/usr/bin/env python3
"""Ingest scan data into stats_cache.

Reads Beast Mode output (betting/data/global_events_api.json) or legacy
scan_summary.json, transforms into the standard stats_cache format,
and writes via build_stats_cache.

CLI: python3 scripts/ingest_scan_stats.py [--date YYYY-MM-DD] [--dry-run]
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_stats_cache import (
    CACHE_DIR,
    create_team_cache_entry,
    now_iso,
    read_cache,
    slugify,
    update_cache,
    validate_sport,
    _compute_stat_averages,
    _compute_combined_stat_averages,
)

# --- DB dual-write (optional) ---
try:
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from bet.db.connection import get_db
    from bet.db.repositories import SportRepo, TeamRepo, StatsRepo
    from bet.db.models import TeamForm
    _HAS_DB = True
except ImportError:
    _HAS_DB = False

SCAN_SUMMARY_PATH = Path(__file__).parent.parent / "betting" / "data" / "scan_summary.json"
BEAST_MODE_PATH = Path(__file__).parent.parent / "betting" / "data" / "global_events_api.json"

# Minimum API-sourced L10 matches before we skip overwriting form with scan data
API_FORM_THRESHOLD = 5


# ---------------------------------------------------------------------------
# Source detection
# ---------------------------------------------------------------------------

_SOURCE_PATTERNS = [
    ("scores24.live", re.compile(r"scores24\.live", re.I)),
    ("forebet.com", re.compile(r"forebet\.com", re.I)),
    ("betexplorer.com", re.compile(r"betexplorer\.com", re.I)),
    ("oddsportal.com", re.compile(r"oddsportal\.com", re.I)),
    ("flashscore.com", re.compile(r"flashscore\.com", re.I)),
    ("sofascore.com", re.compile(r"sofascore\.com", re.I)),
    ("soccerway.com", re.compile(r"soccerway\.com", re.I)),
    ("tennisexplorer.com", re.compile(r"tennisexplorer\.com", re.I)),
    ("tennisabstract.com", re.compile(r"tennisabstract\.com", re.I)),
    ("basketball-reference.com", re.compile(r"basketball-reference\.com", re.I)),
    ("hockey-reference.com", re.compile(r"hockey-reference\.com", re.I)),
    ("covers.com", re.compile(r"covers\.com", re.I)),
    ("totalcorner.com", re.compile(r"totalcorner\.com", re.I)),
    ("soccerstats.com", re.compile(r"soccerstats\.com", re.I)),
    ("whoscored.com", re.compile(r"whoscored\.com", re.I)),
]


def detect_source(url: str, event: dict) -> str:
    """Detect the source adapter from URL or event metadata."""
    # Event-level override
    src = event.get("source", "")
    if src:
        return src

    for name, pattern in _SOURCE_PATTERNS:
        if pattern.search(url):
            return name

    return "unknown"


# ---------------------------------------------------------------------------
# Sport-specific score parsers
# ---------------------------------------------------------------------------

def _parse_volleyball_scores(scores: list) -> dict:
    """[sets_t1, sets_t2, s1_t1, s1_t2, s2_t1, s2_t2, ...]"""
    if len(scores) < 2:
        return {}
    stats = {"sets_won": {"home": int(scores[0]), "away": int(scores[1])}}
    set_scores = scores[2:]
    home_pts, away_pts = 0, 0
    for i in range(0, len(set_scores) - 1, 2):
        home_pts += int(set_scores[i])
        away_pts += int(set_scores[i + 1])
    if home_pts or away_pts:
        stats["total_points"] = {"home": home_pts, "away": away_pts}
        stats["points"] = {"home": home_pts, "away": away_pts}
    return stats


def _parse_tennis_scores(scores: list) -> dict:
    """[sets_t1, sets_t2, s1_t1, s1_t2, s2_t1, s2_t2, ...]"""
    if len(scores) < 2:
        return {}
    stats = {"sets_won": {"home": int(scores[0]), "away": int(scores[1])}}
    set_scores = scores[2:]
    home_games, away_games = 0, 0
    for i in range(0, len(set_scores) - 1, 2):
        home_games += int(set_scores[i])
        away_games += int(set_scores[i + 1])
    if home_games or away_games:
        stats["games_won"] = {"home": home_games, "away": away_games}
        stats["total_games"] = {"home": home_games, "away": away_games}
    return stats


def _parse_football_scores(scores: list) -> dict:
    """[goals_t1, goals_t2] or [goals_t1, goals_t2, ht_t1, ht_t2]"""
    if len(scores) < 2:
        return {}
    return {"goals": {"home": int(scores[0]), "away": int(scores[1])}}


def _parse_basketball_scores(scores: list) -> dict:
    """[pts_t1, pts_t2] or [pts_t1, pts_t2, q1_t1, q1_t2, ...]"""
    if len(scores) < 2:
        return {}
    return {"points": {"home": int(scores[0]), "away": int(scores[1])}}


def _parse_hockey_scores(scores: list) -> dict:
    """[goals_t1, goals_t2]"""
    if len(scores) < 2:
        return {}
    return {"goals": {"home": int(scores[0]), "away": int(scores[1])}}


SCORE_PARSERS = {
    "volleyball": _parse_volleyball_scores,
    "tennis": _parse_tennis_scores,
    "football": _parse_football_scores,
    "basketball": _parse_basketball_scores,
    "hockey": _parse_hockey_scores,
}


def parse_scores(sport: str, scores: list) -> dict:
    """Route to sport-specific score parser. Returns stat dict."""
    parser = SCORE_PARSERS.get(sport)
    if not parser:
        return {}
    try:
        return parser([int(s) if isinstance(s, (int, float, str)) and str(s).lstrip("-").isdigit() else 0 for s in scores])
    except (ValueError, IndexError, TypeError):
        return {}


# ---------------------------------------------------------------------------
# Form / H2H extraction from scan event
# ---------------------------------------------------------------------------

def _extract_form_matches(form_list: list, sport: str, team: str) -> list[dict]:
    """Convert scan form data into cache-compatible l10_matches entries."""
    matches = []
    for idx, entry in enumerate(form_list or []):
        # Handle plain strings like "W", "L", "D" (simplified form data)
        if isinstance(entry, str):
            match_entry = {
                "date": "",
                "opponent": "Unknown",
                "fixture_id": f"scan-form-{idx}",
                "stats": {},
                "was_away": False,
            }
            matches.append(match_entry)
            continue
        if not isinstance(entry, dict):
            continue
        scores = entry.get("scores", [])
        stats = parse_scores(sport, scores)
        if not stats and scores:
            # Fallback: treat first two as main score
            stats = parse_scores(sport, scores[:2])
        opponent = entry.get("opponent", "Unknown")
        result_str = entry.get("result") or ""
        was_away = False  # default home perspective
        # If there's an explicit "away" flag, honour it
        if entry.get("was_away"):
            was_away = True
        match_entry = {
            "date": entry.get("date", ""),
            "opponent": opponent,
            "fixture_id": f"scan-form-{idx}",
            "stats": stats,
            "was_away": was_away,
        }
        matches.append(match_entry)
    # Sort by date descending
    matches.sort(key=lambda m: m.get("date", ""), reverse=True)
    return matches[:10]


def _extract_h2h_matches(h2h_data: dict, sport: str) -> list[dict]:
    """Convert scan H2H matches into cache-compatible entries."""
    # Beast Mode format: {"teamDuel": {"homeWins": N, "awayWins": N, "draws": N}}
    if "teamDuel" in h2h_data:
        td = h2h_data.get("teamDuel") or {}
        if td:
            # Create synthetic H2H summary entry
            return [{
                "date": "",
                "fixture_id": "scan-h2h-summary",
                "stats": {
                    "home_wins": td.get("homeWins", 0),
                    "away_wins": td.get("awayWins", 0),
                    "draws": td.get("draws", 0),
                },
            }]
        return []

    # Legacy format: {"matches": [...]}
    raw_matches = h2h_data.get("matches", [])
    entries = []
    for idx, m in enumerate(raw_matches):
        scores = m.get("scores", [])
        stats = parse_scores(sport, scores)
        entries.append({
            "date": m.get("date", ""),
            "fixture_id": f"scan-h2h-{idx}",
            "stats": stats,
        })
    entries.sort(key=lambda e: e.get("date", ""), reverse=True)
    return entries


# ---------------------------------------------------------------------------
# Beast Mode format normalization
# ---------------------------------------------------------------------------

def _parse_odds_val(choice: dict) -> float | None:
    """Extract decimal odds from a choice dict.
    
    Handles fractional ("5/4" → 2.25) and decimal formats.
    Returns None for invalid or sub-1.0 odds.
    """
    raw = choice.get("fractionalValue") or choice.get("decimalValue")
    if raw is None:
        return None
    if isinstance(raw, str) and "/" in raw:
        parts = raw.split("/", 1)
        try:
            result = round(float(parts[0]) / float(parts[1]) + 1, 3)
        except (ValueError, ZeroDivisionError):
            return None
        if result < 1.0:
            return None
        return result
    try:
        result = float(raw)
    except (ValueError, TypeError):
        return None
    if result < 1.0:
        return None
    return result


def _normalize_beast_mode_event(event: dict) -> tuple[str, dict]:
    """Normalize a Beast Mode event (from global_events_api.json) to legacy format.

    Beast Mode format:
      {"id": N, "sport": "football", "home_team": "X", "away_team": "Y",
       "form": {"homeTeam": {"form": ["W","L"]}, "awayTeam": {"form": ["W","L"]}},
       "h2h": {"teamDuel": {"homeWins": N, ...}},
       "odds": [{"marketName": "Full time", "choices": [...]}]}

    Returns (fake_url, normalized_event) in legacy-compatible format.
    """
    normalized = dict(event)
    # Key renames
    normalized["home"] = event.get("home_team", event.get("home", ""))
    normalized["away"] = event.get("away_team", event.get("away", ""))
    normalized["source"] = "flashscore"

    # Form normalization: Beast Mode nested → flat form_home/form_away
    # Preserve ALL data from pregame-form endpoint (position, value, form sequence, matches)
    form = event.get("form") or {}
    if isinstance(form, dict):
        home_form = form.get("homeTeam") or {}
        away_form = form.get("awayTeam") or {}
        if isinstance(home_form, dict):
            if home_form.get("form"):
                normalized["form_home"] = home_form["form"]
            # Preserve league position and points from form data
            if home_form.get("position") is not None:
                normalized.setdefault("standings", {})["home_pos"] = home_form["position"]
            if home_form.get("value") is not None:
                normalized.setdefault("standings", {})["home_pts"] = home_form["value"]
            # Preserve detailed match history if available
            if home_form.get("matches"):
                normalized["form_home_matches"] = home_form["matches"]
        if isinstance(away_form, dict):
            if away_form.get("form"):
                normalized["form_away"] = away_form["form"]
            if away_form.get("position") is not None:
                normalized.setdefault("standings", {})["away_pos"] = away_form["position"]
            if away_form.get("value") is not None:
                normalized.setdefault("standings", {})["away_pts"] = away_form["value"]
            if away_form.get("matches"):
                normalized["form_away_matches"] = away_form["matches"]
        # Keep the form label (e.g., "Pts")
        if form.get("label"):
            normalized.setdefault("standings", {})["label"] = form["label"]

    # H2H: pass through — _extract_h2h_matches now handles Beast Mode format
    # Odds normalization: Beast Mode array → dict (ALL market types)
    odds_raw = event.get("odds") or []
    if isinstance(odds_raw, list) and odds_raw:
        odds_dict = {}
        for market in odds_raw:
            if not isinstance(market, dict):
                continue
            name = market.get("marketName", "")
            choices = market.get("choices") or market.get("outcomes") or []
            name_lower = name.lower()

            # 1X2 / Match Winner
            if name == "Full time" and choices:
                for choice in choices:
                    if not isinstance(choice, dict):
                        continue
                    cname = choice.get("name", "")
                    odds_val = _parse_odds_val(choice)
                    if odds_val is None:
                        continue
                    if cname == "1" or cname.lower() == "home":
                        odds_dict["w1"] = odds_val
                    elif cname == "X" or cname.lower() == "draw":
                        odds_dict["x"] = odds_val
                    elif cname == "2" or cname.lower() == "away":
                        odds_dict["w2"] = odds_val

            # Totals (goals, games, points)
            elif "total" in name_lower or "over" in name_lower or name_lower == "match goals":
                total_lines = odds_dict.setdefault("total_lines", {})
                for choice in choices:
                    if not isinstance(choice, dict):
                        continue
                    cname = (choice.get("name") or "").strip()
                    odds_val = _parse_odds_val(choice)
                    if odds_val is None:
                        continue
                    cname_lower = cname.lower()
                    if "over" in cname_lower:
                        total_lines[f"over_{cname}"] = odds_val
                    elif "under" in cname_lower:
                        total_lines[f"under_{cname}"] = odds_val

            # Both Teams to Score (BTTS) — R5 statistical market
            elif name_lower == "both teams to score":
                for choice in choices:
                    if not isinstance(choice, dict):
                        continue
                    cname = (choice.get("name") or "").lower()
                    odds_val = _parse_odds_val(choice)
                    if odds_val is None:
                        continue
                    if cname == "yes":
                        odds_dict["btts_yes"] = odds_val
                    elif cname == "no":
                        odds_dict["btts_no"] = odds_val

            # Double Chance
            elif name_lower == "double chance":
                dc = odds_dict.setdefault("double_chance", {})
                for choice in choices:
                    if not isinstance(choice, dict):
                        continue
                    cname = (choice.get("name") or "").strip()
                    odds_val = _parse_odds_val(choice)
                    if odds_val is None:
                        continue
                    dc[cname] = odds_val  # "1X", "12", "X2"

            # Draw No Bet
            elif name_lower == "draw no bet":
                dnb = odds_dict.setdefault("draw_no_bet", {})
                for choice in choices:
                    if not isinstance(choice, dict):
                        continue
                    cname = choice.get("name", "")
                    odds_val = _parse_odds_val(choice)
                    if odds_val is None:
                        continue
                    if cname == "1":
                        dnb["home"] = odds_val
                    elif cname == "2":
                        dnb["away"] = odds_val

            # Asian Handicap
            elif "handicap" in name_lower:
                hc = odds_dict.setdefault("handicap_lines", {})
                for choice in choices:
                    if not isinstance(choice, dict):
                        continue
                    cname = (choice.get("name") or "").strip()
                    odds_val = _parse_odds_val(choice)
                    if odds_val is None:
                        continue
                    hc[cname] = odds_val

            # Corners (R5 — priority statistical market)
            elif "corner" in name_lower:
                corners = odds_dict.setdefault("corners", {})
                for choice in choices:
                    if not isinstance(choice, dict):
                        continue
                    cname = (choice.get("name") or "").strip()
                    odds_val = _parse_odds_val(choice)
                    if odds_val is None:
                        continue
                    corners[cname] = odds_val

            # Cards (R5 — priority statistical market)
            elif "card" in name_lower:
                cards = odds_dict.setdefault("cards", {})
                for choice in choices:
                    if not isinstance(choice, dict):
                        continue
                    cname = (choice.get("name") or "").strip()
                    odds_val = _parse_odds_val(choice)
                    if odds_val is None:
                        continue
                    cards[cname] = odds_val

            # Half-time / half markets (1st and 2nd half)
            elif "1st half" in name_lower or "half time" in name_lower:
                ht = odds_dict.setdefault("half_time", {})
                for choice in choices:
                    if not isinstance(choice, dict):
                        continue
                    cname = (choice.get("name") or "").strip()
                    odds_val = _parse_odds_val(choice)
                    if odds_val is None:
                        continue
                    ht[cname] = odds_val

            elif "2nd half" in name_lower:
                ht2 = odds_dict.setdefault("half_time_2nd", {})
                for choice in choices:
                    if not isinstance(choice, dict):
                        continue
                    cname = (choice.get("name") or "").strip()
                    odds_val = _parse_odds_val(choice)
                    if odds_val is None:
                        continue
                    ht2[cname] = odds_val

            # Tennis: set winner
            elif "set winner" in name_lower:
                sw = odds_dict.setdefault("set_winner", {})
                for choice in choices:
                    if not isinstance(choice, dict):
                        continue
                    cname = (choice.get("name") or "").strip()
                    odds_val = _parse_odds_val(choice)
                    if odds_val is None:
                        continue
                    sw[f"{name}_{cname}"] = odds_val

            # Basketball/Hockey: period/quarter markets
            elif "quarter" in name_lower or "period" in name_lower:
                period_key = name_lower.replace(" ", "_")
                pm = odds_dict.setdefault("period_markets", {})
                for choice in choices:
                    if not isinstance(choice, dict):
                        continue
                    cname = (choice.get("name") or "").strip()
                    odds_val = _parse_odds_val(choice)
                    if odds_val is None:
                        continue
                    pm[f"{period_key}_{cname}"] = odds_val

        if odds_dict:
            normalized["odds"] = odds_dict

    # Expected stats (pre-match projections)
    expected_stats = event.get("expected_stats") or {}
    if expected_stats:
        normalized["expected_stats"] = expected_stats

    fake_url = f"flashscore/{event.get('sport', 'unknown')}/{event.get('id', 0)}"
    return fake_url, normalized


# ---------------------------------------------------------------------------
# Main ingestion per event
# ---------------------------------------------------------------------------

def _should_overwrite_form(existing: dict | None) -> bool:
    """Check if existing cache has enough API-sourced form data."""
    if not existing:
        return True
    form = existing.get("form", {})
    l10 = form.get("l10_matches", [])
    sources = existing.get("sources", [])
    # If there are enough API-sourced matches, don't overwrite
    api_matches = sum(
        1 for m in l10
        if not str(m.get("fixture_id", "")).startswith("scan-")
    )
    return api_matches < API_FORM_THRESHOLD


def ingest_event(
    url: str,
    event: dict,
    dry_run: bool = False,
    summary: dict | None = None,
) -> bool:
    """Ingest a single scan event into stats_cache.

    Returns True if data was written (or would be in dry-run).
    """
    sport = event.get("sport", "")
    home = event.get("home", "")
    away = event.get("away", "")
    source = detect_source(url, event)
    source_tag = f"{source}-scan"

    if not sport or not home:
        return False

    try:
        sport = validate_sport(sport)
    except ValueError:
        print(f"[ingest] SKIP invalid sport '{sport}' from {url}")
        return False

    if summary is not None:
        if sport not in summary:
            summary[sport] = {"teams_ingested": 0, "h2h_added": 0, "form_added": 0,
                              "market_types": set()}

    wrote_any = False

    # Deep parse fallback: if top-level fields are empty, try deep_parse
    dp = event.get("deep_parse") or {}
    
    # Odds fallback from deep_parse
    odds_raw = event.get("odds", {})
    if not odds_raw or (isinstance(odds_raw, dict) and not any(v for k, v in odds_raw.items() if k != "total_lines")):
        dp_odds = {}
        if dp.get("odds_1"):
            dp_odds["w1"] = dp["odds_1"]
        if dp.get("odds_x"):
            dp_odds["x"] = dp["odds_x"]
        if dp.get("odds_2"):
            dp_odds["w2"] = dp["odds_2"]
        if dp_odds:
            odds_raw = dp_odds
    
    # Form fallback from deep_parse
    form_home = event.get("form_home", [])
    form_away = event.get("form_away", [])
    if not form_home and dp.get("recent_form_data"):
        # deep_parse recent_form_data may contain form info
        rfd = dp["recent_form_data"]
        if isinstance(rfd, dict):
            form_home = rfd.get("home", [])
            form_away = rfd.get("away", [])
        elif isinstance(rfd, list):
            form_home = rfd  # Best effort
    
    h2h_raw = event.get("h2h", {})

    # Enriched adapter fields
    corners = event.get("corners") or {}
    cards = event.get("cards") or {}
    fouls = event.get("fouls") or {}
    shots = event.get("shots") or {}
    standings = event.get("standings") or {}
    predictions = event.get("predictions") or {}
    dangerous_attacks = event.get("dangerous_attacks") or {}

    enriched = {
        "corners": corners,
        "cards": cards,
        "fouls": fouls,
        "shots": shots,
        "standings": standings,
        "predictions": predictions,
        "dangerous_attacks": dangerous_attacks,
        "expected_stats": event.get("expected_stats") or {},
    }

    # --- Process HOME team ---
    wrote_any |= _ingest_team_side(
        sport=sport,
        team=home,
        opponent=away,
        form_raw=form_home,
        h2h_raw=h2h_raw,
        odds_raw=odds_raw,
        source_tag=source_tag,
        is_home=True,
        deep_parse=dp,
        enriched=enriched,
        dry_run=dry_run,
        summary=summary,
    )

    # --- Process AWAY team ---
    if away:
        wrote_any |= _ingest_team_side(
            sport=sport,
            team=away,
            opponent=home,
            form_raw=form_away,
            h2h_raw=h2h_raw,
            odds_raw=odds_raw,
            source_tag=source_tag,
            is_home=False,
            deep_parse=dp,
            enriched=enriched,
            dry_run=dry_run,
            summary=summary,
        )

    return wrote_any


def _ingest_team_side(
    sport: str,
    team: str,
    opponent: str,
    form_raw: list,
    h2h_raw: dict,
    odds_raw: dict,
    source_tag: str,
    is_home: bool,
    deep_parse: dict | None,
    enriched: dict | None,
    dry_run: bool,
    summary: dict | None,
) -> bool:
    """Ingest data for one team side (home or away) of an event."""
    if not team:
        return False

    existing = read_cache(sport, team)
    existing_sources = existing.get("sources", []) if existing else []
    existing_h2h = existing.get("h2h", {}) if existing else {}

    # --- Form data ---
    form_matches = _extract_form_matches(form_raw, sport, team)
    overwrite_form = _should_overwrite_form(existing)

    form_data = {}
    form_added = 0
    if form_matches and overwrite_form:
        form_data = {
            "l10_matches": form_matches,
            "l10_avg": _compute_stat_averages(form_matches),
            "l5_avg": _compute_stat_averages(form_matches[:5]),
            "recent_matches": form_matches,
        }
        form_added = len(form_matches)
    elif existing and existing.get("form"):
        # Preserve existing form
        form_data = existing["form"]

    # --- H2H data ---
    h2h_data = dict(existing_h2h)
    h2h_added = 0
    if h2h_raw and opponent:
        h2h_matches = _extract_h2h_matches(h2h_raw, sport)
        if h2h_matches:
            opp_slug = slugify(opponent)
            # Merge: add scan H2H alongside existing
            if opp_slug not in h2h_data:
                h2h_avg = _compute_combined_stat_averages(h2h_matches)
                h2h_data[opp_slug] = {
                    "last_updated": now_iso(),
                    "matches": h2h_matches,
                    "avg": h2h_avg,
                }
                h2h_added = len(h2h_matches)
            else:
                # Existing H2H — merge new matches by date dedup
                existing_dates = {
                    m.get("date") for m in h2h_data[opp_slug].get("matches", [])
                }
                new_matches = [
                    m for m in h2h_matches if m.get("date") not in existing_dates
                ]
                if new_matches:
                    merged = h2h_data[opp_slug].get("matches", []) + new_matches
                    merged.sort(key=lambda m: m.get("date", ""), reverse=True)
                    h2h_data[opp_slug]["matches"] = merged
                    h2h_data[opp_slug]["avg"] = _compute_combined_stat_averages(merged)
                    h2h_data[opp_slug]["last_updated"] = now_iso()
                    h2h_added = len(new_matches)

    # --- Odds ---
    scan_odds = {}
    if odds_raw:
        if isinstance(odds_raw, list):
            # BetExplorer format: ["2.00", "3.18", "3.65"] → w1/x/w2 or w1/w2
            try:
                float_odds = [float(o) for o in odds_raw if o]
            except (ValueError, TypeError):
                float_odds = []
            if len(float_odds) == 3:
                scan_odds = {"w1": float_odds[0], "x": float_odds[1], "w2": float_odds[2]}
            elif len(float_odds) == 2:
                scan_odds = {"w1": float_odds[0], "w2": float_odds[1]}
        elif isinstance(odds_raw, dict):
            for key in ("w1", "w2", "x", "draw"):
                if key in odds_raw and odds_raw[key]:
                    scan_odds[key] = odds_raw[key]
            # Pass through ALL structured market types from Beast Mode
            for market_key in ("handicap_lines", "total_lines", "double_chance",
                               "draw_no_bet", "corners", "cards", "half_time",
                               "half_time_2nd", "set_winner", "period_markets"):
                if odds_raw.get(market_key):
                    scan_odds[market_key] = odds_raw[market_key]
            # Scalar market odds
            for scalar_key in ("btts_yes", "btts_no"):
                if odds_raw.get(scalar_key):
                    scan_odds[scalar_key] = odds_raw[scalar_key]

    # --- Stats from deep_parse ---
    scan_stats = {}
    if deep_parse:
        for key in ["corners_ft_home", "corners_ft_away", "corners_ht_home", "corners_ht_away",
                     "yellow_cards_home", "yellow_cards_away", 
                     "prob_home", "prob_draw", "prob_away",
                     "predicted_score"]:
            if deep_parse.get(key) is not None:
                scan_stats[key] = deep_parse[key]

    # --- Stats from enriched adapter output ---
    if enriched:
        corners = enriched.get("corners") or {}
        cards = enriched.get("cards") or {}
        fouls = enriched.get("fouls") or {}
        shots = enriched.get("shots") or {}
        standings = enriched.get("standings") or {}
        predictions = enriched.get("predictions") or {}
        dangerous_attacks = enriched.get("dangerous_attacks") or {}

        if is_home:
            if corners.get("home") is not None:
                scan_stats["corners_per_game"] = corners["home"]
            if cards.get("yellow_home") is not None:
                scan_stats["yellow_cards_per_game"] = cards["yellow_home"]
            elif cards.get("home") is not None:
                scan_stats["yellow_cards_per_game"] = cards["home"]
            if cards.get("red_home") is not None:
                scan_stats["red_cards_per_game"] = cards["red_home"]
            if fouls.get("home") is not None:
                scan_stats["fouls_per_game"] = fouls["home"]
            if shots.get("home") is not None:
                scan_stats["shots_per_game"] = shots["home"]
            if shots.get("on_target_home") is not None:
                scan_stats["shots_on_target_per_game"] = shots["on_target_home"]
            if standings.get("home_pos") is not None:
                scan_stats["league_position"] = standings["home_pos"]
            if dangerous_attacks.get("home") is not None:
                scan_stats["dangerous_attacks"] = dangerous_attacks["home"]
        else:
            if corners.get("away") is not None:
                scan_stats["corners_per_game"] = corners["away"]
            if cards.get("yellow_away") is not None:
                scan_stats["yellow_cards_per_game"] = cards["yellow_away"]
            elif cards.get("away") is not None:
                scan_stats["yellow_cards_per_game"] = cards["away"]
            if cards.get("red_away") is not None:
                scan_stats["red_cards_per_game"] = cards["red_away"]
            if fouls.get("away") is not None:
                scan_stats["fouls_per_game"] = fouls["away"]
            if shots.get("away") is not None:
                scan_stats["shots_per_game"] = shots["away"]
            if shots.get("on_target_away") is not None:
                scan_stats["shots_on_target_per_game"] = shots["on_target_away"]
            if standings.get("away_pos") is not None:
                scan_stats["league_position"] = standings["away_pos"]
            if dangerous_attacks.get("away") is not None:
                scan_stats["dangerous_attacks"] = dangerous_attacks["away"]

        # Predictions (same for both sides — match-level data)
        if predictions.get("prob_home") is not None:
            scan_stats["prob_home"] = predictions["prob_home"]
        if predictions.get("prob_draw") is not None:
            scan_stats["prob_draw"] = predictions["prob_draw"]
        if predictions.get("prob_away") is not None:
            scan_stats["prob_away"] = predictions["prob_away"]
        if predictions.get("predicted_score") is not None:
            scan_stats["predicted_score"] = predictions["predicted_score"]
        if predictions.get("avg_stat") is not None:
            scan_stats["avg_stat"] = predictions["avg_stat"]

        # Expected stats (pre-match projections)
        expected = enriched.get("expected_stats") or {}
        if expected:
            # Store the full expected stats blob for downstream analysis
            scan_stats["expected_stats"] = expected

    # --- Build sources list ---
    sources = list(set(existing_sources + [source_tag]))

    # --- Construct log message ---
    parts = []
    if form_added:
        parts.append(f"form ({form_added} matches)")
    if h2h_added:
        parts.append(f"H2H vs {opponent} ({h2h_added} matches)")
    if scan_odds:
        # Count market categories
        market_types = []
        if "w1" in scan_odds or "w2" in scan_odds:
            market_types.append("1X2")
        if "btts_yes" in scan_odds:
            market_types.append("BTTS")
        if "total_lines" in scan_odds:
            market_types.append("totals")
        if "corners" in scan_odds:
            market_types.append("corners")
        if "cards" in scan_odds:
            market_types.append("cards")
        if "double_chance" in scan_odds:
            market_types.append("DC")
        if "handicap_lines" in scan_odds:
            market_types.append("HC")
        if "half_time" in scan_odds:
            market_types.append("HT")
        if "draw_no_bet" in scan_odds:
            market_types.append("DNB")
        if "period_markets" in scan_odds:
            market_types.append("periods")
        if "set_winner" in scan_odds:
            market_types.append("sets")
        market_str = ",".join(market_types) if market_types else f"{len(scan_odds)} keys"
        parts.append(f"odds [{market_str}]")
    if scan_stats:
        parts.append(f"stats ({len(scan_stats)} keys)")
        
    enriched_count = sum(1 for k in ["corners_per_game", "yellow_cards_per_game", "fouls_per_game", 
                                      "shots_per_game", "league_position", "dangerous_attacks"]
                         if k in scan_stats and k not in (deep_parse or {}))
    if enriched_count:
        parts.append(f"enriched ({enriched_count} stat keys)")

    if not parts:
        return False

    log_detail = ", ".join(parts)

    if dry_run:
        print(f"[ingest] DRY-RUN {sport}/{slugify(team)}: {log_detail}")
    else:
        entry = create_team_cache_entry(
            team=team,
            sport=sport,
            form_data=form_data if form_data else {},
            h2h_data=h2h_data,
            sources=sources,
        )
        if scan_odds:
            entry["scan_odds"] = scan_odds
        if scan_stats:
            entry["scan_stats"] = scan_stats

        update_cache(sport, team, entry)

        # Dual-write to DB
        if _HAS_DB:
            try:
                from build_stats_cache import _persist_to_db
                _persist_to_db(sport, team, entry)
            except Exception:
                pass

        print(f"[ingest] {sport}/{slugify(team)}: {log_detail} → cached")

    # Update summary
    if summary is not None and sport in summary:
        summary[sport]["teams_ingested"] += 1
        summary[sport]["h2h_added"] += h2h_added
        summary[sport]["form_added"] += form_added
        # Track which market types were extracted
        if scan_odds:
            for mk in ("btts_yes", "btts_no"):
                if mk in scan_odds:
                    summary[sport]["market_types"].add("BTTS")
            for mk in ("corners", "cards", "double_chance", "draw_no_bet",
                        "handicap_lines", "total_lines", "half_time", "half_time_2nd",
                        "set_winner", "period_markets"):
                if mk in scan_odds:
                    summary[sport]["market_types"].add(mk)

    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(scan_path: Path, dry_run: bool = False, target_date: str | None = None,
        out: "AgentOutput | None" = None) -> dict:
    """Run full ingestion from scan data.

    Supports both:
    - Beast Mode: global_events_api.json (flat list of events)
    - Legacy: scan_summary.json (dict of URL → events list)

    Returns summary dict: {sport: {teams_ingested, h2h_added, form_added}}.
    """
    if not scan_path.exists():
        msg = f"scan file not found: {scan_path}"
        if out:
            out.error(msg, recoverable=False)
        else:
            print(f"[ingest] ERROR: {msg}", file=sys.stderr)
        return {}

    try:
        raw = json.loads(scan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        msg = f"invalid JSON in {scan_path}: {exc}"
        if out:
            out.error(msg, recoverable=False)
        else:
            print(f"[ingest] ERROR: {msg}", file=sys.stderr)
        return {}

    summary: dict = {}
    total_events = 0
    ingested_events = 0
    errors = 0

    # Detect format: Beast Mode (list) vs legacy (dict)
    if isinstance(raw, list):
        # Beast Mode format: flat list of events from global_events_api.json
        print(f"[ingest] Beast Mode format detected — {len(raw)} events")
        for idx, event in enumerate(raw, 1):
            if not isinstance(event, dict):
                continue

            # Optional date filter
            if target_date:
                event_date = (event.get("start_time", "") or "")[:10]
                if event_date and event_date != target_date:
                    continue

            total_events += 1
            try:
                fake_url, normalized = _normalize_beast_mode_event(event)
                if ingest_event(fake_url, normalized, dry_run=dry_run, summary=summary):
                    ingested_events += 1
            except Exception as exc:
                errors += 1
                sport = event.get("sport", "?")
                home = event.get("home_team", event.get("home", "?"))
                if out:
                    out.error(f"{sport}/{home}: {exc}", recoverable=True)
                else:
                    print(f"[ingest] ERROR processing {sport}/{home}: {exc}", file=sys.stderr)

            if out and idx % 100 == 0:
                out.progress(idx, len(raw), f"Beast Mode event {idx}")

    elif isinstance(raw, dict):
        # Legacy format: dict keyed by URL → list of events
        url_list = list(raw.items())
        for idx, (url, events) in enumerate(url_list, 1):
            if not isinstance(events, list):
                continue
            for event in events:
                if not isinstance(event, dict):
                    continue

                # Optional date filter
                if target_date:
                    event_date = (
                        event.get("match_info", {}).get("date", "")
                        or event.get("date", "")
                    )
                    if event_date and event_date != target_date:
                        continue

                total_events += 1
                try:
                    if ingest_event(url, event, dry_run=dry_run, summary=summary):
                        ingested_events += 1
                except Exception as exc:
                    errors += 1
                    sport = event.get("sport", "?")
                    home = event.get("home", "?")
                    if out:
                        out.error(f"{sport}/{home} from {url}: {exc}", recoverable=True)
                    else:
                        print(f"[ingest] ERROR processing {sport}/{home} from {url}: {exc}", file=sys.stderr)

            if out:
                out.progress(idx, len(url_list), url[:60])

    else:
        msg = f"expected list or dict in {scan_path}, got {type(raw).__name__}"
        if out:
            out.error(msg, recoverable=False)
        else:
            print(f"[ingest] ERROR: {msg}", file=sys.stderr)
        return {}

    # Post-ingest DB verification
    db_verify = {}
    if not dry_run:
        try:
            from bet.db.connection import get_db
            with get_db() as conn:
                rows = conn.execute(
                    "SELECT sport, COUNT(*) as cnt FROM team_form GROUP BY sport"
                ).fetchall()
                db_verify = {row[0]: row[1] for row in rows}
                if out:
                    out.event("db_verify", team_form_by_sport=db_verify)
        except Exception as e:
            if out:
                out.warning(f"DB verification failed: {e}")
            else:
                print(f"[ingest] DB verification failed: {e}", file=sys.stderr)

    # Print summary
    mode = "DRY-RUN " if dry_run else ""
    # Convert sets to lists for JSON serialization
    serializable_summary = {}
    for sport, counts in summary.items():
        serializable_summary[sport] = dict(counts)
        if "market_types" in serializable_summary[sport]:
            serializable_summary[sport]["market_types"] = sorted(serializable_summary[sport]["market_types"])

    if out:
        out.summary(
            verdict="OK" if errors == 0 else "PARTIAL",
            metrics={
                "total_events": total_events,
                "ingested_events": ingested_events,
                "errors": errors,
                "per_sport": serializable_summary,
                "db_verify": db_verify,
            },
        )
    else:
        print(f"\n[ingest] {mode}DONE — {ingested_events}/{total_events} events ingested, {errors} errors")
        for sport, counts in sorted(serializable_summary.items()):
            market_str = ", ".join(counts.get("market_types", []))
            print(
                f"  {sport}: "
                f"{counts['teams_ingested']} teams, "
                f"{counts['h2h_added']} H2H matches, "
                f"{counts['form_added']} form matches"
                + (f", markets: [{market_str}]" if market_str else "")
            )
        if db_verify:
            print(f"[ingest] DB verification — team_form rows: {db_verify}")

    return summary


def main():
    from agent_output import AgentOutput, add_agent_args

    parser = argparse.ArgumentParser(
        description="Ingest scan data into stats_cache (Beast Mode or legacy format)"
    )
    parser.add_argument(
        "--date",
        help="Only ingest events for this date (YYYY-MM-DD)",
        default=None,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate without writing to cache",
    )
    parser.add_argument(
        "--scan-file",
        type=Path,
        default=None,
        help="Path to scan data file. Auto-detects: tries global_events_api.json (Beast Mode) first, falls back to scan_summary.json (legacy)",
    )
    add_agent_args(parser)
    args = parser.parse_args()

    out = AgentOutput("s1_ingest", verbose=args.verbose, stop_on_error=args.stop_on_error)

    # Auto-detect scan file: Beast Mode first, then legacy
    scan_file = args.scan_file
    if scan_file is None:
        if BEAST_MODE_PATH.exists():
            scan_file = BEAST_MODE_PATH
            print(f"[ingest] Auto-detected Beast Mode file: {scan_file}")
        elif SCAN_SUMMARY_PATH.exists():
            scan_file = SCAN_SUMMARY_PATH
            print(f"[ingest] Auto-detected legacy file: {scan_file}")
        else:
            out.error("No scan data found. Run scan_events.py first.", recoverable=False)
            sys.exit(1)

    # Validate date format
    if args.date:
        try:
            datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            out.error(f"invalid date format '{args.date}', expected YYYY-MM-DD", recoverable=False)
            sys.exit(1)

    run(scan_file, dry_run=args.dry_run, target_date=args.date, out=out)


if __name__ == "__main__":
    main()
