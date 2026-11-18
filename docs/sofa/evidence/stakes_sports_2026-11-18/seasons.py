"""League-season structure (counts only, no outcome of a tested game)."""
import json, gzip, collections, re, statistics as st
POST = re.compile(r"play.?off|play.?in|knockout|final|quarter|semi|champion|wild.?card|pre.?play|stanley cup", re.I)
OTHER = re.compile(r"releg|play.?out|placement|promotion|qualif|classification|friendl|pre.?season|relegation|playdown|consolation|cup|5th|7th|9th|lower|upper|championship round|masters|division 2|group 2", re.I)
rows=[json.loads(l) for l in gzip.open("games.jsonl.gz","rt")]
by=collections.defaultdict(list)
for r in rows:
    if r["season_id"] is None or r["ut_id"] is None: continue
    by[(r["sport"],r["ut_id"],r["season_id"])].append(r)
out=[]
for k,v in by.items():
    v.sort(key=lambda r:r["ts"])
    names=collections.Counter(r["t_name"] for r in v)
    main=[n for n,_ in names.most_common() if n and not POST.search(n) and not OTHER.search(n)]
    if not main: continue
    m=main[0]
    reg=[r for r in v if r["t_name"]==m]
    nonpost=[r for r in v if r["t_name"] and not POST.search(r["t_name"]) and not OTHER.search(r["t_name"])]
    post=[r for r in v if r["t_name"] and POST.search(r["t_name"]) and not OTHER.search(r["t_name"])]
    teams=collections.Counter()
    fin=collections.Counter()
    for r in reg:
        for t in (r["h"],r["a"]):
            teams[t]+=1
            if r["st"]=="finished": fin[t]+=1
    if len(teams)<8: continue
    sched=list(teams.values())
    import datetime as dt
    first=dt.datetime.utcfromtimestamp(reg[0]["ts"]); last=dt.datetime.utcfromtimestamp(reg[-1]["ts"])
    sy=first.year-(1 if first.month<7 else 0)
    out.append(dict(sport=k[0],ut=k[1],season=k[2],ut_name=v[0]["ut_name"],cat=v[0]["cat"],season_name=v[0]["season_name"],main=m,
        main_share=round(len(reg)/max(1,len(nonpost)),3),n_reg=len(reg),n_teams=len(teams),
        sched_min=min(sched),sched_med=st.median(sched),sched_max=max(sched),
        fin_ratio_min=round(min(fin[t]/teams[t] for t in teams),3),
        post_teams=len({t for r in post for t in (r["h"],r["a"])}), n_post=len(post),
        first=first.strftime("%Y-%m-%d"),last=last.strftime("%Y-%m-%d"),season_start_year=sy,
        gender=collections.Counter(r["gender"] for r in reg).most_common(1)[0][0]))
json.dump(out,open("seasons.json","w"),indent=0)
print(len(out))
