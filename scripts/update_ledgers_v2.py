#!/usr/bin/env python3
"""Void replaced pre-analysis picks and update coupons ledger with v2 coupons."""

# 1. Void old pre-analysis picks that are replaced by v2
void_picks = {'PK-102', 'PK-103', 'PK-105', 'PK-106', 'PK-111', 'PK-113'}
# PK-102 Millwall ML -> replaced by statistical markets
# PK-103 Basaksehir combo -> same match as PK-101, not in v2 coupons
# PK-105 old Lens ML -> replaced by PK-205 with updated odds_checked_at  
# PK-106 BTTS -> not in v2 coupons
# PK-111 old Shelton -> replaced by PK-206 with updated odds_checked_at
# PK-113 Hawks -> not in v2 coupons

with open('betting/journal/picks-ledger.csv') as f:
    lines = f.readlines()

updated = []
for line in lines:
    stripped = line.strip()
    parts = stripped.split(',')
    if len(parts) >= 16 and parts[1] in void_picks:
        parts[15] = 'void'
        if len(parts) >= 22:
            parts[21] = parts[21].rstrip() + '; VOIDED v2: replaced by statistical markets'
        updated.append(','.join(parts))
        print(f'  Voided: {parts[1]} ({parts[2][:30]}...)')
    else:
        updated.append(stripped)

with open('betting/journal/picks-ledger.csv', 'w') as f:
    for line in updated:
        f.write(line + '\n')

# 2. Void old pre-analysis coupons
void_coupons = {'CP-24-P1', 'CP-24-P2', 'CP-24-P3', 'CP-24-P4', 'CP-24-P5', 'CP-24-P6', 'CP-24-C7', 'CP-24-C8', 'CP-24-C9', 'CP-24-C10'}

with open('betting/journal/coupons-ledger.csv') as f:
    lines = f.readlines()

updated = []
for line in lines:
    stripped = line.strip()
    parts = stripped.split(',')
    if len(parts) >= 10 and parts[1] in void_coupons:
        parts[8] = 'void'
        if len(parts) >= 14:
            parts[13] = parts[13].rstrip() + '; VOIDED v2: replaced by statistical market coupons'
        updated.append(','.join(parts))
        print(f'  Voided coupon: {parts[1]}')
    else:
        updated.append(stripped)

with open('betting/journal/coupons-ledger.csv', 'w') as f:
    for line in updated:
        f.write(line + '\n')

# 3. Add new v2 coupons
new_coupons = [
    '2026-04-24,CP-24-P1v2,pewniaki,2,PK-207|PK-101,2.63,2.50,low-risk,pending,,2026-04-24 07:55,pass,Leipzig O16.5 shots @1.75 + Basaksehir U10.5 CK @1.50; two deep statistical markets,CONDITIONAL all legs; v2 morning analysis',
    '2026-04-24,CP-24-P2v2,pewniaki,2,PK-207|PK-208,2.63,2.50,low-risk,pending,,2026-04-24 07:55,pass,Leipzig O16.5 shots @1.75 + Palmeiras O9.5 CK @1.50; shots + corners multi-continent,CONDITIONAL all legs; v2',
    '2026-04-24,CP-24-P3v2,pewniaki,2,PK-101|PK-208,2.25,3.00,low-risk,pending,,2026-04-24 07:55,pass,Basaksehir U10.5 CK @1.50 + Palmeiras O9.5 CK @1.50; safest pewniaki pair both corners,CONDITIONAL all legs; v2',
    '2026-04-24,CP-24-P4v2,pewniaki,2,PK-101|PK-104,2.10,3.00,low-risk,pending,,2026-04-24 07:55,pass,Basaksehir U10.5 CK @1.50 + Riestra U2.5 @1.40; two structural extremes,CONDITIONAL all legs; v2',
    '2026-04-24,CP-24-P5v2,pewniaki,2,PK-207|PK-104,2.45,2.50,low-risk,pending,,2026-04-24 07:55,pass,Leipzig O16.5 shots @1.75 + Riestra U2.5 @1.40; shots + structural under,CONDITIONAL all legs; v2',
    '2026-04-24,CP-24-P6v2,pewniaki,2,PK-208|PK-209,2.33,2.50,low-risk,pending,,2026-04-24 07:55,pass,Palmeiras O9.5 CK @1.50 + Napoli O8.5 CK @1.55; dominant teams corners,CONDITIONAL all legs; v2',
    '2026-04-24,CP-24-T1v2,low-risk,3,PK-207|PK-101|PK-212,4.33,2.00,low-risk,pending,,2026-04-24 07:55,pass,Leipzig shots + Basaksehir CK + Paris volley +5.5; 3-sport triple,CONDITIONAL all legs; v2',
    '2026-04-24,CP-24-T2v2,low-risk,3,PK-207|PK-208|PK-209,4.07,1.50,low-risk,pending,,2026-04-24 07:55,pass,Leipzig shots + Palmeiras CK + Napoli CK; pure statistical triple,CONDITIONAL all legs; v2',
    '2026-04-24,CP-24-T3v2,low-risk,3,PK-101|PK-208|PK-211,3.38,2.00,low-risk,pending,,2026-04-24 07:55,pass,Basaksehir CK + Palmeiras CK + BOS-BUF U6.5; multi-sport triple,CONDITIONAL all legs; v2',
    '2026-04-24,CP-24-MS1v2,higher-risk,3,PK-207|PK-212|PK-211,4.33,1.50,higher-risk,pending,,2026-04-24 07:55,pass,Leipzig shots + Paris volley + BOS-BUF U6.5; 3 different sports,CONDITIONAL all legs; v2',
    '2026-04-24,CP-24-MS2v2,higher-risk,3,PK-205|PK-206|PK-104,3.71,1.50,higher-risk,pending,,2026-04-24 07:55,pass,Lens ML + Shelton ML + Riestra U2.5; title+champion+turtle,CONDITIONAL all legs; v2',
    '2026-04-24,CP-24-MS3v2,higher-risk,3,PK-209|PK-210|PK-208,3.77,1.50,higher-risk,pending,,2026-04-24 07:55,pass,Napoli CK + Yankees ML + Palmeiras CK; night multi-sport,CONDITIONAL all legs; v2',
]

with open('betting/journal/coupons-ledger.csv') as f:
    existing = f.read()

existing_ids = set()
for line in existing.strip().split('\n'):
    parts = line.split(',')
    if len(parts) >= 2:
        existing_ids.add(parts[1])

added = 0
with open('betting/journal/coupons-ledger.csv', 'a') as f:
    for coupon in new_coupons:
        coupon_id = coupon.split(',')[1]
        if coupon_id not in existing_ids:
            f.write(coupon + '\n')
            added += 1
            print(f'  Added coupon: {coupon_id}')
        else:
            print(f'  Skipped coupon (exists): {coupon_id}')

print(f'\nTotal coupons added: {added}')
