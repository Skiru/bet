"""As-of statistical signals for every football count leg of legs.pkl (read-only, DB copy).

Uses the dossier's own functions, all cut at the match's kickoff
(`dossier.team_games(before_ts=kickoff)` keeps only games that STARTED before it):
  own / opponent-conceded k/n (side legs), each side's games k/n (totals, joints as
  min(own, rival)), league share (season games before the kickoff DAY's 00:00Z -
  conservative cache key), h2h k/n (meetings before kickoff), referee k/n (his last 20
  cached games before kickoff, cards / fouls totals), rest days and games in 14 days.
Output: signals.pkl keyed by (day, key)."""
import json, os, sys, sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from multiprocessing import Pool
import pandas as pd

sys.path.insert(0, '/Users/mkoziol/projects/bet/src')
from bet.sofa import dossier as D  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get('KUPON_DB', f'{HERE}/sofa_copy.db')
ROOT = '/Users/mkoziol/projects/bet/runs/sofa'
REF_N = 20


def hits(values, line, direction):
    return sum(1 for v in values if (v > line if direction == 'OVER' else v < line)), len(values)


def leg_values(metric, both, subject_side, g):
    """value of one game row {metric: v or [own, opp]} from the leg's view."""
    v = g.get(metric)
    if v is None:
        return None
    if both:
        return min(v)
    if metric.endswith('_for'):
        return v[0] if subject_side == 'home' else v[1]
    return v


def day_job(args):
    day, legs = args
    con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    fixtures = {int(f['sofascore_event_id']): f for f in json.load(open(f'{ROOT}/{day}/02_fixtures.json'))
                if isinstance(f, dict) and isinstance(f.get('sofascore_event_id'), int)}
    day0 = int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp())
    by_event = defaultdict(list)
    for l in legs:
        by_event[int(l['eid'])].append(l)
    cache, league_cache, out = {}, {}, []
    for eid, these in by_event.items():
        fx = fixtures.get(eid) or {}
        home, away = fx.get('home_entity_id'), fx.get('away_entity_id')
        ko = D._parse_ts(fx.get('kickoff_utc'))
        if not isinstance(home, int) or not isinstance(away, int) or ko is None:
            continue
        found = {l['key']: D.leg_metric(str(l['market'])) for l in these}
        metrics = sorted({f[0] for f in found.values() if f})
        if not metrics:
            continue
        aw = D.awarded_out_at(ko)
        games = {'home': D._metric_games(con, home, ko, metrics, cache, aw),
                 'away': D._metric_games(con, away, ko, metrics, cache, aw)}
        names = {'home': fx.get('home_name'), 'away': fx.get('away_name')}
        rest = {}
        for side, team in (('home', home), ('away', away)):
            tg = D.team_games(con, team, ko, 15)
            starts = [int(g['startTimestamp']) for g in tg]
            rest[side] = ((ko - starts[0]) / 86400 if starts else None,
                          sum(ko - s <= 14 * 86400 for s in starts))
        # league share
        detail = D.event_detail(con, eid) or {}
        comps = D._competitions_for(detail, games, {'home': home, 'away': away}, con, ko)
        lkey = (day, tuple((c[0], c[1]) for c in comps), tuple(metrics))
        if lkey not in league_cache:
            try:
                league_cache[lkey] = D.league_rates(con, comps, day0, metrics, aw)
            except Exception as e:  # noqa: BLE001
                league_cache[lkey] = {}
        league = league_cache[lkey]
        try:
            h2h = D.head_to_head(con, home, away, ko, metrics=metrics, awarded_out=aw)
        except Exception:  # noqa: BLE001
            h2h = []
        ref = con.execute('select referee_id from sofa_event_referee where event_id=?', (eid,)).fetchone()
        ref_games = []
        if ref and ref[0]:
            for (rid,) in con.execute('select event_id from sofa_event_referee where referee_id=? and start_ts<? '
                                      'and event_id<>? order by start_ts desc limit ?', (ref[0], ko, eid, REF_N * 2)):
                m = D.meeting_metrics(con, {'id': rid}, -1, [x for x in metrics if not x.endswith('_for')], 'football')
                m = {k: v for k, v in m.items() if D._numeric(v)}
                if m:
                    ref_games.append(m)
                if len(ref_games) >= REF_N:
                    break
        for l in these:
            f = found.get(l['key'])
            if not f or l['direction'] not in ('OVER', 'UNDER') or l['line'] is None:
                continue
            metric, both = f
            line, dr = float(l['line']), l['direction']
            row = {'day': day, 'key': l['key'], 'metric': metric, 'joint': int(both),
                   'rest_home': rest['home'][0], 'rest_away': rest['away'][0],
                   'g14_home': rest['home'][1], 'g14_away': rest['away'][1],
                   'n_home': len(games['home']), 'n_away': len(games['away'])}
            side = None
            if metric.endswith('_for') and not both:
                side = D._side_of_subject(str(l.get('subject') or ''), names)
                if side is None:
                    out.append(row)
                    continue
                opp = 'away' if side == 'home' else 'home'
                own = [g[metric][0] for g in games[side] if metric in g]
                conc = [g[metric][1] for g in games[opp] if metric in g]
                row['own_k'], row['own_n'] = hits(own, line, dr)
                row['conc_k'], row['conc_n'] = hits(conc, line, dr)
                row['subject_side'] = side
                pool = [v for g in league.get('values') or [] if metric in g for v in g[metric]]
            else:
                for s, nm in (('home', 'a'), ('away', 'b')):
                    vals = [min(g[metric]) if both else g[metric] for g in games[s] if metric in g]
                    row[f'{nm}_k'], row[f'{nm}_n'] = hits(vals, line, dr)
                pool = [min(g[metric]) if both else g[metric] for g in league.get('values') or [] if metric in g]
            if pool:
                row['lg_k'], row['lg_n'] = hits(pool, line, dr)
            hv = []
            for r in h2h:
                m = r.get('metrics') or {}
                if metric in m and D._numeric(m[metric]):
                    v = m[metric]
                    if both:
                        hv.append(min(v))
                    elif metric.endswith('_for'):
                        hv.append(v[0] if side == 'home' else v[1])
                    else:
                        hv.append(v)
            row['h2h_k'], row['h2h_n'] = hits(hv, line, dr)
            if not metric.endswith('_for') and ('card' in metric or 'foul' in metric):
                rv = [g[metric] for g in ref_games if metric in g]
                row['ref_k'], row['ref_n'] = hits(rv, line, dr)
            out.append(row)
    con.close()
    print(day, len(by_event), len(out), file=sys.stderr, flush=True)
    return out


def main():
    df = pd.read_pickle(f'{HERE}/legs.pkl')
    fb = df[(df.sport == 'football') & df.family.isna()]
    jobs = [(d, g[['key', 'eid', 'market', 'subject', 'line', 'direction']].to_dict('records'))
            for d, g in fb.groupby('day')]
    with Pool(int(os.environ.get('PROCS', '8'))) as p:
        parts = p.map(day_job, jobs)
    sig = pd.DataFrame([r for part in parts for r in part])
    sig.to_pickle(f'{HERE}/signals.pkl')
    print(sig.shape)


if __name__ == '__main__':
    main()
