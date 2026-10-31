"""Leg table for the /kupon redesign backtest (read-only on runs/ and the DB copy).

Every leg that stood on a printed snapshot (`runs/sofa/<d>/printed/*.json`) of
days 2026-10-13..10-30 before its kickoff. Decision time = the last snapshot at
least DECISION_LEAD_MIN before kickoff in which the leg stood in `legs` (the
evening /kupon reads the coupon as rebuilt then); first-seen = the first
snapshot holding it (morning print). Closing price = closing.jsonl (official,
fetched before kickoff). Grade = 13_results.json, else sofa_settled_row.
Output: legs.pkl (one row per leg key per day)."""
import json, os, sys, sqlite3
from datetime import datetime
import pandas as pd

ROOT = '/Users/mkoziol/projects/bet/runs/sofa'
HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get('KUPON_DB', f'{HERE}/sofa_copy.db')
DAYS = [f'2026-10-{d:02d}' for d in range(13, 31)]
DECISION_LEAD_MIN = 30


def ts(s):
    if not s:
        return None
    return datetime.fromisoformat(str(s).replace('Z', '+00:00')).timestamp()


def rkey(l):
    eid = l['sofascore_event_id']
    if 'family' in l and 'market_id' in l:
        return json.dumps([eid, l['family'], l.get('period', 0), l.get('subject', ''), l.get('line'),
                           l.get('side', l.get('direction')), l.get('market_id') or 0, l.get('map_nr', 0) or 0])
    return json.dumps([eid, l['market'], l['subject'], l['line'], l['direction']])


def ckey(l):
    return f"{l['sofascore_event_id']}|{l['market']}|{l['subject']}|{l['line']}|{l['direction']}"


def main():
    db = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    rows = []
    for d in DAYS:
        res = json.load(open(f'{ROOT}/{d}/13_results.json'))['legs']
        snaps = sorted(os.listdir(f'{ROOT}/{d}/printed'))
        clos = {}
        cp = f'{ROOT}/{d}/closing.jsonl'
        if os.path.exists(cp):
            for line in open(cp):
                r = json.loads(line)
                if r.get('variant') != 'official' or not r.get('odds_close'):
                    continue
                k = r['leg_key']
                if k not in clos or r['fetched_at_utc'] > clos[k]['fetched_at_utc']:
                    clos[k] = r
        track = {}
        for i, f in enumerate(snaps):
            q = json.load(open(f'{ROOT}/{d}/printed/{f}'))
            t = ts(q.get('pdf_rendered_at_utc')) or ts(q['created_at_utc'])
            for src, L in (('legs', q['legs']), ('removed', q.get('removed_by_reads') or [])):
                for l in L:
                    ko = ts(l.get('kickoff_utc'))
                    if ko is None or ko <= t:
                        continue
                    k = rkey(l)
                    tr = track.setdefault(k, {'first_t': t, 'first_odds': l.get('offered_odds', l.get('odds')),
                                              'first_conf': l['confidence'], 'first_src': src, 'ko0': ko})
                    tr['ko'] = ko
                    if src == 'removed':
                        tr['ever_removed'] = 1
                    if t <= ko - DECISION_LEAD_MIN * 60:
                        tr['dec'] = (t, src, l)
        for k, tr in track.items():
            if 'dec' not in tr:
                continue
            t, src, l = tr['dec']
            g = res.get(k)
            status = g['status'] if g else None
            gsrc = '13_results' if g else None
            if g is None and 'family' not in l:
                r = db.execute('select outcome from sofa_settled_row where sofascore_event_id=? and market=? '
                               'and subject=? and line=? and direction=?',
                               (l['sofascore_event_id'], l['market'], l['subject'],
                                l['line'] if l['line'] is not None else 0.0, l['direction'])).fetchone()
                if r:
                    status = {'WIN': 'won', 'LOSS': 'lost'}.get(r[0], r[0].lower())
                    gsrc = 'db'
            c = clos.get(ckey(l)) if 'family' not in l else None
            close_ok = c is not None and ts(c['fetched_at_utc']) < tr['ko']
            rows.append(dict(
                day=d, key=k, eid=l['sofascore_event_id'], sport=l['sport'], match=l['match'],
                competition=l.get('competition'), market=l.get('market') or l.get('family'),
                family=l.get('family'), subject=l.get('subject'), line=l.get('line'),
                direction=l.get('direction') or l.get('side'), period=l.get('period'), kickoff=tr['ko'],
                dec_t=t, dec_src=src, first_t=tr['first_t'], first_src=tr['first_src'],
                first_odds=tr['first_odds'], first_conf=tr['first_conf'], ever_removed=tr.get('ever_removed', 0),
                odds=l.get('offered_odds', l.get('odds')), conf=l['confidence'], model_p=l.get('model_p'),
                forecast_p=l.get('forecast_p'), forecast_source=l.get('forecast_source'),
                market_p=l.get('market_p'), overround=l.get('overround'),
                one_sided=1 if l.get('one_sided_market') else 0, line_offset=l.get('line_offset'),
                price_band_cap=l.get('price_band_cap'), calibrated_on=l.get('calibrated_on'),
                calibration_n=l.get('calibration_n'), sample_size=l.get('sample_size'),
                sample_obs=l.get('sample_observations'), sample_hit_rate=l.get('sample_hit_rate'),
                sample_min=l.get('sample_min'), sample_max=l.get('sample_max'),
                price_gap=1 if l.get('price_gap') else 0,
                peer_pref=1 if (l.get('peer') or {}).get('preferred') else 0, has_peer=1 if l.get('peer') else 0,
                context_flags=','.join(l.get('context_flags') or []),
                sb_market=l.get('superbet_market'), sb_selection=l.get('superbet_selection'),
                window=l.get('window'), status=status, gsrc=gsrc,
                close_odds=c['odds_close'] if close_ok else None,
                close_min=c.get('minutes_before') if close_ok else None))
        n = sum(1 for r in rows if r['day'] == d)
        print(d, len(snaps), len(track), n, sum(1 for r in rows if r['day'] == d and r['status'] is None),
              file=sys.stderr)
    df = pd.DataFrame(rows)
    df.to_pickle(f'{HERE}/legs.pkl')
    print(df.shape)


if __name__ == '__main__':
    main()
