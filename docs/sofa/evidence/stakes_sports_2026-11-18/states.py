"""Per-side stakes state as of tip-off, rebuilt from earlier results only.
COUNTS ONLY: the tested game's own outcome is never read."""
import json, gzip, collections, re, math, datetime as dt, sys
from seasons_rules import POST, OTHER, EXCLUDED_STRUCTURE, conference_of, points_rule
rows=[json.loads(l) for l in gzip.open("games.jsonl.gz","rt")]
import os
KEEP=json.load(open("keep.json")) if os.path.exists("keep.json") else None
YEARS={int(y) for y in os.environ.get("STAKES_YEARS","2024,2025").split(",")}
WINDOW=float(sys.argv[1]) if len(sys.argv)>1 else 0.75
def sy(ts):
    d=dt.datetime.utcfromtimestamp(ts); return d.year-(1 if d.month<7 else 0)
# group regular-season games by (sport, ut, season start year, main name)
from seasons_rules import season_groups, start_year
SG=season_groups(rows)
results=collections.Counter(); leagues=[]; excluded=collections.Counter()
for (sport,ut,sid),allrows in SG.items():
    if sport not in ("ice-hockey","basketball","volleyball"): continue
    if (sport,ut) in EXCLUDED_STRUCTURE: continue
    g=[r for r in allrows if not POST.search(r["t_name"]) and not OTHER.search(r["t_name"])]
    if not g: continue
    year=start_year(min(r["ts"] for r in g))
    if year not in YEARS: continue
    if True:
        main=collections.Counter(r["t_name"] for r in g).most_common(1)[0][0]
        g=[r for r in g if r["t_name"]==main]
        # dedup re-listed ids: same pair, same UTC day
        seen={}; 
        for r in sorted(g,key=lambda r:(r["st"]!="finished",r["id"])):
            key=(r["h"],r["a"],r["ts"]//86400)
            seen.setdefault(key,r)
        g=sorted((r for r in seen.values() if r["st"] not in ("postponed","canceled")),key=lambda r:r["ts"])
        teams=collections.Counter(); fin=collections.Counter()
        for r in g:
            for t in (r["h"],r["a"]):
                teams[t]+=1; fin[t]+= r["st"]=="finished"
        if len(teams)<10: continue
        name={}
        for r in g: name[r["h"]]=r["hn"]; name[r["a"]]=r["an"]
        conf=conference_of(sport,ut,name)
        if conf is None: excluded["conference map missing"]+=0; 
        groups=collections.defaultdict(list)
        for t in teams: groups[(conf or {}).get(t,"ALL")].append(t)
        sched=list(teams.values())
        # post-season teams (format: K) from the same ut / year
        post={t for r in allrows if POST.search(r["t_name"]) and (not OTHER.search(r["t_name"]) or "Stanley" in r["t_name"]) for t in (r["h"],r["a"])}
        K=points_rule(sport,ut,len(post),conf,len(teams))
        ok = (max(sched)-min(sched)<=2 and min(fin[t]/teams[t] for t in teams)>=0.95 and K is not None and 2<=K["k"]<=min(len(m) for m in groups.values())-2)
        leagues.append(dict(sport=sport,ut=ut,sid=sid,year=year,name=g[0]["ut_name"],teams=len(teams),sched=(min(sched),max(sched)),fin=round(min(fin[t]/teams[t] for t in teams),3),post=len(post),K=K and K["k"],ok=ok))
        if not ok: continue
        if KEEP is not None and [sport,ut,sid] not in KEEP: continue
        maxpg=K["maxpg"]; k=K["k"]
        pts=collections.Counter(); gp=collections.Counter()
        for r in g:
            if r["st"]=="finished" and r["ts"]>0:
                pass
        # walk in time; state uses only games with ts < tip-off
        i=0; fins=[r for r in g if r["st"]=="finished"]
        for r in fins:
            # (the table is updated after this game's state is taken)
            pass
        tables_pts=collections.Counter(); tables_gp=collections.Counter()
        idx=0
        for r in fins:
            while idx<len(fins) and fins[idx]["ts"]<r["ts"]:
                q=fins[idx]; ph,pa=K["award"](q,sport); tables_pts[q["h"]]+=ph; tables_pts[q["a"]]+=pa; tables_gp[q["h"]]+=1; tables_gp[q["a"]]+=1; idx+=1
            pair=[]
            for t in (r["h"],r["a"]):
                N=teams[t]; GP=tables_gp[t]; GR=N-GP
                if GP < WINDOW*N: pair.append("EARLY"); continue
                grp=(conf or {}).get(t,"ALL"); others=[u for u in groups[grp] if u!=t]
                P=tables_pts[t]; R=lambda u:teams[u]-tables_gp[u]
                can_pass=sum(1 for u in others if tables_pts[u]+maxpg*R(u)>=P)
                beyond=sum(1 for u in others if tables_pts[u]>P+maxpg*GR)
                if can_pass<k: pair.append("SECURED"); continue
                if beyond>=k: pair.append("DEAD"); continue
                order=sorted(others,key=lambda u:-tables_pts[u])
                rank_in= sum(1 for u in others if tables_pts[u]>P) < k
                gap = (P-tables_pts[order[k-1]]) if rank_in else (tables_pts[order[k-1]]-P)
                pair.append("MUST_WIN" if abs(gap)/maxpg <= max(1.0, GR/4) else "ALIVE")
            part="dev" if year<=2024 else "hold"
            results[(sport,part,"side",pair[0])]+=1; results[(sport,part,"side",pair[1])]+=1
            for s_ in pair: results[(sport,part,"ut",ut,s_)]+=1
            results[(sport,part,"game","late" if pair!=["EARLY","EARLY"] else "early")]+=1
            results[(sport,part,"pair","|".join(sorted(pair)))]+=1
json.dump([dict(k=list(k),n=n) for k,n in results.items()],open(f"counts_{WINDOW}.json","w"))
json.dump(leagues,open("leagues.json","w"),indent=0)
for sport in ("ice-hockey","basketball","volleyball"):
    print("====",sport, "leagues ok:", sum(1 for l in leagues if l["sport"]==sport and l["ok"]))
    for part in ("dev","hold"):
        s={st:results[(sport,part,"side",st)] for st in ("EARLY","ALIVE","MUST_WIN","SECURED","DEAD")}
        print(part,"games",results[(sport,part,"game","late")]+results[(sport,part,"game","early")],"late-games",results[(sport,part,"game","late")],"sides",s)
