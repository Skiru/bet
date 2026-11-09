import json,collections,sys
sys.path[:0]=["/Users/mkoziol/projects/bet/src"]
from bet.sofa import epochs
scope=epochs.SCHEDULE_TERM_MARKETS|epochs.SCHEDULE_TERM_FLOOR_EXCLUDED
def K(l): return (l.get("sofascore_event_id"),l.get("sport"),l.get("market"),str(l.get("subject") or ""),l.get("line"),l.get("direction"))
on={K(r):r for r in json.load(open("runs/sofa/2026-11-08/05_sheet.json"))}
re_={K(r):r for r in json.load(open("real_05_sheet.json"))}
both=[k for k in on if k in re_]
print("keys ON",len(on),"REAL",len(re_),"both",len(both),"onlyON",len(set(on)-set(re_)),"onlyREAL",len(set(re_)-set(on)))
c=collections.Counter(); ex={}
for k in both:
    a,b=on[k].get("p_central"),re_[k].get("p_central")
    ins=k[2] in scope
    ch= a!=b
    c[(k[1],ins,ch)]+=1
    if ch and not ins: ex.setdefault(k[2],[]).append((k,a,b))
for x,v in sorted(c.items(),key=str): print(x,v)
print("out-of-scope changed by market:",sorted(((m,len(v)) for m,v in ex.items()),key=lambda x:-x[1])[:20])
for m,v in list(ex.items())[:6]: print(m, v[:2])
# in-scope: does shadow equal real p?
ins=[k for k in both if k[2] in epochs.SCHEDULE_TERM_MARKETS and on[k].get("p_central_no_schedule_term") is not None]
eq=sum(1 for k in ins if abs(on[k]["p_central_no_schedule_term"]-(re_[k].get("p_central") or -9))<1e-9)
print("in-scope shadow == real p:",eq,"of",len(ins))
