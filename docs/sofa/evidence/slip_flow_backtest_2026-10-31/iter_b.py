"""Iteration (b)/(c): leakage fixes (dedupe tennis keys across days; late rules at their late price),
leg pools with walk-forward params, implied AKO ROI, and E2E slips with more slips/day for power.
usage: iter_b.py dev|hold [slips]"""
import sys, numpy as np, pandas as pd
from lib import *
from slips import simulate, boot_slips, drawdown
which=sys.argv[1]; DAYS=DEV if which=='dev' else HOLD
df=load(); m=morning(df).sort_values('first_t').drop_duplicates('key',keep='first')
m['two_sided']=m.overround.notna()
CAPS=[0.06,0.07,0.08,0.09,0.10,0.15]
def learned_cap(day):
    p=m[(m.day<day)&m.status.isin(['won','lost'])&m.two_sided]
    best=0.15; bv=-9
    for c in CAPS:
        x=p[p.overround<c]
        if len(x)<500: continue
        v=leg_profit(x).mean()
        if v>bv: bv=v; best=c
    return best
caps={d:learned_cap(d) for d in DAYS}
print('walk-forward learned caps:',caps)
m['wf_cap']=m.day.map(caps)
def rung_min_ovr(x):
    x=x[x.two_sided].sort_values(['overround','conf'],ascending=[True,False])
    return x.drop_duplicates(['day','eid','market','subject','direction'])
def rung_max_conf(x):
    return x.sort_values('conf',ascending=False).drop_duplicates(['day','eid','market','subject','direction'])
U=m[m.day.isin(DAYS)]
POOLS={
 'P0 all printed':                lambda x: x,
 'P1 two-sided ovr<0.08':          lambda x: x[x.two_sided&(x.overround<0.08)],
 'P2 two-sided ovr<wf_cap':        lambda x: x[x.two_sided&(x.overround<x.wf_cap)],
 'P3 KEEP at morning':             lambda x: x[x.verd0.str.contains('KEEP')],
 'P4 ovr<0.08 & KEEP':             lambda x: x[x.two_sided&(x.overround<0.08)&x.verd0.str.contains('KEEP')],
 'P5 min-ovr rung per ladder':     rung_min_ovr,
 'P6 max-conf rung per ladder':    rung_max_conf,
 'P7 agree 0<=edge<0.03':          lambda x: x[(x.edge>=0)&(x.edge<0.03)],
 'P8 odds>=1.30 (2-leg band)':     lambda x: x[x.odds>=1.30],
 'P9 ovr<0.08 & odds>=1.30':       lambda x: x[x.two_sided&(x.overround<0.08)&(x.odds>=1.30)],
}
print(f'== legs, {which} days {DAYS[0]}..{DAYS[-1]}; ROI pre-tax per leg; single after tax; implied random-AKO after tax 0.88*(1+r)^n-1')
for name,f in POOLS.items():
    x=f(U); x=x[x.status.isin(['won','lost'])]
    r=boot_roi(x,leg_profit(x)); st=boot_roi(x,leg_profit(x,True))
    imp=lambda n: tuple(100*(TAX*(1+v)**n-1) for v in r[:3])
    print(f'{name:30s} {fmt(r)} single_tax={st[0]*100:+6.1f}% [{st[1]*100:+.1f},{st[2]*100:+.1f}] 2leg={imp(2)[0]:+.1f}% [{imp(2)[1]:+.1f},{imp(2)[2]:+.1f}] 3leg={imp(3)[0]:+.1f}%')
# late read rule: legs KEEP in the last pre-kickoff snapshot, bet then at that snapshot's price
x=U[U.last_verdicts.str.contains('KEEP')&U.status.isin(['won','lost'])&(U.last_src=='legs')]
print(f'{"P10 KEEP late, at late price":30s} {fmt(boot_roi(x,leg_profit(x,odds_col="last_odds")))}')
if len(sys.argv)>2:
    print('== E2E slips: up to 10 disjoint slips/day, one leg per match, legs <=3.5, ungraded/void legs removed and price recomputed')
    day_legs={d:U[(U.day==d)&(U.odds<=3.5)] for d in DAYS}
    for lo,hi,nmin,nmax in [(2.5,3.5,2,4),(1.6,2.4,2,2),(2.5,3.5,3,3)]:
        print(f'-- target [{lo},{hi}] legs {nmin}-{nmax}')
        for name in ['P0 all printed','P1 two-sided ovr<0.08','P2 two-sided ovr<wf_cap','P4 ovr<0.08 & KEEP','P5 min-ovr rung per ladder']:
            f=POOLS[name]
            for sname,sc in [('rand',None),('logconf',lambda c: np.log(c.conf)),('minovr',lambda c: -c.overround.fillna(1))]:
                if sc is None:
                    res=[]
                    for seed in range(5):
                        rng=np.random.default_rng(seed)
                        res.append(simulate({d:f(c) for d,c in day_legs.items()}, lambda c: rng.random(len(c)), lo,hi,nmin,nmax,K=10).assign(seed=seed))
                    s=pd.concat(res); s['day_seed']=s.day+s.seed.astype(str)
                    per=s.groupby('seed').profit.mean()
                    r=boot_slips(s)  # by day
                    print(f'  {name:28s} {sname:7s} slips={len(s)/5:5.0f}/seed hit={s.won.mean():.3f} price={s.price.mean():.2f} ROI_tax={r[0]*100:+6.1f}% [{r[1]*100:+.1f},{r[2]*100:+.1f}] seeds[{per.min()*100:+.1f},{per.max()*100:+.1f}]')
                    s.to_csv(f'b_{which}_{name[:2]}_{sname}_{lo}_{nmin}{nmax}.csv',index=False)
                else:
                    s=simulate({d:f(c) for d,c in day_legs.items()}, sc, lo,hi,nmin,nmax,K=10)
                    r=boot_slips(s)
                    print(f'  {name:28s} {sname:7s} slips={len(s):5d}      hit={s.won.mean():.3f} price={s.price.mean():.2f} ROI_tax={r[0]*100:+6.1f}% [{r[1]*100:+.1f},{r[2]*100:+.1f}] maxDD={drawdown(s):.1f}u')
                    s.to_csv(f'b_{which}_{name[:2]}_{sname}_{lo}_{nmin}{nmax}.csv',index=False)
