import json, glob, collections, sys
base='/Users/mkoziol/projects/bet/runs/sofa/shadow/hockey/'
nhl_ev=set(); oth_ev=set()
cnt=collections.Counter(); nhl_mk=collections.Counter(); oth_mk=collections.Counter()
nhl_ev_by_day=collections.defaultdict(set)
for d in sorted(glob.glob(base+'2026-11-1*')):
    day=d.split('/')[-1]
    f=d+'/snapshots.jsonl'
    try: fh=open(f)
    except FileNotFoundError: continue
    for line in fh:
        r=json.loads(line)
        nhl = r.get('tournament')=='USA - NHL'
        ev=r['superbet_event_id']
        (nhl_ev if nhl else oth_ev).add(ev)
        if nhl: nhl_ev_by_day[day].add(ev)
        for l in r.get('lines',[]):
            fam=l['family']
            if fam in ('total','handicap','team_total'):
                cnt[(nhl,fam)]+=1
            (nhl_mk if nhl else oth_mk)[(l['market_id'],fam)]+=1
print('days',sorted(nhl_ev_by_day), {k:len(v) for k,v in sorted(nhl_ev_by_day.items())})
print('NHL events',len(nhl_ev),'other',len(oth_ev))
print('reg lines', dict(cnt))
print('NHL markets', sorted(nhl_mk.items()))
