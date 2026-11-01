"""COPY for ruch_kursu_2026-11-01 (original: slip_flow_backtest_2026-10-31/iter_a_clv.py).
Changes: every day 10-13..10-31 (no DEV cut), tax=True beside tax=False, football and tennis apart,
close = newest closing.jsonl record 3-30 min before the start (see load.py), move also on the devigged price.
Descriptive: the move is known only at the close (look-ahead) - this is the CEILING of a perfect move forecast,
betting at the PRINTED (taken) price."""
import json
import numpy as np, pandas as pd
from lib import *
df=load()
print('all tracked legs',len(df),'| first_snap>0 (added in a later print, not in morning())',
      int(((df.first_snap>0)&(df.first_src=='legs')).sum()))
m=morning(df)
print('morning legs (first print, >=15 min lead)',len(m),'| football/tennis',int(m.sport.isin(['football','tennis']).sum()))
ft=m[m.sport.isin(['football','tennis'])]
print('football/tennis morning: with close-file record',int(ft.had_close_file.fillna(False).sum()),
      '| close under ORIGINAL rule (newest, any minutes)',int(ft.orig_close.notna().sum()),
      '| close under 3-30 min rule',int(ft.clv_close.notna().sum()),
      '| dropped by the rule',int((ft.orig_close.notna()&ft.clv_close.isna()).sum()))
print('settled won/lost among 3-30 close',int((ft.clv_close.notna()&ft.status.isin(['won','lost'])).sum()))
print('closing drops per day:',json.dumps(json.load(open(__file__.rsplit('/',1)[0]+'/closing_drops.json'))))

def table(d,label):
    d=d.copy()
    d['mv']=d.odds/d.clv_close-1            # >0: price shortened after the print (print price beat close)
    fair_ok=d.market_p.notna()&d.p_close.notna()
    d['mv_fair']=np.where(fair_ok,d.p_close/d.market_p-1,np.nan)   # >0: devigged p rose = shortened
    print(f'\n=== {label}: legs {len(d)} matches {d.eid.nunique()} days {d.day.min()}..{d.day.max()}')
    print('share moved',round((d.mv!=0).mean(),3),'shortened',round((d.mv>0).mean(),3),'drifted',round((d.mv<0).mean(),3),
          '| odds_taken == print odds',round((d.clv_taken==d.odds).mean(),3))
    clv=d.odds*d.p_close-1
    ok=clv.notna()
    if ok.any():
        x=d[ok]
        r=boot_roi(x,clv[ok].values)
        print(f'CLV at the print price, devigged close (two_way_close): legs {r[3]} mean {r[0]*100:+.2f}% [{r[1]*100:+.2f},{r[2]*100:+.2f}] above close {(x.odds>x.clv_close).mean():.3f}'
              f' | devig share of legs {ok.mean():.3f}')
    print('devigged move available (market_p & partner_close):',int(fair_ok.sum()),
          '| moved >1% devigged',round((d.mv_fair.abs()>0.01).mean(),3) if fair_ok.any() else None,
          '| corr(raw move, devigged move)',round(d.loc[fair_ok,['mv','mv_fair']].corr().iloc[0,1],3) if fair_ok.sum()>2 else None)
    hdr=f'{"group":30s} {"n":>6s} {"hit":>6s} {"1/odds":>6s}  ROI before tax                    ROI after 12% tax'
    print(hdr)
    def row(name,x):
        a=boot_roi(x,leg_profit(x)); b=boot_roi(x,leg_profit(x,tax=True))
        print(f'{name:30s} {len(x):6d} {x.won.mean():6.3f} {x.inv.mean():6.3f}  {fmt(a)}  {fmt(b)}')
        return b
    for name,mask in [('shortened (mv>0)',d.mv>0),('unchanged',d.mv==0),('drifted (mv<0)',d.mv<0)]:
        row(name,d[mask])
    nz=d[d.mv!=0].copy(); nz['q']=pd.qcut(nz.mv,5,duplicates='drop')
    best=None
    for q,x in nz.groupby('q',observed=True):
        best=row(f'raw mv q {str(q)}',x)
    f=d[fair_ok&(d.mv_fair!=0)].copy()
    if len(f)>=50:
        f['q']=pd.qcut(f.mv_fair,5,duplicates='drop')
        for q,x in f.groupby('q',observed=True):
            row(f'devig mv q {str(q)}',x)
    return best
out={}
for sp in ['football','tennis']:
    d=ft[(ft.sport==sp)&ft.status.isin(['won','lost'])&ft.clv_close.notna()]
    out[sp]=table(d,sp)
d=ft[ft.status.isin(['won','lost'])&ft.clv_close.notna()]
out['football+tennis']=table(d,'football+tennis (pooled only for the headline; two sports)')
print('\nbest raw-move quintile after tax (ROI, lo, hi, n):',{k:tuple(round(float(v),4) if isinstance(v,float) else v for v in t) for k,t in out.items()})
