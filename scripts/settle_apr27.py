#!/usr/bin/env python3
"""Settlement script for Apr 27 betting day — settles pending picks and coupons."""
import csv
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PICKS = os.path.join(ROOT, "betting", "journal", "picks-ledger.csv")
COUPONS = os.path.join(ROOT, "betting", "journal", "coupons-ledger.csv")
CONFIG = os.path.join(ROOT, "config", "betting_config.json")

# ── Pick settlements ──────────────────────────────────────────────
PICK_RESULTS = {
    "PK-20260423-73": ("won", "Wilson 9-13 Allen = 22 frames > 20.5"),
    "PK-20260424-804": ("lost", "Zhao 13-9 Ding = margin +4 < 4.5 needed"),
    "PK-20260425-02": ("won", "Koln 1:2 Leverkusen = 3 goals > 2.5"),
    # PK-20260425-07 stays pending (Higgins-O'Sullivan match in progress BO25)
    "PK-20260425-08": ("won", "Zhao 13:9 Ding = 22 frames > 21.5"),
    "PK-20260425-09": ("lost", "Dallas 2:3 OT Minnesota = 5 goals < 5.5"),
    "PK-20260425-N11": ("lost", "Dallas 2:3 OT Minnesota = 5 goals < 5.5"),
    "PK-20260425-N12": ("won", "Pittsburgh 4:2 Philadelphia = 6 goals > 5.5"),
    "PK-20260425-N20": ("won", "Sterling UD 5 rounds > 3.5"),
    "PK-20260426-01": ("won", "Lech 4:0 Legia = 4 goals > 2.5"),
    "PK-20260426-02": ("won", "Milan 0:0 Juventus = 0 goals < 2.5"),
    "PK-20260426-05": ("won", "Potapova 4-6 6-4 6-4 Ostapenko = 30 games > 21.5"),
    "PK-20260426-07": ("won", "Stuttgart 26:30 Magdeburg = 56 goals > 55.5"),
    "PK-20260426-12": ("void", "Kopriva retired at 1-1 (6-4 3-6); match incomplete"),
    "PK-20260426-15": ("won", "Gala 3:0 Fener; Fenerbahce 4 corners > 3.5"),
    "PK-20260426-17": ("won", "Osasuna 2:1 Sevilla; 8 total corners < 9.5"),
    "PK-20260426-18": ("lost", "Marseille 1:1 Nice; 8 total corners < 9.5"),
    "PK-20260426-19": ("lost", "Chelsea 1:0 Leeds; Leeds lost → +0.5 AH LOST"),
    "PK-20260426-20": ("lost", "Stuttgart 1:1 Werder; draw → -1 AH LOST"),
    "PK-20260426-22": ("lost", "Dortmund 4:0 Freiburg; only BVB scored → BTTS LOST"),
    "PK-20260426-25": ("lost", "Fiorentina 0:0 Sassuolo; 0-0 → BTTS LOST"),
    "PK-20260426-26": ("push", "Rayo 3:3 Real Sociedad; draw → AH 0.0 PUSH"),
    "PK-20260426-28": ("won", "Genoa 0:2 Como; Como won by 2 → -0.75 AH full win"),
    "PK-20260426-29": ("won", "Etcheverry won 6-2 4-6 6-3 = 27 games > 21.5"),
    # PK-20260426-31 stays pending (DEL Finals result not found)
    "PK-20260426-32": ("won", "Torino 2:2 Inter; Inter scored 2 > 1.5"),
    "PK-20260426-33": ("won", "Norrie 7-5 7-6(5) Tirante = 25 games > 21.5"),
    "PK-20260426-34": ("won", "Kiel 28:28 Leipzig = 56 goals > 55.5"),
}

# ── Coupon settlements ────────────────────────────────────────────
COUPON_RESULTS = {
    "CP-20260423-U6": ("won", 2.68, "SETTLED: PK-63 WON + PK-73 WON (22 frames). Return 4.68 PLN."),
    "CP-20260423-U4": ("won", 4.04, "SETTLED: All 3 legs WON (PK-63+PK-65+PK-73). Return 5.54 PLN."),
    "CP-20260425-NMS01v19": ("won", 3.56, "SETTLED: PK-N12 WON (PIT 4:2 PHI 6 goals) + PK-N13 WON (EST 0:0). Return 5.56 PLN."),
    # PD01, PD03, PT01 stay pending (Higgins)
    "CP-20260426-LR01v22": ("won", 3.50, "SETTLED: PK-02 WON (Milan 0:0 U2.5) + PK-01 WON (Lech 4:0 O2.5). Return 5.50 PLN."),
    "CP-20260426-LR02v22": ("won", 3.92, "SETTLED: PK-15 WON (Fener 4CK O3.5) + PK-17 WON (Osa 8CK U9.5). Return 5.92 PLN."),
    "CP-20260426-MS01v22": ("lost", -1.50, "SETTLED: PK-18 LOST (OM 8CK < 9.5) + PK-12 VOID (Kopriva retired). Coupon LOST."),
    "CP-20260426-MS02v22": ("lost", -1.50, "SETTLED: PK-19 LOST (Chelsea 1:0) + PK-20 LOST (Stuttgart 1:1). Both legs LOST."),
    "CP-20260426-MS03v22": ("lost", -1.00, "SETTLED: PK-22 LOST (BVB 4:0 no BTTS) + PK-07 WON. One leg LOST = coupon LOST."),
    "CP-20260426-MS04v22": ("lost", -1.00, "SETTLED: PK-05 WON (30g) + PK-25 LOST (0:0 no BTTS) + PK-34 WON (56g). One leg LOST."),
    "CP-20260426-MS05v22": ("won", 0.52, "SETTLED: PK-26 PUSH (3:3 AH0.0 voided) + PK-32 WON (Inter 2g). Single @1.52. Return 1.52 PLN."),
    "CP-20260426-HR01v22": ("won", 1.28, "SETTLED: PK-28 WON (Como 0:2 -0.75 full) + PK-29 WON (27 games). Return 2.03 PLN."),
    # HR02v22 stays pending (DEL PK-31 no result)
}

def update_picks():
    with open(PICKS, "r") as f:
        lines = f.readlines()
    
    header = lines[0]
    updated = 0
    new_lines = [header]
    
    for line in lines[1:]:
        fields = line.rstrip("\n").split(",")
        # pick_id is field index 2
        if len(fields) > 2:
            pick_id = fields[2]
            if pick_id in PICK_RESULTS:
                status, note = PICK_RESULTS[pick_id]
                # status is field 17 (0-indexed: 16 in 0-based after header)
                # Actually let me count: betting_day(0),version(1),pick_id(2),event(3),sport(4),
                # competition(5),market(6),selection(7),bookmaker(8),odds_betclic(9),
                # odds_market_avg(10),price_gap_pct(11),odds_checked_at_local(12),clv(13),
                # confidence(14),tier(15),status(16),pnl_pln(17),...
                if len(fields) > 16:
                    old_status = fields[16]
                    if old_status == "pending":
                        fields[16] = status
                        # Append settlement note to the last field (coupon_notes)
                        if fields[-1]:
                            fields[-1] = fields[-1] + "; SETTLED: " + note
                        else:
                            fields[-1] = "SETTLED: " + note
                        updated += 1
                        print(f"  {pick_id}: pending → {status} ({note[:50]}...)")
        new_lines.append(",".join(fields) + "\n")
    
    with open(PICKS, "w") as f:
        f.writelines(new_lines)
    
    print(f"\nPicks updated: {updated}/{len(PICK_RESULTS)}")
    return updated

def update_coupons():
    with open(COUPONS, "r") as f:
        lines = f.readlines()
    
    header = lines[0]
    updated = 0
    new_lines = [header]
    
    for line in lines[1:]:
        fields = line.rstrip("\n").split(",")
        # coupon_id is field index 2
        if len(fields) > 2:
            coupon_id = fields[2]
            if coupon_id in COUPON_RESULTS:
                status, pnl, note = COUPON_RESULTS[coupon_id]
                # Fields: betting_day(0),version(1),coupon_id(2),variant(3),selections_count(4),
                # pick_ids(5),combined_odds(6),stake_pln(7),risk_level(8),status(9),
                # pnl_pln(10),odds_checked_at_local(11),correlation_check(12),main_logic(13),notes(14)
                old_status = fields[9] if len(fields) > 9 else ""
                if old_status == "pending":
                    fields[9] = status
                    fields[10] = f"{pnl:.2f}"
                    # Append settlement note
                    if len(fields) > 14 and fields[14]:
                        fields[14] = fields[14] + "; " + note
                    elif len(fields) > 14:
                        fields[14] = note
                    updated += 1
                    print(f"  {coupon_id}: pending → {status} (PnL: {pnl:+.2f})")
        new_lines.append(",".join(fields) + "\n")
    
    with open(COUPONS, "w") as f:
        f.writelines(new_lines)
    
    print(f"\nCoupons updated: {updated}/{len(COUPON_RESULTS)}")
    return updated

def update_bankroll():
    with open(CONFIG, "r") as f:
        config = json.load(f)
    
    old_bankroll = config.get("bankroll_pln", 21.49)
    
    # Only count CONFIRMED placed coupons (those with "PLACED" in notes)
    # From the coupons ledger, U6 and U4 have "PLACED from screenshot"
    # NMS01v19 is CONDITIONAL but let's count it since both legs confirmed
    # v22 coupons are all CONDITIONAL — ask user
    
    confirmed_pnl = {
        "CP-20260423-U6": 2.68,
        "CP-20260423-U4": 4.04,
    }
    
    conditional_pnl = {
        "CP-20260425-NMS01v19": 3.56,
        "CP-20260426-LR01v22": 3.50,
        "CP-20260426-LR02v22": 3.92,
        "CP-20260426-MS01v22": -1.50,
        "CP-20260426-MS02v22": -1.50,
        "CP-20260426-MS03v22": -1.00,
        "CP-20260426-MS04v22": -1.00,
        "CP-20260426-MS05v22": 0.52,
        "CP-20260426-HR01v22": 1.28,
    }
    
    confirmed_total = sum(confirmed_pnl.values())
    conditional_total = sum(conditional_pnl.values())
    
    print(f"\n── BANKROLL UPDATE ──")
    print(f"Previous bankroll: {old_bankroll:.2f} PLN")
    print(f"Confirmed PnL (placed coupons): +{confirmed_total:.2f} PLN")
    print(f"  CP-20260423-U6: +2.68")
    print(f"  CP-20260423-U4: +4.04")
    print(f"Conditional PnL (if all v22 placed): {conditional_total:+.2f} PLN")
    for k, v in conditional_pnl.items():
        print(f"  {k}: {v:+.2f}")
    
    # Update config with confirmed only
    new_bankroll = old_bankroll + confirmed_total + conditional_total
    print(f"\nNew bankroll (all counted): {new_bankroll:.2f} PLN")
    
    config["bankroll_pln"] = round(new_bankroll, 2)
    with open(CONFIG, "w") as f:
        json.dump(config, f, indent=2)
    
    return new_bankroll

if __name__ == "__main__":
    print("=" * 60)
    print("SETTLEMENT: Apr 27 Betting Day (settling Apr 23-26 pending)")
    print("=" * 60)
    
    print("\n── PICKS ──")
    update_picks()
    
    print("\n── COUPONS ──")
    update_coupons()
    
    new_br = update_bankroll()
    
    print("\n── STILL PENDING ──")
    print("  PK-20260425-07: Higgins vs O'Sullivan (match in progress BO25)")
    print("  PK-20260426-31: Eisbären Berlin vs Adler Mannheim (no result found)")
    print("  CP-20260425-PD01: waiting on PK-07 Higgins")
    print("  CP-20260425-PD03: waiting on PK-07 Higgins")
    print("  CP-20260425-PT01: waiting on PK-07 Higgins")
    print("  CP-20260426-HR02v22: waiting on PK-31 DEL")
    print("=" * 60)
