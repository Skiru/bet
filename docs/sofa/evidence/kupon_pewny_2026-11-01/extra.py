import json, math, random, sys, collections
exec(open(sys.argv[0].replace("extra.py","analyse.py")).read().split("periods =")[0].replace("rows = [json.loads(l) for l in open(sys.argv[1])]","rows=[json.loads(l) for l in open(sys.argv[1])]"))
C = [s for s in slips if s["arm"]=="C_safe_114"]
print("C odds dist", collections.Counter(round(s["prod"],2) for s in C).most_common(8))
print("C chance==1/odds (capped at price):", sum(abs(s["chance"]-1/s["prod"])<1e-9 for s in C), "of", len(C))
print("C conf mean", sum(l["conf"] for s in C for l in s["legs"])/sum(len(s["legs"]) for s in C))
print("C 2-leg:", [ (s["day"], s["win"], [(l["odds"], round(l["chance"],3)) for l in s["legs"]]) for s in C if len(s["legs"])>1])
print("C markets", collections.Counter(f'{l["market"]}|{l["dir"]}' for s in C for l in s["legs"]).most_common(10))
# paired by request day+window+rank
def key(s): return (s["day"], s["win"], s["rank"])
def daydiff(a, b, pf):
    xa=[s for s in slips if s["arm"]==a and pf(s["day"]) and s["ret"] is not None]
    xb=[s for s in slips if s["arm"]==b and pf(s["day"]) and s["ret"] is not None]
    days=sorted({s["day"] for s in xa+xb}); rng=random.Random(7); v=[]
    ba=collections.defaultdict(list); bb=collections.defaultdict(list)
    for s in xa: ba[s["day"]].append(s["ret"])
    for s in xb: bb[s["day"]].append(s["ret"])
    def m(ds,by): z=[r for d in ds for r in by[d]]; return sum(z)/len(z)
    pt=m(days,ba)-m(days,bb)
    for _ in range(2000):
        ds=[rng.choice(days) for _ in days]; v.append(m(ds,ba)-m(ds,bb))
    v.sort(); return pt, v[50], v[1949]
for pn,pf in {"dev":lambda d:d<="2026-10-24","hold":lambda d:d>="2026-10-25","all":lambda d:True}.items():
    for a,b in [("C_safe_114","A_def_t2"),("C_safe_114","B_def_t125"),("C_safe_114","D_safe_t13")]:
        pt,lo,hi=daydiff(a,b,pf); print(pn,a,"-",b,f"ROI diff {100*pt:+.1f} pp [{100*lo:+.1f},{100*hi:+.1f}]")
# leg-level: does conf above price matter in C
for src in ["pewność","cena (pewność ponad cenę)"]:
    g=[l for s in C for l in s["legs"] if l["src"]==src and l["status"] in("won","lost")]
    print(src, len(g), "hit", round(sum(l["status"]=="won" for l in g)/len(g),3), "chance", round(sum(l["chance"] for l in g)/len(g),3), "conf", round(sum(l["conf"] for l in g)/len(g),3))
# per-day C hit
print("C per-day losses:", {d: sum(1 for s in C if s["day"]==d and s["st"]=="lost") for d in sorted({s["day"] for s in C})})
