"""Step 3: grade every collected N+ selection from the cache the way SETTLE
grades the existing keys (run_settle._event_payload + metrics.extract_metric
settling=True). Read-only DB, keyed by primary key."""
import json, sqlite3, sys, collections
sys.path.insert(0, 'src'); sys.path.insert(0, 'scripts/sofa')
from bet.sofa.settle import is_completed_event, settle_completed
from bet.sofa.metrics import extract_flat_statistics, extract_metric
from bet.sofa.contracts import GapReason
from run_settle import unfinished_reason

D = sys.argv[1]
meta = json.load(open(f'{D}/events_meta.json'))
TPL = {}
for stat, key in (('asy', 'aces'), ('podwojne bledy', 'double_faults'), ('asy + podwojne bledy', 'serve_points')):
    TPL[stat] = (f'{key}_total', None)
    TPL['{a} ' + stat] = (f'{key}_for', True)
    TPL['{b} ' + stat] = (f'{key}_for', False)
    for s in (1, 2):
        TPL[f'{s}. set - {stat}'] = (f'{key}_set{s}_total', None)
        TPL[f'{s}. set - {{a}} {stat}'] = (f'{key}_set{s}_for', True)
        TPL[f'{s}. set - {{b}} {stat}'] = (f'{key}_set{s}_for', False)

conn = sqlite3.connect('file:data/sofa.db?mode=ro', uri=True)
ev_state = {}
reasons = collections.Counter()
stats_state = collections.Counter()
for sid in meta:
    sid_i = int(sid)
    row = conn.execute('SELECT detail_json FROM sofa_event_detail WHERE sofascore_event_id=?', (sid_i,)).fetchone()
    if row is None:
        ev_state[sid] = ('NO_EVENT_DETAIL', None, None); continue
    event = json.loads(row[0]).get('event') or {}
    if not is_completed_event(event):
        ev_state[sid] = (str(unfinished_reason(event)), event, None); continue
    if not settle_completed(event):
        ev_state[sid] = ('AWARDED', event, None); continue
    st = conn.execute('SELECT statistics_json, incidents_json FROM sofa_event_stats WHERE sofascore_event_id=?', (sid_i,)).fetchone()
    if st is None or not st[0]:
        ev_state[sid] = ('NO_STATS_ROW' if st is None else 'STATS_NULL', event, None); continue
    flat = extract_flat_statistics(json.loads(st[0]))
    ev_state[sid] = ('OK', event, (flat, json.loads(st[1]) if st[1] else None))
c = collections.Counter(v[0] for v in ev_state.values())
print('events by state', c)
# per category
bycat = collections.defaultdict(collections.Counter)
for sid, v in ev_state.items():
    bycat[meta[sid]['cat']][v[0]] += 1
for k, v in bycat.items():
    print(k, dict(v))

out = open(f'{D}/graded.jsonl', 'w')
gc = collections.Counter()
for line in open(f'{D}/selections.jsonl'):
    r = json.loads(line)
    t = r['template']
    if t not in TPL:
        gc['TEMPLATE_UNKNOWN:' + t] += 1; continue
    metric, side = TPL[t]
    n = int(r['name'].rstrip('+'))
    state, event, payload = ev_state[str(r['sofascore_event_id'])]
    rec = dict(sid=r['sofascore_event_id'], day=meta[str(r['sofascore_event_id'])]['day'], template=t, metric=metric,
               side=side, n=n, price=r['price'], active_price=r.get('active_price'),
               last_status=r.get('last_status'), fetched=r['fetched_at_utc'], cat=meta[str(r['sofascore_event_id'])]['cat'],
               sbv=r.get('specialBetValue'))
    if state != 'OK':
        rec['grade'] = state
    else:
        flat, inc = payload
        is_home = True if side is None else side
        v = extract_metric(metric, 'tennis', flat, inc, event, is_home, settling=True)
        if isinstance(v, GapReason):
            rec['grade'] = f'{metric}:{v.value}'
        else:
            rec['value'] = v
            rec['grade'] = 'WIN' if v >= n else 'LOSS'
    gc[rec['grade'] if rec['grade'] in ('WIN', 'LOSS') else 'X:' + rec['grade']] += 1
    out.write(json.dumps(rec) + '\n')
print(gc.most_common())
