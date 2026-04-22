#!/usr/bin/env python3
"""Aggregate scan outputs and select candidate picks.

Requirements: run `scripts/scan_events.py` first to populate `betting/data/scan_summary.json`.

This script applies simple rules:
- require at least one Tier-A stat source (flashscore/sofascore)
- require Betclic odds present for a candidate (bookmaker_odds)
- compute market_best as max odds across all sources
- compute price_gap_pct = 100 * ((bookmaker_odds / market_best) - 1)
- accept low-risk picks with price_gap_pct >= -3

Outputs: `betting/data/picks_suggested.json`
"""
import json
from pathlib import Path
from collections import defaultdict
import math

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE.parent / "betting" / "data"
SUMMARY = DATA_DIR / "scan_summary.json"

TIER_A_STATS = {"flashscore.com", "sofascore.com"}
TIER_A_MARKETS = {"oddsportal.com", "oddspedia.com", "betexplorer.com", "betclic.pl", "betclic.com"}


def normalize(name: str) -> str:
    return " ".join(name.lower().replace("[", "").replace("]", "").split()) if name else ""


def load_summary():
    if not SUMMARY.exists():
        raise SystemExit(f"Summary file not found: {SUMMARY} — run scripts/scan_events.py first")
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


def extract_odds(item):
    # item may have 'odds' as list of strings; try to parse decimals
    odds = []
    for k in ("odds", "price", "prices"):
        v = item.get(k)
        if isinstance(v, list):
            for x in v:
                try:
                    odds.append(float(x))
                except Exception:
                    pass
    # also check raw for numbers like 1.23
    raw = item.get("raw", "")
    import re
    for m in re.findall(r"\b\d+\.\d{2}\b", raw or ""):
        try:
            odds.append(float(m))
        except:
            pass
    return sorted(set(odds))


def aggregate(summary):
    # key by normalized home|away
    matches = defaultdict(lambda: {"sources": [], "odds": {}, "sample_items": []})
    for url, items in summary.items():
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.replace("www.", "")
        for it in items:
            home = normalize(it.get("home") or it.get("team1") or "")
            away = normalize(it.get("away") or it.get("team2") or "")
            if not home or not away:
                # try parse raw
                raw = (it.get("raw") or "")
                if " - " in raw:
                    parts = raw.split(" - ", 1)
                    home = normalize(parts[0]); away = normalize(parts[1])
            if not home or not away:
                continue
            key = f"{home} | {away}"
            matches[key]["sources"].append(domain)
            odds_list = extract_odds(it)
            if odds_list:
                matches[key]["odds"].setdefault(domain, []).extend(odds_list)
            matches[key]["sample_items"].append({"domain": domain, "raw": it.get("raw"), "time": it.get("time"), "odds": odds_list})
    return matches


def select_candidates(matches):
    candidates = []
    for key, meta in matches.items():
        domains = set(meta["sources"]) if meta.get("sources") else set()
        # require at least one Tier-A stat source
        if not (domains & TIER_A_STATS):
            continue
        # require Betclic odds present
        odds_map = meta.get("odds", {})
        betclic_odds = None
        for d in ("betclic.pl", "betclic.com"):
            if d in odds_map and odds_map[d]:
                betclic_odds = max(odds_map[d])
                break
        if not betclic_odds:
            continue
        # compute market_best across all market sources
        market_odds = []
        for d, vals in odds_map.items():
            if d in TIER_A_MARKETS or True:
                market_odds.extend(vals)
        if not market_odds:
            continue
        market_best = max(market_odds)
        price_gap_pct = 100.0 * ((betclic_odds / market_best) - 1.0)
        candidates.append({"match": key, "betclic_odds": betclic_odds, "market_best": market_best, "price_gap_pct": price_gap_pct, "sources": list(domains), "sample": meta.get("sample_items")[:3]})
    # sort by number of Tier-A sources and price gap (prefer positive gap)
    candidates.sort(key=lambda x: ( -len([s for s in x["sources"] if s in TIER_A_STATS or s in TIER_A_MARKETS]), -x["price_gap_pct"]))
    return candidates


def allocate_stakes(candidates):
    # Simple allocation: up to 3 singles with stake 2.00 PLN if allowed by price_gap
    picks = []
    used = 0.0
    for c in candidates:
        if len(picks) >= 3:
            break
        # low-risk threshold
        if c["price_gap_pct"] < -3.0:
            continue
        stake = 2.0
        picks.append({"match": c["match"], "odds": c["betclic_odds"], "stake_pln": round(stake,2), "price_gap_pct": round(c["price_gap_pct"],2), "sources": c["sources"]})
        used += stake
    return picks


def main():
    summary = load_summary()
    matches = aggregate(summary)
    candidates = select_candidates(matches)
    picks = allocate_stakes(candidates)
    out = DATA_DIR / "picks_suggested.json"
    out.write_text(json.dumps({"candidates": candidates, "picks": picks}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote picks and candidates to {out}")


if __name__ == "__main__":
    main()
