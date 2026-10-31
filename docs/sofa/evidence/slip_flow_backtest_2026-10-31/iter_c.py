"""Iteration (c): is the low-margin effect real or composition? within sport, within market family, per day."""
import numpy as np, pandas as pd
from lib import *
df=load(); m=morning(df).sort_values('first_t').drop_duplicates('key',keep='first')
d=m[m.day.isin(DEV)&m.status.isin(['won','lost'])&m.overround.notna()].copy()
d['low']=d.overround<0.08
d['p']=leg_profit(d)
print('by sport: low vs high margin, pre-tax ROI')
for s,x in d.groupby('sport'):
    a=x[x.low]; b=x[~x.low]
    if len(a)>=30: print(f'  {s:10s} low {fmt(boot_roi(a,a.p))} | high {fmt(boot_roi(b,b.p))}')
# within-market: difference low-high weighted by market (stratified)
g=d.groupby(['market','low']).p.agg(['mean','count']).unstack()
g=g.dropna()
w=g[('count',True)]
diff=(g[('mean',True)]-g[('mean',False)])
print('markets with both:',len(g),'legs low:',int(w.sum()),' stratified diff (low-high) weighted by low n: %+.2f pp'%(100*(diff*w).sum()/w.sum()))
# bootstrap the stratified difference by match
rng=np.random.default_rng(0); eids=d.eid.unique(); res=[]
grp={e:x for e,x in d.groupby('eid')}
for b in range(300):
    s=pd.concat([grp[e] for e in rng.choice(eids,len(eids))])
    gg=s.groupby(['market','low']).p.agg(['mean','count']).unstack().dropna()
    ww=gg[('count',True)]; res.append(((gg[('mean',True)]-gg[('mean',False)])*ww).sum()/ww.sum())
print('  95%% CI [%+.2f, %+.2f] pp'%(100*np.percentile(res,2.5),100*np.percentile(res,97.5)))
print('per day low-margin pre-tax ROI vs all two-sided:')
for day,x in d.groupby('day'):
    print(f'  {day} low n={x.low.sum():4d} {x[x.low].p.mean()*100:+6.1f}% | high n={(~x.low).sum():5d} {x[~x.low].p.mean()*100:+6.1f}%')
print('hit vs implied by margin:'); print(d.groupby('low').agg(hit=('won','mean'),inv=('inv','mean'),mkt=('market_p','mean'),conf=('conf','mean'),odds=('odds','mean')))
