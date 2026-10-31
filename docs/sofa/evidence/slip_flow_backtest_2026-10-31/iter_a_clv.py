"""H4 / L1 CLV on DEV football+tennis (closing.jsonl from 10-20; earlier days have files too if present).
Descriptive deciles use the close (look-ahead); actionable late rules bet AT the close price."""
import numpy as np, pandas as pd
from lib import *
df=load(); m=morning(df)
d=m[m.day.isin(DEV)&m.status.isin(['won','lost'])&m.clv_close.notna()].copy()
print('legs with close',len(d),'days',sorted(d.day.unique())[0],'..',sorted(d.day.unique())[-1])
d['mv']=d.odds/d.clv_close-1   # >0: price shortened after morning (morning price beat close)
print('share moved:',(d.mv!=0).mean().round(3),'shortened',(d.mv>0).mean().round(3),'drifted',(d.mv<0).mean().round(3))
print('odds_taken == morning odds share',(d.clv_taken==d.odds).mean().round(3))
tried=0
for name,mask in [('shortened (mv>0)',d.mv>0),('unchanged',d.mv==0),('drifted out (mv<0)',d.mv<0)]:
    x=d[mask]; tried+=1
    print(f'{name:22s} morning price {fmt(boot_roi(x,leg_profit(x)))} | at close {fmt(boot_roi(x,leg_profit(x,odds_col="clv_close")))} hit={x.won.mean():.3f} 1/close={(1/x.clv_close).mean():.3f}')
# deciles of nonzero moves
nz=d[d.mv!=0].copy(); nz['q']=pd.qcut(nz.mv,5,duplicates='drop')
for q,x in nz.groupby('q',observed=True):
    tried+=1; print(f'mv quintile {str(q):22s} morning {fmt(boot_roi(x,leg_profit(x)))} close {fmt(boot_roi(x,leg_profit(x,odds_col="clv_close")))}')
# is the move predictable from morning features? correlation of mv with edge, overround
for f in ['edge','overround','conf','odds','ko_lag_h']:
    print('corr mv ~',f, round(d[['mv',f]].corr().iloc[0,1],3))
print('tried',tried)
