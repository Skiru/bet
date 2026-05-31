#!/usr/bin/env python3
"""S2 Tipster Cross-Reference — cross-reference picks with tipster consensus.

Extracted from pipeline_orchestrator.py (Phase 3.3).
"""

import json
import sys
from pathlib import Path
import re as _re
try:
    from rapidfuzz import fuzz
    _RAPIDFUZZ_AVAILABLE = True
except ImportError:
    _RAPIDFUZZ_AVAILABLE = False


# Patterns that indicate garbage lines in scraped team names
_GARBAGE_PATTERNS = [
    _re.compile(r'^\d+\s*-\s*\d+\s+\w+', _re.IGNORECASE),  # "00 - 24 May"
    _re.compile(r'^(view\s+)?prediction', _re.IGNORECASE),       # "Predictions", "View Prediction"
    _re.compile(r'^\d+$'),                                       # bare numbers like "15"
]
_KNOWN_LEAGUES = {
    'premier league', 'la liga', 'serie a', 'serie b', 'bundesliga', 'ligue 1',
    'eredivisie', 'liga acb', 'euroleague', 'mls', 'wnba', 'nba', 'nhl',
    'allsvenskan', 'eliteserien', 'league one', 'league two', 'championship',
    'laliga 2', 'brazil série a', 'brazil série b', 'liga mx', 'liga 1',
    'england', 'spain', 'italy', 'germany', 'france', 'netherlands', 'norway',
    'sweden', 'portugal', 'turkey', 'greece', 'scotland', 'belgium',
}


def _clean_team_name(raw: str) -> str:
    """Extract actual team name from potentially dirty scraper data.

    Dirty examples:
      'West Ham\n\nEngland' → 'West Ham'
      '00 - 24 May\nPremier League\nBrighton' → 'Brighton'
      'Manchester United\nPredictions' → 'Manchester United'
    """
    if not raw:
        return ""
    # Fast path: no newlines = already clean
    if '\n' not in raw and 'Predictions' not in raw:
        return raw.strip()

    lines = [ln.strip() for ln in raw.split('\n') if ln.strip()]
    clean_lines = []
    for ln in lines:
        # Skip known garbage patterns
        if any(p.match(ln) for p in _GARBAGE_PATTERNS):
            continue
        # Skip known league names or country names
        if ln.lower() in _KNOWN_LEAGUES:
            continue
        clean_lines.append(ln)

    # Return first clean line (typically the team name)
    return clean_lines[0] if clean_lines else raw.strip()

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
        print(f"  ⚠ TipsterRepo DB load failed: {e}")

    if not tips:
        return True, "No tipster data in DB — skipping cross-reference"
    # Import smart matching from shared utils
    from bet.utils import normalize_for_matching, names_match

    tip_lookup: dict[str, list[dict]] = {}
    for tip in tips:
        raw_home = tip.get("home") or tip.get("home_team") or ""
        raw_away = tip.get("away") or tip.get("away_team") or ""
        home = normalize_for_matching(_clean_team_name(raw_home))
        away = normalize_for_matching(_clean_team_name(raw_away))
        if home and away:
            key = f"{home}|{away}"
            tip_lookup.setdefault(key, []).append(tip)

    # Load shortlist — DB-first (R2), JSON fallback
    shortlist_path = DATA_DIR / f"{date}_s2_shortlist.json"

    matched = 0
    total = 0
    candidates = []
    shortlist_source = "none"
    shortlist = {}

    # Try pipeline_candidates DB table first
    try:
        from db_data_loader import load_shortlist_from_db
        db_candidates = load_shortlist_from_db(date)
        if db_candidates:
            candidates = db_candidates
            shortlist_source = "db:pipeline_candidates"
            print(f"  → Loaded {len(candidates)} candidates from pipeline_candidates DB")
    except Exception:
        pass

    # Fallback to JSON
    if not candidates and shortlist_path.exists():
        try:
            shortlist = json.loads(shortlist_path.read_text(encoding="utf-8"))
            candidates = shortlist.get("candidates", shortlist.get("shortlist", []))
            shortlist_source = "json"
            print(f"  → Loaded {len(candidates)} candidates from JSON (fallback)")
        except (json.JSONDecodeError, OSError):
            pass

    total = len(candidates)
    if candidates:
        try:
            for c in candidates:
                raw_home = (c.get("home_team") or "").strip()
                raw_away = (c.get("away_team") or "").strip()
                home = normalize_for_matching(raw_home)
                away = normalize_for_matching(raw_away)
                key = f"{home}|{away}"
                matching_tips = tip_lookup.get(key, [])

                # Smart fuzzy matching with names_match (handles diacritics, emoji, surname-only)
                if not matching_tips:
                    best_match_tips = []
                    for tip_key, tips_list in tip_lookup.items():
                        parts = tip_key.split("|")
                        if len(parts) == 2:
                            t_home, t_away = parts
                            score_home = names_match(home, t_home)
                            score_away = names_match(away, t_away)
                            score_home_swapped = names_match(home, t_away)
                            score_away_swapped = names_match(away, t_home)

                            if (score_home >= 70 and score_away >= 70) or (score_home_swapped >= 70 and score_away_swapped >= 70):
                                best_match_tips.extend(tips_list)

                    if best_match_tips:
                        matching_tips = best_match_tips
                        print(f"    ~ Smart matched: {raw_home} vs {raw_away}")

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

            # Save enriched shortlist — DB + JSON
            # DB: enrich pipeline_candidates with tipster data
            try:
                from bet.db.connection import get_db
                from bet.db.repositories import PipelineCandidateRepo
                with get_db() as conn:
                    repo = PipelineCandidateRepo(conn)
                    enriched_count = 0
                    for c in candidates:
                        ts = c.get("tipster_support")
                        if ts and ts.get("count", 0) > 0:
                            home = c.get("home_team", "")
                            away = c.get("away_team", "")
                            repo.enrich_tipster(date, home, away, ts["count"], ts["tipsters"])
                            enriched_count += 1
                    conn.commit()
                    if enriched_count:
                        print(f"  → Enriched {enriched_count} pipeline_candidates with tipster data in DB")
            except Exception as e:
                print(f"  ⚠ DB tipster enrichment failed: {e}")

            # JSON: write back for backward compatibility
            if shortlist_source == "json" and shortlist:
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

    try:
        from bet.pipeline import PipelineState
        state = PipelineState.load(args.date)
        state.advance("S2", summary={"tips": metrics.get("total_tips", 0), "matches": metrics.get("matches", 0)})
    except Exception:
        pass

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
