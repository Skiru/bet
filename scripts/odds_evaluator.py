#!/usr/bin/env python3
"""S4 Odds Evaluation — cross-validate odds, compute EV, detect drift.

Extracted from pipeline_orchestrator.py (Phase 3.1).
Supports --verbose + AGENT_SUMMARY for agent-driven pipeline (R17/R19).
"""

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths (same as orchestrator)
# ---------------------------------------------------------------------------
SCRIPTS_DIR = Path(__file__).parent
ROOT_DIR = SCRIPTS_DIR.parent
DATA_DIR = ROOT_DIR / "betting" / "data"

# Add scripts/ and src/ to path for imports
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(ROOT_DIR / "src"))

from utils import normalize_team_name as _norm_team


# ---------------------------------------------------------------------------
# ESPN American odds → decimal conversion
# ---------------------------------------------------------------------------
def _convert_espn_odds_to_decimal(odds_data: dict) -> dict:
    """Convert ESPN American odds to decimal format.

    American odds: +X → 1 + X/100; −X → 1 + 100/X
    """
    def _american_to_decimal(american) -> float | None:
        try:
            val = float(american)
        except (ValueError, TypeError):
            return None
        if val > 0:
            return round(1 + val / 100, 3)
        elif val < 0:
            return round(1 + 100 / abs(val), 3)
        return None

    result = {}

    # Moneyline
    ml = odds_data.get("moneyline", {})
    if ml:
        result["moneyline"] = {}
        for side in ("home", "away", "draw"):
            dec = _american_to_decimal(ml.get(side))
            if dec:
                result["moneyline"][side] = dec

    # Total
    total = odds_data.get("total", {})
    if total:
        result["total"] = {"line": total.get("line", "")}
        over_dec = _american_to_decimal(total.get("over_odds"))
        under_dec = _american_to_decimal(total.get("under_odds"))
        if over_dec:
            result["total"]["over"] = over_dec
        if under_dec:
            result["total"]["under"] = under_dec

    # Spread
    spread = odds_data.get("spread", {})
    if spread:
        result["spread"] = {
            "home_line": spread.get("home_line", ""),
            "away_line": spread.get("away_line", ""),
        }
        home_dec = _american_to_decimal(spread.get("home_odds"))
        away_dec = _american_to_decimal(spread.get("away_odds"))
        if home_dec:
            result["spread"]["home"] = home_dec
        if away_dec:
            result["spread"]["away"] = away_dec

    return result


# ---------------------------------------------------------------------------
# EV injection from odds API
# ---------------------------------------------------------------------------
def _inject_ev_from_odds(candidates: list[dict], date: str):
    """Compute and inject EV into candidates using odds API snapshots.

    Sources: SQLite DB (odds_history — 97K+ rows with Betclic PL, Bet365)
    + the-odds-api (odds_api_snapshot.json) + odds-api.io (odds_api_io_snapshot.json)
    + ESPN DraftKings (espn_enrichment_{date}.json).
    EV = (probability × odds) - 1. If no odds snapshot exists, candidates
    keep ev=None and the gate handles it gracefully (stats-first mode).

    The odds_lookup stores:  key = "home|away" -> {
        "market_best": float,   # best ML/totals odds from any bookmaker
        "betclic": float|None,  # Betclic PL odds specifically
        "bet365": float|None,   # Bet365 odds
        "totals": [{line, over, under, bookmaker}],  # totals lines
    }
    """
    odds_lookup: dict[str, dict] = {}

    def _ensure_entry(key: str) -> dict:
        if key not in odds_lookup:
            odds_lookup[key] = {"market_best": 0, "betclic": None, "bet365": None, "totals": []}
        return odds_lookup[key]

    # Source 0: SQLite DB (richest source — Betclic PL + Bet365 + 10+ bookmakers)
    db_path = DATA_DIR / "betting.db"
    if db_path.exists():
        try:
            sys.path.insert(0, str(ROOT_DIR / "src"))
            from bet.db.connection import get_db

            with get_db() as conn:
                cur = conn.cursor()
                cur.execute('''
                    SELECT t1.name, t2.name, o.bookmaker, o.market, o.selection, o.odds, o.line
                    FROM odds_history o
                    JOIN fixtures f ON o.fixture_id = f.id
                    JOIN teams t1 ON f.home_team_id = t1.id
                    JOIN teams t2 ON f.away_team_id = t2.id
                    WHERE date(o.fetched_at) = ?
                ''', (date,))
                db_rows = cur.fetchall()

            # Parse DB odds: group totals lines with their over/under prices
            # DB stores totals as interleaved rows: hdp (line), over (price), under (price)
            totals_buffer: dict[str, dict] = {}  # key -> {current_line, entries}
            for home, away, bookmaker, market, selection, odds_val, line_val in db_rows:
                h = _norm_team(home)
                a = _norm_team(away)
                key = f"{h}|{a}"
                entry = _ensure_entry(key)

                bk_lower = (bookmaker or "").lower()
                is_betclic = "betclic" in bk_lower
                is_bet365 = "bet365" in bk_lower

                if market in ("h2h", "ml"):
                    # ML odds — track market_best (highest) + per-bookmaker
                    if odds_val and odds_val > entry["market_best"]:
                        entry["market_best"] = float(odds_val)
                    sel_lower = (selection or "").lower()
                    if sel_lower in ("draw", "x"):
                        pass  # Skip draw for per-bookmaker tracking
                    elif is_betclic:
                        prev_betclic = entry.get("betclic") or 0
                        if odds_val and odds_val > prev_betclic:
                            entry["betclic"] = float(odds_val)
                    elif is_bet365:
                        prev_bet365 = entry.get("bet365") or 0
                        if odds_val and odds_val > prev_bet365:
                            entry["bet365"] = float(odds_val)

                elif market == "totals":
                    sel_lower = (selection or "").lower()
                    # Format 1: standard Over/Under with line in `line` column
                    if line_val is not None and sel_lower in ("over", "under"):
                        line_f = float(line_val)
                        # Find existing entry for this line+bookmaker, or create
                        found = False
                        for tl in entry["totals"]:
                            if abs(tl.get("line", 0) - line_f) < 0.01 and tl.get("bookmaker") == bookmaker:
                                tl[sel_lower] = float(odds_val)
                                found = True
                                break
                        if not found:
                            new_tl = {"line": line_f, "bookmaker": bookmaker, "over": None, "under": None}
                            new_tl[sel_lower] = float(odds_val)
                            entry["totals"].append(new_tl)

                    # Format 2: Betclic/Bet365 interleaved hdp/over/under (no line column)
                    else:
                        buf_key = f"{key}|{bookmaker}"
                        if buf_key not in totals_buffer:
                            totals_buffer[buf_key] = {"line": None, "over": None, "under": None}
                        buf = totals_buffer[buf_key]

                        if sel_lower == "hdp":
                            # This is the line value (stored in odds column)
                            if buf["line"] is not None and buf["over"] is not None:
                                # Flush previous complete line
                                entry["totals"].append({
                                    "line": buf["line"], "over": buf["over"],
                                    "under": buf["under"], "bookmaker": bookmaker,
                                })
                            buf["line"] = float(odds_val)
                            buf["over"] = None
                            buf["under"] = None
                        elif sel_lower == "over":
                            buf["over"] = float(odds_val)
                        elif sel_lower == "under":
                            buf["under"] = float(odds_val)

                        # Flush complete line
                        if buf["line"] is not None and buf["over"] is not None and buf["under"] is not None:
                            entry["totals"].append({
                                "line": buf["line"], "over": buf["over"],
                                "under": buf["under"], "bookmaker": bookmaker,
                            })
                            totals_buffer[buf_key] = {"line": None, "over": None, "under": None}

            # Flush any remaining incomplete totals buffers (line+over without under)
            for buf_key, buf in totals_buffer.items():
                if buf["line"] is not None and buf["over"] is not None:
                    parts = buf_key.split("|")
                    bk = parts[2] if len(parts) > 2 else "unknown"
                    match_key = f"{parts[0]}|{parts[1]}" if len(parts) > 1 else buf_key
                    if match_key in odds_lookup:
                        odds_lookup[match_key]["totals"].append({
                            "line": buf["line"], "over": buf["over"],
                            "under": buf.get("under"), "bookmaker": bk,
                        })

            if db_rows:
                print(f"  → DB: loaded {len(db_rows)} odds rows → {len(odds_lookup)} fixtures")
        except Exception as e:
            print(f"  ⚠️ DB odds load failed: {e}")

    # Source 1: the-odds-api snapshot
    odds_path = DATA_DIR / "odds_api_snapshot.json"
    if odds_path.exists():
        try:
            odds_data = json.loads(odds_path.read_text(encoding="utf-8"))
            for event in odds_data if isinstance(odds_data, list) else odds_data.get("events", []):
                home = _norm_team(event.get("home_team") or "")
                away = _norm_team(event.get("away_team") or "")
                if not home or not away:
                    continue
                key = f"{home}|{away}"
                entry = _ensure_entry(key)

                # Try pre-computed best_odds first
                best_odds = event.get("best_odds") or event.get("odds", {}).get("market_best")
                if best_odds:
                    val = float(best_odds)
                    if val > entry["market_best"]:
                        entry["market_best"] = val

                # Parse bookmakers array (raw the-odds-api format)
                for bm in event.get("bookmakers") or []:
                    bk_title = (bm.get("title") or bm.get("key") or "").lower()
                    is_betclic = "betclic" in bk_title
                    is_bet365 = "bet365" in bk_title
                    for mkt in bm.get("markets") or []:
                        mkt_key = (mkt.get("key") or "").lower()
                        if mkt_key in ("ml", "h2h", "moneyline"):
                            for outcome in mkt.get("outcomes") or []:
                                price = outcome.get("price")
                                if not price or price <= 1.0:
                                    continue
                                if price > entry["market_best"]:
                                    entry["market_best"] = float(price)
                                side = (outcome.get("name") or "").lower()
                                if side in ("draw", "x"):
                                    continue
                                if is_betclic:
                                    prev = entry.get("betclic") or 0
                                    if price > prev:
                                        entry["betclic"] = float(price)
                                elif is_bet365:
                                    prev = entry.get("bet365") or 0
                                    if price > prev:
                                        entry["bet365"] = float(price)
                        elif mkt_key in ("totals", "over_under"):
                            for outcome in mkt.get("outcomes") or []:
                                price = outcome.get("price")
                                point = outcome.get("point")
                                side = (outcome.get("name") or "").lower()
                                if price and point is not None and side in ("over", "under"):
                                    entry["totals"].append({
                                        "line": float(point),
                                        side: float(price),
                                        "bookmaker": bm.get("title") or bm.get("key"),
                                    })

                # Load pre-computed totals from API snapshot
                api_totals = event.get("totals")
                if api_totals and isinstance(api_totals, list):
                    for tl in api_totals:
                        if tl.get("line") is not None:
                            entry["totals"].append(tl)
        except (json.JSONDecodeError, OSError):
            pass

    # Source 2: odds-api.io snapshot (265 bookmakers, more coverage)
    io_path = DATA_DIR / "odds_api_io_snapshot.json"
    if io_path.exists():
        try:
            io_data = json.loads(io_path.read_text(encoding="utf-8"))
            for event in io_data.get("events", []):
                home = _norm_team(event.get("home") or "")
                away = _norm_team(event.get("away") or "")
                if not home or not away:
                    continue
                key = f"{home}|{away}"
                entry = _ensure_entry(key)
                for bookie_name, markets in (event.get("bookmakers") or {}).items():
                    if not isinstance(markets, list):
                        continue
                    for market in markets:
                        if market.get("name") == "ML":
                            for odds_entry in market.get("odds", []):
                                for side in ["home", "away"]:
                                    try:
                                        val = float(odds_entry.get(side, 0))
                                        if val > entry["market_best"]:
                                            entry["market_best"] = val
                                    except (ValueError, TypeError):
                                        pass
            # Inject from value bets (pre-calculated EV!)
            for vb in io_data.get("value_bets", []):
                ev_data = vb.get("event", {})
                home = _norm_team(ev_data.get("home") or "")
                away = _norm_team(ev_data.get("away") or "")
                if home and away:
                    pre_ev = vb.get("expectedValue")
                    if pre_ev is not None:
                        for c in candidates:
                            ch = _norm_team(c.get("home_team") or "")
                            ca = _norm_team(c.get("away_team") or "")
                            if ch == home and ca == away and c.get("ev") is None:
                                c["ev"] = round(float(pre_ev), 4)
                                c["ev_source"] = "odds-api-io-value-bet"
        except (json.JSONDecodeError, OSError):
            pass

    # Source 3: ESPN DraftKings odds (free, unlimited)
    espn_path = DATA_DIR / f"espn_enrichment_{date}.json"
    if espn_path.exists():
        try:
            espn_data = json.loads(espn_path.read_text(encoding="utf-8"))
            for event in espn_data.get("odds", []):
                home = _norm_team(event.get("home") or "")
                away = _norm_team(event.get("away") or "")
                if not home or not away:
                    continue
                key = f"{home}|{away}"
                entry = _ensure_entry(key)
                dec_odds = event.get("odds_decimal", {}).get("moneyline", {})
                for side in ("home", "away"):
                    val = dec_odds.get(side)
                    if val and val > entry["market_best"]:
                        entry["market_best"] = val
        except (json.JSONDecodeError, OSError):
            pass

    if not odds_lookup:
        return

    injected = 0
    odds_enriched = 0
    for c in candidates:
        home = _norm_team(c.get("home_team") or "")
        away = _norm_team(c.get("away_team") or "")
        key = f"{home}|{away}"
        entry = odds_lookup.get(key)
        # Fuzzy fallback: try substring/containment match if exact key not found
        if not entry:
            for ok, ov in odds_lookup.items():
                parts = ok.split("|", 1)
                if len(parts) != 2:
                    continue
                oh, oa = parts
                # Check containment both ways (e.g. "montreal" in "montreal canadiens")
                h_match = (home in oh or oh in home) and len(home) >= 4 and len(oh) >= 4
                a_match = (away in oa or oa in away) and len(away) >= 4 and len(oa) >= 4
                if h_match and a_match:
                    entry = ov
                    break
        if not entry:
            continue

        # Always inject odds data (even without probability — for coupon builder)
        best_market = c.get("best_market") or {}

        # Determine which odds to use: Betclic first, then Bet365, then market_best
        betclic_odds = entry.get("betclic")
        bet365_odds = entry.get("bet365")
        market_best = entry.get("market_best", 0)
        # Pick best available odds for the candidate
        use_odds = betclic_odds or bet365_odds or (market_best if market_best > 1.0 else None)

        if use_odds:
            c.setdefault("odds", {})["market_best"] = use_odds
            if betclic_odds:
                c["odds"]["betclic"] = betclic_odds
            if bet365_odds:
                c["odds"]["bet365"] = bet365_odds
            odds_enriched += 1

        # Inject totals data for statistical market matching
        if entry.get("totals"):
            c.setdefault("odds", {})["totals"] = entry["totals"]

        # EV calculation (skip if already has EV)
        if c.get("ev") is not None:
            continue
        
        market_name = (best_market.get("name") or "").lower()
        is_ml_market = any(kw in market_name for kw in ("winner", "ml", "match winner", "moneyline", "1x2"))
        is_totals_market = any(kw in market_name for kw in ("o/u", "over", "under", "total", "corners", "fouls", "cards", "shots", "games", "sets", "frames", "points", "goals"))

        prob = best_market.get("probability")
        safety = best_market.get("safety_score")
        
        # For totals/statistical markets, try to find matching line in DB totals
        matched_odds = None
        if is_totals_market and entry.get("totals"):
            line = best_market.get("line")
            direction = (best_market.get("direction") or "").upper()
            if line is not None:
                for tl in entry["totals"]:
                    if abs(tl.get("line", 0) - float(line)) < 0.01:
                        if "OVER" in direction and tl.get("over"):
                            if matched_odds is None or tl["over"] > matched_odds:
                                matched_odds = tl["over"]
                        elif "UNDER" in direction and tl.get("under"):
                            if matched_odds is None or tl["under"] > matched_odds:
                                matched_odds = tl["under"]
        elif is_ml_market:
            # ML market — use ML odds directly
            matched_odds = use_odds
        
        # Only calculate EV when odds match the analyzed market
        p = prob or safety
        odds_for_ev = matched_odds or (use_odds if is_ml_market else None)
        if p and odds_for_ev:
            ev = round(float(p) * float(odds_for_ev) - 1, 4)
            c["ev"] = ev
            c["ev_source"] = "db+api-composite"
            injected += 1

    print(f"  → Odds enriched: {odds_enriched}/{len(candidates)} candidates")
    if injected:
        print(f"  → EV injected: {injected}/{len(candidates)} candidates")


def run_odds_eval(date: str, state: dict) -> tuple[bool, str]:
    """S4: Cross-validate odds, compute EV, detect drift."""
    # Load current candidates from S3 JSON output (primary — has ALL candidates)
    # IMPORTANT: Do NOT read from DB here — DB only has entries with resolved
    # fixture_ids (~166), while JSON has the full set (~1440) including
    # shortlist-fallback candidates.
    candidates = None

    s3_path = DATA_DIR / f"{date}_s3_deep_stats.json"
    if s3_path.exists():
        try:
            s3_data = json.loads(s3_path.read_text(encoding="utf-8"))
            candidates = s3_data.get("analyses", [])
            if candidates:
                print(f"  → JSON: loaded {len(candidates)} S3 analyses")
        except (json.JSONDecodeError, OSError):
            pass

    if not candidates:
        try:
            from db_data_loader import load_analysis_results_from_db
            db_analyses = load_analysis_results_from_db(date)
            if db_analyses:
                candidates = db_analyses
                print(f"  → DB fallback: loaded {len(candidates)} S3 analysis results")
        except Exception as e:
            print(f"  ⚠️ DB read also failed: {e}")

    if not candidates:
        return True, "S4: No S3 data yet — skipping EV injection"

    try:
        _inject_ev_from_odds(candidates, date)

        # Count how many have EV and log details
        with_ev = 0
        positive_ev = 0
        for c in candidates:
            ev = c.get("ev")
            if ev is not None:
                with_ev += 1
                if ev > 0:
                    positive_ev += 1
                home = c.get("home_team", "?")
                away = c.get("away_team", "?")
                odds = (c.get("odds") or {}).get("market_best", 0)
                source = c.get("ev_source", "calculated")
                marker = "💰" if ev > 0 else "📉"
                print(f"    {marker} {home} vs {away}: EV={ev:+.1%} @{odds:.2f} ({source})")
        total = len(candidates)

        # Save back enriched data to JSON (for downstream consumers)
        s3_path = DATA_DIR / f"{date}_s3_deep_stats.json"
        if s3_path.exists():
            try:
                s3_data = json.loads(s3_path.read_text(encoding="utf-8"))
                s3_data["analyses"] = candidates
                s3_path.write_text(
                    json.dumps(s3_data, indent=2, ensure_ascii=False), encoding="utf-8"
                )
            except (json.JSONDecodeError, OSError):
                pass

        # Save EV data back to analysis_results in DB
        try:
            from bet.db.connection import get_db
            from bet.db.repositories import AnalysisResultRepo, FixtureRepo, SportRepo
            with get_db() as conn:
                repo = AnalysisResultRepo(conn)
                existing = repo.get_by_date(date)
                db_lookup = {ar.fixture_id: ar for ar in existing}

                # Build name→fixture_id resolver for candidates without fixture_id
                fixture_repo = FixtureRepo(conn)
                sport_repo = SportRepo(conn)

                def _resolve_fid(c: dict) -> int | None:
                    fid = c.get("fixture_id")
                    if fid:
                        return fid
                    sport_name = c.get("sport", "")
                    s = sport_repo.get_by_name(sport_name) if sport_name else None
                    if not s:
                        return None
                    ko = c.get("kickoff", date)
                    f = fixture_repo.get_by_teams_and_date(
                        c.get("home_team", ""), c.get("away_team", ""),
                        ko[:10] if ko else date, s.id,
                    )
                    return f.id if f else None

                updated = 0
                for c in candidates:
                    ev = c.get("ev")
                    if ev is None:
                        continue
                    fid = _resolve_fid(c)
                    if fid and fid in db_lookup:
                        ar = db_lookup[fid]
                        summary = ar.stats_summary_json or {}
                        summary["ev"] = ev
                        summary["ev_source"] = c.get("ev_source", "calculated")
                        odds_data = c.get("odds", {})
                        if odds_data:
                            summary["odds_market_best"] = odds_data.get("market_best")
                            summary["odds_betclic"] = odds_data.get("betclic")
                        repo.update_stats_summary(fid, date, summary)
                        updated += 1
                    elif fid is None:
                        print(f"  ⚠ S4 DB: fixture_id not resolved for {c.get('home_team', '?')} vs {c.get('away_team', '?')}")
                conn.commit()
                if updated:
                    print(f"  → DB: updated {updated} analysis_results with EV data")
        except Exception as e:
            print(f"  ⚠ DB EV update failed (non-fatal): {e}")

        return True, f"S4 completed: {with_ev}/{total} with EV data ({positive_ev} positive EV)"
    except Exception as e:
        return True, f"S4 odds evaluation error: {e} — continuing without"


# ---------------------------------------------------------------------------
# CLI entry point with --verbose + AGENT_SUMMARY (R17/R19)
# ---------------------------------------------------------------------------
def main():
    from agent_output import AgentOutput, add_agent_args

    parser = argparse.ArgumentParser(
        description="S4 Odds Evaluation — cross-validate odds, compute EV, detect drift"
    )
    parser.add_argument("--date", required=True, help="Betting date YYYY-MM-DD")
    add_agent_args(parser)
    args = parser.parse_args()

    out = AgentOutput("s4_odds_eval", verbose=args.verbose, stop_on_error=args.stop_on_error)

    ok, msg = run_odds_eval(args.date, {})

    # Parse the message for metrics
    import re
    m = re.search(r"(\d+)/(\d+) with EV data \((\d+) positive", msg)
    with_ev = int(m.group(1)) if m else 0
    total = int(m.group(2)) if m else 0
    positive_ev = int(m.group(3)) if m else 0

    if not m:
        # Regex didn't match — error path or unexpected format
        verdict = "PARTIAL" if ok else "FAILED"
    elif positive_ev > 0:
        verdict = "OK"
    elif with_ev > 0:
        verdict = "PARTIAL"
    else:
        verdict = "FAILED"

    # Phase 6: Dropping odds signal
    all_dropping_count = 0
    try:
        from bet.api_clients.unified import UnifiedAPIClient
        
        drop_client = UnifiedAPIClient()
        all_dropping = []
        for s in ["football", "tennis", "basketball", "hockey", "volleyball"]:
            drops = drop_client.get_dropping_odds(s)
            if drops:
                all_dropping.extend(drops)
        drop_client.close()
        
        if all_dropping:
            print(f"  → Phase 6: Found {len(all_dropping)} dropping odds signals")
            all_dropping_count = len(all_dropping)
    except Exception as e:
        print(f"  ⚠ Dropping odds check failed: {e}")

    out.summary(
        verdict=verdict,
        metrics={
            "total_candidates": total,
            "with_ev": with_ev,
            "positive_ev": positive_ev,
            "ev_coverage_pct": round(with_ev / max(total, 1) * 100, 1),
            "dropping_odds_count": all_dropping_count,
        },
        issues=[] if ok else [{"level": "error", "message": msg}],
    )

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
