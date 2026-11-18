"""Pooled (all states, all of the dev seasons) team-score mean / variance for the power table only."""
import json,gzip,statistics as st,datetime as dt
L={(l["sport"],l["ut"],l["year"]) for l in json.load(open("leagues.json")) if l["ok"] and l["year"]==2024}
from seasons_rules import POST,OTHER
vb={}
for l in gzip.open("vb_periods_dev.jsonl.gz","rt"):
    r=json.loads(l); vb[r[0]]=r[1:]
sy=lambda ts:(lambda d:d.year-(1 if d.month<7 else 0))(dt.datetime.utcfromtimestamp(ts))
vals={"ice-hockey":[],"basketball":[],"volleyball":[]}
for l in gzip.open("games.jsonl.gz","rt"):
    r=json.loads(l)
    if r["st"]!="finished" or not r["t_name"] or POST.search(r["t_name"]) or OTHER.search(r["t_name"]): continue
    if (r["sport"],r["ut_id"],sy(r["ts"])) not in L: continue
    if r["sport"]=="volleyball":
        p=vb.get(r["id"]); 
        if not p: continue
        hs=[p[2*i] for i in range(5) if p[2*i] is not None]; as_=[p[2*i+1] for i in range(5) if p[2*i+1] is not None]
        if len(hs)<3 or len(hs)!=len(as_): continue
        vals["volleyball"]+= [sum(hs)/len(hs), sum(as_)/len(as_)]
    elif isinstance(r["hs"],int) and isinstance(r["as"],int):
        vals[r["sport"]]+=[r["hs"],r["as"]]
for s,v in vals.items():
    m=st.mean(v); var=st.pvariance(v); print(s,len(v),"mean",round(m,3),"var",round(var,3),"var/mu^2",round(var/m/m,5))
