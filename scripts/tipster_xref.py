#!/usr/bin/env python3
"""S2 Tipster Cross-Reference — cross-reference picks with tipster consensus.

Extracted from pipeline_orchestrator.py (Phase 3.3).
"""

import json
import sys
from pathlib import Path
from rapidfuzz import fuzz

# ---------------------------------------------------------------------------
# Paths (same as orchestrator)
# ---------------------------------------------------------------------------
SCRIPTS_DIR = Path(__file__).parent
ROOT_DIR = SCRIPTS_DIR.parent
DATA_DIR = ROOT_DIR / "betting" / "data"

# Add scripts/ and src/ to path for imports
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(ROOT_DIR / "src"))


def run_tipster_xref(date: str, state: dict) -> tuple[bool, str]:
    """S2: Cross-reference shortlist with tipster consensus data.

    Enriches shortlist candidates with tipster support, consensus %, and arguments.
    """
    # DB-first (R2) — use TipsterRepo
    tips = []
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import TipsterRepo
        with get_db() as conn:
            repo = TipsterRepo(conn)
            db_picks = repo.get_picks_by_date(date)
            if db_picks:
                tips = [
                    {
                        "source_site": p.source_site, "tipster_name": p.tipster_name,
                        "sport": p.sport, "event": p.event,
                        "home_team": p.home_team, "away_team": p.away_team,
                        "competition": p.competition, "market": p.market,
                        "market_type": p.market_type, "direction": p.direction,
                        "odds": p.odds, "reasoning": p.reasoning,
                    }
                    for p in db_picks
                ]
                print(f"  → Loaded {len(tips)} tipster picks from DB (TipsterRepo)")
    except Exception as e:
        print(f"  \u26a0 TipsterRepo DB load failed: {e}")  # fall through to JSON

    # JSON fallback if DB had no data
    if not tips:
        consensus_path = DATA_DIR / f"{date}_tipster_consensus.json"
        tipster_path = DATA_DIR / f"tipster_aggregation_{date}.json"

        tipster_data = None
        for tpath in [consensus_path, tipster_path]:
            if tpath.exists():
                try:
                    tipster_data = json.loads(tpath.read_text(encoding="utf-8"))
                    print(f"  → Loaded tipster data from {tpath.name}")
                    break
                except (json.JSONDecodeError, OSError):
                    continue

        if tipster_data is None:
            return True, "No tipster data available — skipping cross-reference"

        # Parse tips — use "all_picks" key (written by tipster_aggregator.py)
        tips = tipster_data if isinstance(tipster_data, list) else tipster_data.get("all_picks", tipster_data.get("tips", []))
    tip_lookup: dict[str, list[dict]] = {}
    for tip in tips:
        home = (tip.get("home") or tip.get("home_team") or "").strip().lower()
        away = (tip.get("away") or tip.get("away_team") or "").strip().lower()
        if home and away:
            key = f"{home}|{away}"
            tip_lookup.setdefault(key, []).append(tip)

    # Load shortlist and cross-reference
    shortlist_path = DATA_DIR / f"{date}_s2_shortlist.json"

    matched = 0
    total = 0
    if shortlist_path.exists():
        try:
            shortlist = json.loads(shortlist_path.read_text(encoding="utf-8"))
            candidates = shortlist.get("candidates", shortlist.get("shortlist", []))
            total = len(candidates)

            for c in candidates:
                home = (c.get("home_team") or "").strip().lower()
                away = (c.get("away_team") or "").strip().lower()
                key = f"{home}|{away}"
                matching_tips = tip_lookup.get(key, [])
                
                if not matching_tips:
                    best_match_tips = []
                    for tip_key, tips_list in tip_lookup.items():
                        parts = tip_key.split("|")
                        if len(parts) == 2:
                            t_home, t_away = parts
                            score_home = fuzz.token_sort_ratio(home, t_home)
                            score_away = fuzz.token_sort_ratio(away, t_away)
                            score_home_swapped = fuzz.token_sort_ratio(home, t_away)
                            score_away_swapped = fuzz.token_sort_ratio(away, t_home)
                            
                            if (score_home >= 70 and score_away >= 70) or (score_home_swapped >= 70 and score_away_swapped >= 70):
                                best_match_tips.extend(tips_list)
                    
                    if best_match_tips:
                        matching_tips = best_match_tips
                        print(f"    ~ Fuzzy matched: {home} vs {away}")

                if matching_tips:
                    matched += 1
                    tipster_names = list({t.get("source_site") or t.get("tipster") or t.get("source") or "unknown" for t in matching_tips})
                    consensus = len(matching_tips)
                    c["tipster_support"] = {
                        "count": consensus,
                        "tipsters": tipster_names,
                        "tips": matching_tips,
                    }
                    # Also set tipster_count directly for gate_checker compatibility
                    c["tipster_count"] = consensus
                    home_disp = c.get("home_team", "?")
                    away_disp = c.get("away_team", "?")
                    print(f"    ✓ {home_disp} vs {away_disp}: {consensus} tips from {', '.join(tipster_names[:3])}")

            # Save enriched shortlist
            shortlist_path.write_text(
                json.dumps(shortlist, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except (json.JSONDecodeError, OSError) as e:
            print(f"  ⚠ Shortlist enrichment error: {e}")

    n_tips = len(tips)
    return True, f"Tipster cross-reference: {n_tips} tips loaded, {matched}/{total} shortlist candidates matched"


# ---------------------------------------------------------------------------
# CLI entry point — agent-friendly
# ---------------------------------------------------------------------------

def main():
    import argparse
    from agent_output import AgentOutput, add_agent_args

    parser = argparse.ArgumentParser(
        description="S2 Tipster Cross-Reference — match tipster picks to shortlist"
    )
    parser.add_argument("--date", required=True, help="Betting date YYYY-MM-DD")
    add_agent_args(parser)
    args = parser.parse_args()

    out = AgentOutput("s2_xref", verbose=args.verbose, stop_on_error=args.stop_on_error)

    ok, msg = run_tipster_xref(args.date, {})

    # Parse metrics from message for structured summary
    # Message format: "Tipster cross-reference: N tips loaded, M/T shortlist candidates matched"
    import re
    m = re.search(r"(\d+) tips loaded, (\d+)/(\d+)", msg)
    metrics = {}
    if m:
        metrics = {"tips_loaded": int(m.group(1)), "matched": int(m.group(2)), "total": int(m.group(3))}
    else:
        metrics = {"tips_loaded": 0, "matched": 0, "total": 0, "skipped": True}

    if args.verbose:
        out.event("xref_result", ok=ok, message=msg, **metrics)

    out.summary(
        verdict="OK" if ok else "FAILED",
        metrics=metrics,
    )

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
