"""Per-leg realisation on printed legs 10-20..10-30 (morning print, settled)."""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from lib import load, morning, leg_profit, boot_roi, fmt
df=load()
for name, sub in [('all snapshots', df), ('morning', morning(df).sort_values('first_t').drop_duplicates('key',keep='first'))]:
    x=sub[(sub.day>='2026-10-20')&(sub.day<='2026-10-30')&sub.status.isin(['won','lost'])]
    r=boot_roi(x,leg_profit(x))
    print(f'{name:14s} {fmt(r)} hit={x.won.mean():.3f} 1/o={x.inv.mean():.3f} hit/(1/o)={x.won.mean()/x.inv.mean():.3f} mean(won*odds)={(x.won*x.odds).mean():.3f}')
