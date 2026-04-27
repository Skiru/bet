#!/usr/bin/env python3
"""§0.2 Historical Learning Query — aggregate hit rates for portfolio optimization."""
import csv
import os
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PICKS = os.path.join(ROOT, "betting", "journal", "picks-ledger.csv")
COUPONS = os.path.join(ROOT, "betting", "journal", "coupons-ledger.csv")

def normalize_status(status):
    """Normalize status values: win→won, loss→lost."""
    status = status.strip().lower()
    if status == "win":
        return "won"
    if status == "loss":
        return "lost"
    return status


def analyze_picks():
    if not os.path.exists(PICKS):
        print(f"Picks ledger not found: {PICKS}")
        return

    sport_stats = defaultdict(lambda: {"won": 0, "lost": 0, "void": 0, "push": 0, "pending": 0, "superseded": 0})
    market_stats = defaultdict(lambda: {"won": 0, "lost": 0, "void": 0, "push": 0, "pending": 0})
    day_stats = defaultdict(lambda: {"won": 0, "lost": 0, "void": 0, "push": 0, "pending": 0})
    total = {"won": 0, "lost": 0, "void": 0, "push": 0, "pending": 0, "superseded": 0}
    
    with open(PICKS, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            status = normalize_status(row.get("status", ""))
            sport = row.get("sport", "").strip()
            market = row.get("market", "").strip()
            day = row.get("betting_day", "").strip()
            
            if status in ("superseded", "void"):
                sport_stats[sport][status] += 1
                total[status] += 1
                continue
            
            if status in ("won", "lost", "push", "pending"):
                sport_stats[sport][status] += 1
                market_stats[market][status] += 1
                day_stats[day][status] += 1
                total[status] += 1
    
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
    if not os.path.exists(COUPONS):
        print(f"Coupons ledger not found: {COUPONS}")
        return

    day_stats = defaultdict(lambda: {"won": 0, "lost": 0, "void": 0, "pending": 0, "superseded": 0, "pnl": 0.0, "staked": 0.0})
    total = {"won": 0, "lost": 0, "void": 0, "pending": 0, "superseded": 0, "pnl": 0.0, "staked": 0.0}
    
    with open(COUPONS, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            status = normalize_status(row.get("status", ""))
            day = row.get("betting_day", "").strip()
            pnl_str = row.get("pnl_pln", "").strip()
            stake_str = row.get("stake_pln", "").strip()
            
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

if __name__ == "__main__":
    analyze_picks()
    analyze_coupons()
