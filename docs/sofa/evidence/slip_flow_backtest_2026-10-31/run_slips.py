"""E2E slip flows on a set of days. usage: run_slips.py dev|hold [flows...]"""
import sys, numpy as np, pandas as pd
from lib import *
from slips import simulate, boot_slips, drawdown
df=load(); m=morning(df)
which=sys.argv[1]; DAYS=DEV if which=='dev' else HOLD
# walk-forward base-rate cells: learned on all days strictly before the test day
def base_cells(before):
    p=m[m.day<before]
    g=p.groupby(['market','line','direction']).conf.agg(['std','count'])
    return set(g[(g['count']>=10)&(g['std']<0.01)].index)
day_legs={}
for d in DAYS:
    c=m[(m.day==d)&(m.odds>=1.05)&(m.odds<=3.5)].copy()
    bc=base_cells(d)
    c['base_rate']=[(a,b,e) in bc for a,b,e in zip(c.market,c.line,c.direction)]
    # ungraded legs stay in the universe (decision time) and grade as void if picked
    day_legs[d]=c
CAP=0.03
S={
 'CUR  log(conf)':            (lambda c: np.log(c.conf), None),
 'EVc  log(min(conf,1/o+.03)*o)': (lambda c: np.log(np.minimum(c.conf,1/c.odds+CAP)*c.odds), None),
 'EVraw log(conf*o)':        (lambda c: np.log(c.conf*c.odds), None),
 'LOWM ovr<=.06 log(conf)':   (lambda c: np.log(c.conf), lambda c: c.overround.fillna(9)<=0.06),
 'SPEC no base-rate log(conf)':(lambda c: np.log(c.conf), lambda c: ~c.base_rate),
 'KEEP read only log(conf)':  (lambda c: np.log(c.conf), lambda c: c.verd0.str.contains('KEEP')),
}
def prune(fn,flt):
    def f(c): return fn(c)
    return f
cfgs=[(2.5,3.5,2,4)]
if len(sys.argv)>2 and sys.argv[2]=='legs':
    cfgs=[(1.6,2.4,2,2),(2.5,3.5,3,3),(2.5,3.5,4,4),(2.5,3.5,2,2),(3.5,5,3,4)]
for lo,hi,nmin,nmax in cfgs:
    print(f'== target [{lo},{hi}] legs {nmin}-{nmax}, up to 3 disjoint slips/day, days {DAYS[0]}..{DAYS[-1]}')
    for name,(fn,flt) in S.items():
        s=simulate(day_legs, fn, lo,hi,nmin,nmax,K=3,filt=flt)
        r=boot_slips(s)
        print(f'{name:32s} slips={len(s):3d} hit={s.won.mean():.3f} avg_price={s.price.mean():.2f} legs={s.n.mean():.2f} ROI_tax={r[0]*100:+6.1f}% [{r[1]*100:+6.1f},{r[2]*100:+6.1f}] maxDD={drawdown(s):.1f}u voids={s.voids.sum()}')
        s.to_csv(f'slips_{which}_{name.split()[0]}_{lo}_{nmin}{nmax}.csv',index=False)
    # random baseline: 30 seeds
    rs=[]
    for seed in range(30):
        rng=np.random.default_rng(seed)
        s=simulate(day_legs, lambda c: rng.random(len(c)), lo,hi,nmin,nmax,K=3)
        rs.append(s.assign(seed=seed))
    R=pd.concat(rs); per=R.groupby('seed').profit.mean()
    print(f'{"RAND (30 seeds)":32s} slips/seed={len(R)/30:.0f} hit={R.won.mean():.3f} avg_price={R.price.mean():.2f} ROI_tax mean={per.mean()*100:+6.1f}% seed-range [{per.min()*100:+.1f},{per.max()*100:+.1f}]')
