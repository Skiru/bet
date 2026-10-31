"""E2E slip simulation: per test day, from the morning-available legs, build up to K disjoint AKO slips
(one leg per match, n legs in [nmin,nmax], product of odds in [lo,hi]) maximising an additive leg score by DP."""
import numpy as np, pandas as pd
from lib import TAX
BIN=0.01
def best_slip(c, score, lo, hi, nmin, nmax):
    """c: DataFrame of candidates (index aligned with score). DP over matches, one leg each."""
    L=np.log(c.odds.values); S=np.asarray(score,float)
    nb=int(np.ceil(np.log(hi)/BIN))+1
    bins=np.round(L/BIN).astype(int)
    NEG=-1e18
    best=np.full((nmax+1,nb),NEG); best[0,0]=0.0
    back={}  # (k,b) -> list of chosen leg idx (store path)
    path=[[None]*nb for _ in range(nmax+1)]; path[0][0]=()
    eids=c.eid.values
    order=np.argsort(eids,kind='stable')
    groups={}
    for i in order: groups.setdefault(eids[i],[]).append(i)
    for e,idxs in groups.items():
        old=best.copy(); oldp=[row[:] for row in path]
        for i in idxs:
            b=bins[i]
            if b<=0 or b>=nb: continue
            for k in range(nmax,0,-1):
                src=old[k-1,:nb-b]; cand=src+S[i]
                tgt=best[k,b:]
                imp=np.where(cand>tgt)[0]
                for j in imp:
                    if src[j]<=NEG/2: continue
                    best[k,b+j]=cand[j]; path[k][b+j]=oldp[k-1][j]+(i,)
    blo=int(np.ceil(np.log(lo)/BIN)); bhi=int(np.floor(np.log(hi)/BIN))
    top=None; topv=NEG
    for k in range(nmin,nmax+1):
        for b in range(max(blo,0),min(bhi,nb-1)+1):
            if best[k,b]>topv: topv=best[k,b]; top=path[k][b]
    return list(top) if top else None
def grade_slip(legs):
    st=legs.status.values; o=legs.odds.values
    if (st=='lost').any(): return -1.0, 0
    ok=(st=='won')
    price=float(np.prod(o[ok])) if ok.any() else 1.0
    return TAX*price-1.0, 1
def simulate(day_legs, score_fn, lo=2.5, hi=3.5, nmin=2, nmax=4, K=3, filt=None):
    """day_legs: dict day -> candidate DataFrame. score_fn(df)->array. returns slips DataFrame."""
    out=[]
    for d,c in day_legs.items():
        c=c if filt is None else c[filt(c)]
        c=c.reset_index(drop=True)
        used=set()
        for s in range(K):
            cc=c[~c.eid.isin(used)].reset_index(drop=True)
            if len(cc)<nmin: break
            cc=cc.assign(_s=np.asarray(score_fn(cc),float)).sort_values('_s',ascending=False).groupby('eid').head(3).reset_index(drop=True)
            sel=best_slip(cc, cc._s.values, lo, hi, nmin, nmax)
            if not sel: break
            L=cc.iloc[sel]
            p,w=grade_slip(L)
            out.append(dict(day=d,slip=s,n=len(L),price=float(np.prod(L.odds)),profit=p,won=w,
                            legs_won=int((L.status=='won').sum()),voids=int((~L.status.isin(['won','lost'])).sum()),
                            mean_conf=float(L.conf.mean()),keys='; '.join(L.key)))
            used|=set(L.eid)
    return pd.DataFrame(out)
def boot_slips(s, B=2000, seed=1, by='day'):
    if len(s)==0: return (np.nan,)*3+(0,)
    g=s.groupby(by).profit.agg(['sum','count'])
    sm=g['sum'].values; ct=g['count'].values; n=len(sm)
    rng=np.random.default_rng(seed); idx=rng.integers(0,n,(B,n))
    r=sm[idx].sum(1)/ct[idx].sum(1)
    return (sm.sum()/ct.sum(),np.percentile(r,2.5),np.percentile(r,97.5),int(ct.sum()))
def drawdown(s):
    cum=np.cumsum(s.sort_values(['day','slip']).profit.values)
    peak=np.maximum.accumulate(np.concatenate([[0],cum]))[1:]
    return float((peak-cum).max()) if len(cum) else 0.0
