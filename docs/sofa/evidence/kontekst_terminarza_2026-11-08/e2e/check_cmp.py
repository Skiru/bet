import json, collections, sys
sys.path[:0]=["/Users/mkoziol/projects/bet/src"]
from bet.sofa import epochs
scope=epochs.SCHEDULE_TERM_MARKETS
def legs(path):
    c=json.load(open(path)); out={}
    for p in c["singles"]:
        for l in (p.get("legs") or [p]):
            k=(l.get("sofascore_event_id") or l.get("event_id"),l.get("sport"),l.get("market"),str(l.get("subject")),l.get("line"),l.get("direction"))
            out[k]=l
    return c,out
_,on=legs("runs/sofa/2026-11-08/11_coupon.json")
_,ct=legs("runs_ctrl/sofa/2026-11-08/11_coupon.json")
_,re_=legs("/Users/mkoziol/projects/bet/runs/sofa/2026-11-08/11_coupon.json")
for name,a,b in (("ON vs CTRL(off, same clock 08:00)",on,ct),("ON vs REAL (built 17:5x, off)",on,re_)):
    print("==",name,"| ON",len(a),"other",len(b))
    fam=lambda d,s: collections.Counter(k[2] for k in d if (k[2] in scope)==s and k[1]=="football")
    for s in (True,False):
        fa,fb_=fam(a,s),fam(b,s)
        ms=sorted(set(fa)|set(fb_),key=lambda m:-(fa[m]+fb_[m]))
        print(" in-scope" if s else " football out-of-scope", "tot",sum(fa.values()),"vs",sum(fb_.values()))
        print("  ",[(m,fa[m],fb_[m]) for m in ms if fa[m]!=fb_[m] or s][:25])
    ins_a={k for k in a if k[2] in scope}; ins_b={k for k in b if k[2] in scope}
    both=ins_a&ins_b
    dconf=[k for k in both if a[k].get("confidence")!=b[k].get("confidence")]
    print(" in-scope: only ON",len(ins_a-ins_b),"only other",len(ins_b-ins_a),"both",len(both),"both w/ different confidence",len(dconf))
    oth_a={k for k in a if k[2] not in scope}; oth_b={k for k in b if k[2] not in scope}
    print(" out-of-scope: only ON",len(oth_a-oth_b),"only other",len(oth_b-oth_a), "by sport only-ON",collections.Counter(k[1] for k in oth_a-oth_b), "only-other", collections.Counter(k[1] for k in oth_b-oth_a))
    if name.startswith("ON vs CTRL"):
        x=collections.Counter(k[2] for k in oth_a ^ oth_b); print("  out-of-scope symmetric diff by market",x.most_common(8))
