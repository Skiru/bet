#!/usr/bin/env python3
"""Aggregate scan outputs and select candidate picks.

Requirements: run `scripts/scan_events.py` first to populate `betting/data/scan_summary.json`.

This script applies rules from config/betting_config.json:
- require at least one Tier-A stat source (flashscore/sofascore)
- require at least one Tier-A market source for odds comparison
- compute market_best as max odds across Tier-A market sources
- compute price_gap_pct = 100 * ((bookmaker_odds / market_best) - 1)
- accept low-risk picks with price_gap_pct >= -3, higher-risk with >= -5
- respect max_coupon_stake_pln and daily allocation from config

Outputs: `betting/data/picks_suggested.json`
"""
import json
import re
from pathlib import Path
from collections import defaultdict
from urllib.parse import urlparse
from typing import Optional
from difflib import SequenceMatcher

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE.parent / "betting" / "data"
CONFIG_PATH = BASE.parent / "config" / "betting_config.json"
SUMMARY = DATA_DIR / "scan_summary.json"
ODDS_SNAPSHOT = DATA_DIR / "odds_api_snapshot.json"

TIER_A_STATS = {"flashscore.com", "sofascore.com"}
TIER_A_STATS_EXTENDED = {
    "tennis": {"flashscore.com", "sofascore.com", "tennisabstract.com", "tennisexplorer.com"},
    "basketball": {"flashscore.com", "sofascore.com", "covers.com", "teamrankings.com", "basketball-reference.com"},
    "baseball": {"flashscore.com", "sofascore.com", "covers.com", "teamrankings.com"},
    "hockey": {"flashscore.com", "sofascore.com", "covers.com", "teamrankings.com", "hockey-reference.com"},
    "football": {"flashscore.com", "sofascore.com", "betideas.com", "soccerstats.com", "soccerway.com", "aiscore.com", "xscores.com"},
    "volleyball": {"flashscore.com", "sofascore.com"},
    "handball": {"flashscore.com", "sofascore.com"},
    "snooker": {"flashscore.com", "cuetracker.net"},
    "esports": {"flashscore.com", "gosugamers.net"},
    "darts": {"flashscore.com", "dartsorakel.com"},
    "table_tennis": {"flashscore.com", "sofascore.com"},
    "mma": {"flashscore.com", "sofascore.com"},
}
TIER_A_MARKETS = {"oddsportal.com", "betexplorer.com", "odds-api"}
BOOKMAKER_DOMAINS = {"betclic.pl", "betclic.com"}
COMMUNITY_SOURCES = {
    "zawodtyper.pl", "typersi.pl", "tipstrr.com",
    "pickswise.com", "betideas.com", "gosugamers.net",
    "feedinco.com", "bettingclosed.com", "tips180.com", "asiabet.org",
}

# Price gap thresholds
LOW_RISK_GAP_THRESHOLD = -3.0
HIGH_RISK_GAP_THRESHOLD = -5.0


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "low_risk_coupon_max_stake_pln": 3.0,
            "higher_risk_coupon_max_stake_pln": 2.0,
            "daily_exposure_range": [5.0, 15.0],
        }


def normalize(name: str) -> str:
    if not name:
        return ""
    # Remove brackets, extra whitespace, lowercase
    name = re.sub(r"[\[\]()\{\}]", "", name)
    name = re.sub(r"\s+", " ", name).strip().lower()
    # Remove common suffixes/prefixes that vary across sources
    for suffix in (" fc", " cf", " sc", " ac", " afc"):
        if name.endswith(suffix):
            name = name[: -len(suffix)].strip()
    return name


def load_odds_snapshot() -> dict:
    """Load odds from odds_api_snapshot.json and return keyed by normalized match.

    Returns dict mapping 'normalized_home | normalized_away' → event data.
    """
    if not ODDS_SNAPSHOT.exists():
        return {}
    try:
        data = json.loads(ODDS_SNAPSHOT.read_text(encoding="utf-8"))
        events = data.get("events", []) if isinstance(data, dict) else data
        lookup = {}
        for ev in events:
            home = normalize(ev.get("home_team", ""))
            away = normalize(ev.get("away_team", ""))
            if home and away:
                lookup[f"{home} | {away}"] = ev
        return lookup
    except (json.JSONDecodeError, OSError):
        return {}


# --- Garbage filters (Bug #8, #9, #10, #11) ---
# Bookmaker names that get parsed as team names from comparison sites
BOOKMAKER_NAME_BLOCKLIST = {
    "1xbet", "unibet", "betway", "bet365", "pinnacle", "betfair", "bwin",
    "betclic", "williamhill", "william hill", "paddy power", "paddypower",
    "ladbrokes", "coral", "888sport", "betfred", "marathon", "marathonbet",
    "22bet", "sts", "fortuna", "lvbet", "superbet", "betsson", "coolbet",
    "novibet", "betano", "sportingbet", "stake", "cloudbet", "bovada",
    "fanduel", "draftkings", "caesars", "pointsbet", "betmgm", "betrivers",
    "sportsbet", "tab", "neds", "betr", "tipsport", "chance", "toto",
    "fonbet", "leon", "melbet", "mostbet", "1win", "parimatch", "vbet",
}

# Short strings that are noise (sidebar labels, nav items)
GARBAGE_TEAM_PATTERNS = re.compile(
    r"^(live|today|tomorrow|yesterday|popular|featured|top|trending|"
    r"all sports|my bets|results|schedule|standings|statistics|"
    r"pinned leagues|my teams|add the team|promoted|"
    r"multimedia|news|article|photo|video|gallery|"
    r"\d{1,2}:\d{2}|odds|bet now|place bet|"
    r"today\'s matches|upcoming|finished)$",
    re.IGNORECASE,
)


def is_garbage_team(name: str) -> bool:
    """Return True if name is a known bookmaker, UI element, or garbage."""
    if not name or len(name) < 2:
        return True
    n = name.strip().lower()
    # Bookmaker names
    if n in BOOKMAKER_NAME_BLOCKLIST:
        return True
    # UI/nav garbage
    if GARBAGE_TEAM_PATTERNS.match(n):
        return True
    # All digits or all special chars
    if re.match(r"^[\d\s\-\.]+$", n):
        return True
    # Too short to be a real team (single char)
    if len(n) <= 1:
        return True
    return False


def fuzzy_match(name1: str, name2: str, threshold: float = 0.75) -> bool:
    """Check if two team names are likely the same team."""
    n1 = normalize(name1)
    n2 = normalize(name2)
    if not n1 or not n2:
        return False
    if n1 == n2:
        return True
    # Check containment
    if n1 in n2 or n2 in n1:
        return True
    return SequenceMatcher(None, n1, n2).ratio() >= threshold


def match_key(home: str, away: str) -> str:
    return f"{normalize(home)} | {normalize(away)}"


def find_existing_key(new_home: str, new_away: str, matches: dict) -> Optional[str]:
    """Find an existing match key that fuzzy-matches the new home/away pair.

    Uses a two-pass strategy for performance:
    1. Direct normalized key lookup (O(1))
    2. Containment check on home team only (O(n) but rarely needed)
    Avoids full O(n) SequenceMatcher on every insert.
    """
    # Fast path: exact normalized match
    direct_key = match_key(new_home, new_away)
    if direct_key in matches:
        return direct_key

    # Medium path: check if normalized home is contained in existing keys
    n_home = normalize(new_home)
    n_away = normalize(new_away)
    if not n_home or not n_away:
        return None

    for key in matches:
        parts = key.split(" | ", 1)
        if len(parts) != 2:
            continue
        # Only do cheap containment check, skip expensive SequenceMatcher
        eh, ea = parts
        if not eh or not ea:
            continue
        # Containment: "man city" in "manchester city" or vice versa
        # Require minimum 5 chars to avoid false matches on short names like "inter"
        home_match = (n_home == eh)
        if not home_match and len(n_home) >= 5 and len(eh) >= 5:
            home_match = (n_home in eh) or (eh in n_home)
        if not home_match:
            continue
        away_match = (n_away == ea)
        if not away_match and len(n_away) >= 5 and len(ea) >= 5:
            away_match = (n_away in ea) or (ea in n_away)
        if away_match:
            return key

    return None


def load_summary():
    if not SUMMARY.exists():
        raise SystemExit(f"Summary file not found: {SUMMARY} — run scripts/scan_events.py first")
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


def extract_odds(item):
    """Extract decimal odds from an item dict."""
    odds = []
    for k in ("odds", "price", "prices"):
        v = item.get(k)
        if isinstance(v, list):
            for x in v:
                try:
                    f = float(x)
                    if 1.01 <= f <= 100.0:
                        odds.append(f)
                except (ValueError, TypeError):
                    pass
        elif isinstance(v, (int, float)):
            try:
                f = float(v)
                if 1.01 <= f <= 100.0:
                    odds.append(f)
            except (ValueError, TypeError):
                pass
    # Also check raw for decimal odds patterns
    raw = item.get("raw", "")
    if raw:
        for m in re.findall(r"\b\d+\.\d{2}\b", raw):
            try:
                f = float(m)
                if 1.01 <= f <= 100.0:
                    odds.append(f)
            except (ValueError, TypeError):
                pass
    return sorted(set(odds))


def aggregate(summary):
    """Group extracted items by normalized match key across all sources."""
    matches = defaultdict(lambda: {"sources": [], "odds": {}, "sample_items": [], "times": set(), "sports": set()})
    # Track (normalized_home, normalized_away, domain) to avoid counting same event twice from same URL
    _seen_source_events: set[tuple[str, str, str]] = set()
    for url, items in summary.items():
        domain = urlparse(url).netloc.replace("www.", "")
        for it in items:
            home = it.get("home") or it.get("team1") or ""
            away = it.get("away") or it.get("team2") or ""
            if not home or not away:
                raw = it.get("raw") or ""
                if " - " in raw:
                    parts = raw.split(" - ", 1)
                    home = parts[0].strip()
                    away = parts[1].strip()
            if not home or not away:
                continue

            # Garbage filter: reject bookmaker names, UI elements, garbage text
            if is_garbage_team(home) or is_garbage_team(away):
                continue

            # Source-level dedup: same event from same domain counted only once
            dedup_key = (normalize(home), normalize(away), domain)
            if dedup_key in _seen_source_events:
                continue
            _seen_source_events.add(dedup_key)

            # Try to find an existing fuzzy match
            key = find_existing_key(home, away, matches)
            if key is None:
                key = match_key(home, away)

            matches[key]["sources"].append(domain)
            odds_list = extract_odds(it)
            if odds_list:
                matches[key]["odds"].setdefault(domain, []).extend(odds_list)
            if it.get("time"):
                matches[key]["times"].add(it["time"])
            if it.get("sport"):
                # Normalize sport: strip source suffixes like "_odds_api_io", "_betclic"
                raw_sport = it["sport"].lower().strip()
                raw_sport = re.sub(r"_(odds_api(_io)?|betclic|flashscore|sofascore|betexplorer|api)$", "", raw_sport)
                matches[key]["sports"].add(raw_sport)
            matches[key]["sample_items"].append({
                "domain": domain,
                "raw": it.get("raw"),
                "time": it.get("time"),
                "odds": odds_list,
                "sport": it.get("sport"),
            })

    # Convert sets to lists for JSON serialization
    for key in matches:
        matches[key]["times"] = sorted(matches[key]["times"])
        matches[key]["sports"] = sorted(matches[key]["sports"])

    return matches


def select_candidates(matches):
    """Select ALL candidates — no auto-rejection. Advisory flags only."""
    candidates = []
    for key, meta in matches.items():
        domains = set(meta["sources"])

        # Determine sport for Tier-A stats mapping
        sport = meta.get("sports", ["football"])
        sport = sport[0] if sport else "football"
        tier_a_stat_set = TIER_A_STATS_EXTENDED.get(sport, TIER_A_STATS)

        # Track Tier-A stat sources (advisory, not filtering)
        stat_sources = domains & tier_a_stat_set
        advisory_flags = []
        if not stat_sources:
            advisory_flags.append("no_tier_a_stats")

        # Track Tier-A market sources (advisory, not filtering)
        market_sources = domains & TIER_A_MARKETS
        odds_map = meta.get("odds", {})

        # Get bookmaker odds — prefer Betclic, fall back to ANY source with odds
        betclic_odds = None
        for d in BOOKMAKER_DOMAINS:
            if d in odds_map and odds_map[d]:
                betclic_odds = max(odds_map[d])
                break

        # Fallback: use odds from ANY source (Tier-A market, API snapshot, etc.)
        any_odds = betclic_odds
        if not any_odds:
            # Try Tier-A market sources
            for d in TIER_A_MARKETS:
                if d in odds_map and odds_map[d]:
                    any_odds = max(odds_map[d])
                    break
        if not any_odds:
            # Try ANY source that has odds
            for d, d_odds in odds_map.items():
                if d_odds:
                    any_odds = max(d_odds)
                    break
        if not any_odds:
            # Try API snapshot odds
            api_odds = meta.get("api_odds")
            if api_odds:
                any_odds = api_odds
        if not any_odds:
            advisory_flags.append("no_odds_found")

        # Use Betclic odds for gap calculation; fall back to any available odds
        reference_odds = betclic_odds or any_odds

        # Compute market_best from Tier-A market sources only
        market_odds = []
        for d in TIER_A_MARKETS:
            if d in odds_map:
                market_odds.extend(odds_map[d])
        # If no Tier-A market data, use reference odds as fallback (gap = 0)
        if not market_odds:
            market_best = reference_odds
        else:
            market_best = max(market_odds)

        price_gap_pct = 100.0 * ((reference_odds / market_best) - 1.0) if reference_odds and market_best and market_best > 0 else 0.0

        # Advisory price gap flags (NEVER filter — user decides)
        if price_gap_pct < HIGH_RISK_GAP_THRESHOLD:
            advisory_flags.append("below_hr_threshold")
        elif price_gap_pct < LOW_RISK_GAP_THRESHOLD:
            advisory_flags.append("below_lr_threshold")

        # Determine risk tier based on source coverage
        tier_a_count = len(stat_sources) + len(market_sources)
        if tier_a_count >= 3 and price_gap_pct >= LOW_RISK_GAP_THRESHOLD:
            risk_tier = "low"
        elif tier_a_count >= 2:
            risk_tier = "medium"
        else:
            risk_tier = "high"

        candidates.append({
            "match": key,
            "sport": meta.get("sports", ["football"])[0] if meta.get("sports") else "football",
            "betclic_odds": round(reference_odds, 2) if reference_odds else None,
            "odds_source": "betclic" if betclic_odds else ("market" if any_odds else "none"),
            "market_best": round(market_best, 2) if market_best else None,
            "price_gap_pct": round(price_gap_pct, 2) if reference_odds and market_best else None,
            "risk_tier": risk_tier,
            "advisory_flags": advisory_flags,
            "sources": sorted(set(domains)),
            "stat_sources": sorted(stat_sources),
            "market_sources": sorted(market_sources),
            "community_sources": sorted(domains & COMMUNITY_SOURCES),
            "community_covered": bool(domains & COMMUNITY_SOURCES),
            "times": meta.get("times", []),
            "sample": meta.get("sample_items", [])[:3],
        })

    # Sort by: risk tier (low first), then by number of Tier-A sources desc, then price gap desc
    tier_order = {"low": 0, "medium": 1, "high": 2}
    candidates.sort(key=lambda x: (
        tier_order.get(x["risk_tier"], 3),
        -len(x["stat_sources"]) - len(x["market_sources"]),
        -(x["price_gap_pct"] or 0),
    ))
    return candidates


def allocate_stakes(candidates, config):
    """Allocate stakes respecting config limits."""
    max_stake = config.get("low_risk_coupon_max_stake_pln", 3.0)
    alloc_range = config.get("daily_exposure_range", config.get("suggested_daily_allocation_range_pln", [5.0, 15.0]))
    max_daily = alloc_range[1] if len(alloc_range) > 1 else 12.0
    max_picks = config.get("max_picks_per_day", 50)
    low_gap = config.get("low_risk_price_gap_threshold_pct", LOW_RISK_GAP_THRESHOLD)
    high_gap = config.get("higher_risk_price_gap_threshold_pct", HIGH_RISK_GAP_THRESHOLD)

    picks = []
    used = 0.0
    for c in candidates:
        if len(picks) >= max_picks:
            break
        if used + max_stake > max_daily:
            break

        # Advisory-only: tag events below threshold but NEVER filter them
        # User decides what to bet on

        # Reduce stake for higher-risk picks
        if c["risk_tier"] == "high":
            stake = min(max_stake * 0.5, max_daily - used)
        else:
            stake = min(max_stake, max_daily - used)

        if stake <= 0:
            break

        picks.append({
            "match": c["match"],
            "odds": c["betclic_odds"],
            "stake_pln": round(stake, 2),
            "price_gap_pct": c["price_gap_pct"],
            "risk_tier": c["risk_tier"],
            "sources": c["sources"],
            "stat_sources": c["stat_sources"],
            "market_sources": c["market_sources"],
        })
        used += stake

    return picks, round(used, 2)


def enrich_with_api_odds(matches: dict) -> dict:
    """Merge odds from odds_api_snapshot.json into aggregated matches.

    For each API odds event, find matching aggregated match and add odds.
    For events not yet in matches, add them with API odds data.
    """
    odds_data = load_odds_snapshot()
    if not odds_data:
        return matches

    enriched_count = 0
    added_count = 0

    for odds_key, event in odds_data.items():
        home = event.get("home_team", "")
        away = event.get("away_team", "")
        if not home or not away:
            continue

        # Extract best odds from API event bookmakers
        best_price = 0.0
        for bm in event.get("bookmakers", []):
            for market in bm.get("markets", []):
                for outcome in market.get("outcomes", []):
                    price = outcome.get("price", 0)
                    if isinstance(price, (int, float)) and price > best_price:
                        best_price = price

        if best_price < 1.01:
            continue

        # Find matching aggregated match
        matched_key = find_existing_key(home, away, matches)
        if matched_key:
            matches[matched_key]["api_odds"] = round(best_price, 2)
            matches[matched_key].setdefault("sources", []).append("odds-api")
            sport = event.get("_our_sport", "football")
            sports_val = matches[matched_key].get("sports", [])
            if isinstance(sports_val, set):
                sports_val.add(sport)
            elif isinstance(sports_val, list) and sport not in sports_val:
                sports_val.append(sport)
            enriched_count += 1
        else:
            # Add as new match entry — event found in API but not in scan
            key = match_key(home, away)
            sport = event.get("_our_sport", "football")
            matches[key] = {
                "sources": ["odds-api"],
                "odds": {},
                "sample_items": [],
                "times": [],
                "sports": [sport] if sport else [],
                "api_odds": round(best_price, 2),
            }
            added_count += 1

    print(f"API odds: enriched {enriched_count} existing matches, added {added_count} new")
    return matches


def main():
    config = load_config()
    summary = load_summary()
    matches = aggregate(summary)
    matches = enrich_with_api_odds(matches)
    candidates = select_candidates(matches)
    picks, total_exposure = allocate_stakes(candidates, config)

    alloc_range = config.get("daily_exposure_range", config.get("suggested_daily_allocation_range_pln", [5.0, 15.0]))
    max_daily = alloc_range[1] if len(alloc_range) > 1 else 15.0

    output = {
        "config_used": {
            "max_coupon_stake_pln": config.get("low_risk_coupon_max_stake_pln", 3.0),
            "max_daily_pln": max_daily,
        },
        "total_matches_aggregated": len(matches),
        "candidates_count": len(candidates),
        "candidates": candidates,
        "picks": picks,
        "total_exposure_pln": total_exposure,
        "unused_budget_pln": round(max_daily - total_exposure, 2),
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / "picks_suggested.json"
    out.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Aggregated {len(matches)} matches, {len(candidates)} candidates, {len(picks)} picks")
    print(f"Total exposure: {total_exposure} PLN / {max_daily} PLN")
    print(f"Wrote output to {out}")


if __name__ == "__main__":
    main()
