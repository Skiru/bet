#!/usr/bin/env python3
"""Compare scanned Betclic coupon results against pipeline predictions.

Reads VLM-scanned coupon data (from scan_coupon.py) and matches each pick
against our pipeline's predictions (bets table, analysis_results, gate_results).
Produces a deep learning report: what we predicted, what actually happened, why.

Usage:
    # From a single scan JSON:
    PYTHONPATH=src python3 scripts/learn_from_coupons.py --scan betting/coupons/scan_IMG_001.json

    # From batch scan output:
    PYTHONPATH=src python3 scripts/learn_from_coupons.py --scan betting/coupons/batch_scan_screenshots.json

    # From a directory of scan JSONs:
    PYTHONPATH=src python3 scripts/learn_from_coupons.py --dir betting/coupons/

    # Specify betting day for matching context:
    PYTHONPATH=src python3 scripts/learn_from_coupons.py --scan file.json --date 2026-05-28
"""
import argparse
import json
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from bet.utils import names_match

BASE = Path(__file__).resolve().parent.parent
DB_PATH = BASE / "betting" / "data" / "betting.db"
JOURNAL_DIR = BASE / "betting" / "journal"
COUPONS_DIR = BASE / "betting" / "coupons"


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def load_scan_data(path: Path) -> list[dict]:
    """Load scanned coupon data — handles single coupon or batch array."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    return [data]


def load_scans_from_dir(dir_path: Path) -> list[dict]:
    """Load all scan JSONs from a directory."""
    results = []
    for f in sorted(dir_path.glob("scan_*.json")):
        results.extend(load_scan_data(f))
    for f in sorted(dir_path.glob("batch_scan_*.json")):
        results.extend(load_scan_data(f))
    return results


def match_pick_to_bet(pick: dict, bets: list[dict]) -> dict | None:
    """Match a scanned pick to a bet in our DB using fuzzy event + market matching.

    Two-pass strategy:
    1. Match on event name (fuzzy)
    2. Among event matches, prefer the one with matching market type
    """
    pick_event = pick.get("event", "")
    pick_market = (pick.get("market") or "").lower()
    if not pick_event:
        return None

    # Collect all event matches above threshold
    candidates = []
    for bet in bets:
        bet_event = bet["event_name"] or ""
        score = names_match(pick_event.lower(), bet_event.lower(), threshold=55)
        if score >= 55:
            candidates.append((score, bet))

    if not candidates:
        return None

    # If only one match, return it
    if len(candidates) == 1:
        return candidates[0][1]

    # Multiple matches for same event — prefer market match
    for score, bet in sorted(candidates, key=lambda x: -x[0]):
        bet_market = (bet["market"] or "").lower()
        # Check if markets are compatible (fuzzy)
        if _markets_similar(pick_market, bet_market):
            return bet

    # Fall back to best event match
    return max(candidates, key=lambda x: x[0])[1]


def _markets_similar(scan_market: str, db_market: str) -> bool:
    """Check if a scanned market name matches a DB market name (loose matching)."""
    if not scan_market or not db_market:
        return False

    # Normalize common terms
    m1 = scan_market.replace("/", " ").replace("-", " ").lower()
    m2 = db_market.replace("/", " ").replace("-", " ").lower()

    # Direct containment
    if m1 in m2 or m2 in m1:
        return True

    # Category mapping for common Betclic Polish → English translations
    market_aliases = {
        "over": ["powyżej", "over", "o ", "więcej"],
        "under": ["poniżej", "under", "u ", "mniej"],
        "winner": ["zwycięzca", "winner", "1x2", "match winner", "wynik meczu"],
        "corners": ["rożne", "corner", "rzuty rożne"],
        "cards": ["kartki", "card", "kartek"],
        "totals": ["total", "łączn", "suma", "gole powyżej"],
        "handicap": ["handicap", "fory"],
        "btts": ["oba zespoły", "btts", "both teams"],
    }

    for _category, aliases in market_aliases.items():
        m1_match = any(a in m1 for a in aliases)
        m2_match = any(a in m2 for a in aliases)
        if m1_match and m2_match:
            return True

    return False


def build_fixture_name_cache(analyses: list[dict], conn) -> dict[int, str]:
    """Pre-load fixture names for all analysis fixture_ids in one query."""
    if not analyses:
        return {}
    fixture_ids = list({a["fixture_id"] for a in analyses if a.get("fixture_id")})
    if not fixture_ids:
        return {}

    placeholders = ",".join("?" * len(fixture_ids))
    rows = conn.execute(
        f"""SELECT f.id, t1.name as home_team, t2.name as away_team
            FROM fixtures f
            JOIN teams t1 ON f.home_team_id = t1.id
            JOIN teams t2 ON f.away_team_id = t2.id
            WHERE f.id IN ({placeholders})""",
        fixture_ids
    ).fetchall()
    return {row["id"]: f"{row['home_team']} vs {row['away_team']}" for row in rows}


def match_pick_to_analysis(pick: dict, analyses: list[dict], fixture_names: dict[int, str]) -> dict | None:
    """Match a scanned pick to an analysis_result via pre-cached fixture names."""
    pick_event = pick.get("event", "")
    if not pick_event:
        return None

    best_match = None
    best_score = 0

    for analysis in analyses:
        fixture_id = analysis["fixture_id"]
        fixture_name = fixture_names.get(fixture_id)
        if not fixture_name:
            continue
        score = names_match(pick_event.lower(), fixture_name.lower(), threshold=55)
        if score > best_score and score >= 55:
            best_score = score
            best_match = analysis

    return dict(best_match) if best_match else None


def build_learning_entry(pick: dict, matched_bet: dict | None, matched_analysis: dict | None) -> dict:
    """Build a learning entry comparing prediction vs outcome."""
    entry = {
        "event": pick.get("event"),
        "market": pick.get("market"),
        "selection": pick.get("selection"),
        "odds_placed": pick.get("odds"),
        "actual_status": pick.get("status", "unknown"),
    }

    if matched_bet:
        safety = matched_bet.get("safety_score")
        hit_rate = matched_bet.get("hit_rate")

        entry["prediction"] = {
            "market_predicted": matched_bet.get("market"),
            "selection_predicted": matched_bet.get("selection"),
            "odds_predicted": matched_bet.get("odds"),
            "safety_score": safety,
            "hit_rate": hit_rate,
            "stats_detail": matched_bet.get("stats_detail"),
        }
        # Determine if prediction was correct
        if pick.get("status") in ("won", "lost"):
            entry["prediction_correct"] = pick["status"] == "won"
        else:
            entry["prediction_correct"] = None

        # Learning signals — guard against None values
        pick_status = pick.get("status")
        if pick_status == "lost" and safety is not None:
            if safety >= 7.0:
                entry["learning_signal"] = "HIGH_CONFIDENCE_LOSS"
                hr_str = f"{hit_rate:.0%}" if isinstance(hit_rate, (int, float)) and hit_rate is not None else "N/A"
                entry["learning_note"] = (
                    f"Lost despite safety_score={safety:.1f}, "
                    f"hit_rate={hr_str}. Investigate: was the model "
                    f"over-relying on historical averages vs actual line coverage?"
                )
            elif safety >= 5.0:
                entry["learning_signal"] = "MODERATE_LOSS"
            else:
                entry["learning_signal"] = "EXPECTED_RISK_LOSS"
        elif pick_status == "won" and safety is not None:
            if safety < 5.0:
                entry["learning_signal"] = "LOW_CONFIDENCE_WIN"
                entry["learning_note"] = (
                    f"Won despite low safety_score={safety:.1f}. "
                    f"The pick had genuine edge that the model undervalued."
                )
            else:
                entry["learning_signal"] = "CONFIRMED_EDGE"
        elif pick_status == "won":
            entry["learning_signal"] = "WIN_NO_SCORE"
        elif pick_status == "lost":
            entry["learning_signal"] = "LOSS_NO_SCORE"
        else:
            entry["learning_signal"] = "PENDING"
    else:
        entry["prediction"] = None
        entry["learning_signal"] = "UNMATCHED"
        entry["learning_note"] = "Pick not found in pipeline predictions — manual bet or different day?"

    if matched_analysis and not matched_bet:
        entry["analysis_context"] = {
            "best_market": matched_analysis.get("best_market_name"),
            "best_line": matched_analysis.get("best_market_line"),
            "best_direction": matched_analysis.get("best_market_direction"),
            "safety_score": matched_analysis.get("best_safety_score"),
        }

    return entry


def compute_learning_summary(entries: list[dict]) -> dict:
    """Aggregate learning signals into actionable insights."""
    total = len(entries)
    matched = sum(1 for e in entries if e.get("prediction"))
    won = sum(1 for e in entries if e.get("actual_status") == "won")
    lost = sum(1 for e in entries if e.get("actual_status") == "lost")

    high_conf_losses = [e for e in entries if e.get("learning_signal") == "HIGH_CONFIDENCE_LOSS"]
    low_conf_wins = [e for e in entries if e.get("learning_signal") == "LOW_CONFIDENCE_WIN"]
    confirmed_edges = [e for e in entries if e.get("learning_signal") == "CONFIRMED_EDGE"]

    # Market performance breakdown
    market_stats = {}
    for e in entries:
        market = e.get("market") or "unknown"
        if market not in market_stats:
            market_stats[market] = {"won": 0, "lost": 0, "total": 0}
        market_stats[market]["total"] += 1
        if e.get("actual_status") == "won":
            market_stats[market]["won"] += 1
        elif e.get("actual_status") == "lost":
            market_stats[market]["lost"] += 1

    # PnL estimation (where we have odds)
    estimated_pnl = 0.0
    pnl_computed = 0
    for e in entries:
        odds = e.get("odds_placed")
        status = e.get("actual_status")
        stake = e.get("stake")
        if odds and stake and status in ("won", "lost"):
            if status == "won":
                estimated_pnl += stake * (odds - 1)
            else:
                estimated_pnl -= stake
            pnl_computed += 1

    # Safety score accuracy — do high scores correlate with wins?
    safety_bins = {"high_7plus": {"won": 0, "lost": 0}, "mid_5_7": {"won": 0, "lost": 0}, "low_under_5": {"won": 0, "lost": 0}}
    for e in entries:
        pred = e.get("prediction")
        if not pred:
            continue
        safety = pred.get("safety_score")
        status = e.get("actual_status")
        if safety is None or status not in ("won", "lost"):
            continue
        if safety >= 7.0:
            safety_bins["high_7plus"][status] += 1
        elif safety >= 5.0:
            safety_bins["mid_5_7"][status] += 1
        else:
            safety_bins["low_under_5"][status] += 1

    return {
        "total_picks_scanned": total,
        "matched_to_predictions": matched,
        "unmatched": total - matched,
        "won": won,
        "lost": lost,
        "hit_rate_pct": round(won / (won + lost) * 100, 1) if (won + lost) > 0 else 0,
        "estimated_pnl": round(estimated_pnl, 2),
        "pnl_picks_counted": pnl_computed,
        "high_confidence_losses": len(high_conf_losses),
        "low_confidence_wins": len(low_conf_wins),
        "confirmed_edges": len(confirmed_edges),
        "safety_score_accuracy": safety_bins,
        "market_breakdown": market_stats,
        "critical_learnings": [e["learning_note"] for e in entries if e.get("learning_note")],
    }


def main():
    parser = argparse.ArgumentParser(description="Learn from scanned coupon results vs predictions")
    parser.add_argument("--scan", help="Path to scan JSON (single or batch)")
    parser.add_argument("--dir", help="Directory of scan JSONs to process")
    parser.add_argument("--date", help="Betting day (YYYY-MM-DD) for matching context")
    parser.add_argument("--save", action="store_true", help="Save learning report")
    args = parser.parse_args()

    if not args.scan and not args.dir:
        parser.error("Provide --scan <file.json> or --dir <directory>")

    # Load scanned data
    if args.scan:
        scan_path = Path(args.scan)
        if not scan_path.exists():
            print(f"Error: {scan_path} not found", file=sys.stderr)
            sys.exit(1)
        scanned_coupons = load_scan_data(scan_path)
    else:
        dir_path = Path(args.dir)
        if not dir_path.is_dir():
            print(f"Error: {dir_path} is not a directory", file=sys.stderr)
            sys.exit(1)
        scanned_coupons = load_scans_from_dir(dir_path)

    if not scanned_coupons:
        print("No scanned coupon data found.", file=sys.stderr)
        sys.exit(1)

    # Determine betting date for DB query scope
    betting_date = args.date or date.today().isoformat()

    conn = get_db()

    # Load our predictions from DB — strict date match first, then ±1 day fallback
    bets = [dict(row) for row in conn.execute(
        """SELECT b.*, c.coupon_id as coupon_ref, c.placed_at
           FROM bets b
           JOIN coupons c ON b.coupon_id = c.id
           WHERE c.placed_at LIKE ?""",
        (f"{betting_date}%",)
    ).fetchall()]

    # If no bets found for exact date, try ±1 day (coupons placed night before)
    if not bets:
        from datetime import timedelta
        dt = datetime.strptime(betting_date, "%Y-%m-%d")
        prev_day = (dt - timedelta(days=1)).strftime("%Y-%m-%d")
        next_day = (dt + timedelta(days=1)).strftime("%Y-%m-%d")
        bets = [dict(row) for row in conn.execute(
            """SELECT b.*, c.coupon_id as coupon_ref, c.placed_at
               FROM bets b
               JOIN coupons c ON b.coupon_id = c.id
               WHERE c.placed_at LIKE ? OR c.placed_at LIKE ?""",
            (f"{prev_day}%", f"{next_day}%")
        ).fetchall()]
        if bets:
            print(f"  (no bets for {betting_date}, using ±1 day: found {len(bets)})", file=sys.stderr)

    analyses = [dict(row) for row in conn.execute(
        "SELECT * FROM analysis_results WHERE betting_date = ?",
        (betting_date,)
    ).fetchall()]

    # Pre-cache fixture names for analysis matching (avoids O(N*M) DB queries)
    fixture_names = build_fixture_name_cache(analyses, conn)

    print(f"Loaded {len(bets)} bets, {len(analyses)} analyses, {len(fixture_names)} fixtures for {betting_date}", file=sys.stderr)

    # Process each scanned coupon
    all_entries = []
    for coupon_data in scanned_coupons:
        if coupon_data.get("_parse_failed"):
            continue
        picks = coupon_data.get("picks", [])
        coupon_status = coupon_data.get("status", "unknown")
        coupon_stake = coupon_data.get("stake")

        for pick in picks:
            matched_bet = match_pick_to_bet(pick, bets)
            matched_analysis = match_pick_to_analysis(pick, analyses, fixture_names) if not matched_bet else None
            entry = build_learning_entry(pick, matched_bet, matched_analysis)
            entry["coupon_status"] = coupon_status
            entry["coupon_type"] = coupon_data.get("coupon_type")
            entry["stake"] = coupon_stake
            all_entries.append(entry)

    conn.close()

    # Build learning report
    summary = compute_learning_summary(all_entries)
    report = {
        "generated_at": datetime.now().isoformat(),
        "betting_date": betting_date,
        "summary": summary,
        "entries": all_entries,
    }

    formatted = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    print(formatted)

    if args.save:
        out_dir = JOURNAL_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{betting_date}-coupon-learning.json"
        out_file.write_text(formatted)
        print(f"\nSaved learning report to {out_file}", file=sys.stderr)

    # Print actionable summary to stderr
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"LEARNING SUMMARY — {betting_date}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"  Picks scanned:       {summary['total_picks_scanned']}", file=sys.stderr)
    print(f"  Matched to pipeline: {summary['matched_to_predictions']}", file=sys.stderr)
    print(f"  Hit rate:            {summary['hit_rate_pct']}% ({summary['won']}W / {summary['lost']}L)", file=sys.stderr)
    print(f"  Estimated PnL:       {summary['estimated_pnl']:+.2f} PLN ({summary['pnl_picks_counted']} picks)", file=sys.stderr)
    print(f"  High-conf losses:    {summary['high_confidence_losses']} ← INVESTIGATE", file=sys.stderr)
    print(f"  Low-conf wins:       {summary['low_confidence_wins']} ← MODEL UNDERVALUED", file=sys.stderr)
    print(f"  Confirmed edges:     {summary['confirmed_edges']}", file=sys.stderr)

    # Safety score correlation
    sa = summary.get("safety_score_accuracy", {})
    if any(sa[k]["won"] + sa[k]["lost"] > 0 for k in sa):
        print(f"\n  SAFETY SCORE CALIBRATION:", file=sys.stderr)
        for label, key in [("  7+  (high)", "high_7plus"), ("  5-7 (mid)", "mid_5_7"), ("  <5  (low)", "low_under_5")]:
            w, l = sa[key]["won"], sa[key]["lost"]
            total_bin = w + l
            hr = f"{w/total_bin*100:.0f}%" if total_bin > 0 else "N/A"
            print(f"    {label}: {w}W/{l}L = {hr} hit rate", file=sys.stderr)

    if summary["critical_learnings"]:
        print(f"\n  CRITICAL LEARNINGS:", file=sys.stderr)
        for note in summary["critical_learnings"][:5]:
            print(f"    • {note}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)


if __name__ == "__main__":
    main()
