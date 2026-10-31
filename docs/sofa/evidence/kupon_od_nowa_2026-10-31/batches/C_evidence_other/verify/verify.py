"""Independent recompute of C_evidence_other top 3 leg cells (no bt_lib)."""
import numpy as np, pandas as pd
H='/Users/mkoziol/projects/bet/data/kupon_redesign_2026-10-31'
DEV=[f'2026-10-{d}' for d in range(13,25)]; VAL=[f'2026-10-{d}' for d in range(25,29)]
L=pd.read_pickle(f'{H}/legs.pkl')
L=L[L.day.isin(DEV+VAL)].copy()   # hold-out dropped immediately
S=pd.read_pickle(f'{H}/signals.pkl'); S=S[S.day.isin(DEV+VAL)]
def prep(days):
    x=L[L.day.isin(days)&L.status.isin(['won','lost','refund'])&(L.dec_src=='legs')]
    x=x.merge(S,on=['day','key'],how='left')
    x['inv']=1/x.odds.astype(float); x['w']=(x.status=='won').astype(float); x['rf']=x.status=='refund'
    above=(x.conf.astype(float)>x.inv).astype(float)
    g=above.groupby([x.day,x.eid,x.market,x.subject,x.direction],dropna=False)
    x['lag']=g.transform('mean'); x['lan']=g.transform('size')
    x['cnt']=x.metric.notna()
    edges=np.round(np.arange(0.40,1.0001,0.05),2)
    x['band']=pd.cut(x.inv,edges,include_lowest=True).astype(str)
    return x
out=[]
for sp,days in (('dev',DEV),('val',VAL)):
    x=prep(days)
    s=x[~x.rf]; bl=(s.w-s.inv).groupby(s.band).mean()
    cells={'pooled|caln_lt300|inv_lt75':~x.cnt&(x.calibration_n<300)&(x.inv<0.75),
           'pooled|ladder_eq1_n3':~x.cnt&(x.lag>=1)&(x.lan>=3),
           'fb_noncount|ladder_eq1_n3':~x.cnt&(x.sport=='football')&(x.lag>=1)&(x.lan>=3)}
    for c,m in cells.items():
        cc=x[m.fillna(False)&~x.rf]
        ex=((cc.w-cc.inv)-cc.band.map(bl).fillna(0)).mean()
        out.append(dict(split=sp,cell=c,n=len(cc),matches=cc.eid.nunique(),hit=cc.w.mean(),inv=cc.inv.mean(),
          lift_pp=100*(cc.w.mean()-cc.inv.mean()),excess_pp=100*ex,roi_pre=100*(cc.w*cc.odds-1).mean(),
          sat=100*((cc.w*cc.odds*0.88).mean()-1),
          n_cal_na=int(cc.calibration_n.isna().sum()) ))
r=pd.DataFrame(out); print(r.round(4).to_string())
r.to_csv(f'{H}/batches/C_evidence_other/verify/recomputed.csv',index=False)
