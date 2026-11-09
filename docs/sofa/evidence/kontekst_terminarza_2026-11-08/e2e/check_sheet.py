import json, sys, statistics, collections
sys.path[:0]=["/Users/mkoziol/projects/bet/src","/Users/mkoziol/projects/bet"]
from bet.sofa import epochs, sheet_config
E="/Users/mkoziol/projects/bet/data/refit_2026-11-08_schedule/e2e"
d=json.load(open(E+"/runs/sofa/2026-11-08/05_sheet.json"))
print(type(d))
rows=d if isinstance(d,list) else d["rows"]
print("rows",len(rows))
fb=[r for r in rows if r.get("sport")=="football"]
print("football rows",len(fb))
scope=epochs.SCHEDULE_TERM_MARKETS; floor=epochs.SCHEDULE_TERM_FLOOR_EXCLUDED
c=collections.Counter()
bad=[]
for r in fb:
    m=r.get("market"); has=("schedule_term" in r and r["schedule_term"] is not None); hp=r.get("p_central_no_schedule_term") is not None
    ins=m in scope; fl=m in floor
    c[(("scope" if ins else "floor" if fl else "other"),has,hp)]+=1
    c[("marker",r.get("schedule_term_rule"))]+=1
    if not ins and not fl and (has or hp): bad.append(m)
for k,v in sorted(c.items(),key=str): print(k,v)
print("out-of-scope rows with fields:",len(bad),collections.Counter(bad).most_common(5))
nf=[r for r in rows if r.get("sport")!="football" and (r.get("schedule_term") is not None or r.get("p_central_no_schedule_term") is not None or r.get("schedule_term_rule"))]
print("non-football rows with fields/marker:",len(nf))
# floor keys equal uncorrected
fl=[r for r in fb if r.get("market") in floor]
neq=[r for r in fl if r.get("p_central_no_schedule_term") is not None and abs(r["p_central_no_schedule_term"]-r["p_central"])>1e-12]
print("floor rows",len(fl),"with shadow",sum(r.get("p_central_no_schedule_term") is not None for r in fl),"shadow!=p",len(neq), "status", collections.Counter((r.get("schedule_term") or {}).get("status") for r in fl))
sc=[r for r in fb if r.get("market") in scope]
print("scope rows",len(sc),"status",collections.Counter((r.get("schedule_term") or {}).get("status") for r in sc))
diff=[r["p_central"]-r["p_central_no_schedule_term"] for r in sc if r.get("p_central_no_schedule_term") is not None and r.get("p_central") is not None]
nz=[x for x in diff if abs(x)>1e-9]
print("scope p - shadow: n",len(diff),"nonzero",len(nz), "mean|d|", statistics.mean(abs(x) for x in nz) if nz else 0, "max|d|", max((abs(x) for x in nz),default=0))
# per-fixture t
ev={}
for r in sc:
    t=r.get("schedule_term") or {}
    ev.setdefault(r.get("event_id") or r.get("sofascore_event_id"), (t.get("status"),t.get("t_home"),t.get("t_away")))
st=collections.Counter(v[0] for v in ev.values()); print("fixtures",len(ev),st)
ts=[x for v in ev.values() if v[0]=="APPLIED" for x in (v[1],v[2]) if x is not None]
nzt=[x for x in ts if x!=0]
if ts:
    q=statistics.quantiles(ts,n=10)
    print("t sides",len(ts),"nonzero",len(nzt),"min %.3f max %.3f mean %.4f sd %.4f"%(min(ts),max(ts),statistics.mean(ts),statistics.pstdev(ts)),"deciles",[round(x,3) for x in q])
ex=next((r for r in sc if (r.get("schedule_term") or {}).get("status")=="APPLIED"),None)
print("example schedule_term keys", list((ex or {}).get("schedule_term",{}).keys()))
print(json.dumps(ex.get("schedule_term"))[:600] if ex else None)
# config_sha
shas=collections.Counter(r.get("config_sha") for r in rows); print("config_sha",shas)
print("SHEET_CONFIG_FILES has schedule_terms:", "sofa_schedule_terms.json" in sheet_config.SHEET_CONFIG_FILES, getattr(sheet_config,"SHEET_CONFIG_FILES",None))
real=json.load(open(E+"/real_05_sheet.json")); rr=real if isinstance(real,list) else real["rows"]
print("real config_sha",collections.Counter(r.get("config_sha") for r in rr))
