"""Steps 3-5: tie calibration, OT/SO winner, regulation vs incl-OT/SO lines on NHL history (walk.pkl),
and the offered Superbet selections 11-06..11-20 (offers.pkl + results.pkl) priced from the same
walk-forward sims. Curves: (a) fitted here on NHL history rows (sport_confidence.fit_curves,
effective n, monotone; confidence = bucket realised_lo95, as SportCalibration reads), (b) the installed
hockey curves of the file 2026-11-20 reads (calibration_path_for)."""
import pickle, sys, collections, math, random, re, json
import numpy as np
from bet.sofa import sport_confidence as scf
S = sys.argv[1]
W = pickle.load(open(f'{S}/walk.pkl', 'rb'))
D = pickle.load(open(f'{S}/offers.pkl', 'rb'))
R = pickle.load(open(f'{S}/results.pkl', 'rb'))
rng = np.random.default_rng(7)
out = []
def P(*a):
    s = ' '.join(str(x) for x in a)
    print(s); out.append(s)

def boot_mean(vals, games, B=2000):
    """mean of vals, 95% CI by game bootstrap (vals grouped by game)."""
    by = collections.defaultdict(list)
    for v, g in zip(vals, games):
        by[g].append(v)
    keys = list(by)
    sums = np.array([sum(by[k]) for k in keys]); cnts = np.array([len(by[k]) for k in keys])
    idx = rng.integers(0, len(keys), size=(B, len(keys)))
    m = sums[idx].sum(1) / cnts[idx].sum(1)
    return float(sums.sum() / cnts.sum()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))

def fmt(t, k=4, scale=1.0):
    return f"{t[0]*scale:+.{k}f} [{t[1]*scale:+.{k}f}, {t[2]*scale:+.{k}f}]"

def probs(row):
    n = row['n']; j = row['joint']
    return j, n
def p_of(row, pred):
    j, n = probs(row)
    return sum(c for (a, b, o), c in j.items() if pred(a, b, o)) / n

nhl = [w for w in W if w['nhl'] and not w.get('no_p')]
nhl_nop = sum(1 for w in W if w['nhl'] and w.get('no_p'))
oth = [w for w in W if not w['nhl'] and not w.get('no_p')]
def season(ts):
    import time
    y, m = time.gmtime(ts).tm_year, time.gmtime(ts).tm_mon
    return f"{y}-{y+1-2000:02d}" if m >= 8 else f"{y-1}-{y-2000:02d}"
P(f"## Walk-forward: NHL games scored {len(nhl)} (no p: {nhl_nop}), other leagues sample {len(oth)}")
P("seasons", dict(collections.Counter(season(w['ts']) for w in nhl)))

# ---------- 4a. tie after regulation ----------
P("\n## 4a. P(remis po 60') - model vs historia")
for name, rows in (("NHL", nhl), ("inne ligi (próbka 1/10)", oth)):
    pt = [p_of(w, lambda a, b, o: a == b) for w in rows]
    yt = [1.0 if w['reg'][0] == w['reg'][1] else 0.0 for w in rows]
    g = [w['event_id'] for w in rows]
    d = boot_mean([y - p for y, p in zip(yt, pt)], g)
    P(f"{name}: n {len(rows)}, model mean {np.mean(pt):.4f}, realised {np.mean(yt):.4f}, realised - model {fmt(d)}")
    if name == "NHL":
        for s in sorted(set(season(w['ts']) for w in rows)):
            ii = [i for i, w in enumerate(rows) if season(w['ts']) == s]
            dd = boot_mean([yt[i] - pt[i] for i in ii], [g[i] for i in ii])
            P(f"   {s}: n {len(ii)}, model {np.mean([pt[i] for i in ii]):.4f}, realised {np.mean([yt[i] for i in ii]):.4f}, diff {fmt(dd)}")
        # by bands of model tie p
        for lo, hi in ((0, .20), (.20, .22), (.22, .24), (.24, 1)):
            ii = [i for i, p in enumerate(pt) if lo <= p < hi]
            if ii:
                P(f"   p_tie {lo:.2f}-{hi:.2f}: n {len(ii)}, model {np.mean([pt[i] for i in ii]):.4f}, realised {np.mean([yt[i] for i in ii]):.4f}")
        bt = np.mean([(y - p) ** 2 for y, p in zip(yt, pt)]); base = np.mean(yt)
        bc = np.mean([(y - base) ** 2 for y in yt])
        P(f"   Brier tie: model {bt:.5f} vs constant (in-sample mean {base:.4f}) {bc:.5f}")
        # regulation total goals mean vs model
        mu = [sum(w['mu']) for w in rows]; rt = [sum(w['reg']) for w in rows]
        P(f"   regulation goals: model mean (rating mean, pre late goal) {np.mean(mu):.3f}, sim mean "
          f"{np.mean([sum((a+b)*c for (a,b,o),c in w['joint'].items())/w['n'] for w in rows]):.3f}, realised {np.mean(rt):.3f}")
        P(f"   tie share by regulation total (real): " + ", ".join(
            f"{t}: {sum(1 for w in rows if sum(w['reg'])==t and w['reg'][0]==w['reg'][1])}/{sum(1 for w in rows if sum(w['reg'])==t)}" for t in (0,2,4,6,8)))

# ---------- 4b. OT/SO winner ----------
P("\n## 4b. P(gospodarz wygrywa dogrywkę/karne | remis)")
ties = [w for w in nhl if w['reg'][0] == w['reg'][1] and w['winner'] in ('T1', 'T2')]
ph = [p_of(w, lambda a, b, o: a == b and o == 1) / max(p_of(w, lambda a, b, o: a == b), 1e-9) for w in ties]
yh = [1.0 if w['winner'] == 'T1' else 0.0 for w in ties]
d = boot_mean([y - p for y, p in zip(yh, ph)], [w['event_id'] for w in ties])
hw = boot_mean(yh, [w['event_id'] for w in ties])
P(f"NHL ties {len(ties)}: home won {fmt(hw,3)}; model mean {np.mean(ph):.3f}; realised - model {fmt(d)}")
for st in ('AET', 'AP'):
    ii = [i for i, w in enumerate(ties) if w['status'] == st]
    P(f"   {st}: n {len(ii)}, home won {np.mean([yh[i] for i in ii]):.3f}")
b_model = np.mean([(y - p) ** 2 for y, p in zip(yh, ph)]); b_half = np.mean([(y - .5) ** 2 for y in yh])
P(f"   Brier: model {b_model:.5f} vs 0.5 {b_half:.5f}")

# ---------- 5a. lines on NHL history: regulation vs incl ----------
def lines_of(w):
    """(market, line, side, p, y) for fixed lines; home = team1."""
    rows = []
    rr, ff = w['reg'], w['full']
    for L in (3.5, 4.5, 5.5, 6.5, 7.5, 8.5):
        for scope, f, real in (('total', lambda a, b, o: a + b, sum(rr)),
                               ('total_incl', lambda a, b, o: a + b + (o > 0), sum(ff))):
            p = p_of(w, lambda a, b, o, f=f: f(a, b, o) > L)
            rows += [(scope, L, 'OVER', p, int(real > L)), (scope, L, 'UNDER', 1 - p, int(real < L))]
    for L in (1.5, 2.5, 3.5, 4.5):
        for t in (1, 2):
            for scope, f, real in (('team_total', (lambda a, b, o: a) if t == 1 else (lambda a, b, o: b), rr[t-1]),
                                   ('team_total_incl', (lambda a, b, o: a + (o == 1)) if t == 1 else (lambda a, b, o: b + (o == 2)), ff[t-1])):
                p = p_of(w, lambda a, b, o, f=f: f(a, b, o) > L)
                rows += [(scope, L, 'OVER', p, int(real > L)), (scope, L, 'UNDER', 1 - p, int(real < L))]
    for h in (-2.5, -1.5, 1.5, 2.5):
        for scope, f, real in (('handicap', lambda a, b, o: a - b, rr[0]-rr[1]),
                               ('handicap_incl', lambda a, b, o: a - b + (o == 1) - (o == 2), ff[0]-ff[1])):
            p = p_of(w, lambda a, b, o, f=f: f(a, b, o) + h > 0)
            rows += [(scope, h, 'T1', p, int(real + h > 0)), (scope, h, 'T2', 1 - p, int(real + h < 0))]
    return rows

hist = []
for w in nhl:
    for (m, L, side, p, y) in lines_of(w):
        hist.append({'m': m, 'L': L, 'side': side, 'p': p, 'y': y, 'game': w['event_id'], 'ts': w['ts']})
P(f"\n## 5a. Linie stałe na historii NHL (walk-forward), {len(hist)} wierszy")
# identity check
idt = collections.Counter()
by_game = collections.defaultdict(dict)
for r in hist:
    by_game[r['game']][(r['m'], r['L'], r['side'])] = r
for g, d in by_game.items():
    for L in (3.5, 5.5, 7.5):
        a, b = d[('total', L, 'OVER')], d[('total_incl', L, 'OVER')]
        idt[('total odd-k same y', a['y'] == b['y'])] += 1; idt[('total odd-k same p', abs(a['p'] - b['p']) < 1e-12)] += 1
    for L in (4.5, 6.5):
        a, b = d[('total', L, 'OVER')], d[('total_incl', L, 'OVER')]
        idt[('total even-k same y', a['y'] == b['y'])] += 1
    for h in (-2.5, -1.5, 1.5, 2.5):
        a, b = d[('handicap', h, 'T1')], d[('handicap_incl', h, 'T1')]
        idt[('handicap same y', a['y'] == b['y'])] += 1; idt[('handicap same p', abs(a['p'] - b['p']) < 1e-12)] += 1
P("identity check (game x line):", dict(idt))

def calib(rows, label):
    g = [r['game'] for r in rows]
    d = boot_mean([r['y'] - r['p'] for r in rows], g)
    ll = np.mean([-math.log(max(min(r['p'] if r['y'] else 1 - r['p'], 1 - 1e-6), 1e-6)) for r in rows])
    br = np.mean([(r['y'] - r['p']) ** 2 for r in rows])
    s = f"{label}: n {len(rows)}, claim {np.mean([r['p'] for r in rows]):.4f}, real {np.mean([r['y'] for r in rows]):.4f}, real-claim {fmt(d)}, Brier {br:.5f}, logloss {ll:.5f}"
    P(s)
for m in ('total', 'total_incl', 'team_total', 'team_total_incl', 'handicap', 'handicap_incl'):
    rows = [r for r in hist if r['m'] == m and r['side'] in ('OVER', 'T1')]
    calib(rows, f"{m} (OVER/T1, all lines)")
    for lo, hi in ((.6, .7), (.7, .8), (.8, .92)):
        rr = [r for r in hist if r['m'] == m and lo <= r['p'] < hi]
        if len(rr) > 30:
            calib(rr, f"    band {lo:.2f}-{hi:.2f}")
# incl total even-k lines only (where incl differs) vs same lines regulation
for L in (4.5, 6.5):
    for m in ('total', 'total_incl'):
        rr = [r for r in hist if r['m'] == m and r['L'] == L and r['side'] == 'OVER']
        calib(rr, f"{m} O{L}")
for L in (1.5, 2.5, 3.5):
    for m in ('team_total', 'team_total_incl'):
        rr = [r for r in hist if r['m'] == m and r['L'] == L and r['side'] == 'OVER']
        calib(rr, f"{m} O{L} (both teams)")
# paired: incl minus reg calibration gap (abs) on matched game-lines, printable-ish p
for m1, m2 in (('total', 'total_incl'), ('team_total', 'team_total_incl')):
    a = [r for r in hist if r['m'] == m1 and r['p'] >= .6]
    b = [r for r in hist if r['m'] == m2 and r['p'] >= .6]
    da = boot_mean([r['y'] - r['p'] for r in a], [r['game'] for r in a])
    db = boot_mean([r['y'] - r['p'] for r in b], [r['game'] for r in b])
    P(f"p>=0.60: {m1} real-claim {fmt(da)} (n {len(a)}) | {m2} {fmt(db)} (n {len(b)})")

# ---------- curves ----------
fit_rows = [dict(key=f"{r['m']}|{r['side'] if r['side'] in ('OVER','UNDER') else 'TEAM'}", p=r['p'], y=r['y'], game=r['game'])
            for r in hist if r['ts'] < scf.day_ts('2026-10-01')]
curves = scf.fit_curves(fit_rows, effective_n=True, monotone=True)
cal_path = scf.calibration_path_for('2026-11-20')
inst = json.load(open(cal_path))['sports']['hockey']['curves']
P(f"\ncurves fitted on NHL history < 2026-10-01: {len(fit_rows)} rows; installed file read on 11-20: {cal_path.name}")
for k in ('total|OVER', 'total|UNDER', 'total_incl|OVER', 'total_incl|UNDER', 'team_total_incl|OVER', 'team_total_incl|UNDER', 'handicap|TEAM'):
    c = curves.get(k, {})
    P(f"  NHL {k}: " + "; ".join(f"{lab} n{e['n']} r{e['realised']:.3f} lo{e['realised_lo95']:.3f}" for lab, e in c.items() if float(lab.split('-')[0]) >= .6))
for k in ('total|OVER', 'total|UNDER', 'team_total|OVER', 'team_total|UNDER', 'handicap|TEAM'):
    c = inst.get(k, {})
    P(f"  installed {k}: " + "; ".join(f"{lab} r{e['realised']:.3f} lo{e['realised_lo95']:.3f}" for lab, e in c.items() if float(lab.split('-')[0]) >= .6))
def conf(curve, p):
    e = scf._find(curve, p) if curve else None
    return None if e is None else float(e['realised_lo95'])

# NHL hold-out of the new season (history rows >= 2026-10-01): curve applied
P("\n## 5b. NHL hold-out 2026-10-01..11-20 (krzywa NHL z historii < 10-01): pewność vs realizacja")
ho = [r for r in hist if r['ts'] >= scf.day_ts('2026-10-01')]
for m in ('total', 'total_incl', 'team_total', 'team_total_incl', 'handicap'):
    rr = []
    for r in ho:
        if r['m'] != m: continue
        k = f"{m}|{r['side'] if r['side'] in ('OVER','UNDER') else 'TEAM'}"
        c = conf(curves.get(k), r['p'])
        if c is not None and c >= .70:
            rr.append({**r, 'c': c})
    if rr:
        d = boot_mean([r['y'] - r['c'] for r in rr], [r['game'] for r in rr])
        P(f"{m}: conf>=0.70 rows {len(rr)} ({len({r['game'] for r in rr})} games), conf {np.mean([r['c'] for r in rr]):.3f}, real {np.mean([r['y'] for r in rr]):.3f}, real-conf {fmt(d, 3)}")

# ---------- 5c. offered Superbet selections ----------
P("\n## 5c. Oferowane linie Superbetu (NHL, 11-06..11-20, ostatnia cena przed startem)")
ev, settled, last = D['events'], D['settled'], D['last']
wby = {w['event_id']: w for w in nhl}
groups = collections.defaultdict(dict)
for (eid, m, mn, sbv, name), (ts, price) in last.items():
    if m in (617, 613, 621, 653):
        groups[(eid, m, sbv)][name] = price
legs = []
skip = collections.Counter()
for (eid, m, sbv), g in groups.items():
    r = R.get(eid)
    if not r or r['state'] != 'SETTLED':
        skip['not settled'] += 1; continue
    w = wby.get(r['sofascore_event_id'])
    if w is None:
        skip['no walk row'] += 1; continue
    if len(g) != 2:
        skip['one-sided group'] += 1; continue
    h1 = r['home_is_team1']
    t1f, t2f = (w['full'] if h1 else w['full'][::-1])
    t1r, t2r = (w['reg'] if h1 else w['reg'][::-1])
    # model in team1 orientation
    def pm(pred):  # pred on (t1reg, t2reg, otw team1=1)
        def f(a, b, o):
            if not h1:
                a, b, o = b, a, {0: 0, 1: 2, 2: 1}[o]
            return pred(a, b, o)
        return p_of(w, f)
    L = float(sbv)
    s = sum(1 / x for x in g.values())
    for name, price in g.items():
        if m in (617, 621, 653):
            over = name.startswith('Powyżej')
            if m == 617:
                q = lambda a, b, o: a + b + (o > 0); real = t1f + t2f; mk = 'total_incl'; regq = lambda a, b, o: a + b
            elif m == 621:
                q = lambda a, b, o: a + (o == 1); real = t1f; mk = 'team_total_incl'; regq = lambda a, b, o: a
            else:
                q = lambda a, b, o: b + (o == 2); real = t2f; mk = 'team_total_incl'; regq = lambda a, b, o: b
            p_over = pm(lambda a, b, o, q=q: q(a, b, o) > L)
            p = p_over if over else 1 - p_over
            y = int((real > L) == over)
            side = 'OVER' if over else 'UNDER'
            same_reg = (m == 617 and int(L) % 2 == 1)
            p_reg_curve_input = pm(lambda a, b, o, regq=regq: regq(a, b, o) > L)
            p_reg_curve_input = p_reg_curve_input if over else 1 - p_reg_curve_input
        else:
            mm = re.match(r'^(.*) \((-?\d+(?:\.\d+)?)\)$', name)
            t1side = mm.group(1) == r['team1']
            hh = L  # team1's handicap
            p_t1 = pm(lambda a, b, o: a - b + hh > 0)
            p = p_t1 if t1side else 1 - p_t1
            marg = t1f - t2f
            y = int((marg + hh > 0) == t1side)
            mk, side, same_reg, p_reg_curve_input = 'handicap', 'TEAM', True, p
        legs.append({'eid': eid, 'game': eid, 'm': m, 'mk': mk, 'L': L, 'side': side, 'name': name, 'odds': price,
                     'fair': (1 / price) / s, 'ovr': s - 1, 'p': p, 'y': y, 'same_reg': same_reg, 'p_regkey': p_reg_curve_input,
                     'day': ev[eid]['kickoff_utc'][:10], 'tie_real': t1r == t2r})
P("skipped groups:", dict(skip), "| legs (sides):", len(legs), "events:", len({l['eid'] for l in legs}))
def cmp(rows, label):
    if not rows: return
    g = [r['game'] for r in rows]
    bm = [(r['y'] - r['p']) ** 2 for r in rows]; bk = [(r['y'] - r['fair']) ** 2 for r in rows]
    lm = [-math.log(max(r['p'] if r['y'] else 1 - r['p'], 1e-6)) for r in rows]
    lk = [-math.log(max(r['fair'] if r['y'] else 1 - r['fair'], 1e-6)) for r in rows]
    db = boot_mean([a - b for a, b in zip(bm, bk)], g); dl = boot_mean([a - b for a, b in zip(lm, lk)], g)
    P(f"{label}: n {len(rows)} sides / {len(set(g))} games; Brier model {np.mean(bm):.4f} market {np.mean(bk):.4f} diff {fmt(db, 4)}; logloss diff {fmt(dl, 4)}")
for m in (617, 613, 621, 653):
    cmp([l for l in legs if l['m'] == m], f"m{m}")
cmp([l for l in legs if l['m'] == 617 and not l['same_reg']], "m617 even-k lines (differ from regulation)")
cmp([l for l in legs if l['m'] in (621, 653)], "m621+653 team totals")
cmp(legs, "all four")
P("calibration bands (model p) on offered sides:")
for lo, hi in ((.6, .7), (.7, .8), (.8, .92)):
    rr = [l for l in legs if lo <= l['p'] < hi]
    if rr:
        d = boot_mean([r['y'] - r['p'] for r in rr], [r['game'] for r in rr])
        P(f"   {lo:.2f}-{hi:.2f}: n {len(rr)}, claim {np.mean([r['p'] for r in rr]):.3f}, real {np.mean([r['y'] for r in rr]):.3f}, fair {np.mean([r['fair'] for r in rr]):.3f}, real-claim {fmt(d,3)}")
# tie: model vs Superbet 640 DRAW
P("\nP(remis po 60') na tych meczach: model vs Superbet 640 (de-vig 3-drogowy) vs realizacja")
tie_rows = []
for eid in {l['eid'] for l in legs}:
    rl = ev[eid].get('reg_lines', {})
    odds = {k[2]: v[1] for k, v in rl.items() if k[0] == 640}
    r = R[eid]; w = wby[r['sofascore_event_id']]
    if set(odds) >= {'T1', 'DRAW', 'T2'}:
        s = sum(1 / o for o in odds.values())
        tie_rows.append((p_of(w, lambda a, b, o: a == b), (1 / odds['DRAW']) / s, int(w['reg'][0] == w['reg'][1]), eid))
if tie_rows:
    a = np.array([t[:3] for t in tie_rows])
    P(f"n {len(a)}: model {a[:,0].mean():.4f}, market {a[:,1].mean():.4f}, realised {a[:,2].mean():.4f}; Brier model {((a[:,2]-a[:,0])**2).mean():.4f} market {((a[:,2]-a[:,1])**2).mean():.4f}")
# confidence + gates
P("\n## 5d. Bramki druku (pewność = krzywa; ovr <= 15%, conf >= 0.70, conf x kurs >= 0.90)")
def run_gates(curve_src, label):
    rows = []
    for l in legs:
        if curve_src == 'nhl':
            k = f"{l['mk']}|{l['side']}" if l['mk'] != 'handicap' else 'handicap|TEAM'
            c = conf(curves.get(k), l['p'])
        else:  # installed regulation keys (incl lines read as their regulation family)
            k = {'total_incl': 'total', 'team_total_incl': 'team_total', 'handicap': 'handicap'}[l['mk']]
            k = f"{k}|{l['side']}"
            c = conf(inst.get(k), l['p'])
        if c is None: continue
        if c >= .70 and c * l['odds'] >= .90 and l['ovr'] <= .15:
            rows.append({**l, 'c': c})
    if not rows:
        P(f"{label}: 0 legs"); return
    g = [r['game'] for r in rows]
    hit = boot_mean([r['y'] for r in rows], g)
    roi = boot_mean([r['y'] * r['odds'] - 1 for r in rows], g)
    roit = boot_mean([r['y'] * r['odds'] * .88 - 1 for r in rows], g)
    days = collections.Counter(r['day'] for r in rows)
    P(f"{label}: legs {len(rows)} on {len(set(g))} games, per day {dict(sorted(days.items()))}")
    P(f"   by market {dict(collections.Counter(r['m'] for r in rows))}; same-as-regulation {sum(r['same_reg'] for r in rows)}")
    P(f"   conf {np.mean([r['c'] for r in rows]):.3f}, hit {fmt(hit,3)}, mean 1/odds {np.mean([1/r['odds'] for r in rows]):.3f}, fair {np.mean([r['fair'] for r in rows]):.3f}")
    P(f"   ROI {fmt(roi,3)}; after 12% tax {fmt(roit,3)}")
run_gates('nhl', 'krzywe NHL (nowe klucze)')
run_gates('inst', 'zainstalowane krzywe regulaminowe (total/team_total/handicap)')
pickle.dump({'legs': legs, 'hist_n': len(hist), 'curves': curves}, open(f'{S}/analysis.pkl', 'wb'))
open(f'{S}/out_s06.txt', 'w').write('\n'.join(out))
