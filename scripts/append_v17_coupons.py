#!/usr/bin/env python3
"""Append v17 coupons to coupons-ledger.csv"""
import os

LEDGER = os.path.join(os.path.dirname(__file__), '..', 'betting', 'journal', 'coupons-ledger.csv')

v17_coupons = [
    "2026-04-25,v17,CP-20260425-LR1,PD01 Pewniaki 2-ka #1,2,PK-20260425-01|PK-20260425-02,2.33,2.00,low,pending,,2026-04-25 12:00,pass,Heerenveen O2.5 + Koln O2.5,CONDITIONAL",
    "2026-04-25,v17,CP-20260425-LR2,PD02 Pewniaki 2-ka #2,2,PK-20260425-01|PK-20260425-03,2.10,1.50,low,pending,,2026-04-25 12:00,pass,Heerenveen O2.5 + Mainz O2.5,CONDITIONAL",
    "2026-04-25,v17,CP-20260425-LR3,PD03 Resilience 2-ka,2,PK-20260425-02|PK-20260425-03,2.17,1.50,low,pending,,2026-04-25 12:00,pass,Koln O2.5 + Mainz O2.5 (BEZ Heerenveen),CONDITIONAL; resilience",
    "2026-04-25,v17,CP-20260425-LR4,PT01 Pewniaki 3-ka #1,3,PK-20260425-01|PK-20260425-02|PK-20260425-04,3.95,1.50,low,pending,,2026-04-25 12:00,pass,Heerenveen O2.5 + Koln O2.5 + Motor HC,CONDITIONAL",
    "2026-04-25,v17,CP-20260425-LR5,PT02 Pewniaki 3-ka #2,3,PK-20260425-01|PK-20260425-03|PK-20260425-04,3.57,1.00,low,pending,,2026-04-25 12:00,pass,Heerenveen O2.5 + Mainz O2.5 + Motor HC,CONDITIONAL",
    "2026-04-25,v17,CP-20260425-LR6,MS01 Multi-Sport #1,3,PK-20260425-04|PK-20260425-08|PK-20260425-05,5.35,1.00,medium,pending,,2026-04-25 12:00,pass,Motor HC + Zhao O21.5fr + Denver O229.5; 3 sports no football,CONDITIONAL",
    "2026-04-25,v17,CP-20260425-LR7,MS02 Multi-Sport #2,3,PK-20260425-02|PK-20260425-07|PK-20260425-09,3.48,1.00,medium,pending,,2026-04-25 12:00,pass,Koln O2.5 + Humbert O20.5 + Sterling O2.5rds; 3 sports,CONDITIONAL",
    "2026-04-25,v17,CP-20260425-HR1,HR01 Higher Risk 4-ka,4,PK-20260425-06|PK-20260425-02|PK-20260425-07|PK-20260425-05,6.65,1.00,high,pending,,2026-04-25 12:00,pass,Arsenal O2.5 + Koln O2.5 + Humbert O20.5 + Denver O229.5,CONDITIONAL; check Arsenal lineup 17:30",
    "2026-04-25,v17,CP-20260425-LR8,N01 Night 2-ka,2,PK-20260425-05|PK-20260425-09,2.87,1.00,low,pending,,2026-04-25 12:00,pass,Denver O229.5 + Sterling O2.5rds; late night,CONDITIONAL; 02:00+ CEST",
]

with open(LEDGER, 'a') as f:
    for coupon in v17_coupons:
        f.write(coupon + '\n')

print(f"Appended {len(v17_coupons)} v17 coupons")
