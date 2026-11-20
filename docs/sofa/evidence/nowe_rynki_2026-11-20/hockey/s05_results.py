"""Step 2: the 108 NHL events with incl-OT/SO markets. Sofascore detail (sofa_event_detail, PK lookup)
vs SHADOW's settled record vs Superbet's own result metadata (GET /v2/pl-PL/events/<id>, finished events).
Writes results.pkl: superbet id -> dict(reg (t1,t2), incl (t1,t2) per Sofascore rule, superbet final, status)."""
import json, pickle, sqlite3, sys, time, collections
from bet.sofa.superbet import SuperbetClient
D = pickle.load(open(sys.argv[1], 'rb'))
OUT = sys.argv[2]
events, settled = D['events'], D['settled']
nhl = sorted(e for e, v in events.items() if v['tournament'] == 'USA - NHL' and v['kickoff_utc'] >= '2026-11-06')
con = sqlite3.connect('file:data/sofa.db?mode=ro', uri=True)
client = SuperbetClient()
out = {}
cnt = collections.Counter()
for eid in nhl:
    rec = settled.get(eid) or {}
    sid = rec.get('sofascore_event_id')
    row = {'superbet_event_id': eid, 'kickoff_utc': events[eid]['kickoff_utc'], 'state': rec.get('state', 'NO_RECORD'),
           'sofascore_event_id': sid, 'home_is_team1': rec.get('home_is_team1'), 'team1': events[eid]['team1'], 'team2': events[eid]['team2']}
    if sid:
        r = con.execute('SELECT detail_json FROM sofa_event_detail WHERE sofascore_event_id = ?', (sid,)).fetchone()
        if r:
            det = json.loads(r[0])
            ev = det.get('event', det)
            H, A = ev.get('homeScore') or {}, ev.get('awayScore') or {}
            row['sofa_status'] = (ev.get('status') or {}).get('description')
            row['sofa_home'] = {k: H.get(k) for k in ('current', 'normaltime', 'period1', 'period2', 'period3', 'overtime', 'penalties')}
            row['sofa_away'] = {k: A.get(k) for k in ('current', 'normaltime', 'period1', 'period2', 'period3', 'overtime', 'penalties')}
            row['winnerCode'] = ev.get('winnerCode')
    if row['state'] == 'SETTLED' or events[eid]['kickoff_utc'] < '2026-11-20T06':
        try:
            d = client.event_odds(eid)
            md = (d or {}).get('metadata') or {}
            row['sb_final'] = (md.get('homeTeamScore'), md.get('awayTeamScore'))
            row['sb_periods'] = [(p.get('type'), p.get('homeTeamScore'), p.get('awayTeamScore')) for p in md.get('periods') or []]
            row['sb_status'] = md.get('status')
            row['sb_home_team_id'] = (d or {}).get('homeTeamId')
            row['sb_match_name'] = (d or {}).get('matchName')
        except Exception as exc:  # noqa
            row['sb_error'] = repr(exc)[:200]
        time.sleep(0.4)
    out[eid] = row
pickle.dump(out, open(OUT, 'wb'))
print(len(out), collections.Counter(r['state'] for r in out.values()), collections.Counter(r.get('sofa_status') for r in out.values()))
