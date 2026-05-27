#!/usr/bin/env python3
"""Generate a comprehensive MARKET MATRIX for ALL discovered fixtures.

This script bridges the gap between fixture discovery (10,000+ events) and the
analysis pool (which requires cached stats and often produces 0 events).

It produces a FULL DECISION MATRIX showing:
- Every discovered fixture
- ALL available odds markets per fixture (from odds_api_snapshot, multi-source, scan data)
- Stats data when available (from cache)
- Safety scores when calculable
- NO auto-rejection — everything is shown, user decides
- In STATS-FIRST mode: suggested statistical markets for events without odds

Output:
  betting/data/market_matrix_{date}.json
  betting/data/market_matrix_{date}.md  (human-readable matrix)
  betting/data/decision_matrix_{date}.md  (compact bettable opportunities)

Usage:
    python3 scripts/generate_market_matrix.py --date 2026-04-30
    python3 scripts/generate_market_matrix.py --date 2026-04-30 --stats-first
    python3 scripts/generate_market_matrix.py --date 2026-04-30 --min-odds 1.20 --max-odds 5.00
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "betting" / "data"
CACHE_DIR = DATA_DIR / "stats_cache"

sys.path.insert(0, str(Path(__file__).parent))

try:
    from normalize_stats import build_safety_input, build_safety_input_from_cache
    from bet.stats.market_ranking import SPORT_MARKETS
    from compute_safety_scores import rank_markets
except ImportError:
    build_safety_input = None
    build_safety_input_from_cache = None
    rank_markets = None

from utils import normalize_team_name as _normalize
from bet.utils import is_same_event, names_match

from db_data_loader import load_fixtures_from_db, load_odds_from_db, load_scan_summary_from_db

# Allowed sports — filter out legacy data for removed sports
_ALLOWED_SPORTS = {"football", "basketball", "hockey", "tennis", "volleyball", "cs2", "dota2", "valorant"}


# ---------------------------------------------------------------------------
# Sport key mapping
# ---------------------------------------------------------------------------

def _sport_from_odds_key(sport_key: str) -> str:
    """Convert Odds API sport key to our sport name."""
    if not sport_key:
        return "football"
    sk = sport_key.lower()
    if "soccer" in sk:
        return "football"
    if "basketball" in sk:
        return "basketball"
    if "hockey" in sk or "icehockey" in sk:
        return "hockey"
    if "tennis" in sk:
        return "tennis"
    if "volleyball" in sk:
        return "volleyball"
    # Unknown sport — return as-is instead of defaulting to football
    return sk or "other"


# ---------------------------------------------------------------------------
# Kickoff normalization
# ---------------------------------------------------------------------------

from utils import normalize_kickoff as _normalize_kickoff


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_fixtures(date: str) -> list[dict]:
    """Load discovered fixtures (DB-first via db_data_loader)."""
    return load_fixtures_from_db(date)


def load_odds_api_snapshot(date: str | None = None) -> dict:
    """Load odds API snapshot, return lookup by normalized key.

    Uses DB-first loading via load_odds_from_db when date is provided.
    """
    try:
        if date is not None:
            data = load_odds_from_db(date)
        else:
            path = DATA_DIR / "odds_api_snapshot.json"
            if not path.exists():
                return {}
            data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, Exception):
        return {}

    items = []
    if isinstance(data, dict):
        if "events" in data:
            items = data["events"]
        else:
            for v in data.values():
                if isinstance(v, list):
                    items.extend(v)
    elif isinstance(data, list):
        items = data
    lookup = {}
    for ev in items:
        home = _normalize(ev.get("home_team", ""))
        away = _normalize(ev.get("away_team", ""))
        if home and away:
            lookup[f"{home}|{away}"] = ev
    return lookup


def load_espn_odds_snapshot(date: str) -> dict:
    """Load ESPN odds snapshot (free, no credit cost) as primary odds source.

    Returns lookup by normalized key, same format as load_odds_api_snapshot.
    Falls back to DB odds_history if ESPN JSON files don't exist.
    """
    # Try date-specific file first, then current
    espn_file = DATA_DIR / f"espn_odds_snapshot_{date}.json"
    if not espn_file.exists():
        espn_file = DATA_DIR / "espn_odds_snapshot.json"
    if not espn_file.exists():
        # DB fallback: load odds from odds_history table
        try:
            data = load_odds_from_db(date)
            items = data.get("events", []) if isinstance(data, dict) else []
            lookup = {}
            for ev in items:
                home = _normalize(ev.get("home_team", ""))
                away = _normalize(ev.get("away_team", ""))
                if home and away:
                    lookup[f"{home}|{away}"] = ev
            if lookup:
                print(f"[market_matrix] ESPN fallback: loaded {len(lookup)} events from DB odds_history")
            return lookup
        except Exception as e:
            print(f"[market_matrix] ESPN DB fallback failed: {e}")
            return {}

    try:
        data = json.loads(espn_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

    items = data.get("events", []) if isinstance(data, dict) else []
    lookup = {}
    for ev in items:
        home = _normalize(ev.get("home_team", ""))
        away = _normalize(ev.get("away_team", ""))
        if home and away:
            lookup[f"{home}|{away}"] = ev

    if lookup:
        print(f"[market_matrix] ESPN odds: loaded {len(lookup)} events from {espn_file.name}")
    return lookup


# Pre-compiled garbage patterns for scan item filtering (performance)
_SCAN_GARBAGE_LOWER = frozenset([
    "error", "forbidden", "play offs", "group stage", "standings",
    "draw 1 x 2", "bonus", "free", "sign up", "promo",
    "wyniki", "mecze", "typy dnia", "tips", "picks",
    "best bets", "predictions", "overview", "expert",
    "today's matches", "pinned leagues", "my teams",
    "advertisement", "latest scores", "completed",
    "match stats", "pregame report", "postgame",
    "advancing to next round", "winner:",
    "atp - singles", "wta - singles", "sets legs points",
    "picks & odds", "typy bukmacherów", "kolejka", "wydarzenie",
])


def _is_scan_garbage(home: str, away: str) -> bool:
    """Fast pre-filter for obvious garbage scan items."""
    if len(home) < 3 or len(away) < 3:
        return True
    if len(home) > 60 or len(away) > 60:
        return True
    combined_lower = f"{home} {away}".lower()
    for pat in _SCAN_GARBAGE_LOWER:
        if pat in combined_lower:
            return True
    return False


def load_scan_summary(date: str | None = None) -> dict:
    """Load scan summary items grouped by normalized match key.

    Uses DB-first loading via load_scan_summary_from_db for raw data,
    then applies local grouping/normalization.
    Pre-filters garbage items early for performance (45K+ items).
    """
    try:
        data = load_scan_summary_from_db(date)
    except Exception:
        data = {}

    if not data:
        return {}

    match_data = defaultdict(list)
    skipped = 0
    for url, items in data.items():
        if not isinstance(items, list):
            continue
        for item in items:
            home = item.get("home", item.get("home_team", ""))
            away = item.get("away", item.get("away_team", ""))
            if not home or not away:
                continue
            # Early garbage filter — skip before expensive normalization
            if _is_scan_garbage(home, away):
                skipped += 1
                continue
            key = f"{_normalize(home)}|{_normalize(away)}"
            entry = {
                "source_url": url,
                "raw": item.get("raw", ""),
                "odds": item.get("odds", []),
                "sport": item.get("sport", ""),
                "league": item.get("league", item.get("competition", "")),
                "home": home,
                "away": away,
                "time": item.get("time"),
            }
            if "scores24.live" in url:
                for deep_key in ("h2h", "form_home", "form_away", "trends", "match_info"):
                    if deep_key in item:
                        entry[deep_key] = item[deep_key]
            match_data[key].append(entry)
    if skipped:
        print(f"[matrix] Scan summary: skipped {skipped} garbage items early")
    return dict(match_data)


def load_multi_source_odds() -> dict:
    """Load multi-source odds if available. DB-first, JSON fallback."""
    # Try DB first (odds from multiple sources are stored in odds_history)
    try:
        db_odds = load_odds_from_db(None)
        if db_odds and isinstance(db_odds, dict):
            items = db_odds.get("events", []) if "events" in db_odds else []
            if items:
                lookup = {}
                for ev in items:
                    home = _normalize(ev.get("home_team", ""))
                    away = _normalize(ev.get("away_team", ""))
                    if home and away:
                        lookup[f"{home}|{away}"] = ev
                if lookup:
                    print(f"[market_matrix] DB: loaded {len(lookup)} multi-source odds entries")
                    return lookup
    except Exception:
        pass

    # JSON fallback
    path = DATA_DIR / "odds_multi_sources.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        lookup = {}
        for ev in data.get("events", []):
            home = _normalize(ev.get("home_team", ""))
            away = _normalize(ev.get("away_team", ""))
            if home and away:
                lookup[f"{home}|{away}"] = ev
        return lookup
    except (json.JSONDecodeError, OSError):
        return {}


def load_picks_suggested() -> dict:
    """Load picks_suggested.json as lookup."""
    path = DATA_DIR / "picks_suggested.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else data.get("picks", [])
        lookup = {}
        for p in items:
            match_key = _normalize(p.get("match", ""))
            if match_key:
                lookup[match_key] = p
        return lookup
    except (json.JSONDecodeError, OSError):
        return {}


def load_analysis_pool(date: str) -> dict:
    """Load analysis pool events as lookup."""
    path = DATA_DIR / f"analysis_pool_{date}.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        lookup = {}
        for ev in data.get("events", []):
            home = _normalize(ev.get("home_team", ""))
            away = _normalize(ev.get("away_team", ""))
            if home and away:
                lookup[f"{home}|{away}"] = ev
        return lookup
    except (json.JSONDecodeError, OSError):
        return {}


# ---------------------------------------------------------------------------
# Market extraction from odds data
# ---------------------------------------------------------------------------

def extract_markets_from_odds_api(odds_event: dict) -> list[dict]:
    """Extract all markets from an Odds API event with best prices."""
    markets = []
    market_best: dict = {}

    for bm in odds_event.get("bookmakers", []):
        bm_name = bm.get("title", bm.get("key", "?"))
        for market in bm.get("markets", []):
            mkey = market.get("key", "")
            for outcome in market.get("outcomes", []):
                oname = outcome.get("name", "")
                point = outcome.get("point")
                price = outcome.get("price", 0)

                if point is not None:
                    outcome_key = f"{mkey}|{oname}|{point}"
                else:
                    outcome_key = f"{mkey}|{oname}"

                if outcome_key not in market_best or price > market_best[outcome_key]["price"]:
                    market_best[outcome_key] = {
                        "price": price,
                        "bookmaker": bm_name,
                        "market_type": mkey,
                        "outcome": oname,
                        "point": point,
                    }

    for key, data in market_best.items():
        label = data["market_type"]
        if data["point"] is not None:
            label = f"{data['outcome']} {data['point']}"
        else:
            label = f"{data['market_type']}:{data['outcome']}"
        markets.append({
            "market": label,
            "market_type": data["market_type"],
            "outcome": data["outcome"],
            "point": data["point"],
            "best_odds": round(data["price"], 2),
            "best_bookmaker": data["bookmaker"],
            "source": "odds-api",
        })

    return markets


def extract_markets_from_scan(scan_items: list[dict]) -> list[dict]:
    """Extract odds/market hints from scan summary items."""
    markets = []
    seen = set()
    for item in scan_items:
        odds_list = item.get("odds", [])
        source_url = item.get("source_url", "")

        # Determine source domain for labeling
        source_domain = ""
        if source_url:
            try:
                source_domain = urlparse(source_url).netloc.replace("www.", "")
            except Exception:
                source_domain = source_url

        # Map odds positions to market types based on count
        # 3 odds = 1X2 (football), 2 odds = ML (tennis, basketball, hockey)
        if len(odds_list) == 3:
            labels = ["1X2:Home", "1X2:Draw", "1X2:Away"]
        elif len(odds_list) == 2:
            labels = ["ML:Home", "ML:Away"]
        else:
            labels = [f"scan_odd_{i + 1}" for i in range(len(odds_list))]

        for i, odd in enumerate(odds_list):
            try:
                price = float(odd)
                if 1.01 < price < 50.0:
                    label = labels[i] if i < len(labels) else f"scan_odd_{i + 1}"
                    market_key = f"{source_domain}|{label}"
                    if market_key not in seen:
                        seen.add(market_key)
                        markets.append({
                            "market": label,
                            "market_type": "h2h" if "ML" in label or "1X2" in label else "scan",
                            "outcome": label.split(":")[-1] if ":" in label else label,
                            "point": None,
                            "best_odds": round(price, 2),
                            "best_bookmaker": source_domain,
                            "source": f"scan:{source_domain}",
                        })
            except (ValueError, TypeError):
                pass

    return markets


# ---------------------------------------------------------------------------
# Scores24 deep data extraction (H2H, form, odds, trends)
# ---------------------------------------------------------------------------

def _extract_scores24_deep_data(match_key: str, scan_lookup: dict) -> dict | None:
    """Extract rich data from scores24 detail pages found in scan_summary.

    Scores24 detail page entries have fields: h2h, form_home, form_away,
    odds (w1/x/w2 + handicap_lines + total_lines), trends.
    Returns dict with odds_markets and trend_markets lists.
    """
    # Look through ALL scan items for this match key to find scores24 detail data
    items = scan_lookup.get(match_key)
    if not items or not isinstance(items, list):
        return None

    result = {"odds_markets": [], "trend_markets": [], "h2h": None, "form": None}
    for item in items:
        source_url = item.get("source_url", "")
        if "scores24.live" not in source_url:
            continue

        raw = item.get("raw", item)

        # Always extract H2H and form — they live on `item` even when raw is a string
        h2h = item.get("h2h") if isinstance(raw, str) else raw.get("h2h", item.get("h2h"))
        if isinstance(h2h, dict) and (h2h.get("matches") or h2h.get("home_wins") or h2h.get("away_wins")):
            result["h2h"] = h2h
        form_home = item.get("form_home") if isinstance(raw, str) else raw.get("form_home", item.get("form_home"))
        form_away = item.get("form_away") if isinstance(raw, str) else raw.get("form_away", item.get("form_away"))
        if form_home or form_away:
            result["form"] = {"home": form_home, "away": form_away}

        # Also extract trends from item when raw is a string
        trends_src = item.get("trends", []) if isinstance(raw, str) else raw.get("trends", item.get("trends", []))
        if isinstance(trends_src, list):
            for trend in trends_src:
                if not isinstance(trend, dict):
                    continue
                hit_rate = trend.get("hit_rate")
                hit_count = trend.get("hit_count")
                sample_size = trend.get("sample_size")
                bet_name = trend.get("bet_name", "")
                trend_odds = trend.get("odds")
                if hit_rate and hit_count and sample_size and bet_name:
                    result["trend_markets"].append({
                        "market": bet_name,
                        "market_type": "scores24_trend",
                        "direction": trend.get("category", ""),
                        "safety_score": round(hit_rate, 2) if hit_rate else 0,
                        "hit_count": hit_count,
                        "sample_size": sample_size,
                        "description": trend.get("description", ""),
                        "trend_odds": round(float(trend_odds), 2) if isinstance(trend_odds, (int, float)) else None,
                        "source": "scores24_trends",
                    })

        if isinstance(raw, str):
            continue

        # Extract odds from detail page data
        odds = raw.get("odds", item.get("odds", {}))
        if isinstance(odds, dict):
            # W1/X/W2 moneyline odds
            for label, key in [("ML:Home", "w1"), ("1X2:Draw", "x"), ("ML:Away", "w2")]:
                val = odds.get(key)
                if val and isinstance(val, (int, float)) and 1.01 < val < 50.0:
                    result["odds_markets"].append({
                        "market": label,
                        "market_type": "h2h",
                        "outcome": label.split(":")[-1],
                        "point": None,
                        "best_odds": round(float(val), 2),
                        "best_bookmaker": "scores24.live",
                        "source": "scores24",
                    })
            # Totals lines (over/under)
            for tl in odds.get("total_lines", []):
                direction = tl.get("direction", "")
                line = tl.get("line")
                tl_odds = tl.get("odds")
                if direction and line is not None and tl_odds and isinstance(tl_odds, (int, float)) and 1.01 < tl_odds < 50.0:
                    label = f"{'Over' if direction == 'over' else 'Under'} {line}"
                    result["odds_markets"].append({
                        "market": label,
                        "market_type": "totals",
                        "outcome": label,
                        "point": float(line) if isinstance(line, (int, float)) else None,
                        "best_odds": round(float(tl_odds), 2),
                        "best_bookmaker": "scores24.live",
                        "source": "scores24",
                    })
            # Handicap lines
            for hl in odds.get("handicap_lines", []):
                hline = hl.get("line", "")
                hl_odds = hl.get("odds")
                if hline and hl_odds and isinstance(hl_odds, (int, float)) and 1.01 < hl_odds < 50.0:
                    result["odds_markets"].append({
                        "market": f"HC {hline}",
                        "market_type": "spreads",
                        "outcome": f"HC {hline}",
                        "point": None,
                        "best_odds": round(float(hl_odds), 2),
                        "best_bookmaker": "scores24.live",
                        "source": "scores24",
                    })

        # Store H2H and form for downstream use (from non-string raw)
        h2h = raw.get("h2h", item.get("h2h"))
        if isinstance(h2h, dict) and (h2h.get("matches") or h2h.get("home_wins") or h2h.get("away_wins")):
            result["h2h"] = h2h
        form_home = raw.get("form_home", item.get("form_home"))
        form_away = raw.get("form_away", item.get("form_away"))
        if form_home or form_away:
            result["form"] = {"home": form_home, "away": form_away}

    has_any_data = (
        result["odds_markets"]
        or result["trend_markets"]
        or (result["h2h"] and (result["h2h"].get("matches") or result["h2h"].get("home_wins") or result["h2h"].get("away_wins")))
        or result["form"]
    )
    if not has_any_data:
        return None

    return result


# ---------------------------------------------------------------------------
# Safety score integration (when cache is available)
# ---------------------------------------------------------------------------

# Pre-built cache index for fast safety analysis lookups
_CACHE_INDEX: set | None = None


def _build_cache_index() -> set:
    """Build a set of (sport, slug) tuples for all cached teams. O(1) lookups."""
    global _CACHE_INDEX
    if _CACHE_INDEX is not None:
        return _CACHE_INDEX
    _CACHE_INDEX = set()
    cache_base = ROOT_DIR / "betting" / "data" / "stats_cache"
    if not cache_base.exists():
        return _CACHE_INDEX
    for sport_dir in cache_base.iterdir():
        if not sport_dir.is_dir():
            continue
        sport_name = sport_dir.name
        for f in sport_dir.iterdir():
            if f.suffix == ".json":
                _CACHE_INDEX.add((sport_name, f.stem))
    return _CACHE_INDEX


def try_safety_analysis(sport: str, home: str, away: str, competition: str) -> dict | None:
    """Try to build safety analysis from cache. Return None on cache miss.

    Uses pre-built cache index for O(1) miss detection — avoids expensive
    file system lookups for 15K+ events where most won't have cached data.
    """
    if not build_safety_input or not rank_markets:
        return None
    # Fast-path: check cache index before expensive file I/O
    cache_index = _build_cache_index()
    if cache_index:
        slug_home = _normalize(home).replace(" ", "-")
        slug_away = _normalize(away).replace(" ", "-")
        if (sport, slug_home) not in cache_index and (sport, slug_away) not in cache_index:
            return None
    try:
        safety_input = build_safety_input(sport, home, away, competition)
        if safety_input is None:
            return None
        result = rank_markets(safety_input)
        if not result or not result.get("ranking"):
            return None
        return result
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main matrix generator
# ---------------------------------------------------------------------------

def generate_market_matrix(
    date: str,
    min_odds: float = 1.10,
    max_odds: float = 10.0,
    evening_only: bool = False,
    stats_first: bool = False,
) -> dict:
    """Generate comprehensive market matrix for all fixtures on date.

    Returns dict with:
    - metadata (date, counts, generation time)
    - events: list of event dicts, each with ALL available markets
    """
    print(f"[matrix] Loading data for {date}...")

    fixtures = load_fixtures(date)
    # Filter to supported sports only (DB may contain legacy data for removed sports)
    fixtures = [f for f in fixtures if f.get("sport", "football") in _ALLOWED_SPORTS]
    odds_lookup = load_espn_odds_snapshot(date)  # ESPN first (free, primary)
    odds_api_lookup = load_odds_api_snapshot(date)  # the-odds-api (supplement)
    # Merge: odds_api supplements ESPN (ESPN is primary, don't overwrite)
    for key, val in odds_api_lookup.items():
        if key not in odds_lookup:
            odds_lookup[key] = val
    scan_lookup = load_scan_summary(date)
    multi_odds = load_multi_source_odds()
    picks_suggested = load_picks_suggested()
    analysis_pool = load_analysis_pool(date)

    print(f"[matrix] Fixtures: {len(fixtures)}")
    print(f"[matrix] Odds API events: {len(odds_lookup)}")
    print(f"[matrix] Scan summary keys: {len(scan_lookup)}")
    print(f"[matrix] Multi-source events: {len(multi_odds)}")
    print(f"[matrix] Analysis pool events: {len(analysis_pool)}")

    # Build a set of normalized fixture keys for dedup
    fixture_keys = set()
    for fixture in fixtures:
        home = fixture.get("home_team", fixture.get("home", ""))
        away = fixture.get("away_team", fixture.get("away", ""))
        if home and away:
            fixture_keys.add(f"{_normalize(home)}|{_normalize(away)}")

    # SCAN EXPANSION: Add scan events ONLY if cross-verified against an independent source.
    # FIX: Previously, scan items with just a time (no date) were assigned today's date,
    # causing phantom fixtures from future matchdays (e.g., Europa League Final on May 20
    # appearing in May 11 matrix). Now we require cross-verification.
    #
    # Cross-verification sources: odds_lookup (Odds API), multi_odds, analysis_pool.
    # A scan item is promoted to fixture ONLY if it matches one of these sources
    # OR has an explicit date field matching the target date.
    scan_only_events = 0
    scan_rejected_no_verification = 0

    # Build cross-verification keys from independent sources
    verified_keys: set[str] = set()
    for key in odds_lookup:
        verified_keys.add(key)
    for key in multi_odds:
        verified_keys.add(key)
    for key in analysis_pool:
        verified_keys.add(key)
    # Also use API-sourced fixture keys as verification (different name normalization
    # might cause scan items to not directly match fixtures, but fuzzy-matching
    # against known API fixtures is a valid verification)
    for key in fixture_keys:
        verified_keys.add(key)

    for match_key, scan_items in scan_lookup.items():
        # Skip if already a fixture
        if match_key in fixture_keys:
            continue

        # Check if any item has odds (meaning this event is bettable)
        best_item = None
        best_odds_count = 0
        for item in scan_items:
            odds_count = len(item.get("odds", []))
            if odds_count > best_odds_count:
                best_odds_count = odds_count
                best_item = item
            elif not best_item:
                best_item = item

        if best_item and best_item.get("home") and best_item.get("away"):
            home = best_item["home"]
            away = best_item["away"]

            # CROSS-VERIFICATION GATE: only promote scan items that are
            # independently verified by an API source OR have an explicit date
            item_date = best_item.get("date", "")
            has_explicit_date = bool(item_date and item_date.startswith(date))
            is_cross_verified = match_key in verified_keys

            # Also check reversed key (home/away might be swapped)
            parts = match_key.split("|", 1)
            if not is_cross_verified and len(parts) == 2:
                reversed_key = f"{parts[1]}|{parts[0]}"
                is_cross_verified = reversed_key in verified_keys

            # Fuzzy cross-verification: check if any verified key has BOTH teams
            # matching (not just one). Require minimum token length of 5 to avoid
            # false positives on short names.
            if not is_cross_verified:
                norm_home = parts[0] if len(parts) == 2 else ""
                norm_away = parts[1] if len(parts) == 2 else ""
                if norm_home and norm_away and len(norm_home) >= 5 and len(norm_away) >= 5:
                    for vkey in verified_keys:
                        vparts = vkey.split("|", 1)
                        if len(vparts) != 2:
                            continue
                        # Require BOTH teams to match (home↔home AND away↔away, or swapped)
                        home_match_h = (norm_home == vparts[0] or
                                        (len(norm_home) >= 6 and len(vparts[0]) >= 6 and
                                         (norm_home in vparts[0] or vparts[0] in norm_home)))
                        away_match_a = (norm_away == vparts[1] or
                                        (len(norm_away) >= 6 and len(vparts[1]) >= 6 and
                                         (norm_away in vparts[1] or vparts[1] in norm_away)))
                        if home_match_h and away_match_a:
                            is_cross_verified = True
                            break
                        # Swapped check
                        home_match_a = (norm_home == vparts[1] or
                                        (len(norm_home) >= 6 and len(vparts[1]) >= 6 and
                                         (norm_home in vparts[1] or vparts[1] in norm_home)))
                        away_match_h = (norm_away == vparts[0] or
                                        (len(norm_away) >= 6 and len(vparts[0]) >= 6 and
                                         (norm_away in vparts[0] or vparts[0] in norm_away)))
                        if home_match_a and away_match_h:
                            is_cross_verified = True
                            break

            if not has_explicit_date and not is_cross_verified:
                # STATS-FIRST MODE: When the scan was run explicitly for this date,
                # trust scan events even without cross-verification. The scan already
                # filtered by date. Without this, events from sports without fixture
                # APIs (tennis) or minor leagues are lost entirely.
                if not stats_first:
                    scan_rejected_no_verification += 1
                    continue

            # Most garbage already filtered by _is_scan_garbage in load_scan_summary.
            # Additional regex checks for edge cases that slipped through:
            if _normalize(home) == _normalize(away):
                continue
            combined = f"{home} {away}".lower()
            # Reject entries with embedded odds/scores (e.g. "37 ' Chelsea 1.68 3.75")
            if re.search(r"\d+\.\d{2}\s+\d+\.\d{2}", combined):
                continue
            # Reject entries with match minute markers (e.g. "37  '")
            if re.search(r"\d+\s*'", combined):
                continue
            # Reject section header blobs: " : " followed by time pattern
            if re.search(r" : .+\d{1,2}:\d{2}", home) or re.search(r" : .+\d{1,2}:\d{2}", away):
                continue
            # Skip items where "home" is actually a league/tip label
            if home.startswith(("HOLANDIA:", "FINLANDIA:", "IZRAEL:", "Liga ")):
                continue
            # Reject items with future dates embedded in name (e.g. "10/05/2026")
            if re.search(r"\d{2}/\d{2}/\d{4}", combined):
                continue
            # Reject items where away field is a date (OddsPortal parsing bug)
            if re.match(r"^\d{2}/\d{2}/\d{4}$", away.strip()):
                continue
            # Additional patterns not in the pre-filter
            extra_skip = ["bet $", "get $", "code ", "odds &", "opening odds",
                          "season has", "analysis link", "confidence level",
                          "line-ups", "head-to-head", "win tips", "correct score",
                          "handicap tips", "shots tips", "behind tips",
                          "#", "pln za", "transmisja", "gdzie oglądać", "stream",
                          "add the team", "previous match day",
                          "there are no ", " / ", "✅", "❌"]
            if any(pat in combined for pat in extra_skip):
                continue

            # Use explicit date if available, otherwise use time with betting date
            # (only reached for cross-verified items)
            item_time = best_item.get("time", "")
            if has_explicit_date:
                kickoff_value = _normalize_kickoff(item_date, date)
            elif item_time:
                kickoff_value = _normalize_kickoff(item_time, date)
            else:
                kickoff_value = f"{date}T00:00:00+02:00"

            fixture = {
                "sport": best_item.get("sport", "football"),
                "home_team": home,
                "away_team": away,
                "competition": best_item.get("league", ""),
                "kickoff": kickoff_value,
                "source": "scan-expansion",
            }
            # Skip removed sports
            if fixture["sport"] not in _ALLOWED_SPORTS:
                continue
            fixtures.append(fixture)
            fixture_keys.add(match_key)
            scan_only_events += 1

    if scan_rejected_no_verification:
        print(f"[matrix] Scan-expansion: rejected {scan_rejected_no_verification} items (no cross-verification)")

    # Also add Odds API events not in fixtures
    odds_only_events = 0
    for okey, oev in odds_lookup.items():
        if okey not in fixture_keys:
            home = oev.get("home_team", "")
            away = oev.get("away_team", "")
            if home and away:
                sport = _sport_from_odds_key(oev.get("sport_key", ""))
                if sport not in _ALLOWED_SPORTS:
                    continue
                fixture = {
                    "sport": sport,
                    "home_team": home,
                    "away_team": away,
                    "competition": oev.get("sport_title", ""),
                    "kickoff": oev.get("commence_time", ""),
                    "source": "odds-api-expansion",
                }
                fixtures.append(fixture)
                fixture_keys.add(okey)
                odds_only_events += 1

    print(f"[matrix] Scan-only events added: {scan_only_events}")
    print(f"[matrix] Odds-API-only events added: {odds_only_events}")
    print(f"[matrix] Total events after expansion: {len(fixtures)}")

    events = []
    sport_counts = defaultdict(int)
    market_type_counts = defaultdict(int)

    # Pre-gate phantom check: filter already-played events
    # Only filter events whose kickoff date doesn't match the target date
    # AND the kickoff is >2h in the past (defense against phantom fixtures)
    now_utc = datetime.now(timezone.utc)
    already_played_count = 0

    for fixture in fixtures:
        sport = fixture.get("sport", "football")
        if sport not in _ALLOWED_SPORTS:
            continue
        home = fixture.get("home_team", fixture.get("home", ""))
        away = fixture.get("away_team", fixture.get("away", ""))
        competition = fixture.get("competition", fixture.get("league", ""))
        kickoff = _normalize_kickoff(
            fixture.get("kickoff", fixture.get("date", "")), date
        )
        source = fixture.get("source", "")

        if not home or not away:
            continue

        # PHANTOM/ALREADY-PLAYED FILTER: skip events that have already started
        # An event is considered "phantom" if its kickoff date doesn't match the target
        # betting date (prevents future matchdays leaking in from league schedule pages)
        # OR if its kickoff is >2h in the past on the target date
        if kickoff:
            ko_date_str = None
            ko_dt = None
            try:
                # Normalize kickoff to parseable format
                ko_raw = kickoff.replace("Z", "+00:00")
                if "T" not in ko_raw and " " in ko_raw:
                    ko_raw = ko_raw.replace(" ", "T", 1)
                if "T" in ko_raw:
                    ko_dt = datetime.fromisoformat(ko_raw)
                    if ko_dt.tzinfo is None:
                        ko_dt = ko_dt.replace(tzinfo=timezone(timedelta(hours=2)))
                    ko_date_str = ko_dt.strftime("%Y-%m-%d")
                elif len(ko_raw) >= 10:
                    # Date-only format like "2026-05-06"
                    ko_date_str = ko_raw[:10]
            except (ValueError, TypeError, IndexError):
                pass

            if ko_date_str:
                # Strict date filter: only include events ON the target date
                if ko_date_str != date:
                    already_played_count += 1
                    continue
                # Also reject events >2h in the past on the same date
                if ko_dt:
                    elapsed_hours = (now_utc - ko_dt.astimezone(timezone.utc)).total_seconds() / 3600
                    if elapsed_hours > 2:
                        already_played_count += 1
                        continue

        # Evening filter
        if evening_only and kickoff:
            try:
                hour = int(kickoff.split("T")[1].split(":")[0]) if "T" in kickoff else 0
                if hour < 17:
                    continue
            except (IndexError, ValueError):
                pass

        norm_home = _normalize(home)
        norm_away = _normalize(away)
        match_key = f"{norm_home}|{norm_away}"

        # Collect ALL available markets from ALL sources
        all_markets = []

        # 1. Odds API markets
        odds_event = _fuzzy_match(match_key, odds_lookup)
        if odds_event:
            api_markets = extract_markets_from_odds_api(odds_event)
            all_markets.extend(api_markets)

        # 2. Multi-source odds
        multi_event = _fuzzy_match(match_key, multi_odds)
        if multi_event:
            best_odds = multi_event.get("best_odds", {})
            for mkt_key, mkt_data in best_odds.items():
                if isinstance(mkt_data, dict):
                    all_markets.append({
                        "market": mkt_key,
                        "market_type": "multi",
                        "outcome": mkt_key,
                        "point": None,
                        "best_odds": mkt_data.get("price", 0),
                        "best_bookmaker": mkt_data.get("bookmaker", ""),
                        "source": "multi-source",
                    })

        # 3. Scan summary data
        scan_items = _fuzzy_match(match_key, scan_lookup)
        if scan_items and isinstance(scan_items, list):
            scan_markets = extract_markets_from_scan(scan_items)
            all_markets.extend(scan_markets)

        # 4. Safety analysis from cache (deep stats when available)
        safety_result = try_safety_analysis(sport, home, away, competition)
        safety_markets = []
        if safety_result:
            for mkt in safety_result.get("ranking", []):
                safety_markets.append({
                    "market": f"{mkt['name']} {mkt.get('line', '')}",
                    "market_type": "safety_ranked",
                    "direction": mkt.get("direction", ""),
                    "safety_score": mkt.get("safety_score", 0),
                    "l10_avg": mkt.get("combined_avg"),
                    "h2h_avg": mkt.get("h2h_avg"),
                    "hit_rate_l10": mkt.get("hit_rate_l10"),
                    "hit_rate_h2h": mkt.get("hit_rate_h2h"),
                    "margin": mkt.get("margin"),
                    "h2h_blind": mkt.get("h2h_blind", False),
                    "source": "stats_cache",
                })

        # 5. Check picks_suggested for pre-computed suggestions
        suggested = _fuzzy_match_single(match_key, picks_suggested)
        suggested_info = None
        if suggested:
            suggested_info = {
                "suggested_pick": suggested.get("pick", ""),
                "suggested_odds": suggested.get("odds", 0),
                "source_count": suggested.get("source_count", 0),
            }

        # 6. Analysis pool deep data
        pool_event = _fuzzy_match(match_key, analysis_pool)
        pool_markets = []
        if pool_event:
            for pmkt in pool_event.get("all_markets", []):
                pool_markets.append({
                    "market": pmkt.get("name", ""),
                    "market_type": "analysis_pool",
                    "direction": pmkt.get("direction", ""),
                    "safety_score": pmkt.get("safety", 0),
                    "l10_avg": pmkt.get("l10_avg"),
                    "h2h_avg": pmkt.get("h2h_avg"),
                    "source": "analysis_pool",
                })

        # 7. Scores24 deep data (H2H, form, odds, trends from detail pages)
        scores24_data = _extract_scores24_deep_data(match_key, scan_lookup)
        if scores24_data:
            # Add scores24 odds as additional market entries
            for s24_mkt in scores24_data.get("odds_markets", []):
                all_markets.append(s24_mkt)
            # Add scores24 trend-based market hints
            for s24_trend in scores24_data.get("trend_markets", []):
                safety_markets.append(s24_trend)

        # Determine data richness
        has_odds = bool(all_markets)
        has_safety = bool(safety_markets or pool_markets)
        # scores24 H2H/form data counts as partial safety context
        has_scores24_context = bool(
            scores24_data
            and (scores24_data.get("h2h") or scores24_data.get("form"))
        )
        if has_scores24_context and not has_safety:
            has_safety = True
        has_multiple_sources = len(set(m.get("source", "") for m in all_markets)) > 1

        if has_safety and has_odds:
            data_tier = "FULL"
        elif has_odds and has_multiple_sources:
            data_tier = "ODDS_RICH"
        elif has_odds:
            data_tier = "ODDS_BASIC"
        elif has_safety:
            data_tier = "STATS_ONLY"
        else:
            data_tier = "FIXTURE_ONLY"

        sport_counts[sport] += 1

        for m in all_markets:
            mt = m.get("market_type", "unknown")
            market_type_counts[mt] += 1

        event = {
            "sport": sport,
            "competition": competition,
            "home_team": home,
            "away_team": away,
            "kickoff": kickoff,
            "data_tier": data_tier,
            "fixture_source": source,
            "odds_markets": all_markets,
            "safety_markets": safety_markets + pool_markets,
            "suggested": suggested_info,
            "total_markets_available": len(all_markets) + len(safety_markets) + len(pool_markets),
        }
        # Attach scores24 deep context when available (H2H, form, trends)
        if scores24_data:
            if scores24_data.get("h2h"):
                event["scores24_h2h"] = scores24_data["h2h"]
            if scores24_data.get("form"):
                event["scores24_form"] = scores24_data["form"]
        events.append(event)

    if already_played_count:
        print(f"[matrix] Filtered {already_played_count} already-played events (kickoff >2h ago)")

    # Deduplicate events: same teams in same sport = likely same event
    # Pass 1: exact normalized matching with merge
    deduped_events = []
    seen_matchups: set[str] = set()
    for event in events:
        h = _normalize(event.get("home_team", "")).lower()
        a = _normalize(event.get("away_team", "")).lower()
        sport = event.get("sport", "")
        dedup_key = f"{sport}|{h}|{a}"
        dedup_key_rev = f"{sport}|{a}|{h}"
        if dedup_key in seen_matchups or dedup_key_rev in seen_matchups:
            # Merge odds/safety from duplicate into the kept event
            for kept in deduped_events:
                kh = _normalize(kept.get("home_team", "")).lower()
                ka = _normalize(kept.get("away_team", "")).lower()
                if kept["sport"] == sport and ((kh == h and ka == a) or (kh == a and ka == h)):
                    # Merge odds markets (avoid duplicates by source)
                    existing_keys = {(m.get("market", ""), m.get("source", "")) for m in kept.get("odds_markets", [])}
                    for m in event.get("odds_markets", []):
                        mk = (m.get("market", ""), m.get("source", ""))
                        if mk not in existing_keys:
                            kept["odds_markets"].append(m)
                            existing_keys.add(mk)
                    # Merge safety markets
                    for m in event.get("safety_markets", []):
                        kept["safety_markets"].append(m)
                    # Use the better competition name
                    if not kept.get("competition") and event.get("competition"):
                        kept["competition"] = event["competition"]
                    # Upgrade data tier if the duplicate has better data
                    tier_priority = {"FULL": 0, "ODDS_RICH": 1, "ODDS_BASIC": 2, "STATS_ONLY": 3, "FIXTURE_ONLY": 4}
                    if tier_priority.get(event["data_tier"], 5) < tier_priority.get(kept["data_tier"], 5):
                        kept["data_tier"] = event["data_tier"]
                    kept["total_markets_available"] = (
                        len(kept.get("odds_markets", [])) + len(kept.get("safety_markets", []))
                    )
                    break
            continue
        seen_matchups.add(dedup_key)
        deduped_events.append(event)

    n_exact_deduped = len(events) - len(deduped_events)

    # Pass 2: fuzzy dedup using is_same_event (catches "Dnipro" vs "Dnipro-1", "FK Ventspils" vs "Ventspils")
    fuzzy_deduped = []
    fuzzy_removed = 0
    for event in deduped_events:
        h = event.get("home_team", "")
        a = event.get("away_team", "")
        sport = event.get("sport", "")
        is_fuzzy_dup = False
        for existing in fuzzy_deduped:
            if existing.get("sport", "") != sport:
                continue
            if is_same_event(h, a, existing.get("home_team", ""), existing.get("away_team", "")):
                is_fuzzy_dup = True
                break
        if is_fuzzy_dup:
            fuzzy_removed += 1
            continue
        fuzzy_deduped.append(event)

    total_deduped = n_exact_deduped + fuzzy_removed
    if total_deduped:
        print(f"[matrix] Deduplicated {total_deduped} events ({len(events)} → {len(fuzzy_deduped)}) "
              f"[exact: {n_exact_deduped}, fuzzy: {fuzzy_removed}]")
    events = fuzzy_deduped

    # Sort: FULL first, then ODDS_RICH, then by sport
    tier_order = {"FULL": 0, "ODDS_RICH": 1, "ODDS_BASIC": 2, "STATS_ONLY": 3, "FIXTURE_ONLY": 4}
    events.sort(key=lambda e: (tier_order.get(e["data_tier"], 5), e.get("sport") or "", e.get("competition") or ""))

    matrix = {
        "date": date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_fixtures": len(fixtures),
        "total_events_in_matrix": len(events),
        "events_with_odds": sum(1 for e in events if e["odds_markets"]),
        "events_with_safety_data": sum(
            1 for e in events
            if e["safety_markets"] or e.get("scores24_h2h") or e.get("scores24_form")
        ),
        "sport_breakdown": dict(sport_counts),
        "market_type_counts": dict(market_type_counts),
        "data_tier_breakdown": {
            tier: sum(1 for e in events if e["data_tier"] == tier)
            for tier in ["FULL", "ODDS_RICH", "ODDS_BASIC", "STATS_ONLY", "FIXTURE_ONLY"]
        },
        "events": events,
    }

    return matrix


def _fuzzy_match(key: str, lookup: dict):
    """Fuzzy match a key against a lookup dict.

    Performance: uses prefix index for O(1) exact match, falls back to
    substring scan only for small lookups (≤500 keys).
    """
    if key in lookup:
        return lookup[key]
    # For large lookups (scan_summary with 25K+ keys), skip expensive substring scan
    # — the exact match above covers 95%+ of real matches after normalization
    if len(lookup) > 500:
        return None
    # Try substring matching only for small lookups (odds, multi-source)
    parts = key.split("|")
    if len(parts) != 2:
        return None
    home, away = parts
    for lk, lv in lookup.items():
        lparts = lk.split("|")
        if len(lparts) != 2:
            continue
        lhome, laway = lparts
        if names_match(home, lhome, threshold=70) >= 70 and names_match(away, laway, threshold=70) >= 70:
            return lv
    return None


def _fuzzy_match_single(key: str, lookup: dict):
    """Fuzzy match for picks_suggested which uses space-separated keys."""
    # Try direct
    for lk, lv in lookup.items():
        norm_lk = lk.replace(" - ", "|").replace(" vs ", "|")
        if _normalize(norm_lk) == key or key in norm_lk or norm_lk in key:
            return lv
    return None


# ---------------------------------------------------------------------------
# Markdown output
# ---------------------------------------------------------------------------

def write_matrix_markdown(matrix: dict, date: str) -> Path:
    """Write human-readable market matrix."""
    lines = []
    lines.append(f"# 📊 Market Matrix — {date}")
    lines.append(f"Generated: {matrix['generated_at']}")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- Total fixtures discovered: **{matrix['total_fixtures']}**")
    lines.append(f"- Events in matrix: **{matrix['total_events_in_matrix']}**")
    lines.append(f"- Events WITH odds: **{matrix['events_with_odds']}**")
    lines.append(f"- Events with safety data: **{matrix['events_with_safety_data']}**")
    lines.append("")

    lines.append("### Sport Breakdown")
    lines.append("| Sport | Count |")
    lines.append("|-------|-------|")
    for sport, count in sorted(matrix["sport_breakdown"].items(), key=lambda x: -x[1]):
        lines.append(f"| {sport} | {count} |")
    lines.append("")

    lines.append("### Data Tier Breakdown")
    lines.append("| Tier | Count | Description |")
    lines.append("|------|-------|-------------|")
    tier_desc = {
        "FULL": "Odds + Safety stats + H2H",
        "ODDS_RICH": "Odds from multiple sources",
        "ODDS_BASIC": "Odds from single source",
        "STATS_ONLY": "Safety stats but no odds",
        "FIXTURE_ONLY": "Fixture discovered, no odds/stats yet",
    }
    for tier in ["FULL", "ODDS_RICH", "ODDS_BASIC", "STATS_ONLY", "FIXTURE_ONLY"]:
        count = matrix["data_tier_breakdown"].get(tier, 0)
        lines.append(f"| {tier} | {count} | {tier_desc.get(tier, '')} |")
    lines.append("")

    # Group events by sport
    by_sport = defaultdict(list)
    for event in matrix["events"]:
        by_sport[event["sport"]].append(event)

    lines.append("---")
    lines.append("")

    for sport in sorted(by_sport.keys()):
        sport_events = by_sport[sport]
        lines.append(f"## {sport.upper()} ({len(sport_events)} events)")
        lines.append("")

        for event in sport_events:
            home = event["home_team"]
            away = event["away_team"]
            comp = event["competition"]
            kickoff = event["kickoff"]
            tier = event["data_tier"]
            total_mkts = event["total_markets_available"]

            tier_emoji = {
                "FULL": "🟢", "ODDS_RICH": "🔵", "ODDS_BASIC": "🟡",
                "STATS_ONLY": "🟠", "FIXTURE_ONLY": "⚪"
            }

            lines.append(f"### {tier_emoji.get(tier, '⚪')} {home} vs {away}")
            lines.append(f"**{comp}** | {kickoff} | Tier: {tier} | Markets: {total_mkts}")
            lines.append("")

            # Odds markets table
            if event["odds_markets"]:
                lines.append("| Market | Odds | Bookmaker | Source |")
                lines.append("|--------|------|-----------|--------|")
                for mkt in event["odds_markets"]:
                    lines.append(
                        f"| {mkt['market']} | {mkt['best_odds']} | "
                        f"{mkt['best_bookmaker']} | {mkt['source']} |"
                    )
                lines.append("")

            # Safety markets table
            if event["safety_markets"]:
                lines.append("| Market | Direction | Safety | L10 avg | H2H avg | Hit L10 | Hit H2H | H2H Blind |")
                lines.append("|--------|-----------|--------|---------|---------|---------|---------|-----------|")
                for mkt in event["safety_markets"]:
                    h2h_avg = mkt.get("h2h_avg", "N/A")
                    lines.append(
                        f"| {mkt['market']} | {mkt.get('direction', '—')} | "
                        f"{mkt.get('safety_score', '—')} | {mkt.get('l10_avg', '—')} | "
                        f"{h2h_avg} | {mkt.get('hit_rate_l10', '—')} | "
                        f"{mkt.get('hit_rate_h2h', '—')} | "
                        f"{'YES' if mkt.get('h2h_blind') else 'NO'} |"
                    )
                lines.append("")

            if event.get("suggested"):
                s = event["suggested"]
                lines.append(
                    f"> 💡 Suggested: **{s['suggested_pick']}** @ {s['suggested_odds']} "
                    f"(sources: {s['source_count']})"
                )
                lines.append("")

            lines.append("---")
            lines.append("")

    md_text = "\n".join(lines)
    output_path = DATA_DIR / f"market_matrix_{date}.md"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md_text, encoding="utf-8")
    print(f"[matrix] Markdown: {output_path}")
    return output_path


def write_matrix_json(matrix: dict, date: str) -> Path:
    """Write matrix JSON."""
    output_path = DATA_DIR / f"market_matrix_{date}.json"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(matrix, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[matrix] JSON: {output_path} ({matrix['total_events_in_matrix']} events)")
    return output_path


def persist_matrix_to_db(matrix: dict, date: str) -> int:
    """Persist market matrix events to DB (R2 DB-first).

    Resolves fixture_ids for each event, then bulk-inserts into market_matrix_events.
    Returns count of events persisted.
    """
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import MarketMatrixRepo

        events = matrix.get("events", [])
        if not events:
            return 0

        with get_db() as conn:
            repo = MarketMatrixRepo(conn)

            # Resolve fixture_ids
            resolved = []
            for ev in events:
                home = ev.get("home_team", "")
                away = ev.get("away_team", "")
                sport = ev.get("sport", "")
                kickoff = ev.get("kickoff", "")

                # Try to find existing fixture
                row = conn.execute(
                    "SELECT id FROM fixtures WHERE sport=? AND home_team=? AND away_team=? AND betting_date=?",
                    (sport, home, away, date),
                ).fetchone()

                if row:
                    fixture_id = row["id"]
                else:
                    # Create minimal fixture
                    cursor = conn.execute(
                        "INSERT INTO fixtures (sport, home_team, away_team, kickoff, betting_date) VALUES (?, ?, ?, ?, ?)",
                        (sport, home, away, kickoff, date),
                    )
                    fixture_id = cursor.lastrowid

                ev_copy = dict(ev)
                ev_copy["fixture_id"] = fixture_id
                resolved.append(ev_copy)

            saved = repo.save_events(date, resolved)

            # Save run metadata
            meta = {
                "total_fixtures": matrix.get("total_fixtures", 0),
                "total_events_in_matrix": matrix.get("total_events_in_matrix", 0),
                "events_with_odds": matrix.get("events_with_odds", 0),
                "events_with_safety_data": matrix.get("events_with_safety_data", 0),
                "sport_breakdown": matrix.get("sport_breakdown", {}),
                "market_type_counts": matrix.get("market_type_counts", {}),
                "data_tier_breakdown": matrix.get("data_tier_breakdown", {}),
            }
            repo.save_run(date, meta)

            print(f"[matrix] DB: persisted {saved}/{len(events)} events to market_matrix_events")
            return saved
    except Exception as e:
        print(f"[matrix] ⚠ DB persistence failed: {e}")
        return 0


# ---------------------------------------------------------------------------
# Compact decision matrix for coupon building
# ---------------------------------------------------------------------------

from bet.stats.market_ranking import STANDARD_MARKET_LINES

# Major competitions where Betclic is likely to offer statistical markets
MAJOR_COMPETITIONS = {
    "football": [
        "uefa", "champions", "europa", "conference", "premier", "la liga", "laliga",
        "bundesliga", "serie a", "ligue 1", "eredivisie", "ekstraklasa",
        "primeira", "super lig", "mls", "copa libertadores", "copa sudamericana",
        "championship", "2. bundesliga", "serie b", "ligue 2", "segunda",
        "liga mx", "k-league", "j-league", "a-league", "brasileirao",
        "world cup", "nations league", "qualification", "friendly",
        "copa america", "euro 202", "euro 2", "club world cup", "fa cup",
        "coppa italia", "coupe de france", "dfb pokal", "copa del rey",
        "super cup", "community shield", "carabao", "league cup",
        "allsvenskan", "eliteserien", "superliga", "swiss super league",
        "scottish", "belgian", "jupiler", "pro league",
        # §SCAN.9 — Protected domestic leagues (Americas, Asia, Africa)
        "brasileirão", "brazil serie a", "brazil serie b", "copa do brasil",
        "liga profesional", "primera division argentina", "primera nacional",
        "liga betplay", "primera a colombia", "primera division chile",
        "liga de expansion", "usl championship", "nwsl", "mls next pro",
        "chinese super league", "csl", "cfa super", "china",
        "j1 league", "j2 league", "j1", "j2",
        "k league", "k1", "k2",
        "saudi pro league", "spl", "roshn", "saudi arabia",
        "indian super league", "isl", "india",
        "egyptian premier", "south african psl", "egypt", "south africa",
        "primera a", "colombia",
        # Lower divisions expanded
        "3. liga", "serie c", "serie d", "national league", "league two",
        "regionalliga", "division 1", "premier league 2", "primera federacion",
        "national", "2. division", "postnord", "obos", "ykkonen", "1. deild",
        "fnl", "2. liga", "nike liga", "prva liga", "first nl", "nb ii",
        "super league 2", "challenger pro league", "eerste divisie", "1. lig",
        "liga 1", "thai league", "v.league", "persian gulf",
    ],
    "tennis": [
        "atp", "wta", "grand slam", "masters", "open", "500", "250", "1000",
        "australian", "french", "wimbledon", "us open", "roland garros",
        "indian wells", "miami", "monte carlo", "madrid", "rome", "roma",
        "canada", "cincinnati", "shanghai", "paris", "beijing",
        "challenger", "itf", "futures", "billie jean king", "laver cup",
        "olympics", "next gen",
    ],
    "basketball": [
        "nba", "euroleague", "eurocup", "acb", "bbl", "nbl", "bsl", "lnb",
        "serie a", "plk", "bcl", "fiba", "ncaa", "playoff", "finals",
        "world cup", "olympic",
        # §SCAN.9 — Protected domestic leagues
        "cba", "nbb", "b.league", "kbl", "pba", "nbl australia", "lnbp",
        # Expanded
        "g-league", "summer league", "wnba", "wbbl", "ncaa women",
        "basket liga", "pro a", "pro b", "bkt", "a1 ethniki",
        "premijer liga", "adriatic league", "aba league", "copa del rey",
        "lkl", "vtb",
    ],
    "volleyball": [
        "plusliga", "superlega", "ligue a", "bundesliga", "cev", "champions",
        "serie a", "efeler", "superliga", "nations league", "world championship",
        "playoff", "olympic",
        # Expanded
        "serie a2", "a1 ethniki", "eredivisie", "euromillions", "division 1",
        "1st division", "mestaruusliiga", "v-league", "super league",
        "liga a1",
    ],
    "hockey": ["nhl", "khl", "shl", "liiga", "del", "nla", "extraliga", "iihf",
               "playoff", "stanley cup", "world championship",
               # Expanded
               "echl", "eihl", "ligue magnus", "erste liga", "mestis",
               "hockeyallsvenskan", "1. liga", "tipsport liga",
               "metal ligaen", "optibet liga", "allsvenskan"],
}


def _is_major_competition(sport: str, competition: str) -> bool:
    """Check if a competition is considered major for Betclic availability."""
    if not competition:
        return False
    # Normalize: remove ' - ' separators to handle URL-derived names
    comp_lower = competition.lower().replace(" - ", " ").replace("  ", " ")
    keywords = MAJOR_COMPETITIONS.get(sport, [])
    return any(kw in comp_lower for kw in keywords)


def generate_decision_matrix(
    matrix: dict, min_odds: float = 1.20, max_odds: float = 5.0,
    stats_first: bool = False,
) -> list[dict]:
    """Generate a compact decision matrix from the full market matrix.

    Returns a list of bettable opportunities (event + market combinations)
    sorted by data quality and odds attractiveness.

    When stats_first=True, includes ALL events from major competitions with
    suggested statistical markets, even without odds. User checks Betclic manually.
    """
    opportunities = []

    for event in matrix["events"]:
        sport = event["sport"]
        home = event["home_team"]
        away = event["away_team"]
        comp = event["competition"]
        kickoff = event["kickoff"]
        tier = event["data_tier"]

        # Each odds market = one opportunity
        for mkt in event.get("odds_markets", []):
            odds = mkt.get("best_odds", 0)
            if not (min_odds <= odds <= max_odds):
                continue

            # Find matching safety data if available
            safety_data = None
            for sm in event.get("safety_markets", []):
                sm_name = sm.get("market", "").lower()
                mkt_name = mkt.get("market", "").lower()
                if any(word in sm_name for word in mkt_name.split()):
                    safety_data = sm
                    break

            opp = {
                "sport": sport,
                "competition": comp,
                "event": f"{home} vs {away}",
                "home_team": home,
                "away_team": away,
                "kickoff": kickoff,
                "market": mkt["market"],
                "market_type": mkt["market_type"],
                "odds": odds,
                "bookmaker": mkt["best_bookmaker"],
                "data_tier": tier,
                "safety_score": safety_data["safety_score"] if safety_data else None,
                "l10_avg": safety_data.get("l10_avg") if safety_data else None,
                "h2h_avg": safety_data.get("h2h_avg") if safety_data else None,
                "direction": safety_data.get("direction") if safety_data else None,
                "odds_source": "api",
            }
            opportunities.append(opp)

        # Safety-only markets (no odds yet — user checks Betclic)
        for sm in event.get("safety_markets", []):
            if sm.get("safety_score", 0) >= 0.50:
                opp = {
                    "sport": sport,
                    "competition": comp,
                    "event": f"{home} vs {away}",
                    "home_team": home,
                    "away_team": away,
                    "kickoff": kickoff,
                    "market": sm["market"],
                    "market_type": "safety_ranked",
                    "odds": None,
                    "bookmaker": "CHECK_BETCLIC",
                    "data_tier": tier,
                    "safety_score": sm.get("safety_score"),
                    "l10_avg": sm.get("l10_avg"),
                    "h2h_avg": sm.get("h2h_avg"),
                    "direction": sm.get("direction"),
                    "odds_source": "none",
                }
                opportunities.append(opp)

        # STATS_FIRST MODE: add suggested markets for events without odds
        # in major competitions — user will check Betclic manually.
        # Also add for events that HAVE h2h/ML odds but are MISSING
        # statistical market odds (e.g., football with 1X2 but no corners).
        if stats_first and _is_major_competition(sport, comp):
            has_stat_odds = any(
                m.get("market_type") not in ("h2h", "multi", "scan")
                and m.get("market", "").lower() not in (
                    "1x2:home", "1x2:draw", "1x2:away",
                    "ml:home", "ml:away",
                    "h2h:home", "h2h:away",
                )
                for m in event.get("odds_markets", [])
            )
            if not has_stat_odds:
                std_markets = STANDARD_MARKET_LINES.get(sport, [])
                for std_mkt in std_markets:
                    lines = std_mkt["lines"]
                    is_combined = std_mkt.get("is_combined", True)
                    stat_key = std_mkt["stat"]

                    # Dynamic line selection: use team averages from safety_markets
                    # or event-level stats to pick the closest standard line
                    calibrated_line = None
                    team_avg = None
                    for sm in event.get("safety_markets", []):
                        sm_stat = sm.get("stat_key", "")
                        if sm_stat == stat_key or stat_key in sm.get("market", "").lower():
                            l10_avg = sm.get("l10_avg")
                            if l10_avg is not None:
                                team_avg = l10_avg
                                break

                    if team_avg is not None:
                        # For combined markets, team_avg is already the match total
                        # For team-level markets (is_combined=False), team_avg is
                        # per-team so use it directly against team-level lines
                        # Pick the standard line closest to the average
                        calibrated_line = min(lines, key=lambda l: abs(l - team_avg))
                    else:
                        # Fallback: static middle line
                        calibrated_line = lines[len(lines) // 2]

                    opp = {
                        "sport": sport,
                        "competition": comp,
                        "event": f"{home} vs {away}",
                        "home_team": home,
                        "away_team": away,
                        "kickoff": kickoff,
                        "market": f"{std_mkt['market']} O/U {calibrated_line}",
                        "market_type": "stats_first_suggestion",
                        "odds": None,
                        "bookmaker": "CHECK_BETCLIC",
                        "data_tier": tier,
                        "safety_score": None,
                        "l10_avg": team_avg,
                        "h2h_avg": None,
                        "direction": None,
                        "suggested_lines": lines,
                        "stat_key": stat_key,
                        "is_combined": is_combined,
                        "calibrated_from_avg": team_avg is not None,
                        "odds_source": "none",
                    }
                    opportunities.append(opp)

    # Sort by: safety_score (desc, Nones last), then odds
    opportunities.sort(
        key=lambda o: (
            -(o["safety_score"] or 0),
            o["odds"] or 999,
        )
    )

    return opportunities


def write_decision_matrix_md(opportunities: list[dict], date: str, stats_first: bool = False) -> Path:
    """Write compact decision matrix markdown."""
    lines = []
    lines.append(f"# 🎯 Decision Matrix — {date}")
    lines.append(f"Total bettable opportunities: **{len(opportunities)}**")
    lines.append("")

    # Split into odds-available and check-betclic
    with_odds = [o for o in opportunities if o.get("odds")]
    check_betclic = [o for o in opportunities if not o.get("odds")]

    lines.append(f"- With API odds: **{len(with_odds)}**")
    lines.append(f"- CHECK_BETCLIC (manual odds check): **{len(check_betclic)}**")
    lines.append("")

    if stats_first:
        lines.append("> 🔬 **STATS-FIRST MODE**: Events without API odds are included with suggested")
        lines.append("> statistical markets. Check Betclic app for odds, then calculate:")
        lines.append("> `EV = (hit_rate × odds) - 1`. If EV > 0 → bet.")
        lines.append("")

    lines.append("> ⚠️ ALL picks shown — no auto-rejection. User decides.")
    lines.append("")

    # --- Section 1: Events WITH odds ---
    if with_odds:
        lines.append("---")
        lines.append("## 📊 SECTION A: Events WITH Odds")
        lines.append("")
        by_sport = defaultdict(list)
        for opp in with_odds:
            by_sport[opp["sport"]].append(opp)

        for sport in sorted(by_sport.keys()):
            sport_opps = by_sport[sport]
            lines.append(f"### {sport.upper()} ({len(sport_opps)} opportunities)")
            lines.append("")
            lines.append(
                "| # | Event | Competition | Market | Odds | Safety | L10 | H2H | Dir | Tier |"
            )
            lines.append(
                "|---|-------|-------------|--------|------|--------|-----|-----|-----|------|"
            )
            for i, opp in enumerate(sport_opps, 1):
                odds_str = f"{opp['odds']:.2f}" if opp["odds"] else "CHECK"
                safety_str = f"{opp['safety_score']:.2f}" if opp["safety_score"] else "—"
                l10_str = f"{opp['l10_avg']}" if opp["l10_avg"] is not None else "—"
                h2h_str = f"{opp['h2h_avg']}" if opp["h2h_avg"] is not None else "—"
                dir_str = opp["direction"] or "—"
                lines.append(
                    f"| {i} | {opp['event']} | {opp['competition']} | "
                    f"{opp['market']} | {odds_str} | {safety_str} | "
                    f"{l10_str} | {h2h_str} | {dir_str} | {opp['data_tier']} |"
                )
            lines.append("")

    # --- Section 2: CHECK_BETCLIC events (probability portfolio) ---
    if check_betclic:
        lines.append("---")
        lines.append("## 🎲 SECTION B: PROBABILITY PORTFOLIO — Check Betclic for Odds")
        lines.append("")
        lines.append("> These events have statistical potential but no API odds.")
        lines.append("> **Workflow:** Find the event on Betclic → check if the suggested market exists")
        lines.append("> → note the odds → calculate `EV = (hit_rate × odds) - 1` → if EV > 0, bet.")
        lines.append("")

        # Separate: safety-scored vs suggestions-only
        # Note: safety_score=0.0 is falsy in Python, use explicit None check
        scored = [o for o in check_betclic if o.get("safety_score") is not None and o["safety_score"] > 0]
        suggested = [o for o in check_betclic if o.get("market_type") == "stats_first_suggestion" and o.get("safety_score") is None]

        if scored:
            lines.append("### B1: SAFETY-SCORED (statistical data available)")
            lines.append("")
            lines.append(
                "| # | Event | Competition | Market | Safety | L10 | H2H | Dir | Tier |"
            )
            lines.append(
                "|---|-------|-------------|--------|--------|-----|-----|-----|------|"
            )
            for i, opp in enumerate(scored, 1):
                safety_str = f"{opp['safety_score']:.2f}" if opp["safety_score"] else "—"
                l10_str = f"{opp['l10_avg']}" if opp["l10_avg"] is not None else "—"
                h2h_str = f"{opp['h2h_avg']}" if opp["h2h_avg"] is not None else "—"
                dir_str = opp["direction"] or "—"
                lines.append(
                    f"| {i} | {opp['event']} | {opp['competition']} | "
                    f"{opp['market']} | {safety_str} | "
                    f"{l10_str} | {h2h_str} | {dir_str} | {opp['data_tier']} |"
                )
            lines.append("")

        if suggested:
            # Group by sport, show top events per sport
            by_sport = defaultdict(list)
            for opp in suggested:
                by_sport[opp["sport"]].append(opp)

            lines.append("### B2: MAJOR COMPETITION MARKETS — Needs S3 Deep Analysis")
            lines.append("")
            lines.append("> These events are in major competitions likely available on Betclic.")
            lines.append("> Run S3 deep stats analysis to get safety scores, then check odds.")
            lines.append("")

            for sport in sorted(by_sport.keys()):
                sport_opps = by_sport[sport]
                # Deduplicate by event (show each event once with all markets)
                seen_events = {}
                for opp in sport_opps:
                    ev_key = opp["event"]
                    if ev_key not in seen_events:
                        seen_events[ev_key] = {
                            "event": ev_key,
                            "competition": opp["competition"],
                            "kickoff": opp["kickoff"],
                            "markets": [],
                        }
                    seen_events[ev_key]["markets"].append(opp["market"])

                lines.append(f"#### {sport.upper()} ({len(seen_events)} events)")
                lines.append("")
                lines.append(
                    "| # | Event | Competition | Kickoff | Suggested Markets |"
                )
                lines.append(
                    "|---|-------|-------------|---------|-------------------|"
                )
                for i, (ev_key, ev_data) in enumerate(seen_events.items(), 1):
                    mkts_str = ", ".join(ev_data["markets"][:4])  # show top 4
                    if len(ev_data["markets"]) > 4:
                        mkts_str += f" (+{len(ev_data['markets']) - 4} more)"
                    lines.append(
                        f"| {i} | {ev_data['event']} | {ev_data['competition']} | "
                        f"{ev_data['kickoff']} | {mkts_str} |"
                    )
                lines.append("")

    md_text = "\n".join(lines)
    output_path = DATA_DIR / f"decision_matrix_{date}.md"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md_text, encoding="utf-8")
    print(f"[matrix] Decision matrix: {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate comprehensive market matrix")
    parser.add_argument("--date", help="Date YYYY-MM-DD (default: today)")
    parser.add_argument("--min-odds", type=float, default=1.20, help="Min odds filter")
    parser.add_argument("--max-odds", type=float, default=5.00, help="Max odds filter")
    parser.add_argument("--evening-only", action="store_true", help="Only events after 17:00")
    parser.add_argument(
        "--stats-first", action="store_true",
        help="STATS-FIRST mode: include all major competition events with "
             "suggested statistical markets even without odds. User checks "
             "Betclic for odds manually.",
    )
    args = parser.parse_args()

    date = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        print(f"[matrix] ERROR: Invalid date format '{date}'. Use YYYY-MM-DD.")
        sys.exit(1)

    stats_first = args.stats_first
    if stats_first:
        print(f"[matrix] 🔬 STATS-FIRST MODE — including events without odds")

    print(f"[matrix] Generating market matrix for {date}...")

    matrix = generate_market_matrix(
        date=date,
        min_odds=args.min_odds,
        max_odds=args.max_odds,
        evening_only=args.evening_only,
        stats_first=stats_first,
    )

    write_matrix_json(matrix, date)
    persist_matrix_to_db(matrix, date)
    write_matrix_markdown(matrix, date)

    opportunities = generate_decision_matrix(
        matrix, args.min_odds, args.max_odds, stats_first=stats_first,
    )
    write_decision_matrix_md(opportunities, date, stats_first=stats_first)

    # Print summary
    with_odds = sum(1 for o in opportunities if o.get("odds"))
    check_betclic = sum(1 for o in opportunities if not o.get("odds"))

    print(f"\n{'='*60}")
    print(f"MARKET MATRIX SUMMARY — {date}")
    if stats_first:
        print("🔬 STATS-FIRST MODE ACTIVE")
    print(f"{'='*60}")
    print(f"Total fixtures:          {matrix['total_fixtures']}")
    print(f"Events in matrix:        {matrix['total_events_in_matrix']}")
    print(f"Events with odds:        {matrix['events_with_odds']}")
    print(f"Events with safety data: {matrix['events_with_safety_data']}")
    print(f"Bettable opportunities:  {len(opportunities)}")
    if stats_first:
        print(f"  → With API odds:       {with_odds}")
        print(f"  → CHECK_BETCLIC:       {check_betclic}")
    print(f"\nSport breakdown:")
    for sport, count in sorted(matrix["sport_breakdown"].items(), key=lambda x: -x[1]):
        print(f"  {sport}: {count}")
    print(f"\nData tier breakdown:")
    for tier, count in matrix["data_tier_breakdown"].items():
        if count > 0:
            print(f"  {tier}: {count}")


if __name__ == "__main__":
    main()
