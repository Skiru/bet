#!/usr/bin/env python3
"""Filter gate results to night session (22:00-05:59 CEST) and produce structured output."""
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

CEST = timezone(timedelta(hours=2))

SPORT_EMOJI = {
    "football": "⚽", "basketball": "🏀", "tennis": "🎾",
    "hockey": "🏒", "volleyball": "🏐",
}


def parse_kickoff_to_cest(raw: str):
    """Parse kickoff string to CEST datetime."""
    if not raw:
        return None
    try:
        if "+" in raw or raw.endswith("Z"):
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        else:
            # Naive timestamps are already in CEST per scan convention
            dt = datetime.fromisoformat(raw).replace(tzinfo=CEST)
        return dt.astimezone(CEST)
    except (ValueError, TypeError):
        return None


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else "2026-05-11"
    base = Path(__file__).resolve().parent.parent
    gate_path = base / f"betting/data/{date}_s7_gate_results.json"

    if not gate_path.exists():
        print(f"ERROR: Gate results file not found: {gate_path}")
        sys.exit(1)

    with open(gate_path) as f:
        data = json.load(f)

    candidates = data.get("gate_results", {}).get("approved", [])
    print(f"Total candidates in gate results: {len(candidates)}")

    night_events = []

    for c in candidates:
        raw = c.get("kickoff", "")
        dt_cest = parse_kickoff_to_cest(raw)
        if not dt_cest:
            continue

        h = dt_cest.hour
        if h >= 22 or h < 6:
            bm = c.get("best_market") or {}
            night_events.append({
                "kickoff_cest": dt_cest.strftime("%H:%M"),
                "kickoff_raw": raw,
                "sport": c.get("sport", "?"),
                "home_team": c.get("home_team", "?"),
                "away_team": c.get("away_team", "?"),
                "competition": c.get("competition", "?"),
                "market": bm.get("name", "?"),
                "direction": bm.get("direction", "?"),
                "line": bm.get("line", ""),
                "safety_score": bm.get("safety_score", 0),
                "l10_avg": bm.get("l10_avg", ""),
                "l5_avg": bm.get("l5_avg", ""),
                "hit_rate_l5": bm.get("hit_rate_l5", ""),
                "margin": bm.get("margin", 0),
                "advisory_tier": c.get("advisory_tier", "?"),
                "gate_score": c.get("gate_score", "?"),
                "risk_tier": c.get("risk_tier", "?"),
                "data_quality": (c.get("data_quality") or {}).get("label", "?"),
                "upset_risk_level": (c.get("upset_risk") or {}).get("level", "?"),
                "effective_failures": (c.get("systemic_discount") or {}).get("effective_failures", "?"),
                "three_way": c.get("three_way_alignment", ""),
                "h2h_count": c.get("h2h_count", 0),
                "market_count": c.get("market_count", 0),
            })

    # Sort by kickoff time
    night_events.sort(key=lambda x: x["kickoff_cest"])

    print(f"\n{'=' * 120}")
    print(f"NIGHT SESSION (22:00-05:59 CEST) — {len(night_events)} events")
    print(f"{'=' * 120}\n")

    # Group by unique event (home+away)
    seen_events = {}
    for e in night_events:
        key = f"{e['home_team']} vs {e['away_team']}"
        if key not in seen_events:
            seen_events[key] = []
        seen_events[key].append(e)

    print(f"Unique matches: {len(seen_events)}\n")

    for i, e in enumerate(sorted(night_events, key=lambda x: (x["kickoff_cest"], -x["safety_score"])), 1):
        min_odds = round(1 / e["safety_score"], 2) if e["safety_score"] > 0 else "N/A"
        emoji = SPORT_EMOJI.get(e["sport"], "🎯")
        print(f"#{i:>2} | {e['kickoff_cest']} | {emoji} {e['sport']:>10} | {e['home_team']} vs {e['away_team']}")
        print(f"     Liga: {e['competition']}")
        print(f"     Market: {e['market']} {e['direction']} {e['line']}")
        print(f"     Safety: {e['safety_score']:.2f} | Min kurs: {min_odds} | Gate: {e['gate_score']} | Tier: {e['advisory_tier']} | Risk: {e['risk_tier']}")
        print(f"     L10: {e['l10_avg']} | L5: {e['l5_avg']} | Hit L5: {e['hit_rate_l5']} | Margin: {e['margin']:.1%} | 3-Way: {e['three_way']}")
        print(f"     DQ: {e['data_quality']} | H2H: {e['h2h_count']} | Markets: {e['market_count']} | Upset: {e['upset_risk_level']} | EffFail: {e['effective_failures']}")
        print()

    # Summaries
    tiers = {}
    for e in night_events:
        t = e["advisory_tier"]
        tiers[t] = tiers.get(t, 0) + 1
    print(f"Tier distribution: {tiers}")

    sports = {}
    for e in night_events:
        s = e["sport"]
        sports[s] = sports.get(s, 0) + 1
    print(f"Sport distribution: {sports}")

    # Save JSON
    out_path = base / f"betting/data/{date}_night_session.json"
    with open(out_path, "w") as f:
        json.dump({
            "date": date, "session": "night", "window": "22:00-05:59 CEST",
            "total_events": len(night_events), "unique_matches": len(seen_events),
            "events": night_events,
        }, f, indent=2, default=str)
    print(f"\nSaved to: {out_path}")


if __name__ == "__main__":
    main()
