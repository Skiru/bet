#!/usr/bin/env python3
"""§0.2 Historical Learning Query — aggregate hit rates for portfolio optimization."""
import csv
import os
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PICKS = os.path.join(ROOT, "betting", "journal", "picks-ledger.csv")
COUPONS = os.path.join(ROOT, "betting", "journal", "coupons-ledger.csv")

def normalize_status(status):
    """Normalize status values: win→won, loss→lost, half_win→half_won, etc."""
    status = status.strip().lower()
    if status == "win":
        return "won"
    if status == "loss":
        return "lost"
    if status == "half_win":
        return "half_won"
    if status == "half_loss":
        return "half_lost"
    return status


def analyze_picks():
    # DB-first: try loading bet history from DB
    db_rows = None
    try:
        from db_data_loader import load_betclic_history_from_db
        db_history = load_betclic_history_from_db()
        if db_history:
            # Convert coupon-level DB data to pick-level rows
            db_rows = []
            for coupon in db_history:
                for pick in coupon.get("picks", []):
                    db_rows.append({
                        "sport": pick.get("sport", ""),
                        "market": pick.get("market", ""),
                        "status": pick.get("status", coupon.get("status", "")),
                        "betting_day": coupon.get("placed_at", "")[:10],
                    })
            if db_rows:
                print(f"[historical_learning] DB: loaded {len(db_rows)} pick rows from {len(db_history)} coupons")
    except Exception as e:
        print(f"[historical_learning] DB read failed, falling back to CSV: {e}")

    if not db_rows and not os.path.exists(PICKS):
        print(f"Picks ledger not found: {PICKS}")
        return

    sport_stats = defaultdict(lambda: {"won": 0, "lost": 0, "void": 0, "push": 0, "pending": 0, "superseded": 0})
    market_stats = defaultdict(lambda: {"won": 0, "lost": 0, "void": 0, "push": 0, "pending": 0})
    day_stats = defaultdict(lambda: {"won": 0, "lost": 0, "void": 0, "push": 0, "pending": 0})
    total = {"won": 0, "lost": 0, "void": 0, "push": 0, "pending": 0, "superseded": 0}

    if db_rows:
        rows_iter = db_rows
    else:
        with open(PICKS, encoding="utf-8") as f:
            rows_iter = list(csv.DictReader(f))

    for row in rows_iter:
        status = normalize_status(row.get("status", ""))
        sport = row.get("sport", "").strip()
        market = row.get("market", "").strip()
        day = row.get("betting_day", "").strip()
        
        if status in ("superseded", "void"):
            sport_stats[sport][status] += 1
            total[status] += 1
            continue

        # Count half_won as won and half_lost as lost for statistics
        count_status = status
        if status == "half_won":
            count_status = "won"
        elif status == "half_lost":
            count_status = "lost"

        if count_status in ("won", "lost", "push", "pending"):
            sport_stats[sport][count_status] += 1
            market_stats[market][count_status] += 1
            day_stats[day][count_status] += 1
            total[count_status] += 1
    
    print("=" * 70)
    print("§0.2 HISTORICAL LEARNING QUERY — Full Portfolio Analysis")
    print("=" * 70)
    
    settled = total["won"] + total["lost"]
    print(f"\n── OVERALL ──")
    print(f"Won: {total['won']}  Lost: {total['lost']}  Void: {total['void']}  Push: {total['push']}  Pending: {total['pending']}  Superseded: {total['superseded']}")
    if settled > 0:
        print(f"Hit rate: {total['won']}/{settled} = {100*total['won']/settled:.1f}%")
    
    print(f"\n── BY SPORT (settled only) ──")
    print(f"{'Sport':<20} {'W':>3} {'L':>3} {'V':>3} {'P':>3} {'Pend':>4}  {'Rate':>6}")
    for sport, s in sorted(sport_stats.items(), key=lambda x: -(x[1]["won"]+x[1]["lost"])):
        sw = s["won"] + s["lost"]
        if sw == 0:
            continue
        rate = 100*s["won"]/sw
        print(f"{sport:<20} {s['won']:>3} {s['lost']:>3} {s['void']:>3} {s['push']:>3} {s['pending']:>4}  {rate:>5.1f}%")
    
    print(f"\n── BY MARKET (settled only) ──")
    print(f"{'Market':<25} {'W':>3} {'L':>3} {'V':>3} {'P':>3}  {'Rate':>6}")
    for market, s in sorted(market_stats.items(), key=lambda x: -(x[1]["won"]+x[1]["lost"])):
        sw = s["won"] + s["lost"]
        if sw == 0:
            continue
        rate = 100*s["won"]/sw
        flag = " ⚠️" if rate < 40 else " ✅" if rate >= 60 else ""
        print(f"{market:<25} {s['won']:>3} {s['lost']:>3} {s['void']:>3} {s['push']:>3}  {rate:>5.1f}%{flag}")
    
    print(f"\n── BY DAY ──")
    print(f"{'Day':<12} {'W':>3} {'L':>3} {'V':>3} {'P':>3} {'Pend':>4}  {'Rate':>6}")
    for day, s in sorted(day_stats.items()):
        sw = s["won"] + s["lost"]
        if sw == 0:
            continue
        rate = 100*s["won"]/sw
        print(f"{day:<12} {s['won']:>3} {s['lost']:>3} {s['void']:>3} {s['push']:>3} {s['pending']:>4}  {rate:>5.1f}%")

def analyze_coupons():
    # DB-first: try loading coupon history from DB
    db_rows = None
    try:
        from db_data_loader import load_betclic_history_from_db
        db_history = load_betclic_history_from_db()
        if db_history:
            # Convert coupon-level DB data to coupon rows compatible with CSV format
            db_rows = []
            for coupon in db_history:
                db_rows.append({
                    "status": coupon.get("status", ""),
                    "betting_day": coupon.get("placed_at", "")[:10],
                    "pnl_pln": str(coupon.get("pnl", 0) or 0),
                    "stake_pln": str(coupon.get("stake", 0) or 0),
                })
            if db_rows:
                print(f"[historical_learning] DB: loaded {len(db_rows)} coupon rows")
    except Exception as e:
        print(f"[historical_learning] DB read failed for coupons, falling back to CSV: {e}")

    if not db_rows and not os.path.exists(COUPONS):
        print(f"Coupons ledger not found: {COUPONS}")
        return

    day_stats = defaultdict(lambda: {"won": 0, "lost": 0, "void": 0, "pending": 0, "superseded": 0, "pnl": 0.0, "staked": 0.0})
    total = {"won": 0, "lost": 0, "void": 0, "pending": 0, "superseded": 0, "pnl": 0.0, "staked": 0.0}

    if db_rows:
        rows_iter = db_rows
    else:
        with open(COUPONS, encoding="utf-8") as f:
            rows_iter = list(csv.DictReader(f))

    for row in rows_iter:
        status = normalize_status(row.get("status", ""))
        day = row.get("betting_day", "").strip()
        pnl_str = str(row.get("pnl_pln", "")).strip()
        stake_str = str(row.get("stake_pln", "")).strip()
        
        if status in ("void", "superseded"):
            day_stats[day][status] += 1
            total[status] += 1
            continue
        
        if status in ("won", "lost", "pending"):
            day_stats[day][status] += 1
            total[status] += 1
            
            try:
                pnl = float(pnl_str) if pnl_str else 0.0
                day_stats[day]["pnl"] += pnl
                total["pnl"] += pnl
            except ValueError:
                pass
            
            try:
                stake = float(stake_str) if stake_str else 0.0
                day_stats[day]["staked"] += stake
                total["staked"] += stake
            except ValueError:
                pass
    
    print(f"\n{'='*70}")
    print("COUPON ANALYSIS")
    print(f"{'='*70}")
    
    settled = total["won"] + total["lost"]
    print(f"\nWon: {total['won']}  Lost: {total['lost']}  Void: {total['void']}  Pending: {total['pending']}  Superseded: {total['superseded']}")
    if settled > 0:
        print(f"Coupon hit rate: {total['won']}/{settled} = {100*total['won']/settled:.1f}%")
    print(f"Total PnL: {total['pnl']:+.2f} PLN  |  Total staked: {total['staked']:.2f} PLN")
    if total["staked"] > 0:
        print(f"ROI: {100*total['pnl']/total['staked']:+.1f}%")
    
    print(f"\n── COUPON PnL BY DAY ──")
    print(f"{'Day':<12} {'W':>3} {'L':>3} {'Void':>4} {'PnL':>8} {'Staked':>7} {'ROI':>7}")
    for day, s in sorted(day_stats.items()):
        sw = s["won"] + s["lost"]
        if sw == 0 and s["void"] == 0 and s["superseded"] == 0:
            continue
        roi = 100*s["pnl"]/s["staked"] if s["staked"] > 0 else 0
        print(f"{day:<12} {s['won']:>3} {s['lost']:>3} {s['void']:>4} {s['pnl']:>+7.2f} {s['staked']:>7.2f} {roi:>+6.1f}%")

def analyze_decision_accuracy():
    """§ DECISION ACCURACY ANALYSIS — query decision_outcomes for systematic biases."""
    try:
        from db_data_loader import load_decision_outcomes, get_deviation_stats
    except ImportError:
        print("[learning] Cannot import decision learning functions — skipping accuracy analysis")
        return

    outcomes = load_decision_outcomes(limit=500)
    if not outcomes:
        print(f"\n{'='*70}")
        print("§ DECISION ACCURACY ANALYSIS")
        print(f"{'='*70}")
        print("\n  No decision outcomes available yet.")
        print("  Outcomes are created after settlement when decision snapshots exist.")
        print("  Run: python3 scripts/evaluate_decisions.py --date YYYY-MM-DD")
        return

    print(f"\n{'='*70}")
    print("§ DECISION ACCURACY ANALYSIS")
    print(f"{'='*70}")

    # Filter to outcomes with actual data
    with_values = [o for o in outcomes if o.get("actual_value") is not None and o.get("predicted_value") is not None]
    print(f"\nTotal outcomes: {len(outcomes)} | With actual data: {len(with_values)}")

    if not with_values:
        print("  No outcomes with both predicted and actual values available.")
        return

    # Overall stats (filter out None deviations from predicted_value=0 edge case)
    valid_devs = [o for o in with_values if o["deviation"] is not None and o["deviation_pct"] is not None]
    if not valid_devs:
        print("  No outcomes with valid deviation data.")
        return
    avg_dev = sum(o["deviation"] for o in valid_devs) / len(valid_devs)
    avg_dev_pct = sum(o["deviation_pct"] for o in valid_devs) / len(valid_devs)
    won = sum(1 for o in outcomes if o["result"] == "won")
    lost = sum(1 for o in outcomes if o["result"] == "lost")
    print(f"Average deviation: {avg_dev:+.2f} (actual - predicted)")
    print(f"Average deviation %: {avg_dev_pct:+.1f}%")
    print(f"Overall: {won} won / {lost} lost ({100*won/(won+lost):.1f}% hit rate)" if (won+lost) > 0 else "")

    direction = "OVERESTIMATE" if avg_dev_pct < -5 else "UNDERESTIMATE" if avg_dev_pct > 5 else "ACCURATE"
    print(f"Direction: {direction}")

    # By sport
    print(f"\n── DEVIATION BY SPORT ──")
    print(f"{'Sport':<15} {'N':>4} {'Avg Dev':>8} {'Dev%':>7} {'Won':>4} {'Lost':>4} {'Hit%':>6}")
    sports = sorted(set(o["sport"] for o in with_values))
    for sport in sports:
        group = [o for o in with_values if o["sport"] == sport]
        n = len(group)
        avg = sum(o["deviation"] for o in group) / n
        avg_pct = sum(o["deviation_pct"] for o in group) / n
        w = sum(1 for o in group if o["result"] == "won")
        l = sum(1 for o in group if o["result"] == "lost")
        hit = 100 * w / (w + l) if (w + l) > 0 else 0
        flag = " ⚠️" if abs(avg_pct) > 10 else ""
        print(f"  {sport:<13} {n:>4} {avg:>+7.2f} {avg_pct:>+6.1f}% {w:>4} {l:>4} {hit:>5.1f}%{flag}")

    # By market
    print(f"\n── DEVIATION BY MARKET ──")
    print(f"{'Market':<20} {'N':>4} {'Avg Dev':>8} {'Dev%':>7} {'Won':>4} {'Lost':>4} {'Hit%':>6}")
    markets = sorted(set(o["market"] for o in with_values))
    for market in markets:
        group = [o for o in with_values if o["market"] == market]
        n = len(group)
        avg = sum(o["deviation"] for o in group) / n
        avg_pct = sum(o["deviation_pct"] for o in group) / n
        w = sum(1 for o in group if o["result"] == "won")
        l = sum(1 for o in group if o["result"] == "lost")
        hit = 100 * w / (w + l) if (w + l) > 0 else 0
        flag = " ⚠️ BIAS" if abs(avg_pct) > 10 else ""
        print(f"  {market:<18} {n:>4} {avg:>+7.2f} {avg_pct:>+6.1f}% {w:>4} {l:>4} {hit:>5.1f}%{flag}")

    # By sport × market (key insight)
    print(f"\n── DEVIATION BY SPORT × MARKET (n≥3) ──")
    print(f"{'Combination':<30} {'N':>4} {'Dev%':>7} {'Hit%':>6} {'Bias':>10}")
    sport_market = defaultdict(list)
    for o in with_values:
        sport_market[(o["sport"], o["market"])].append(o)
    for (sport, market), group in sorted(sport_market.items(), key=lambda x: -len(x[1])):
        if len(group) < 3:
            continue
        n = len(group)
        avg_pct = sum(o["deviation_pct"] for o in group) / n
        w = sum(1 for o in group if o["result"] == "won")
        l = sum(1 for o in group if o["result"] == "lost")
        hit = 100 * w / (w + l) if (w + l) > 0 else 0
        if abs(avg_pct) > 10:
            bias = "OVER" if avg_pct < 0 else "UNDER"
            flag = f" ⚠️ {bias}"
        else:
            flag = " ✅"
        combo = f"{sport}×{market}"
        print(f"  {combo:<28} {n:>4} {avg_pct:>+6.1f}% {hit:>5.1f}%{flag}")

    # By competition (league-level insights)
    comp_groups = defaultdict(list)
    for o in with_values:
        if o.get("competition"):
            comp_groups[o["competition"]].append(o)
    relevant_comps = {k: v for k, v in comp_groups.items() if len(v) >= 3}
    if relevant_comps:
        print(f"\n── DEVIATION BY COMPETITION (n≥3) ──")
        print(f"{'Competition':<30} {'N':>4} {'Dev%':>7} {'Hit%':>6}")
        for comp, group in sorted(relevant_comps.items(), key=lambda x: -len(x[1])):
            n = len(group)
            avg_pct = sum(o["deviation_pct"] for o in group) / n
            w = sum(1 for o in group if o["result"] == "won")
            l = sum(1 for o in group if o["result"] == "lost")
            hit = 100 * w / (w + l) if (w + l) > 0 else 0
            flag = " ⚠️" if abs(avg_pct) > 10 else ""
            print(f"  {comp:<28} {n:>4} {avg_pct:>+6.1f}% {hit:>5.1f}%{flag}")

    # Actionable insights
    print(f"\n── ACTIONABLE INSIGHTS (advisory only) ──")
    biased = [(k, v) for k, v in sport_market.items() if len(v) >= 3 and abs(sum(o["deviation_pct"] for o in v) / len(v)) > 10]
    if biased:
        for (sport, market), group in biased:
            n = len(group)
            avg_pct = sum(o["deviation_pct"] for o in group) / n
            direction = "overestimates" if avg_pct < 0 else "underestimates"
            adj = round(-avg_pct / 100, 2)
            print(f"  📊 {sport}×{market}: Model {direction} by {abs(avg_pct):.0f}% (n={n})")
            print(f"     → Suggested adjustment: multiply L10 avg by {1+adj:.2f}")
    else:
        print("  ✅ No significant systematic biases detected (all within ±10%)")
    print(f"  ℹ️  All insights are advisory only — user decides final picks")


if __name__ == "__main__":
    analyze_picks()
    analyze_coupons()
    analyze_decision_accuracy()

    # Also run Betclic history analysis if available
    betclic_json = os.path.join(ROOT, "betting", "data", "betclic_bets_history.json")
    if os.path.exists(betclic_json):
        print(f"\n{'='*70}")
        print("BETCLIC FULL HISTORY AVAILABLE — run for detailed analysis:")
        print(f"  python3 scripts/analyze_betclic_learning.py")
        print(f"  ({betclic_json})")
        print(f"{'='*70}")
