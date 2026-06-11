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

from bet.utils import strip_team_noise
from bet.tipster_registry import get_tipster_source_status


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
        return strip_team_noise(raw)

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
    return strip_team_noise(clean_lines[0] if clean_lines else raw.strip())

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
        return False, f"PRECONDITION_FAILED: tipster_picks DB query failed ({e}). Check DB connectivity, then run tipster_aggregator.py (execution-spine STEP 6)."

    if not tips:
        return False, "PRECONDITION_FAILED: tipster_picks has 0 rows for this date. Run tipster_aggregator.py first (execution-spine STEP 6)."
    # Import smart matching from shared utils
    from bet.utils import normalize_for_matching, names_match

    tip_lookup_by_sport: dict[str, dict[str, list[dict]]] = {}
    global_tip_lookup: dict[str, list[dict]] = {}
    for tip in tips:
        raw_home = tip.get("home") or tip.get("home_team") or ""
        raw_away = tip.get("away") or tip.get("away_team") or ""
        home = normalize_for_matching(_clean_team_name(raw_home))
        away = normalize_for_matching(_clean_team_name(raw_away))
        if home and away:
            key = f"{home}|{away}"
            sport_key = str(tip.get("sport") or "").strip().lower()
            global_tip_lookup.setdefault(key, []).append(tip)
            if sport_key:
                tip_lookup_by_sport.setdefault(sport_key, {}).setdefault(key, []).append(tip)

    # Load shortlist — prefer DB `pipeline_candidates` (R2), then legacy loader, then JSON fallback
    shortlist_path = DATA_DIR / f"{date}_s2_shortlist.json"

    matched = 0
    total = 0
    candidates: list[dict] = []
    shortlist_source = "none"
    shortlist = {}

    # Try modern PipelineCandidateRepo first (DB-first)
    repo = None
    db_ctx = None
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import PipelineCandidateRepo
        db_ctx = get_db()
        conn = db_ctx.__enter__()
        repo = PipelineCandidateRepo(conn)
        try:
            db_candidates = repo.get_by_date(date)
        except Exception:
            db_candidates = []
        if db_candidates:
            candidates = db_candidates
            shortlist_source = "db:pipeline_candidates"
            print(f"  → Loaded {len(candidates)} candidates from pipeline_candidates DB")
    except Exception as e:
        print(f"  ⚠ PipelineCandidateRepo load failed: {e}")

    # Fallback to legacy loader if present
    if not candidates:
        try:
            from db_data_loader import load_shortlist_from_db
            db_candidates = load_shortlist_from_db(date)
            if db_candidates:
                candidates = db_candidates
                shortlist_source = "db:legacy_loader"
                print(f"  → Loaded {len(candidates)} candidates from legacy DB loader")
        except Exception:
            pass

    # Final fallback to JSON file
    if not candidates and shortlist_path.exists():
        try:
            shortlist = json.loads(shortlist_path.read_text(encoding="utf-8"))
            candidates = shortlist.get("candidates", shortlist.get("shortlist", []))
            shortlist_source = "json"
            print(f"  → Loaded {len(candidates)} candidates from JSON (fallback)")
        except (json.JSONDecodeError, OSError) as e:
            print(f"  ⚠ Shortlist JSON load failed: {e}")

    total = len(candidates)
    enriched_count = 0

    # Enrich candidates by robust matching (direct keys, swapped, fuzzy) and persist to DB
    if candidates:
        try:

            # If we have a live PipelineCandidateRepo (from earlier), reuse it; otherwise open a DB context
            repo_ctx2 = None
            repo_obj = None
            try:
                if shortlist_source.startswith("db") and repo is not None:
                    # repo already available in the context above
                    repo_obj = repo
                else:
                    from bet.db.connection import get_db as _get_db
                    from bet.db.repositories import PipelineCandidateRepo as _PCR
                    repo_ctx2 = _get_db()
                    conn2 = repo_ctx2.__enter__()
                    repo_obj = _PCR(conn2)
            except Exception:
                repo_ctx2 = None
                repo_obj = None

            if repo_obj:
                repo_obj.clear_tipster_enrichment(date)

            match_modes = {"exact": 0, "swapped": 0, "fuzzy": 0}
            unmatched_by_sport: dict[str, int] = {}

            for c in candidates:
                raw_home = (c.get("home_team") or "").strip()
                raw_away = (c.get("away_team") or "").strip()
                candidate_sport = str(c.get("sport") or "").strip().lower()
                home_norm = normalize_for_matching(_clean_team_name(raw_home))
                away_norm = normalize_for_matching(_clean_team_name(raw_away))

                found_tips = []
                match_mode = None
                tip_lookup = tip_lookup_by_sport.get(candidate_sport) or global_tip_lookup
                tip_keys = list(tip_lookup.keys())

                # Try exact normalized key
                key = f"{home_norm}|{away_norm}"
                if key in tip_lookup:
                    found_tips = tip_lookup[key]
                    match_mode = "exact"
                else:
                    # Try swapped key
                    swapped = f"{away_norm}|{home_norm}"
                    if swapped in tip_lookup:
                        found_tips = tip_lookup[swapped]
                        match_mode = "swapped"

                # Fuzzy fallback: pick best matching tip_key by names_match score
                if not found_tips and tip_keys:
                    best_score = 0
                    best_tips = []
                    for tip_key in tip_keys:
                        parts = tip_key.split("|")
                        if len(parts) != 2:
                            continue
                        t_home, t_away = parts
                        # Compute pairwise similarity (consider swapped order)
                        score_direct = min(names_match(home_norm, t_home), names_match(away_norm, t_away))
                        score_swapped = min(names_match(home_norm, t_away), names_match(away_norm, t_home))
                        score = max(score_direct, score_swapped)
                        if score > best_score:
                            best_score = score
                            best_tips = tip_lookup[tip_key]

                    # Require stronger fuzzy agreement once sport filtering is applied.
                    if best_score >= 70:
                        found_tips = best_tips
                        match_mode = "fuzzy"
                        print(f"    ~ Smart fuzzy matched: {raw_home} vs {raw_away} → score={best_score}")

                if found_tips:
                    matched += 1
                    if match_mode:
                        match_modes[match_mode] += 1
                    tipster_names = list({t.get("source_site") or t.get("tipster_name") or t.get("source") or "unknown" for t in found_tips})
                    consensus = len(found_tips)
                    c["tipster_support"] = {
                        "count": consensus,
                        "tipsters": tipster_names,
                        "tips": found_tips,
                    }
                    c["tipster_count"] = consensus
                    home_disp = c.get("home_team", "?")
                    away_disp = c.get("away_team", "?")
                    print(f"    ✓ {home_disp} vs {away_disp}: {consensus} tips from {', '.join(tipster_names[:3])}")

                    # Persist to DB using fixture_id when available, otherwise try to resolve by fuzzy match
                    try:
                        if repo_obj:
                            fixture_id = c.get("fixture_id")
                            if fixture_id:
                                repo_obj.enrich_tipster(fixture_id, date, consensus, c["tipster_support"])
                                enriched_count += 1
                            else:
                                # Resolve fixture by fuzzy matching against pipeline_candidates rows
                                rows = repo_obj.get_by_date(date)
                                best_row = None
                                best_row_score = 0
                                for r in rows:
                                    if str(r.get("sport") or "").strip().lower() != candidate_sport:
                                        continue
                                    rh = normalize_for_matching(r.get("home_team", ""))
                                    ra = normalize_for_matching(r.get("away_team", ""))
                                    score_direct = min(names_match(home_norm, rh), names_match(away_norm, ra))
                                    score_swapped = min(names_match(home_norm, ra), names_match(away_norm, rh))
                                    row_score = max(score_direct, score_swapped)
                                    if row_score > best_row_score:
                                        best_row_score = row_score
                                        best_row = r
                                if best_row and best_row_score >= 70:
                                    repo_obj.enrich_tipster(best_row.get("fixture_id"), date, consensus, c["tipster_support"])
                                    enriched_count += 1
                    except Exception as e:
                        print(f"  ⚠ DB enrich attempt failed for {raw_home} vs {raw_away}: {e}")
                else:
                    sport_key = candidate_sport or "unknown"
                    unmatched_by_sport[sport_key] = unmatched_by_sport.get(sport_key, 0) + 1
                    # Unmatched candidates stay at tipster_count=0 / tipster_support_json=NULL
                    # (set by clear_tipster_enrichment before each S2 rerun).
                    # Per-sport status metadata lives in tipster_registry — not on candidate rows.

            # Close any DB contexts we opened
            try:
                if repo_ctx2:
                    repo_ctx2.__exit__(None, None, None)
            except Exception:
                pass
            try:
                if db_ctx:
                    db_ctx.__exit__(None, None, None)
            except Exception:
                pass

            if enriched_count:
                print(f"  → Enriched {enriched_count} pipeline_candidates with tipster data in DB")
            print(
                "  → Match modes: "
                f"exact={match_modes['exact']}, swapped={match_modes['swapped']}, fuzzy={match_modes['fuzzy']}"
            )
            if unmatched_by_sport:
                details = ", ".join(f"{sport}={count}" for sport, count in sorted(unmatched_by_sport.items()))
                print(f"  → Unmatched candidates by sport: {details}")

            # JSON: write back for backward compatibility if we originally loaded JSON
            if shortlist_source == "json" and shortlist:
                try:
                    shortlist_path.write_text(
                        json.dumps(shortlist, indent=2, ensure_ascii=False), encoding="utf-8"
                    )
                    print(f"  → Updated shortlist JSON with tipster support: {shortlist_path}")
                except Exception as e:
                    print(f"  ⚠ Failed to update shortlist JSON: {e}")

        except (json.JSONDecodeError, OSError) as e:
            print(f"  ⚠ Shortlist enrichment error: {e}")

    n_tips = len(tips)
    return True, (
        f"Tipster cross-reference: {n_tips} tips loaded, "
        f"{matched}/{total} shortlist candidates matched, "
        f"db_enriched={enriched_count}, "
        f"json_updated={'yes' if shortlist_source == 'json' and shortlist else 'no'}, "
        f"source={shortlist_source}"
    )


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
    import re
    m = re.search(
        r"(\d+) tips loaded, (\d+)/(\d+) shortlist candidates matched, db_enriched=(\d+), json_updated=(\w+), source=([^\s,]+)",
        msg,
    )
    metrics = {}
    if m:
        metrics = {
            "tips_loaded": int(m.group(1)),
            "matched": int(m.group(2)),
            "total": int(m.group(3)),
            "db_enriched_count": int(m.group(4)),
            "json_updated": m.group(5),
            "shortlist_source": m.group(6),
        }
    else:
        metrics = {"tips_loaded": 0, "matched": 0, "total": 0, "skipped": True, "db_enriched_count": 0}

    if args.verbose:
        out.event("xref_result", ok=ok, message=msg, **metrics)

    # Exit code 2 for precondition failures BEFORE summary (so agent sees it immediately)
    if not ok and "PRECONDITION_FAILED" in msg:
        out.error(msg)
        out.summary(verdict="FAILED", metrics=metrics)
        sys.exit(2)

    out.summary(
        verdict="OK" if ok else "FAILED",
        metrics=metrics,
    )

    try:
        from bet.pipeline import PipelineState
        state = PipelineState.load(args.date)
        state.advance("S2", summary={"tips": metrics.get("tips_loaded", 0), "matches": metrics.get("matched", 0)})
    except Exception:
        pass

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
