#!/usr/bin/env python3
"""Quick Betclic extractor + presence check on Flashscore/SofaScore.

Produces quick suggested singles where the match appears on Betclic and on
Flashscore or SofaScore (Tier-A stat source). Prioritizes matches with
the best source confirmation and reasonable odds range (1.30-3.50).
"""
import sys
from pathlib import Path
import json

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
try:
    from fetch_with_playwright import fetch
except Exception:
    import requests

    def fetch(url: str) -> str:
        resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        return resp.text

CONFIG_PATH = BASE.parent / "config" / "betting_config.json"


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"low_risk_coupon_max_stake_pln": 3.0}


def normalize(n: str) -> str:
    return " ".join((n or "").lower().replace("www.", "").split())


def extract_from_betclic(html: str):
    from adapters.betclic_adapter import parse as betclic_parse
    return betclic_parse(html, "https://www.betclic.pl/")


def appears_on_site(team_name: str, html: str) -> bool:
    """Check if team name appears in HTML text (case-insensitive, without normalizing entire HTML)."""
    return normalize(team_name) in html.lower()


def main():
    config = load_config()
    max_stake = config.get("low_risk_coupon_max_stake_pln", 3.0)

    betclic_url = "https://www.betclic.pl/"
    flash_url = "https://www.flashscore.com/"
    sofascore_url = "https://www.sofascore.com/"

    print("Fetching Betclic...")
    bhtml = fetch(betclic_url)
    print("Parsing Betclic...")
    candidates = extract_from_betclic(bhtml)
    print(f"Found {len(candidates)} candidate blocks on Betclic")

    print("Fetching Flashscore (tier-A stat)...")
    fhtml = fetch(flash_url)
    print("Fetching SofaScore (tier-A stat)...")
    shtml = fetch(sofascore_url)

    confirmed = []
    for c in candidates:
        key = f"{c['home']} - {c['away']}"
        on_flash = appears_on_site(c["home"], fhtml) or appears_on_site(c["away"], fhtml)
        on_sofa = appears_on_site(c["home"], shtml) or appears_on_site(c["away"], shtml)
        if not (on_flash or on_sofa):
            continue
        try:
            odd = float(c["odds"][0])
        except (IndexError, ValueError):
            continue
        # Filter to reasonable value range (avoid extreme favorites and longshots)
        if odd < 1.10 or odd > 10.0:
            continue
        source_count = int(on_flash) + int(on_sofa)
        confirmed.append({
            "match": key,
            "odds": odd,
            "source_count": source_count,
            "raw": c["raw"],
        })

    # Dedupe by normalized key
    seen = set()
    dedup = []
    for c in confirmed:
        nk = normalize(c["match"])
        if nk in seen:
            continue
        seen.add(nk)
        dedup.append(c)

    # Sort by: most source confirmations, then by odds in value range (1.30-3.50 preferred)
    def sort_key(x):
        odds = x["odds"]
        # Prefer odds in the 1.30-3.50 range (best value zone)
        if 1.30 <= odds <= 3.50:
            odds_score = 0
        else:
            odds_score = 1
        return (-x["source_count"], odds_score, -odds)

    dedup.sort(key=sort_key)

    picks = []
    for p in dedup[:3]:
        picks.append({
            "match": p["match"],
            "bookmaker": "betclic",
            "odds": p["odds"],
            "stake_pln": max_stake,
            "source_count": p["source_count"],
        })

    out = BASE.parent / "betting" / "data" / "quick_picks.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"picks": picks, "candidates_count": len(dedup)}, indent=2, ensure_ascii=False)
    )
    print(f"Wrote quick picks to {out}")
    for p in picks:
        print(p)


if __name__ == "__main__":
    main()
