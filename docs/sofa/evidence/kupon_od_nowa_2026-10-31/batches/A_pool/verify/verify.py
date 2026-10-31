import numpy as np, pandas as pd
D='/Users/mkoziol/projects/bet/data/kupon_redesign_2026-10-31'
dev=[f'2026-10-{d:02d}' for d in range(13,25)]; val=[f'2026-10-{d:02d}' for d in range(25,29)]
legs=pd.read_pickle(f'{D}/legs.pkl')
legs=legs[legs.day.isin(dev+val)]
sig=pd.read_pickle(f'{D}/signals.pkl'); sig=sig[sig.day.isin(dev+val)]
print('cols legs', list(legs.columns)[:80])
print('cs2 markets', legs[legs.sport=='cs2'].market.value_counts().to_dict())
print('fsrc', legs.forecast_source.value_counts(dropna=False).to_dict())
def split(days):
    x=legs[legs.day.isin(days)&legs.status.isin(['won','lost','refund'])&(legs.dec_src=='legs')].copy()
    x=x.merge(sig,on=['day','key'],how='left')
    x['odds']=x.odds.astype(float); x['ip']=1/x.odds; x['w']=(x.status=='won').astype(float)
    g=['day','eid','market','subject']
    x['dd']=(x.ip-0.5).abs(); x['main']=x.dd==x.groupby(g,dropna=False).dd.transform('min')
    edges=np.arange(0.40,1.0001,0.05)
    x['bd']=pd.cut(x.ip,edges,include_lowest=True).astype(str)
    return x
for nm,days in (('dev',dev),('val',val)):
    x=split(days); s=x[x.status!='refund']
    base=(s.w-s.ip).groupby(s.bd).mean()
    cs2r=(s.sport=='cs2')&s.market.str.contains('rounds',na=False)
    cs2r_strict=(s.sport=='cs2')&(s.market.str.startswith('map_rounds_')|(s.market=='map_team_rounds'))
    cells={'cs2_rounds&side':cs2r&~s.main,'cs2_rounds':cs2r,'cs2_rounds_strictdef':cs2r_strict,
      'cs2_engine&1.20-1.35':(s.forecast_source=='cs2_engine')&(s.odds>=1.20)&(s.odds<1.35)}
    for c,m in cells.items():
        c_=s[m]; ex=((c_.w-c_.ip)-c_.bd.map(base).fillna(0)).mean()
        roi=(c_.w*c_.odds-1).mean(); at=(c_.w*c_.odds*0.88).mean()-1
        print(nm,c,'n',len(c_),'hit %.4f inv %.4f lift %.2f excess %.2f roi %.2f at %.2f'%(c_.w.mean(),c_.ip.mean(),(c_.w.mean()-c_.ip.mean())*100,ex*100,roi*100,at*100),
              'nan bd',(c_.bd=='nan').sum(), 'days',c_.day.min(),c_.day.max())
