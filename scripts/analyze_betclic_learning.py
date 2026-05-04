#!/usr/bin/env python3
"""Analyze Betclic bet history for learning patterns.

Reads the parsed betclic_bets_history.json and produces actionable learning
insights: market hit rates, sport performance, coupon-killer analysis,
betting pattern analysis, and rule recommendations.

Usage:
    python3 scripts/analyze_betclic_learning.py
"""
import json
import re
import sys
from pathlib import Path
from collections import Counter, defaultdict

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE.parent / "betting" / "data"
HISTORY_JSON = DATA_DIR / "betclic_bets_history.json"

# Market category mapping (Polish Betclic names -> English categories)
MARKET_CATEGORIES = {
    "Zwycięzca meczu": "match_winner",
    "Wynik meczu": "match_winner",
    "Wynik meczu (z wyłączeniem dogrywki)": "match_winner",
    "Łączna liczba gemów": "game_totals",
    "Gole Powyżej/Poniżej": "totals",
    "Rzuty rożne": "corners",
    "Rzuty rożne (bez dogrywki)": "corners",
    "Suma rzutów rożnych (razem z dogrywką)": "corners",
    "Rzuty rożne (bez dogrywki) -": "team_corners",
    "Oba zespoły strzelą gola": "btts",
    "Suma punktów": "totals",
    "Handicap": "handicap",
    "Handicap setowy": "set_handicap",
    "Liczba kartek": "cards",
    "Liczba fauli w meczu (OPTA)": "fouls",
    "Łączna liczba frejmów": "frame_totals",
    "Podwójna Szansa": "double_chance",
    "Wynik handicap": "handicap",
    "Przewaga dwoma bramkami lub wygrana w meczu (reg. czas)": "win_by_2_or_win",
    "Liczba Runs": "runs_totals",
    "Zawodnik wygra 1. seta 6-0, 6-1, 6-2 lub wygra mecz": "tennis_special",
    "Wynik i gole": "result_and_goals",
    "Liczba goli (Dogrywka i rzuty karne są wliczane do zakładu)": "totals_incl_et",
    "Liczba strzałów w meczu (OPTA)": "shots",
    "Liczba strzałów w meczu (OPTA) -": "team_shots",
    "Liczba celnych strzałów zawodnika (OPTA)": "player_shots",
    "Zwycięzca rywalizacji": "match_winner",
    "Head-to-Head": "match_winner",
    "Liczba rund (0.5 oznacza połowę czasu kolejnej rundy)": "round_totals",
}


def categorize_market(market_name: str) -> str:
    """Map Betclic market name to a standardized category."""
    if not market_name:
        return "unknown"
    # Sort by key length descending to match longest (most specific) first
    for key, cat in sorted(MARKET_CATEGORIES.items(), key=lambda x: -len(x[0])):
        if key in market_name:
            return cat
    # Fallback: check for keywords
    lower = market_name.lower()
    if "rożn" in lower or "corner" in lower:
        return "corners"
    if "kartek" in lower or "card" in lower:
        return "cards"
    if "faul" in lower or "foul" in lower:
        return "fouls"
    if "strzał" in lower or "shot" in lower:
        return "shots"
    if "gem" in lower or "game" in lower:
        return "game_totals"
    if "set" in lower:
        return "set_handicap"
    if "gol" in lower or "bramk" in lower:
        return "totals"
    if "punkt" in lower or "point" in lower:
        return "totals"
    if "handicap" in lower:
        return "handicap"
    return "other"


def is_statistical_market(category: str) -> bool:
    """Check if market category is statistical (not outcome-based)."""
    return category in (
        "corners", "team_corners", "cards", "fouls",
        "game_totals", "frame_totals", "totals", "totals_incl_et",
        "set_handicap", "runs_totals", "shots", "team_shots",
        "player_shots", "round_totals",
    )


def is_over_under(selection: str) -> str:
    """Detect over/under direction from Polish selection text."""
    lower = selection.lower()
    if "powyżej" in lower or "over" in lower:
        return "over"
    if "poniżej" in lower or "under" in lower:
        return "under"
    return "other"


def extract_line(selection: str) -> float:
    """Extract the numeric line from a selection like 'Powyżej 8,5'."""
    m = re.search(r"(\d+[.,]?\d*)", selection)
    if m:
        return float(m.group(1).replace(",", "."))
    return 0.0


def analyze():
    if not HISTORY_JSON.exists():
        print(f"WARNING: Not found: {HISTORY_JSON}")
        print("Run: python3 scripts/parse_betclic_bets.py first")
        print("Continuing with empty history — no learning data available.")
        summary_path = DATA_DIR / "betclic_learning_summary.json"
        summary = {
            "analyzed_at": __import__("datetime").datetime.now().isoformat(),
            "total_coupons": 0, "total_legs": 0, "won": 0, "lost": 0,
            "hit_rate": 0.0, "total_pnl": 0.0, "roi": 0.0,
            "rules_count": 0, "rules": [],
            "warning": "No betclic_bets_history.json found — empty analysis",
        }
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        return [], []

    bets = json.loads(HISTORY_JSON.read_text(encoding="utf-8"))
    if not isinstance(bets, list):
        print(f"ERROR: Expected a JSON array, got {type(bets).__name__}")
        sys.exit(1)
    ended = [b for b in bets if b.get("is_ended", True)]

    print("=" * 80)
    print("BETCLIC BETTING HISTORY — LEARNING ANALYSIS")
    print("=" * 80)

    # ═══════════════════════════════════════════════════
    # 1. OVERALL PERFORMANCE
    # ═══════════════════════════════════════════════════
    total_bets = len(ended)
    won = sum(1 for b in ended if b["coupon_status"] == "won")
    lost = sum(1 for b in ended if b["coupon_status"] == "lost")
    total_staked = sum(b.get("stake_pln", 0) for b in ended)
    total_returned = sum(b.get("tax_free_payout_pln", b.get("winnings_pln", 0)) for b in ended)
    total_pnl = round(total_returned - total_staked, 2)

    print(f"\n§1. OVERALL PERFORMANCE")
    hit_rate = won / (won + lost) * 100 if (won + lost) > 0 else 0
    roi = total_pnl / total_staked * 100 if total_staked > 0 else 0
    print(f"  Coupons: {total_bets} ({won}W / {lost}L) → {hit_rate:.1f}% coupon hit rate")
    print(f"  Staked: {total_staked:.2f} PLN | Returned: {total_returned:.2f} PLN | Net: {total_pnl:+.2f} PLN | ROI: {roi:.1f}%")

    # ═══════════════════════════════════════════════════
    # 2. MARKET HIT RATES
    # ═══════════════════════════════════════════════════
    market_data = defaultdict(lambda: {"won": 0, "lost": 0})
    cat_data = defaultdict(lambda: {"won": 0, "lost": 0})

    all_legs = []
    for b in ended:
        for leg in b.get("legs", []):
            market = leg.get("market", "unknown")
            status = leg.get("leg_status", "unknown")
            cat = categorize_market(market)
            leg["_category"] = cat
            leg["_is_statistical"] = is_statistical_market(cat)
            all_legs.append(leg)

            if status in ("won", "lost"):
                market_data[market][status] += 1
                cat_data[cat][status] += 1

    # Report excluded legs
    missing_status = sum(1 for l in all_legs if l.get("leg_status") not in ("won", "lost", "cancelled"))
    if missing_status > 0:
        print(f"\n  ⚠️  {missing_status} legs excluded from analysis (missing market/status data)")

    print(f"\n§2. MARKET CATEGORY HIT RATES")
    print(f"  {'Category':<25} {'W':>4} {'L':>4} {'Total':>5} {'Rate':>6}  {'Type':<6} Signal")
    print(f"  {'-'*80}")
    for cat, d in sorted(cat_data.items(), key=lambda x: -(x[1]["won"] + x[1]["lost"])):
        total = d["won"] + d["lost"]
        if total == 0:
            continue
        rate = d["won"] / total * 100
        is_stat = "STAT" if is_statistical_market(cat) else "OUTC"
        if rate >= 70:
            signal = "★ STRONG"
        elif rate >= 55:
            signal = "✓ GOOD"
        elif rate >= 40:
            signal = "~ MIXED"
        elif total >= 5:
            signal = "✗ WEAK — REDUCE"
        else:
            signal = "? small sample"
        print(f"  {cat:<25} {d['won']:>4} {d['lost']:>4} {total:>5} {rate:>5.0f}%  {is_stat:<6} {signal}")

    # ═══════════════════════════════════════════════════
    # 3. SPORT HIT RATES
    # ═══════════════════════════════════════════════════
    sport_data = defaultdict(lambda: {"won": 0, "lost": 0})
    for leg in all_legs:
        sport = leg.get("sport", "unknown")
        status = leg.get("leg_status", "unknown")
        if status in ("won", "lost"):
            sport_data[sport][status] += 1

    print(f"\n§3. SPORT HIT RATES")
    print(f"  {'Sport':<20} {'W':>4} {'L':>4} {'Total':>5} {'Rate':>6}  Signal")
    print(f"  {'-'*65}")
    for sport, d in sorted(sport_data.items(), key=lambda x: -(x[1]["won"]+x[1]["lost"])):
        total = d["won"] + d["lost"]
        rate = d["won"] / total * 100 if total > 0 else 0
        if rate < 30 and total >= 5:
            signal = "⛔ AVOID"
        elif rate < 40 and total >= 5:
            signal = "✗ WEAK"
        elif rate >= 65:
            signal = "★ STRONG"
        elif rate >= 50:
            signal = "✓ OK"
        else:
            signal = "~ MIXED"
        print(f"  {sport:<20} {d['won']:>4} {d['lost']:>4} {total:>5} {rate:>5.0f}%  {signal}")

    # ═══════════════════════════════════════════════════
    # 4. STATISTICAL vs OUTCOME MARKETS
    # ═══════════════════════════════════════════════════
    stat_won = sum(1 for l in all_legs if l.get("_is_statistical") and l.get("leg_status") == "won")
    stat_lost = sum(1 for l in all_legs if l.get("_is_statistical") and l.get("leg_status") == "lost")
    outc_won = sum(1 for l in all_legs if not l.get("_is_statistical") and l.get("leg_status") == "won")
    outc_lost = sum(1 for l in all_legs if not l.get("_is_statistical") and l.get("leg_status") == "lost")

    stat_total = stat_won + stat_lost
    outc_total = outc_won + outc_lost

    print(f"\n§4. STATISTICAL vs OUTCOME MARKETS")
    if stat_total > 0:
        print(f"  Statistical markets: {stat_won}W/{stat_lost}L = {stat_won/stat_total*100:.0f}% hit rate ({stat_total} legs)")
    if outc_total > 0:
        print(f"  Outcome markets:     {outc_won}W/{outc_lost}L = {outc_won/outc_total*100:.0f}% hit rate ({outc_total} legs)")
    if stat_total > 0 and outc_total > 0:
        stat_rate = stat_won / stat_total * 100
        outc_rate = outc_won / outc_total * 100
        print(f"  → Statistical markets outperform outcomes by {stat_rate - outc_rate:+.0f} percentage points")

    # ═══════════════════════════════════════════════════
    # 5. OVER/UNDER DIRECTION ANALYSIS
    # ═══════════════════════════════════════════════════
    ou_stats = defaultdict(lambda: {"won": 0, "lost": 0})
    for leg in all_legs:
        sel = leg.get("selection", "")
        direction = is_over_under(sel)
        if direction != "other" and leg.get("leg_status") in ("won", "lost"):
            ou_stats[direction][leg["leg_status"]] += 1

    print(f"\n§5. OVER/UNDER DIRECTION")
    for direction, d in sorted(ou_stats.items()):
        total = d["won"] + d["lost"]
        rate = d["won"] / total * 100 if total > 0 else 0
        print(f"  {direction.upper()}: {d['won']}W/{d['lost']}L = {rate:.0f}% ({total} legs)")

    # ═══════════════════════════════════════════════════
    # 6. COUPON SIZE ANALYSIS
    # ═══════════════════════════════════════════════════
    size_data = defaultdict(lambda: {"won": 0, "lost": 0, "staked": 0, "pnl": 0})
    for b in ended:
        legs = b.get("expected_legs", 1)
        status = b["coupon_status"]
        if status in ("won", "lost"):
            size_data[legs][status] += 1
            size_data[legs]["staked"] += b.get("stake_pln", 0)
            size_data[legs]["pnl"] += b.get("pnl_pln", 0)

    print(f"\n§6. COUPON SIZE ANALYSIS")
    print(f"  {'Legs':>4} {'W':>4} {'L':>4} {'Rate':>6} {'Staked':>8} {'PnL':>8}  Signal")
    print(f"  {'-'*55}")
    for legs in sorted(size_data.keys()):
        d = size_data[legs]
        total = d["won"] + d["lost"]
        rate = d["won"] / total * 100 if total > 0 else 0
        if legs >= 5 and rate == 0:
            signal = "⛔ NEVER HITS"
        elif rate < 10 and total >= 5:
            signal = "✗ TOO RISKY"
        elif rate >= 30:
            signal = "★ SWEET SPOT"
        else:
            signal = "~ OK"
        print(f"  {legs:>4} {d['won']:>4} {d['lost']:>4} {rate:>5.0f}% {d['staked']:>7.2f} {d['pnl']:>+7.2f}  {signal}")

    # ═══════════════════════════════════════════════════
    # 7. COUPON KILLER ANALYSIS
    # ═══════════════════════════════════════════════════
    killer_sports = Counter()
    killer_markets = Counter()
    killer_categories = Counter()
    total_lost_coupons = 0

    for b in ended:
        if b["coupon_status"] != "lost":
            continue
        total_lost_coupons += 1
        legs = b.get("legs", [])
        for leg in legs:
            if leg.get("leg_status") == "lost":
                killer_sports[leg.get("sport", "unknown")] += 1
                killer_markets[leg.get("market", "unknown")] += 1
                killer_categories[categorize_market(leg.get("market", ""))] += 1

    print(f"\n§7. COUPON KILLER ANALYSIS (which legs kill coupons)")
    print(f"  Total lost coupons: {total_lost_coupons}")
    print(f"\n  Top killer sports:")
    for sport, count in killer_sports.most_common(5):
        pct = count / total_lost_coupons * 100 if total_lost_coupons > 0 else 0
        print(f"    {sport}: killed {count} coupon legs ({pct:.0f}% of lost coupons)")
    print(f"\n  Top killer market categories:")
    for cat, count in killer_categories.most_common(8):
        print(f"    {cat}: killed {count} legs")
    print(f"\n  Top killer specific markets:")
    for mkt, count in killer_markets.most_common(8):
        print(f"    {mkt}: {count} kills")

    # ═══════════════════════════════════════════════════
    # 8. SPORT × MARKET CROSS-ANALYSIS
    # ═══════════════════════════════════════════════════
    cross_data = defaultdict(lambda: {"won": 0, "lost": 0})
    for leg in all_legs:
        sport = leg.get("sport", "unknown")
        cat = leg.get("_category", "unknown")
        status = leg.get("leg_status", "unknown")
        if status in ("won", "lost"):
            cross_data[(sport, cat)][status] += 1

    print(f"\n§8. SPORT × MARKET CROSS-ANALYSIS (top 20 by volume)")
    print(f"  {'Sport × Market':<40} {'W':>4} {'L':>4} {'Rate':>6}")
    print(f"  {'-'*60}")
    for (sport, cat), d in sorted(cross_data.items(), key=lambda x: -(x[1]["won"]+x[1]["lost"]))[:20]:
        total = d["won"] + d["lost"]
        rate = d["won"] / total * 100 if total > 0 else 0
        marker = "★" if rate >= 70 and total >= 5 else "✗" if rate < 40 and total >= 5 else ""
        print(f"  {sport} × {cat:<26} {d['won']:>4} {d['lost']:>4} {rate:>5.0f}% {marker}")

    # ═══════════════════════════════════════════════════
    # 9. STAKE EFFICIENCY
    # ═══════════════════════════════════════════════════
    stake_ranges = {"0-1": [0, 1], "1-2": [1, 2], "2-3": [2, 3], "3-5": [3, 5], "5+": [5, 999]}
    stake_perf = defaultdict(lambda: {"won": 0, "lost": 0, "staked": 0, "pnl": 0})
    for b in ended:
        stake = b.get("stake_pln", 0)
        for label, (lo, hi) in stake_ranges.items():
            if lo <= stake < hi:
                key = label
                break
        else:
            key = "5+"
        if b["coupon_status"] in ("won", "lost"):
            stake_perf[key][b["coupon_status"]] += 1
            stake_perf[key]["staked"] += stake
            stake_perf[key]["pnl"] += b.get("pnl_pln", 0)

    print(f"\n§9. STAKE SIZE EFFICIENCY")
    print(f"  {'Stake Range':>12} {'W':>4} {'L':>4} {'Rate':>6} {'Staked':>8} {'PnL':>8}")
    print(f"  {'-'*50}")
    for label in ["0-1", "1-2", "2-3", "3-5", "5+"]:
        d = stake_perf.get(label, {"won": 0, "lost": 0, "staked": 0, "pnl": 0})
        total = d["won"] + d["lost"]
        if total == 0:
            continue
        rate = d["won"] / total * 100
        print(f"  {label:>12} {d['won']:>4} {d['lost']:>4} {rate:>5.0f}% {d['staked']:>7.2f} {d['pnl']:>+7.2f}")

    # ═══════════════════════════════════════════════════
    # 10. KEY LEARNINGS & RULES
    # ═══════════════════════════════════════════════════
    print(f"\n{'='*80}")
    print("§10. KEY LEARNINGS & RECOMMENDED RULES")
    print(f"{'='*80}")

    rules = []

    # Rule: statistical vs outcome
    if stat_total > 0 and outc_total > 0:
        stat_rate = stat_won / stat_total * 100
        outc_rate = outc_won / outc_total * 100
        if stat_rate > outc_rate + 10:
            rules.append(f"✓ CONFIRMED: Statistical markets ({stat_rate:.0f}%) beat outcomes ({outc_rate:.0f}%). Priority: corners, fouls, cards, game totals.")

    # Rule: coupon size
    for legs in sorted(size_data.keys()):
        d = size_data[legs]
        total = d["won"] + d["lost"]
        if total >= 5 and d["won"] == 0:
            rules.append(f"⛔ AKO ({legs}): 0 wins in {total} attempts. STOP using {legs}-leg accumulators.")
        elif total >= 5 and d["won"] / total < 0.10:
            rules.append(f"✗ AKO ({legs}): only {d['won']}/{total} wins ({d['won']/total*100:.0f}%). Limit heavily.")

    # Rule: best sports
    for sport, d in sorted(sport_data.items(), key=lambda x: -(x[1]["won"]+x[1]["lost"])):
        total = d["won"] + d["lost"]
        if total >= 10:
            rate = d["won"] / total * 100
            if rate >= 65:
                rules.append(f"★ {sport}: {rate:.0f}% hit rate on {total} legs. Keep prioritizing.")
            elif rate < 35:
                rules.append(f"⛔ {sport}: only {rate:.0f}% hit rate on {total} legs. Reduce exposure or drop.")

    # Rule: best market categories
    for cat, d in sorted(cat_data.items(), key=lambda x: -(x[1]["won"] + x[1]["lost"])):
        total = d["won"] + d["lost"]
        if total >= 8:
            rate = d["won"] / total * 100
            if rate >= 70:
                rules.append(f"★ {cat}: {rate:.0f}% hit rate on {total} legs. Core market — prioritize.")
            elif rate < 40:
                rules.append(f"✗ {cat}: {rate:.0f}% hit rate on {total} legs. Demote or avoid.")

    # Rule: over vs under
    for direction, d in ou_stats.items():
        total = d["won"] + d["lost"]
        if total >= 10:
            rate = d["won"] / total * 100
            if rate >= 65:
                rules.append(f"★ {direction.upper()} picks: {rate:.0f}% hit rate. Keep preference.")
            elif rate < 40:
                rules.append(f"✗ {direction.upper()} picks: only {rate:.0f}%. Re-evaluate approach.")

    # Rule: worst killers
    for sport, count in killer_sports.most_common(3):
        if count >= 10:
            rules.append(f"✗ {sport} killed {count} coupon legs. Screen more carefully or exclude from AKOs.")

    for i, rule in enumerate(rules, 1):
        print(f"  {i}. {rule}")

    # Report uncategorized markets
    other_markets = [l.get("market") for l in all_legs if l.get("_category") == "other"]
    if other_markets:
        print(f"\n⚠️  Uncategorized markets ({len(other_markets)} legs) — add to MARKET_CATEGORIES:")
        for mkt, count in Counter(other_markets).most_common():
            print(f"    {mkt}: {count}")

    print(f"\n{'='*80}")
    print("END OF LEARNING ANALYSIS")
    print(f"{'='*80}")

    # Write summary artifact for pipeline verification (M8)
    summary_path = DATA_DIR / "betclic_learning_summary.json"
    summary = {
        "analyzed_at": __import__("datetime").datetime.now().isoformat(),
        "total_coupons": total_bets,
        "total_legs": len(all_legs),
        "won": won,
        "lost": lost,
        "hit_rate": round(hit_rate, 1),
        "total_pnl": total_pnl,
        "roi": round(roi, 1),
        "rules_count": len(rules),
        "rules": rules,
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\nSummary artifact: {summary_path}")

    return bets, rules


if __name__ == "__main__":
    analyze()
