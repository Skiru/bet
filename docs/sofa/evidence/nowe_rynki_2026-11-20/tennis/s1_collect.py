"""Step 1: collect every new-format tennis serve 'N+' selection from OFFER's
unmapped_prices files (no sport prefix), last pre-start snapshot per
(event, market, selection). Output: selections.jsonl + templates summary."""
import gzip, json, os, re, sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
sys.path.insert(0, 'src')
from bet.sofa.market_mapper import fold
from bet.sofa.market_coverage import template_of

OUT = sys.argv[1]
RUNS = 'runs/sofa'
d0, d1 = datetime(2026, 10, 1), datetime(2026, 11, 21)
NEW = re.compile(r"(?:^|- |\} )(asy|podwojne bledy|asy \+ podwojne bledy)$")

def ts(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00'))

best_active = {}
old_fmt = defaultdict(set)
best = {}   # (sid, marketName, name) -> rec
meta = {}
all_names = Counter()
d = d0
while d <= d1:
    ds = d.strftime('%Y-%m-%d'); d += timedelta(days=1)
    base = f'{RUNS}/{ds}'
    if not os.path.exists(f'{base}/02_fixtures.json'):
        continue
    fx = {f['sofascore_event_id']: f for f in json.load(open(f'{base}/02_fixtures.json')) if f.get('sport') == 'tennis'}
    board = {}
    if os.path.exists(f'{base}/01_board.json'):
        board = {b['superbet_event_id']: b for b in json.load(open(f'{base}/01_board.json'))}
    if os.path.exists(f'{base}/04_offer.json'):
        for o in json.load(open(f'{base}/04_offer.json')):
            for rg in o.get('rungs') or []:
                m = rg.get('market', '')
                if m.startswith(('aces_', 'double_faults_', 'serve_points_')):
                    old_fmt[ds].add(o['sofascore_event_id'])
    up = f'{base}/unmapped_prices'
    if not os.path.isdir(up):
        continue
    for fn in sorted(os.listdir(up)):
        if not fn[0].isdigit():
            continue
        with gzip.open(f'{up}/{fn}', 'rt') as fh:
            for line in fh:
                if '+", "specialBetValue"' not in line:
                    continue
                r = json.loads(line)
                sid = r.get('sofascore_event_id')
                f = fx.get(sid)
                if f is None:
                    continue
                mn = fold(r['marketName'])
                if not ('asy' in mn.split() or 'podwojne bledy' in mn):
                    continue
                if 'liczba' in mn or not r['name'].endswith('+'):
                    continue
                b = board.get(str(r.get('superbet_event_id')), {})
                sides = [b.get('side_a') or '', b.get('side_b') or '', f['home_name'], f['away_name']]
                tpl = template_of(r['marketName'], sides)
                all_names[tpl] += 1
                ko = min(ts(f['kickoff_utc']), ts(f.get('superbet_kickoff_utc') or f['kickoff_utc']))
                fa = ts(r['fetched_at_utc'])
                if fa >= ko:
                    continue
                key = (sid, r['marketName'], r['name'])
                if r.get('status') == 'active':
                    oa = best_active.get(key)
                    if oa is None or oa['fetched_at_utc'] < r['fetched_at_utc']:
                        best_active[key] = dict(price=r['price'], fetched_at_utc=r['fetched_at_utc'])
                old = best.get(key)
                if old is None or old['fetched_at_utc'] < r['fetched_at_utc']:
                    r['template'] = tpl
                    r['day'] = ds
                    r['side_a'] = b.get('side_a'); r['side_b'] = b.get('side_b')
                    best[key] = r
                meta[sid] = dict(day=ds, kickoff=f['kickoff_utc'], sb_kickoff=f.get('superbet_kickoff_utc'),
                                 home=f['home_name'], away=f['away_name'], home_id=f['home_entity_id'],
                                 away_id=f['away_entity_id'], comp=f['competition_name'], comp_id=f['competition_id'],
                                 cat=f['category_name'], ground=f.get('ground_type'), bo=f.get('default_period_count'),
                                 side_a=b.get('side_a'), side_b=b.get('side_b'), sb_id=r.get('superbet_event_id'),
                                 status=f.get('sofascore_status'))
json.dump({k: sorted(v) for k, v in old_fmt.items()}, open(f'{OUT}/old_format_events.json', 'w'))
with open(f'{OUT}/selections.jsonl', 'w') as fh:
    for key, r in best.items():
        a = best_active.get(key)
        r['last_status'] = r.get('status')
        r['active_price'] = a['price'] if a else None
        r['active_fetched_at_utc'] = a['fetched_at_utc'] if a else None
        fh.write(json.dumps(r, ensure_ascii=False) + '\n')
json.dump(meta, open(f'{OUT}/events_meta.json', 'w'), ensure_ascii=False)
for t, n in all_names.most_common(60):
    print(n, t)
print('selections', len(best), 'events', len(meta))
