"""FINAL: one run on hold-out 2026-10-27..10-30 of the pre-specified flows + baselines."""
import numpy as np, pandas as pd
from lib import *
from slips import simulate, boot_slips, drawdown
df=load(); m=morning(df).sort_values('first_t').drop_duplicates('key',keep='first')
m['two_sided']=m.overround.notna()
CAPS=[0.06,0.07,0.08,0.09,0.10,0.15]
def learned_cap(day):
    p=m[(m.day<day)&m.status.isin(['won','lost'])&m.two_sided]; best=0.15; bv=-9
    for c in CAPS:
        x=p[p.overround<c]
        if len(x)<500: continue
        v=leg_profit(x).mean()
        if v>bv: bv=v; best=c
    return best
caps={d:learned_cap(d) for d in HOLD}; print('walk-forward caps for hold-out:',caps)
U=m[m.day.isin(HOLD)].copy(); U['cap']=U.day.map(caps)
LOW=lambda x: x[x.two_sided&(x.overround<x.cap)]
ALL=lambda x: x
print('== legs (singles), hold-out')
for name,f in [('low-margin pool',LOW),('all printed',ALL)]:
    x=f(U); x=x[x.status.isin(['won','lost'])]
    r=boot_roi(x,leg_profit(x)); t=boot_roi(x,leg_profit(x,True))
    print(f'  {name:18s} {fmt(r)} | single after tax {t[0]*100:+.1f}% [{t[1]*100:+.1f},{t[2]*100:+.1f}] hit={x.won.mean():.3f} 1/o={x.inv.mean():.3f}')
day_legs={d:U[(U.day==d)&(U.odds<=3.5)] for d in HOLD}
def run(label,f,score,lo,hi,a,b,seeds=None):
    if seeds:
        S=[]
        for sd in range(seeds):
            rng=np.random.default_rng(100+sd)
            S.append(simulate({d:f(c) for d,c in day_legs.items()}, lambda c: rng.random(len(c)), lo,hi,a,b,K=10).assign(seed=sd))
        s=pd.concat(S); per=s.groupby('seed').profit.mean(); extra=f' seeds[{per.min()*100:+.1f},{per.max()*100:+.1f}] slips/seed={len(s)/seeds:.0f}'
        dd=np.mean([drawdown(s[s.seed==k]) for k in range(seeds)])
    else:
        s=simulate({d:f(c) for d,c in day_legs.items()}, score, lo,hi,a,b,K=10); extra=f' slips={len(s)}'; dd=drawdown(s)
    r=boot_slips(s); r2=boot_slips(s.assign(m=range(len(s))),by='m')
    print(f'  {label:40s} legs/slip={s.n.mean():.2f} price={s.price.mean():.2f} hit={s.won.mean():.3f} ROI_tax={r[0]*100:+6.1f}% dayCI[{r[1]*100:+.1f},{r[2]*100:+.1f}] slipCI[{r2[1]*100:+.1f},{r2[2]*100:+.1f}] maxDD={dd:.1f}u{extra}')
    s.to_csv(f'final_{label.split()[0]}.csv',index=False)
print('== slips, hold-out (up to 10 disjoint slips/day, flat 1u stake, payout 0.88 x price)')
run('F1 low-margin 2-leg [1.6,2.4] random',LOW,None,1.6,2.4,2,2,seeds=20)
run('F2 low-margin 3-leg [2.5,3.5] random',LOW,None,2.5,3.5,3,3,seeds=20)
run('B1 all-printed 2-leg [1.6,2.4] random',ALL,None,1.6,2.4,2,2,seeds=20)
run('B2 all-printed 3-leg [2.5,3.5] random',ALL,None,2.5,3.5,3,3,seeds=20)
run('B3 all-printed 2-4 [2.5,3.5] random',ALL,None,2.5,3.5,2,4,seeds=20)
run('B4 CURRENT max prod conf 2-4 [2.5,3.5]',ALL,lambda c: np.log(c.conf),2.5,3.5,2,4)
