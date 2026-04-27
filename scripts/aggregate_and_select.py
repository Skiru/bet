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

TIER_A_STATS = {"flashscore.com", "sofascore.com"}
TIER_A_STATS_EXTENDED = {
    "tennis": {"flashscore.com", "sofascore.com", "tennisabstract.com", "tennisexplorer.com"},
    "basketball": {"flashscore.com", "sofascore.com", "covers.com", "teamrankings.com", "basketball-reference.com"},
    "baseball": {"flashscore.com", "sofascore.com", "covers.com", "teamrankings.com"},
    "hockey": {"flashscore.com", "sofascore.com", "covers.com", "teamrankings.com", "hockey-reference.com"},
    "football": {"flashscore.com", "sofascore.com", "betideas.com", "soccerstats.com"},
    "volleyball": {"flashscore.com", "sofascore.com"},
    "handball": {"flashscore.com", "sofascore.com"},
    "snooker": {"flashscore.com", "cuetracker.net"},
    "esports": {"flashscore.com", "gosugamers.net"},
    "darts": {"flashscore.com", "dartsorakel.com"},
    "table_tennis": {"flashscore.com", "sofascore.com"},
    "mma": {"flashscore.com", "sofascore.com"},
}
TIER_A_MARKETS = {"oddsportal.com", "betexplorer.com"}
BOOKMAKER_DOMAINS = {"betclic.pl", "betclic.com"}
COMMUNITY_SOURCES = {
    "zawodtyper.pl", "typersi.pl", "tipstrr.com",
    "pickswise.com", "betideas.com", "gosugamers.net",
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
            "suggested_daily_allocation_range_pln": [8.0, 12.0],
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
    """Find an existing match key that fuzzy-matches the new home/away pair."""
    for key in matches:
        parts = key.split(" | ", 1)
        if len(parts) != 2:
            continue
        if fuzzy_match(new_home, parts[0]) and fuzzy_match(new_away, parts[1]):
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
                matches[key]["sports"].add(it["sport"])
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
    """Select candidates that meet Tier-A requirements and price checks."""
    candidates = []
    for key, meta in matches.items():
        domains = set(meta["sources"])

        # Determine sport for Tier-A stats mapping
        sport = meta.get("sports", ["football"])
        sport = sport[0] if sport else "football"
        tier_a_stat_set = TIER_A_STATS_EXTENDED.get(sport, TIER_A_STATS)

        # Require at least one Tier-A stat source
        stat_sources = domains & tier_a_stat_set
        if not stat_sources:
            continue

        # Require at least one Tier-A market source OR bookmaker odds
        market_sources = domains & TIER_A_MARKETS
        odds_map = meta.get("odds", {})

        # Get bookmaker odds
        betclic_odds = None
        for d in BOOKMAKER_DOMAINS:
            if d in odds_map and odds_map[d]:
                betclic_odds = max(odds_map[d])
                break
        if not betclic_odds:
            continue

        # Compute market_best from Tier-A market sources only
        market_odds = []
        for d in TIER_A_MARKETS:
            if d in odds_map:
                market_odds.extend(odds_map[d])
        # If no Tier-A market data, use bookmaker odds as fallback (gap = 0)
        if not market_odds:
            market_best = betclic_odds
        else:
            market_best = max(market_odds)

        price_gap_pct = 100.0 * ((betclic_odds / market_best) - 1.0) if market_best > 0 else 0.0

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
            "betclic_odds": round(betclic_odds, 2),
            "market_best": round(market_best, 2),
            "price_gap_pct": round(price_gap_pct, 2),
            "risk_tier": risk_tier,
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
        -x["price_gap_pct"],
    ))
    return candidates


def allocate_stakes(candidates, config):
    """Allocate stakes respecting config limits."""
    max_stake = config.get("low_risk_coupon_max_stake_pln", 3.0)
    alloc_range = config.get("suggested_daily_allocation_range_pln", [8.0, 12.0])
    max_daily = alloc_range[1] if len(alloc_range) > 1 else 12.0

    picks = []
    used = 0.0
    for c in candidates:
        if len(picks) >= 3:
            break
        if used + max_stake > max_daily:
            break

        # Apply price gap threshold based on risk tier
        if c["risk_tier"] == "low" and c["price_gap_pct"] < LOW_RISK_GAP_THRESHOLD:
            continue
        elif c["risk_tier"] in ("medium", "high") and c["price_gap_pct"] < HIGH_RISK_GAP_THRESHOLD:
            continue

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


def main():
    config = load_config()
    summary = load_summary()
    matches = aggregate(summary)
    candidates = select_candidates(matches)
    picks, total_exposure = allocate_stakes(candidates, config)

    alloc_range = config.get("suggested_daily_allocation_range_pln", [8.0, 12.0])
    max_daily = alloc_range[1] if len(alloc_range) > 1 else 12.0

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
