import numpy as np, pandas as pd
H='/Users/mkoziol/projects/bet/data/kupon_redesign_2026-10-31'
DEV=[f'2026-10-{d:02d}' for d in range(13,25)]; VAL=[f'2026-10-{d:02d}' for d in range(25,29)]
L=pd.read_pickle(f'{H}/legs.pkl'); S=pd.read_pickle(f'{H}/signals.pkl')
L=L[L.day.isin(DEV+VAL)]  # never touch hold-out
print('days loaded', sorted(L.day.unique())[0], sorted(L.day.unique())[-1])
edges=np.arange(0.40,1.0001,0.05)
def prep(days):
    d=L[L.day.isin(days)&L.status.isin(['won','lost','refund'])&(L.dec_src=='legs')]
    d=d.merge(S,on=['day','key'],how='left')
    d['inv']=1/d.odds.astype(float); d['w']=(d.status=='won').astype(float)
    d['b']=pd.cut(d.inv,edges,include_lowest=True).astype(str); return d
def cell(d,mask):
    s=d[d.status!='refund']; base=(s.w-s.inv).groupby(s.b).mean()
    c=d[mask&(d.status!='refund')]
    ex=((c.w-c.inv)-c.b.map(base).fillna(0)).mean()
    od=c.odds.astype(float)
    return dict(n=len(c),hit=round(c.w.mean(),4),inv=round(c.inv.mean(),4),lift=round((c.w.mean()-c.inv.mean())*100,2),
                excess=round(ex*100,2),sat=round(((c.w*od*0.88).mean()-1)*100,2),matches=c.eid.nunique())
for sp,s8 in [('cs2',False),('volleyball',False),('volleyball',True)]:
    for nm,days in [('dev',DEV),('val',VAL)]:
        d=prep(days); m=d.sport==sp
        if s8: m&=(pd.to_numeric(d.sample_size,errors='coerce')>=8)&(d.forecast_source!='league_rate')
        print(sp,'s8' if s8 else 'all',nm,cell(d,m))
