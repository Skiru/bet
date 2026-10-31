"""Printed Bet Builders (first snapshot of each day), graded by 13_results 'builders'; price modelled as
0.90 x product of single prices (Superbet does not price a builder as the product - assumption, stated)."""
import json, os, sys, numpy as np
sys.path.insert(0,os.path.dirname(__file__))
from lib import DEV, HOLD, TAX
ROOT='/Users/mkoziol/projects/bet/runs/sofa'
rows=[]
for d in DEV+HOLD:
    res=json.load(open(f'{ROOT}/{d}/13_results.json')).get('builders',{})
    byev={}
    for k,v in res.items():
        eid=json.loads(k)[0]; byev.setdefault(eid,[]).append(v)
    f=sorted(os.listdir(f'{ROOT}/{d}/printed'))[0]
    q=json.load(open(f'{ROOT}/{d}/printed/{f}'))
    for b in q.get('builders',[]):
        g=byev.get(b['sofascore_event_id'])
        if not g: continue
        st=g[0]['status']
        if st not in ('won','lost'): continue
        prod=float(np.prod([l['odds'] for l in b['legs']]))
        pc=float(np.prod([l['confidence'] for l in b['legs']]))
        rows.append((d,b['sofascore_event_id'],st,prod,pc,len(b['legs'])))
import pandas as pd
x=pd.DataFrame(rows,columns=['day','eid','st','prod','pconf','n'])
for name,sel in [('dev',x.day.isin(DEV)),('hold',x.day.isin(HOLD))]:
    y=x[sel]; w=(y.st=='won')
    for k,fac in [('x1.00',1.0),('x0.90',0.9)]:
        p=np.where(w,TAX*fac*y['prod']-1,-1)
        rng=np.random.default_rng(0); B=np.array([p[rng.integers(0,len(p),len(p))].mean() for _ in range(2000)])
        print(f'{name} builders n={len(y)} hit={w.mean():.3f} mean prod conf={y.pconf.mean():.3f} avg product={y["prod"].mean():.2f} ROI_tax at {k} product: {p.mean()*100:+.1f}% [{np.percentile(B,2.5)*100:+.1f},{np.percentile(B,97.5)*100:+.1f}]')
