#!/usr/bin/env python3
"""Parse Betclic /my-bets HTML export into structured JSON for learning analysis.

Reads an HTML file saved from betclic.pl/my-bets (with all cards expanded)
and produces a structured JSON with all bet cards, legs, markets, and results.

Usage:
    python3 scripts/parse_betclic_bets.py
    python3 scripts/parse_betclic_bets.py --input betting/data/betclic_mybets/Betclic.html
"""
import sys
import json
import re
import argparse
from pathlib import Path
from collections import Counter

import shutil
from datetime import datetime

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE.parent / "betting" / "data"
DEFAULT_INPUT = DATA_DIR / "betclic_mybets" / "Betclic.html"
OUTPUT_JSON = DATA_DIR / "betclic_bets_history.json"

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("BeautifulSoup not available. Install: pip install beautifulsoup4")
    sys.exit(1)


def parse_amount(text: str) -> float:
    """Parse Polish-format amount like '12,07 zł' to float."""
    if not text:
        return 0.0
    cleaned = text.replace("zł", "").replace(" ", "").replace(",", ".").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def parse_odds(text: str) -> float:
    """Parse odds like '5,59' or '5.59' to float."""
    if not text:
        return 0.0
    cleaned = text.replace(",", ".").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def detect_sport(element) -> str:
    """Detect sport from icon_sport_* class on a market element."""
    icon = element.find("span", class_=lambda c: c and "icon_sport_" in c)
    if icon:
        for cls in icon.get("class", []):
            if cls.startswith("icon_sport_"):
                return cls.replace("icon_sport_", "")
    return "unknown"


def parse_leg_status(label_el) -> str:
    """Determine leg status from CSS classes on the selection label."""
    if not label_el:
        return "unknown"
    cls = label_el.get("class", [])
    if "is-lost" in cls or "is-loser" in cls:
        return "lost"
    if "is-won" in cls or "is-winner" in cls:
        return "won"
    if "is-void" in cls or "is-cancelled" in cls:
        return "cancelled"
    return "unknown"  # safer default — let analyzer handle


def parse_card(card) -> dict:
    """Parse a single bet-card element into structured data."""
    d = {}

    # Header: bet type
    header = card.find(class_="betCard_headerTitle")
    d["bet_type"] = header.get_text(strip=True) if header else ""

    # Extract leg count from bet type (e.g., "AKO (4)" -> 4)
    m = re.search(r"\((\d+)\)", d["bet_type"])
    d["expected_legs"] = int(m.group(1)) if m else 1

    # Wrapper div — status flags
    wrapper = card.find(class_="betCard")
    if wrapper:
        cls = wrapper.get("class", [])
        d["ref_id"] = wrapper.get("data-qa", "")
        if "is-won" in cls:
            d["coupon_status"] = "won"
        elif "is-lost" in cls:
            d["coupon_status"] = "lost"
        elif "is-cashout" in cls:
            d["coupon_status"] = "cashout"
        else:
            d["coupon_status"] = "pending"
        d["is_ended"] = "is-ended" in cls
        d["is_betbuilder"] = "is-betbuilder" in cls
        d["is_combined"] = "is-combined" in cls
    else:
        d["ref_id"] = ""
        d["coupon_status"] = "unknown"
        d["is_ended"] = False
        d["is_betbuilder"] = False
        d["is_combined"] = False

    # Status tag label
    tag = card.find(class_="tag_label")
    d["status_label"] = tag.get_text(strip=True) if tag else ""

    # Leg status icons
    leg_icons = []
    for si in card.find_all(class_="statusBets_listItem"):
        icon = si.find("span", class_="icons")
        if icon:
            cls = icon.get("class", [])
            if "icon_betWinner" in cls:
                leg_icons.append("won")
            elif "icon_betLost" in cls:
                leg_icons.append("lost")
            elif "icon_betCancelled" in cls:
                leg_icons.append("cancelled")
            elif "icon_liveMatch" in cls:
                leg_icons.append("live")
            else:
                leg_icons.append("unknown")
    d["leg_status_icons"] = leg_icons

    # Summary: odds, stake, winnings
    odds_el = card.find(class_="is-totalOdds")
    if odds_el:
        # May contain multiple odds (boosted)
        btns = odds_el.find_all(class_="btn_label")
        d["total_odds"] = parse_odds(btns[-1].get_text(strip=True)) if btns else 0.0
        if len(btns) > 1:
            d["original_odds"] = parse_odds(btns[0].get_text(strip=True))

    stake_el = card.find(class_="is-stake")
    if stake_el:
        val = stake_el.find(class_="summaryBets_listItemValue")
        d["stake_pln"] = parse_amount(val.get_text(strip=True)) if val else 0.0

    win_el = card.find(class_="is-winnings")
    if win_el:
        val = win_el.find(class_="summaryBets_listItemValue")
        d["winnings_pln"] = parse_amount(val.get_text(strip=True)) if val else 0.0

    taxfree_el = card.find(class_="is-taxFree")
    if taxfree_el:
        val = taxfree_el.find(class_="summaryBets_listItemValue")
        d["tax_free_payout_pln"] = parse_amount(val.get_text(strip=True)) if val else 0.0

    # Footer: ref + date
    footer = card.find(class_="betCard_footerInfos")
    if footer:
        spans = footer.find_all("span")
        for s in spans:
            txt = s.get_text(strip=True)
            if "Ref" in txt:
                d["footer_ref"] = txt.replace("Ref", "").strip()
            elif re.match(r"\d{2}\.\d{2}\.\d{4}", txt):
                d["placed_date"] = txt

    # Parse legs (bet-card-event-market containers)
    d["legs"] = []
    event_markets = card.find_all("bet-card-event-market")
    for em in event_markets:
        leg = {}

        # Market info
        mc = em.find("bet-card-market-classic") or em.find("bet-card-market-combo")
        if mc:
            leg["sport"] = detect_sport(mc)

            sel = mc.find(class_="marketBets_label")
        else:
            leg["_parse_warning"] = "no market container found"
            sel = None

        if mc and sel:
            # Selection text (what was bet on)
            sel_text = sel.get_text(strip=True)
            leg["selection"] = sel_text
            leg["leg_status"] = parse_leg_status(sel)

        if mc:
            mkt = mc.find(class_="marketBets_value")
            if mkt:
                leg["market"] = mkt.get_text(strip=True)

            odds_btn = mc.find(class_="btn_label")
            if odds_btn:
                leg["odds"] = parse_odds(odds_btn.get_text(strip=True))

            # For combo/betbuilder, get all label-value pairs
            labels = mc.find_all(class_="marketBets_label")
            values = mc.find_all(class_="marketBets_value")
            if len(labels) > 1:
                leg["combo_selections"] = []
                for lbl, val in zip(labels, values):
                    leg["combo_selections"].append({
                        "selection": lbl.get_text(strip=True),
                        "market": val.get_text(strip=True),
                        "status": parse_leg_status(lbl),
                    })

        # Event info (match details)
        ev = em.find("bet-card-event")
        if ev:
            c1 = ev.find(attrs={"data-qa": "contestant-1-label"})
            c2 = ev.find(attrs={"data-qa": "contestant-2-label"})
            leg["home"] = c1.get_text(strip=True) if c1 else ""
            leg["away"] = c2.get_text(strip=True) if c2 else ""

            score_el = ev.find(attrs={"data-qa": "scoreboard-score"})
            if score_el:
                scores = score_el.find_all("span", class_=re.compile(r"scoreboard_score"))
                if len(scores) >= 2:
                    leg["score_home"] = scores[0].get_text(strip=True)
                    leg["score_away"] = scores[1].get_text(strip=True)
                leg["score"] = score_el.get_text(strip=True)

            time_el = ev.find(class_="event_infoTime")
            if time_el:
                leg["event_time"] = time_el.get_text(strip=True)

        d["legs"].append(leg)

    # Calculate PnL
    d["pnl_pln"] = round(
        d.get("tax_free_payout_pln", d.get("winnings_pln", 0.0)) - d.get("stake_pln", 0.0),
        2,
    )

    return d


def main():
    parser = argparse.ArgumentParser(description="Parse Betclic bet history HTML")
    parser.add_argument("--input", type=str, default=str(DEFAULT_INPUT),
                        help="Path to Betclic.html file")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"File not found: {input_path}")
        sys.exit(1)

    print(f"Parsing: {input_path}")
    html = input_path.read_text(encoding="utf-8")

    if "bet-card" not in html[:10000]:
        print("WARNING: File doesn't look like Betclic HTML (no 'bet-card' found in first 10KB)")

    soup = BeautifulSoup(html, "html.parser")

    cards = soup.find_all("bet-card")
    print(f"Found {len(cards)} bet cards")

    bets = [parse_card(card) for card in cards]

    # Backup existing output before overwriting
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_JSON.exists():
        backup = OUTPUT_JSON.with_suffix(f".{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak.json")
        shutil.copy2(OUTPUT_JSON, backup)
        print(f"Backup: {backup}")

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(bets, f, ensure_ascii=False, indent=2)
    print(f"Saved: {OUTPUT_JSON}")

    # Print summary statistics
    print("\n" + "=" * 70)
    print("BETCLIC BET HISTORY SUMMARY")
    print("=" * 70)

    status_counts = Counter(b.get("coupon_status", "unknown") for b in bets)
    print(f"\nTotal coupons: {len(bets)}")
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}")

    total_staked = sum(b.get("stake_pln", 0) for b in bets)
    total_returned = sum(b.get("tax_free_payout_pln", b.get("winnings_pln", 0)) for b in bets)
    total_pnl = round(total_returned - total_staked, 2)
    print(f"\nTotal staked: {total_staked:.2f} PLN")
    print(f"Total returned: {total_returned:.2f} PLN")
    print(f"Net PnL: {total_pnl:+.2f} PLN")
    if total_staked > 0:
        print(f"ROI: {(total_pnl / total_staked) * 100:.1f}%")

    # Sport breakdown
    sport_stats = Counter()
    sport_won = Counter()
    sport_lost = Counter()
    market_stats = Counter()
    market_won = Counter()
    market_lost = Counter()

    for b in bets:
        for leg in b.get("legs", []):
            sport = leg.get("sport", "unknown")
            market = leg.get("market", "unknown")
            status = leg.get("leg_status", "unknown")
            sport_stats[sport] += 1
            market_stats[market] += 1
            if status == "won":
                sport_won[sport] += 1
                market_won[market] += 1
            elif status == "lost":
                sport_lost[sport] += 1
                market_lost[market] += 1

    print(f"\nTotal legs across all coupons: {sum(sport_stats.values())}")
    print(f"\n--- Legs by Sport ---")
    for sport, count in sport_stats.most_common():
        w = sport_won[sport]
        l = sport_lost[sport]
        rate = (w / (w + l) * 100) if (w + l) > 0 else 0
        print(f"  {sport}: {count} legs ({w}W/{l}L = {rate:.0f}% hit rate)")

    print(f"\n--- Legs by Market (top 20) ---")
    for market, count in market_stats.most_common(20):
        w = market_won[market]
        l = market_lost[market]
        rate = (w / (w + l) * 100) if (w + l) > 0 else 0
        print(f"  {market}: {count} legs ({w}W/{l}L = {rate:.0f}% hit rate)")

    # Bet type breakdown
    type_stats = Counter(b.get("bet_type", "?") for b in bets)
    print(f"\n--- By Bet Type ---")
    for bt, count in type_stats.most_common():
        won = sum(1 for b in bets if b.get("bet_type") == bt and b.get("coupon_status") == "won")
        lost = sum(1 for b in bets if b.get("bet_type") == bt and b.get("coupon_status") == "lost")
        staked = sum(b.get("stake_pln", 0) for b in bets if b.get("bet_type") == bt)
        returned = sum(b.get("tax_free_payout_pln", b.get("winnings_pln", 0)) for b in bets if b.get("bet_type") == bt)
        pnl = round(returned - staked, 2)
        print(f"  {bt}: {count} coupons ({won}W/{lost}L) | staked {staked:.2f} | PnL {pnl:+.2f}")

    # Date range
    dates = [b.get("placed_date", "") for b in bets if b.get("placed_date")]
    if dates:
        print(f"\nDate range: {dates[-1]} to {dates[0]}")


if __name__ == "__main__":
    main()
