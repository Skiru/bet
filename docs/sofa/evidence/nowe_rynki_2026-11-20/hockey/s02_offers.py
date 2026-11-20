"""Step 1: shapes of the unread hockey markets. Last pre-kickoff price per
(event, market, specialBetValue, selection) from runs/sofa/<d>/unmapped_prices/hockey_*.jsonl.gz,
joined to SHADOW's event records (runs/sofa/shadow/hockey/<d>/settled.json, snapshots.jsonl)."""
import gzip, json, glob, pickle, sys, collections, os
OUT = sys.argv[1]
TARGET = {617, 613, 621, 653, 633, 666, 643, 236253, 236266}
# --- event records: kickoff, teams, tournament (snapshots), sofascore id + result (settled)
events = {}
for fp in sorted(glob.glob('runs/sofa/shadow/hockey/2026-11-*/snapshots.jsonl')):
    day = fp.split('/')[-2]
    if day < '2026-11-04':
        continue
    with open(fp) as f:
        for l in f:
            r = json.loads(l)
            e = events.setdefault(r['superbet_event_id'], {})
            e.update(team1=r['team1'], team2=r['team2'], kickoff_utc=r['kickoff_utc'],
                     tournament=r['tournament'], tournament_id=r.get('tournament_id'), day=day)
            # regulation lines Superbet posted (for same-event / reg-vs-incl comparisons)
            for ln in r['lines']:
                if ln['market_id'] in (623, 630, 604, 658, 652, 640):
                    e.setdefault('reg_lines', {})[(ln['market_id'], ln.get('line'), ln['side'], ln.get('subject'))] = (r['fetched_at_utc'], ln['odds'])
settled = {}
for fp in sorted(glob.glob('runs/sofa/shadow/hockey/2026-11-*/settled.json')):
    d = json.load(open(fp))
    for sid, rec in d['events'].items():
        prev = settled.get(sid)
        if prev is None or rec.get('state') == 'SETTLED':
            settled[sid] = {k: v for k, v in rec.items() if k != 'graded'}
# --- prices
last = {}
files = sorted(glob.glob('runs/sofa/2026-11-*/unmapped_prices/hockey_*.jsonl.gz'))
markets = collections.Counter()
for fp in files:
    with gzip.open(fp, 'rt') as f:
        for l in f:
            r = json.loads(l)
            m = r['marketId']
            markets[(m, r['marketName'] if m not in (621, 653) else '<team> - liczba goli (z dogrywką i rzutami karnymi)')] += 0
            if m not in TARGET:
                continue
            ev = events.get(r['superbet_event_id'])
            if ev is None or r.get('status') not in (None, 'active') or str(r.get('offerStateId')) == '2':
                continue
            if r['fetched_at_utc'][:19] >= ev['kickoff_utc'][:19]:
                continue
            key = (r['superbet_event_id'], m, r['marketName'], r['specialBetValue'], r['name'])
            if key not in last or r['fetched_at_utc'] > last[key][0]:
                last[key] = (r['fetched_at_utc'], r['price'])
pickle.dump({'events': events, 'settled': settled, 'last': last, 'files': len(files)}, open(OUT, 'wb'))
print('files', len(files), 'events', len(events), 'settled', len(settled), 'price keys', len(last))
