import numpy as np, pandas as pd
TAX=0.88
DEV=[f'2026-10-{d:02d}' for d in range(13,27)]
HOLD=[f'2026-10-{d:02d}' for d in range(27,31)]
def load():
    df=pd.read_pickle(__file__.rsplit('/',1)[0]+'/legs.pkl')
    df['ko_lag_h']=(df.kickoff-df.first_t)/3600
    df['inv']=1/df.odds
    df['edge']=df.conf-df.inv
    df['won']=(df.status=='won').astype(float)
    df['settled']=df.status.isin(['won','lost'])
    return df
def morning(df, min_lead_min=15):
    m=(df.first_snap==0)&(df.first_src=='legs')&(df.kickoff-df.first_t>min_lead_min*60)
    return df[m].copy()
def leg_profit(d, tax=False, odds_col='odds'):
    o=d[odds_col]
    return np.where(d.status=='won',(TAX if tax else 1)*o-1,-1.0)
def boot_roi(d, profit, cluster='eid', B=1000, seed=0):
    """ROI = mean profit per stake; bootstrap clusters (match)."""
    d=d.assign(_p=profit)
    g=d.groupby(cluster)['_p'].agg(['sum','count'])
    s=g['sum'].values; c=g['count'].values
    if len(s)==0: return (np.nan,np.nan,np.nan,0)
    rng=np.random.default_rng(seed); n=len(s)
    idx=rng.integers(0,n,(B,n))
    r=s[idx].sum(1)/c[idx].sum(1)
    return (s.sum()/c.sum(), np.percentile(r,2.5), np.percentile(r,97.5), int(c.sum()))
def fmt(t):
    roi,lo,hi,n=t
    return f'n={n:5d} ROI={roi*100:+6.1f}% [{lo*100:+6.1f},{hi*100:+6.1f}]'
