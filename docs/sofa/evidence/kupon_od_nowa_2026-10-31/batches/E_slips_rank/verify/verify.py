import numpy as np, pandas as pd
from zoneinfo import ZoneInfo
H='/Users/mkoziol/projects/bet/data/kupon_redesign_2026-10-31'
DEV=[f'2026-10-{d:02d}' for d in range(13,25)]; VAL=[f'2026-10-{d:02d}' for d in range(25,29)]
legs=pd.read_pickle(f'{H}/legs.pkl'); sig=pd.read_pickle(f'{H}/signals.pkl')
legs=legs[legs.day.isin(DEV+VAL)]; sig=sig[sig.day.isin(DEV+VAL)]
assert not legs.day.isin(['2026-10-29','2026-10-30']).any()
def prep(days):
    d=legs[legs.day.isin(days)&legs.status.isin(['won','lost','refund'])&(legs.dec_src=='legs')].copy()
    d=d.merge(sig,on=['day','key'],how='left')
    d['odds']=d.odds.astype(float); d['inv']=1/d.odds
    d['w']=(d.status=='won'); d['rf']=(d.status=='refund')
    ko=pd.to_datetime(d.kickoff,unit='s',utc=True).dt.tz_convert(ZoneInfo('Europe/Warsaw'))
    h=ko.dt.hour+ko.dt.minute/60; d['h']=np.where(h<6,h+24,h)
    ss=pd.to_numeric(d.sample_size,errors='coerce')
    d['pool']=(ss>=8)&(d.forecast_source!='league_rate')
    return d
def sim(d,rank,n,t,seed=0,tol=0.15,spw=3):
    rng=np.random.default_rng(seed)
    per=t**(1/n); lo,hi=per*(1-tol),per*(1+tol)
    p=d[d.pool].copy(); p['r']=rank[d.pool].astype(float); p['tie']=rng.random(len(p))
    p=p[(p.odds>=max(lo,1.01))&(p.odds<=hi)]
    out=[]
    for wn,(a,b) in {'afternoon':(12,17),'evening':(17,21),'night':(21,26)}.items():
        g0=p[(p.h>=a)&(p.h<b)]
        for day,g in g0.groupby('day'):
            g=g.sort_values(['r','tie'],ascending=False)
            used=set()
            for s in range(spw):
                sl=[]
                for r in g.itertuples():
                    if r.eid in used or any(x.eid==r.eid for x in sl): continue
                    if len(sl)==n-1:
                        pr=np.prod([x.odds for x in sl])*r.odds
                        if not t*(1-tol)<=pr<=t*(1+2*tol): continue
                    sl.append(r)
                    if len(sl)==n: break
                if len(sl)<n: break
                used|={x.eid for x in sl}
                prod=np.prod([x.odds for x in sl]); eff=np.prod([1 if x.rf else x.odds for x in sl])
                win=all(x.rf or x.w for x in sl)
                out.append((day,prod,win,0.88*eff if win else 0))
    o=pd.DataFrame(out,columns=['day','prod','won','pay'])
    return dict(slips=len(o),hit=round(o.won.mean(),4),prod=round(o['prod'].mean(),3),roi=round((o.pay.mean()-1)*100,2),days=o.day.nunique())
for nm,days in (('dev',DEV),('val',VAL)):
    d=prep(days)
    R={'margin_conf':d.conf.astype(float)-d.inv,'price_long':-d.inv}
    for rk,n,t in [('margin_conf',3,3.0),('price_long',3,3.0),('price_long',2,2.0)]:
        res=sim(d,R[rk],n,t); print(nm,rk,n,t,res)
        if rk=='price_long':
            rs=[sim(d,R[rk],n,t,seed=s)['roi'] for s in range(1,6)]; print('  seed sensitivity roi',rs)
