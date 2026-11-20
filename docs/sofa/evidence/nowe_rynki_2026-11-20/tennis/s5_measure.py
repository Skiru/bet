"""Steps 4b-6: the CONFIDENCE chain on every priced N+ selection (curves of
the point model's keys as run_confidence builds them on the build day, the
installed line evidence, settleability), the gates, and the measurement:
Brier / log-loss of model p, confidence, 1/odds and an approximate de-vig;
calibration bands; gate-passing legs; ROI. Match-level bootstrap, 2,000 draws.
Hold-out = events of 2026-10-21 .. 11-19 (curves fitted on history < 10-20,
model constants < 2026-01-01). Also the old-format pairs (old_pairs.jsonl)."""
import functools
print = functools.partial(print, flush=True)
import json, sys, collections, math, random
from datetime import datetime, UTC
import numpy as np
sys.path.insert(0, 'src')
from bet.sofa import epochs, live_only_curves, tennis_point_curves
from bet.sofa.confidence import (Calibration, calibration_path_for, match_class, one_sided_single,
                                 MIN_ODDS_FOR_CEILING, direction_key)
from bet.sofa.line_evidence import LineEvidence, evidence_key
from bet.sofa.settleability import Settleability, path_for as settle_path_for

D = sys.argv[1]
BUILD_DAY = '2026-11-20'
NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
meta = json.load(open(f'{D}/events_meta.json'))
cal = Calibration.load(calibration_path_for(BUILD_DAY, NOW))
cal = live_only_curves.for_day(cal, BUILD_DAY, NOW)
cal = tennis_point_curves.for_day(cal, BUILD_DAY, NOW, handicap_rows=False)
ev = LineEvidence.load(v2=epochs.line_evidence_v2(BUILD_DAY, NOW),
                       bucket_deff=epochs.bucket_design_effect(BUILD_DAY, NOW),
                       price_gap_sports=epochs.price_gap_offset_sports(BUILD_DAY, NOW))
print('evidence fitted for', ev.doc.get('fitted_for') or ev.doc.get('before'), 'price_gap sports', sorted(ev.price_gap_sports))
sg = Settleability.load(settle_path_for(BUILD_DAY))

# old-format overround per metric (two-sided pairs, both prices)
old = [json.loads(l) for l in open(f'{D}/old_pairs.jsonl')]
ovr = collections.defaultdict(list)
for o in old:
    if o['over_odds'] and o['under_odds']:
        s = 1 / o['over_odds'] + 1 / o['under_odds']
        if 1.0 <= s <= 1.3:
            ovr[o['metric']].append(s - 1)
OVR = {m: float(np.median(v)) for m, v in ovr.items()}
print('old-format median overround per metric:', {m: round(v, 4) for m, v in sorted(OVR.items())},
      'n pairs', {m: len(v) for m, v in sorted(ovr.items())})

rows = []
refuse = collections.Counter()
for l in open(f'{D}/priced.jsonl'):
    r = json.loads(l)
    if r['grade'] not in ('WIN', 'LOSS'):
        continue
    r['y'] = 1 if r['grade'] == 'WIN' else 0
    if r['last_status'] != 'active' or r['active_price'] is None:
        r['refusal'] = 'BLOCKED_AT_LAST_SNAPSHOT'; rows.append(r); continue
    r['odds'] = float(r['active_price'])
    if r['p'] is None:
        r['refusal'] = 'NOT_RATED'; rows.append(r); continue
    e = meta[str(r['sid'])]
    klass = match_class('tennis', e['cat'], None, e['comp_id'])
    r['klass'] = klass
    hit = cal.realised(r['metric'], r['p'], 'tennis', 'OVER', klass)
    rd = ev.read('tennis', evidence_key(direction_key(r['metric'], 'OVER'), klass), r['p'], hit, r['odds'])
    r['curve'] = None if hit is None else hit[0]
    if rd is None:
        r['refusal'] = 'NO_LINE_EVIDENCE' if hit is None else 'NO_LINE_EVIDENCE?'; rows.append(r); continue
    r['conf'], r['source'], r['cal_n'] = rd.value, rd.source, rd.n
    r['offset'] = rd.offset
    leg = dict(one_sided_market=True, overround=None, calibrated_on=rd.source, calibration_n=rd.n)
    if sg.refuses(e['comp_id'], r['metric']):
        r['refusal'] = 'NOT_SETTLEABLE'
    elif r['odds'] < MIN_ODDS_FOR_CEILING:
        r['refusal'] = 'ODDS_TOO_LOW'
    elif r['conf'] < 0.70:
        r['refusal'] = 'CONF<0.70'
    elif r['conf'] * r['odds'] < 0.90:
        r['refusal'] = 'X<0.90'
    elif not one_sided_single(leg):
        r['refusal'] = 'ONE_SIDED_NOT_OWN_CURVE'
    else:
        r['refusal'] = None
    rows.append(r)
json.dump(rows, open(f'{D}/measured_rows.json', 'w'))
print('universe graded', len(rows), 'refusals', collections.Counter(r['refusal'] for r in rows).most_common())

def fam(r):
    t = r['template']
    sc = 'set' if 'set -' in t else 'match'
    st = 'aces+df' if '+ podwojne' in t else 'df' if 'podwojne' in t else 'aces'
    return f'{st}/{sc}'

rng = np.random.default_rng(11)
def boot(items, fn, B=2000):
    """Match bootstrap of the mean of a per-row quantity. items: (match, record);
    fn(list of records) is applied to each record alone (a mean of per-row values)."""
    ms = sorted({m for m, _ in items}); ix = {m: i for i, m in enumerate(ms)}
    vals = np.array([fn([x]) for _, x in items], dtype=float)
    mi = np.array([ix[m] for m, _ in items])
    S = np.bincount(mi, weights=vals, minlength=len(ms)); N = np.bincount(mi, minlength=len(ms)).astype(float)
    point = S.sum() / N.sum()
    W = rng.multinomial(len(ms), np.full(len(ms), 1 / len(ms)), size=B).astype(float)
    bs = (W @ S) / (W @ N)
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return point, lo, hi, len(ms)

def brier(p, y): return (p - y) ** 2
def ll(p, y):
    p = min(max(p, 1e-4), 1 - 1e-4); return -(y * math.log(p) + (1 - y) * math.log(1 - p))

def fmt(t): return f'{t[0]:+.4f} [{t[1]:+.4f}, {t[2]:+.4f}]'

res = {}
for label, cond in (('holdout 10-21..11-19', lambda r: '2026-10-21' <= r['day'] <= '2026-11-19'),
                    ('all 10-17..11-19', lambda r: r['day'] <= '2026-11-19')):
    U = [r for r in rows if cond(r) and r.get('p') is not None and r.get('odds')]
    print(f'\n=== {label}: priced bettable graded selections {len(U)}, matches {len({r["sid"] for r in U})}')
    for fname in ['ALL'] + sorted({fam(r) for r in U}):
        S = [r for r in U if fname == 'ALL' or fam(r) == fname]
        it = [(r['sid'], r) for r in S]
        def dv(r): return min(1 / r['odds'] / (1 + OVR.get(r['metric'], 0.0)), 1.0)
        b_m = boot(it, lambda xs: np.mean([brier(x['p'], x['y']) for x in xs]))
        b_i = boot(it, lambda xs: np.mean([brier(min(1 / x['odds'], 1), x['y']) for x in xs]))
        d_mi = boot(it, lambda xs: np.mean([brier(x['p'], x['y']) - brier(min(1 / x['odds'], 1), x['y']) for x in xs]))
        d_md = boot(it, lambda xs: np.mean([brier(x['p'], x['y']) - brier(dv(x), x['y']) for x in xs]))
        l_md = boot(it, lambda xs: np.mean([ll(x['p'], x['y']) - ll(dv(x), x['y']) for x in xs]))
        mean_p = np.mean([x['p'] for x in S]); mean_i = np.mean([1 / x['odds'] for x in S]); mean_y = np.mean([x['y'] for x in S])
        print(f'{fname:14s} n={len(S):6d} m={b_m[3]:4d} Brier model {b_m[0]:.4f} implied {b_i[0]:.4f} | model-implied {fmt(d_mi)} | model-devig~ {fmt(d_md)} | LL model-devig~ {fmt(l_md)} | mean p {mean_p:.3f} 1/odds {mean_i:.3f} y {mean_y:.3f}')
    # calibration bands
    for what in ('p', 'conf', 'impl'):
        print(f'  calibration by {what}:')
        for lo, hi in ((0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.92), (0.92, 1.01)):
            def val(r): return r['p'] if what == 'p' else (r.get('conf') if what == 'conf' else 1 / r['odds'])
            S = [r for r in U if val(r) is not None and lo <= val(r) < hi]
            if not S: continue
            t = boot([(r['sid'], r) for r in S], lambda xs: np.mean([x['y'] for x in xs]))
            print(f'    {lo:.2f}-{hi:.2f}: n {len(S):6d} m {t[3]:4d} claimed {np.mean([val(r) for r in S]):.3f} realised {t[0]:.3f} [{t[1]:.3f}, {t[2]:.3f}] 1/odds {np.mean([1/r["odds"] for r in S]):.3f}')
    # gate-passing legs
    P = [r for r in U if r.get('refusal') is None]
    if P:
        it = [(r['sid'], r) for r in P]
        hr = boot(it, lambda xs: np.mean([x['y'] for x in xs]))
        roi = boot(it, lambda xs: np.mean([x['y'] * x['odds'] - 1 for x in xs]))
        roit = boot(it, lambda xs: np.mean([x['y'] * x['odds'] * 0.88 - 1 for x in xs]))
        gap = boot(it, lambda xs: np.mean([x['y'] - x['conf'] for x in xs]))
        days = collections.Counter(r['day'] for r in P)
        print(f'  GATE-PASSING legs {len(P)} / matches {hr[3]} over {len(days)} days with any (per day mean {len(P)/len({r["day"] for r in U}):.1f} over {len({r["day"] for r in U})} days with the format)')
        print(f'    conf {np.mean([r["conf"] for r in P]):.3f} model p {np.mean([r["p"] for r in P]):.3f} 1/odds {np.mean([1/r["odds"] for r in P]):.3f} realised {hr[0]:.3f} [{hr[1]:.3f}, {hr[2]:.3f}] realised-conf {fmt(gap)}')
        print(f'    ROI before tax {roi[0]*100:+.1f}% [{roi[1]*100:+.1f}, {roi[2]*100:+.1f}]; after 12% tax {roit[0]*100:+.1f}% [{roit[1]*100:+.1f}, {roit[2]*100:+.1f}]')
        for fname in sorted({fam(r) for r in P}):
            S = [r for r in P if fam(r) == fname]
            t = boot([(r['sid'], r) for r in S], lambda xs: np.mean([x['y'] * x['odds'] - 1 for x in xs]), B=1000)
            print(f'    {fname:12s} legs {len(S):5d} m {t[3]:4d} conf {np.mean([r["conf"] for r in S]):.3f} 1/odds {np.mean([1/r["odds"] for r in S]):.3f} realised {np.mean([r["y"] for r in S]):.3f} ROI {t[0]*100:+.1f}% [{t[1]*100:+.1f}, {t[2]*100:+.1f}]')
        print('    sources', collections.Counter(r['source'].split('|')[0].split('-')[0].split('+')[0] for r in P).most_common(8))
        print('    per day', sorted(days.items()))

# old format, same comparison on OVER lines
print('\n=== OLD format (two-sided), OVER lines with the point model p, 10-21..11-19')
O = [o for o in old if '2026-10-21' <= o['day'] <= '2026-11-19' and o['over_odds'] and o['under_odds']
     and 1.0 <= 1 / o['over_odds'] + 1 / o['under_odds'] <= 1.3]
def fam_old(o):
    m = o['metric']; st = 'aces+df' if m.startswith('serve_points') else 'df' if m.startswith('double') else 'aces'
    return f"{st}/{'set' if '_set' in m else 'match'}"
for fname in ['ALL'] + sorted({fam_old(o) for o in O}):
    S = [o for o in O if fname == 'ALL' or fam_old(o) == fname]
    it = [(o['sid'], o) for o in S]
    def nv(o): return (1 / o['over_odds']) / (1 / o['over_odds'] + 1 / o['under_odds'])
    d_nv = boot(it, lambda xs: np.mean([brier(x['p'], x['y']) - brier(nv(x), x['y']) for x in xs]))
    d_im = boot(it, lambda xs: np.mean([brier(x['p'], x['y']) - brier(min(1 / x['over_odds'], 1), x['y']) for x in xs]))
    print(f'{fname:12s} lines {len(S):5d} m {d_nv[3]:4d} overround median {np.median([1/o["over_odds"]+1/o["under_odds"]-1 for o in S]):.4f} | model-devig {fmt(d_nv)} | model-implied(OVER raw) {fmt(d_im)} | mean p {np.mean([o["p"] for o in S]):.3f} 1/odds_over {np.mean([1/o["over_odds"] for o in S]):.3f} fair {np.mean([nv(o) for o in S]):.3f} y {np.mean([o["y"] for o in S]):.3f}')
