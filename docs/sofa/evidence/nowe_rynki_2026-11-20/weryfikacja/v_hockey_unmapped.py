import gzip, json, glob, collections
B='/Users/mkoziol/projects/bet/runs/sofa/'
ev=collections.defaultdict(set); files=0
for f in sorted(glob.glob(B+'2026-11-*/unmapped_prices/hockey_*.jsonl.gz')):
    files+=1
    with gzip.open(f,'rt') as fh:
        for line in fh:
            r=json.loads(line)
            if r['marketId'] in (617,613,621,653): ev[r['marketId']].add(r['superbet_event_id'])
allev=set().union(*ev.values())
ko={}; tour={}
for f in glob.glob(B+'shadow/hockey/2026-11-*/snapshots.jsonl'):
    with open(f) as fh:
        for line in fh:
            r=json.loads(line)
            if r['superbet_event_id'] in allev:
                ko[r['superbet_event_id']]=r['kickoff_utc']; tour[r['superbet_event_id']]=r['tournament']
print('files',files,{k:len(v) for k,v in ev.items()},'union',len(allev),'no snapshot',len(allev-set(ko)))
print(collections.Counter(tour.values()))
hrs=collections.Counter(ko[e][11:13] for e in ko); print('kickoff hours UTC',sorted(hrs.items()))
days=collections.Counter(ko[e][:10] for e in ko); print('UTC days',len(days),sorted(days.items()))
