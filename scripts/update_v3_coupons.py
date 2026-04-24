#!/usr/bin/env python3
"""Update coupons-ledger.csv: void old v2 coupons, add new v3 coupons."""
import csv
from datetime import datetime

LEDGER = 'betting/journal/coupons-ledger.csv'

with open(LEDGER, 'r') as f:
    reader = csv.reader(f)
    header = next(reader)
    rows = list(reader)

# Void old v2 coupons
status_col = header.index('status')
coupon_id_col = header.index('coupon_id')
notes_col = header.index('notes')

v2_coupons = ['CP-24-P1v2','CP-24-P2v2','CP-24-P3v2','CP-24-P4v2','CP-24-P5v2','CP-24-P6v2',
              'CP-24-T1v2','CP-24-T2v2','CP-24-T3v2','CP-24-MS1v2','CP-24-MS2v2','CP-24-MS3v2']

for row in rows:
    cid = row[coupon_id_col]
    if cid in v2_coupons:
        row[status_col] = 'void'
        if row[notes_col]:
            row[notes_col] += '; VOIDED v3: replaced by expanded 12-sport portfolio'
        else:
            row[notes_col] = 'VOIDED v3: replaced by expanded 12-sport portfolio'

# Also settle night coupons from Apr 23 that had results
# Check which coupons had PK-90, PK-91, PK-93, PK-95
# PK-90 LOST, PK-91 WON, PK-93 WON, PK-95 LOST
# A coupon WINS only if ALL legs win
night_results = {
    'PK-20260423-90': 'lost',
    'PK-20260423-91': 'won',
    'PK-20260423-93': 'won',
    'PK-20260423-95': 'lost',
}

# Check night coupons
legs_col = header.index('pick_ids')
for row in rows:
    cid = row[coupon_id_col]
    if cid.startswith('CP-23-N') and row[status_col] == 'pending':
        legs = row[legs_col].split(';')
        all_resolved = True
        all_won = True
        for leg in legs:
            leg = leg.strip()
            if leg in night_results:
                if night_results[leg] != 'won':
                    all_won = False
            else:
                all_resolved = False
        if all_resolved:
            row[status_col] = 'won' if all_won else 'lost'
            row[notes_col] = (row[notes_col] + '; ' if row[notes_col] else '') + f'SETTLED: {"ALL WON" if all_won else "at least 1 leg lost"}'

now = datetime.now().strftime('%Y-%m-%d %H:%M')

# Header: betting_day,coupon_id,variant,selections_count,pick_ids,combined_odds,stake_pln,risk_level,status,pnl_pln,odds_checked_at_local,correlation_check,main_logic,notes
new_coupons = [
    ['2026-04-24','CP-24-P1v3','v3',2,'PK-101;PK-207','2.63','2.00','low','pending','',now,'pass','Pewniaki Double: Basaksehir U10.5CK + Leipzig O16.5 shots',''],
    ['2026-04-24','CP-24-P2v3','v3',2,'PK-101;PK-205','2.54','2.00','low','pending','',now,'pass','Pewniaki Double: Basaksehir U10.5CK + Lens ML',''],
    ['2026-04-24','CP-24-P3v3','v3',3,'PK-207;PK-205;PK-104','4.14','2.00','low','pending','',now,'pass','Pewniaki Triple: Leipzig shots + Lens ML + Riestra U2.5',''],
    ['2026-04-24','CP-24-P4v3','v3',3,'PK-101;PK-208;PK-207','3.94','2.00','low','pending','',now,'pass','Corners Triple: Basaksehir CK + Palmeiras CK + Leipzig shots',''],
    ['2026-04-24','CP-24-P5v3','v3',4,'PK-101;PK-104;PK-205;PK-207','6.21','1.50','medium','pending','',now,'pass','Pewniaki Quad: 4 strongest pewniaki legs',''],
    ['2026-04-24','CP-24-P6v3','v3',5,'PK-101;PK-104;PK-205;PK-207;PK-208','9.31','1.00','higher','pending','',now,'pass','Full Pewniaki: all 5 pewniaki legs',''],
    ['2026-04-24','CP-24-MS1v3','v3',3,'PK-302;PK-306;PK-205','4.83','1.50','medium','pending','',now,'pass','Multi-Sport: Williams snooker + Blue Fox hockey + Lens football',''],
    ['2026-04-24','CP-24-MS2v3','v3',3,'PK-206;PK-303;PK-305','5.22','1.50','medium','pending','',now,'pass','Multi-Sport: Shelton tennis + Utah NHL + Detroit MLB',''],
    ['2026-04-24','CP-24-MS3v3','v3',3,'PK-212;PK-304;PK-308','5.34','1.50','medium','pending','',now,'pass','Multi-Sport: Paris volley + Montreal NHL + Cleveland MLB',''],
    ['2026-04-24','CP-24-MS4v3','v3',4,'PK-302;PK-212;PK-306;PK-104','6.60','1.00','medium','pending','',now,'pass','Niche Sport Mix: snooker + volleyball + Danish hockey + football',''],
    ['2026-04-24','CP-24-HR1v3','v3',5,'PK-207;PK-205;PK-206;PK-302;PK-306','13.27','1.00','higher','pending','',now,'pass','High Risk: Leipzig + Lens + Shelton + Williams + Blue Fox',''],
    ['2026-04-24','CP-24-HR2v3','v3',5,'PK-208;PK-209;PK-104;PK-212;PK-304','9.83','1.00','higher','pending','',now,'pass','High Risk: Palmeiras CK + Napoli CK + Riestra + Paris + Montreal',''],
    ['2026-04-24','CP-24-N1v3','v3',4,'PK-305;PK-308;PK-303;PK-309','11.64','1.00','higher','pending','',now,'pass','Night Session: Detroit + Cleveland + Utah + MTL-TBL U6',''],
    ['2026-04-24','CP-24-N2v3','v3',2,'PK-305;PK-304','3.18','1.50','medium','pending','',now,'pass','Night Safe: Detroit Tigers + Montreal Canadiens',''],
]

rows.extend(new_coupons)

with open(LEDGER, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(header)
    writer.writerows(rows)

print(f'Updated {LEDGER}: v2 coupons voided, {len(new_coupons)} new v3 coupons added.')
print(f'Total rows: {len(rows)}')
