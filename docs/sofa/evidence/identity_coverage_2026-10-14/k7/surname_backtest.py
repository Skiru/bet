"""K7 backtest (read-only): players.match_player_by_surname against the squads of each
fixture's sampled matches - on the players SAMPLES matched (must pick the same person) and on
the NO_SQUAD_MATCH players (what it would add). Usage: surname_backtest.py <day>..."""
import json,sqlite3,collections,sys
sys.path[:0]=['src','.']
from bet.sofa.names import normalize_name
from scripts.sofa import measure_team_identity as m

from bet.sofa.players import match_player_by_surname as rule


c=sqlite3.connect("file:data/sofa.db?mode=ro",uri=True)
lcache={}
def squads(evs):
    sq=set()
    for e in evs:
        if e not in lcache:
            row=c.execute("select lineups_json from sofa_event_stats where sofascore_event_id=?",(e,)).fetchone()
            names=set()
            if row and row[0]:
                L=json.loads(row[0])
                for side in ('home','away'):
                    for p in (L.get(side) or {}).get('players') or []:
                        nm=(p.get('player') or {}).get('name')
                        if nm: names.add(nm)
            lcache[e]=names
        sq|=lcache[e]
    return sq
res=collections.Counter(); wrong=[]; rec=[]
for day in sys.argv[1:]:
    d=json.load(open(f'runs/sofa/{day}/03_samples.json'))
    for r in d:
        evs=set()
        for v in (r.get('metrics') or {}).values():
            for side in ('side_a','side_b'):
                for o in v.get(side) or []: evs.add(o['sofascore_event_id'])
        seen=set()
        for p in (r.get('players') or {}).values():
            if p['player'] in seen: continue
            seen.add(p['player'])
            sq=squads(set(o['sofascore_event_id'] for o in p['observations'])|evs)
            got=rule(p['player'], sq)
            if got is None: res['matched:no_pick']+=1
            elif normalize_name(got)==p['matched_name']: res['matched:SAME']+=1
            else:
                res['matched:WRONG']+=1; wrong.append((day,p['player'],p['matched_name'],got))
        names=set()
        for g in r['gaps']:
            if g['reason']=='NO_ENTITY_FOUND' and g['metric'].startswith('player_'):
                q=m.parse_player_gap(g['detail'])
                if q and q[1]=='NO_SQUAD_MATCH': names.add(q[0])
        sq=squads(evs) if names else set()
        for n in names:
            got=rule(n,sq)
            res['unmatched:'+('PICK' if got else 'none')]+=1
            if got: rec.append((day,n,got))
print(res); print('WRONG',wrong[:30]); print('PICKS',len(rec),rec[:60])
