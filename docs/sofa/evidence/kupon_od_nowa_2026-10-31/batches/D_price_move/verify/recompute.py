import numpy as np, pandas as pd
H='/Users/mkoziol/projects/bet/data/kupon_redesign_2026-10-31'
DEV=[f'2026-10-{d:02d}' for d in range(13,25)]; VAL=[f'2026-10-{d:02d}' for d in range(25,29)]
L=pd.read_pickle(f'{H}/legs.pkl'); S=pd.read_pickle(f'{H}/signals.pkl')
L=L[L.day.isin(DEV+VAL)]
assert not L.day.isin(['2026-10-29','2026-10-30']).any()
S=S[S.day.isin(DEV+VAL)]
L=L[L.status.isin(['won','lost','refund']) & (L.dec_src=='legs')]
df=L.merge(S,on=['day','key'],how='left')
assert len(df)==len(L)
df['o']=df.odds.astype(float); df['inv']=1/df.o; df['w']=(df.status=='won').astype(float)
df['mf']=df.o/pd.to_numeric(df.first_odds,errors='coerce')-1
edges=np.round(np.arange(0.40,1.0001,0.05),2)
def band(x):
    # bands of width .05 from .40; first band includes lower edge, (a,b] otherwise; outside -> nan
    b=np.full(len(x),-1)
    for i in range(len(edges)-1):
        lo,hi=edges[i],edges[i+1]
        m=((x>lo)|((i==0)&(x>=lo)))&(x<=hi)
        b[m.values]=i
    return b
df['band']=band(df.inv)
cells={
 'A shortened move_first<-0 | sport=bb/vb/cs2': lambda d:(d.mf<0)&d.sport.isin(['basketball','volleyball','cs2']),
 'A shortened move_first<-0 | dir=other': lambda d:(d.mf<0)&~d.direction.isin(['OVER','UNDER']),
 'A shortened move_first<-0.02 | fam=other_sports': lambda d:(d.mf<-0.02)&~d.sport.isin(['football','tennis']),
}
for name,fn in cells.items():
    for sp,days in (('dev',DEV),('val',VAL)):
        d=df[df.day.isin(days)]
        nr=d[d.status!='refund']
        base=(nr.w-nr.inv).groupby(nr.band).mean()
        c=nr[fn(nr).fillna(False)]
        exp=c.band.map(base).fillna(0); exp[c.band<0]=0
        ex=((c.w-c.inv)-exp).mean()
        roi=(c.w*c.o-1).mean(); at=(c.w*c.o*0.88).mean()-1
        print(f'{name} {sp}: n={len(c)} hit={c.w.mean():.4f} inv={c.inv.mean():.4f} lift={100*(c.w.mean()-c.inv.mean()):.2f} excess={100*ex:.2f} roi={100*roi:.2f} at={100*at:.2f} outside_bands={(c.band<0).sum()} sports={c.sport.value_counts().to_dict()}')
print('mf nan in dec:',df.mf.isna().sum(),' first_t<=dec_t all:',(df.first_t<=df.dec_t).all(), ' dec_t<=ko-1800:',(df.dec_t<=df.kickoff-1800).all())
