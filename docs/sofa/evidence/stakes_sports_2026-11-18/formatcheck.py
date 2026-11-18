"""Format check: rebuilt end-of-regular-season top-K vs the set of teams seen in the post-season (structure only)."""
import json,gzip,collections,datetime as dt
from seasons_rules import POST,OTHER,EXCLUDED_STRUCTURE,conference_of,points_rule
rows=[json.loads(l) for l in gzip.open("games.jsonl.gz","rt")]
sy=lambda ts:(lambda d:d.year-(1 if d.month<7 else 0))(dt.datetime.utcfromtimestamp(ts))
L=[l for l in json.load(open("leagues.json")) if l["ok"]]
res=collections.Counter(); bad=[]; keep=[]
from seasons_rules import season_groups
idx=season_groups(rows)
for l in L:
    g=idx[(l["sport"],l["ut"],l["sid"])]
    main=collections.Counter(r["t_name"] for r in g if not POST.search(r["t_name"]) and not OTHER.search(r["t_name"])).most_common(1)[0][0]
    reg={};  
    for r in sorted((r for r in g if r["t_name"]==main and r["st"]=="finished"),key=lambda r:r["id"]): reg[(r["h"],r["a"],r["ts"]//86400)]=r
    post={t for r in g if POST.search(r["t_name"]) and (not OTHER.search(r["t_name"]) or "Stanley" in r["t_name"]) for t in (r["h"],r["a"])}
    names={}
    for r in reg.values(): names[r["h"]]=r["hn"]; names[r["a"]]=r["an"]
    conf=conference_of(l["sport"],l["ut"],names)
    K=points_rule(l["sport"],l["ut"],len(post),conf,l["teams"])
    pts=collections.Counter()
    for r in reg.values():
        a,b=K["award"](r,l["sport"]); pts[r["h"]]+=a; pts[r["a"]]+=b
    groups=collections.defaultdict(list)
    for t in names: groups[(conf or {}).get(t,"ALL")].append(t)
    top=set()
    for grp in groups.values(): top|=set(sorted(grp,key=lambda t:-pts[t])[:K["k"]])
    miss=len(top-post)
    res[(l["sport"],"exact" if miss==0 else "off1" if miss==1 else "off2+")]+=1
    if miss>=2: bad.append((l["sport"],l["ut"],l["name"],l["year"],miss))
    else: keep.append([l["sport"],l["ut"],l["sid"]])
print(sorted(res.items())); print(bad)
json.dump(keep,open("keep.json","w"))
