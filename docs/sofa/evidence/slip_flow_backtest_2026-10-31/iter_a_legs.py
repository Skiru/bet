"""Iteration (a): leg-level screening on DEV days (10-13..10-26), morning universe, singles at morning price."""
import numpy as np, pandas as pd, sys
from lib import *
df=load(); m=morning(df)
dev=m[m.day.isin(DEV)&m.status.isin(['won','lost'])].copy()
print('DEV morning settled legs',len(dev),'matches',dev.eid.nunique(),'days',dev.day.nunique())
print('unsettled in morning dev universe:',(m.day.isin(DEV)&~m.status.isin(['won','lost'])).sum(), m[m.day.isin(DEV)].status.value_counts(dropna=False).to_dict())
tried=[0]
def rep(name, mask, odds_col='odds'):
    d=dev[mask]; tried[0]+=1
    if len(d)<30: print(f'{name:55s} n<30'); return
    pre=boot_roi(d, leg_profit(d,False,odds_col)); post=boot_roi(d, leg_profit(d,True,odds_col))
    print(f'{name:55s} {fmt(pre)} | tax {post[0]*100:+6.1f}% hit={d.won.mean():.3f} conf={d.conf.mean():.3f} 1/o={(1/d[odds_col]).mean():.3f}')
rep('ALL', dev.index==dev.index)
for s in sorted(dev.sport.unique()): rep(f'sport={s}', dev.sport==s)
print('-- H6 price band')
for a,b in [(1,1.15),(1.15,1.3),(1.3,1.6),(1.6,2.2),(2.2,9)]: rep(f'odds [{a},{b})', (dev.odds>=a)&(dev.odds<b))
print('-- H1 edge = conf - 1/odds')
for a,b in [(-1,0),(0,0.02),(0.02,0.05),(0.05,0.1),(0.1,1)]: rep(f'edge [{a},{b})', (dev.edge>=a)&(dev.edge<b))
rep('price_gap flag', dev.price_gap==1)
rep('line_offset present', dev.line_offset.notna())
rep('line_offset absent', dev.line_offset.isna())
rep('price_band_cap present', dev.price_band_cap.notna())
dev['sh_edge']=dev.sample_hit_rate-dev.inv
for a,b in [(-1,-0.1),(-0.1,0),(0,0.1),(0.1,1)]: rep(f'sample_hit - 1/odds [{a},{b})', (dev.sh_edge>=a)&(dev.sh_edge<b))
for a,b in [(0,500),(500,5000),(5000,50000),(50000,1e9)]: rep(f'calibration_n [{a},{b})', (dev.calibration_n>=a)&(dev.calibration_n<b))
for a,b in [(0,5),(5,10),(10,20),(20,1e9)]: rep(f'sample_size [{a},{b})', (dev.sample_size>=a)&(dev.sample_size<b))
# base-rate market detection on DEV: sd of conf within (market,line,direction) across events
g=dev.groupby(['market','line','direction']).conf.agg(['std','count'])
base=g[(g['count']>=10)&(g['std']<0.01)].index
dev['base_rate']=[ (a,b,c) in set(base) for a,b,c in zip(dev.market,dev.line,dev.direction)]
print('base-rate market cells:',len(base), sorted({x[0] for x in base})[:30])
rep('base-rate markets (conf sd<0.01)', dev.base_rate)
rep('match-specific markets', ~dev.base_rate)
rep('one_sided', dev.one_sided==1)
print('-- H2 margin')
for a,b in [(-1,0.04),(0.04,0.06),(0.06,0.08),(0.08,0.10),(0.10,0.15),(0.15,1)]: rep(f'overround [{a},{b})', (dev.overround>=a)&(dev.overround<b))
rep('overround NaN', dev.overround.isna())
print('-- H3 agreement')
dev['dis']=dev.model_p-dev.market_p
for a,b in [(-1,0),(0,0.03),(0.03,0.07),(0.07,1)]: rep(f'model_p - market_p [{a},{b})', (dev.dis>=a)&(dev.dis<b))
dev['fdis']=dev.forecast_p-dev.inv
for a,b in [(-1,0),(0,0.03),(0.03,0.07),(0.07,1)]: rep(f'forecast_p - 1/odds [{a},{b})', (dev.fdis>=a)&(dev.fdis<b))
print('-- H5 reads (as known at morning print)')
rep('morning read KEEP', dev.verd0.str.contains('KEEP'))
rep('morning unread', dev.verd0=='')
rep('last pre-KO verdict KEEP', dev.last_verdicts.str.contains('KEEP'))
rep('peer preferred', dev.peer_pref==1)
rep('has peer not preferred', (dev.has_peer==1)&(dev.peer_pref==0))
print('-- L4 lag to kickoff (h)')
for a,b in [(0,3),(3,6),(6,12),(12,99)]: rep(f'lag [{a},{b})', (dev.ko_lag_h>=a)&(dev.ko_lag_h<b))
print('tried',tried[0])
dev.to_pickle('dev_legs.pkl')
