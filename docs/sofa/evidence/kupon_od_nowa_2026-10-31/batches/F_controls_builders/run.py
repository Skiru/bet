"""Batch F_controls_builders - controls and Bet Builders of the /kupon redesign backtest.

Run:
  PYTHONPATH=/Users/mkoziol/projects/bet/src:/Users/mkoziol/projects/bet/data/kupon_redesign_2026-10-31 \
    /Users/mkoziol/projects/bet/.venv/bin/python run.py

Dimensions:
  singles      leg_cell per pool x odds band (single_after_tax = one-leg slip after 12% tax)
  realisation  leg_cell per pool x sport + realisation = hit / mean(1/odds) (the 0.946 benchmark)
  random       simulate_slips with a random rank, 20 seeds pooled, pools x (n_legs, target)
               x slips_per_window {1, 3}
  kupon        the current /kupon: rank log(min(conf, inv)) + log(1.0025) when overround < 0.08,
               odds 1.10..2.00, slips_per_window 3, all windows; legs 2/3/4 x targets
               (and a log(conf) rank on the all pool for comparison)
  builder      own simulator (below): 2 legs of ONE match on different markets (or families),
               up to 3 builders per (day, window), each match once; payout 0.90 x product
               (refund leg 1.00); ranks conf product / min(conf,inv) product / evidence
               score / random (20 seeds); no target or target 2 (product in [1.70, 2.60]).
               Extra columns: joint_inv (mean product of 1/odds) and ROI with the measured
               builder markup 8.8% / 19.6% (payout / 1.088, / 1.196).
Pools (as batch E): all; s8 = sample_size >= 8 and forecast_source != 'league_rate';
  ci = conf >= inv.
"""
from __future__ import annotations

import os
import time

import numpy as np
import pandas as pd

import bt_lib as b

OUT = os.path.dirname(os.path.abspath(__file__))
BATCH = 'F_controls_builders'
SEEDS = list(range(20))
EV_SIGNALS = ['m_own', 'm_conc', 'm_a', 'm_b', 'm_lg', 'm_h2h', 'm_ref', 'm_sample']

POOLS = {
    'all': ('True', lambda d: pd.Series(True, index=d.index)),
    's8': ("(sample_size >= 8) & (forecast_source != 'league_rate')",
           lambda d: (pd.to_numeric(d.sample_size, errors='coerce') >= 8)
           & (d.forecast_source != 'league_rate')),
    'ci': ('conf >= inv', lambda d: d.conf.astype(float) >= d.inv),
}
BANDS = {
    'all': (0, 99), 'lt1.15': (0, 1.15), '1.15-1.25': (1.15, 1.25), '1.25-1.35': (1.25, 1.35),
    '1.35-1.50': (1.35, 1.50), 'ge1.50': (1.50, 99),
}
SPORTS = ['football', 'tennis', 'hockey', 'basketball', 'volleyball', 'cs2']
COMBOS = [(2, 2.0), (3, 2.0), (3, 3.0), (3, 4.0), (4, 2.0), (4, 3.0), (4, 4.0)]


def kupon_rank(d):
    m = np.minimum(d.conf.astype(float), d.inv)
    low = (pd.to_numeric(d.overround, errors='coerce') < 0.08).fillna(False)
    return np.log(m) + np.where(low, np.log(1.0025), 0.0)


def summarise(slips, extra=True):
    s = b.slip_summary(slips)
    if extra and slips is not None and len(slips):
        s['roi_seed_mean'] = round((slips.groupby('seed').payout.mean() - 1).mean() * 100, 2) \
            if 'seed' in slips else None
        s['roi_seed_sd'] = round((slips.groupby('seed').payout.mean() - 1).std() * 100, 2) \
            if 'seed' in slips and slips.seed.nunique() > 1 else None
        if 'joint_inv' in slips:
            s['joint_inv'] = round(slips.joint_inv.mean(), 4)
            for tag, mk in (('mk088', 1.088), ('mk196', 1.196)):
                s[f'roi_{tag}'] = round(((slips.payout / mk).mean() - 1) * 100, 2)
    return s


def builders(df, pool_mask, score, windows=('afternoon', 'evening', 'night'), per_window=3,
             distinct='market', target=None, band_tol=0.15, top_k=40):
    """Bet Builders: in each (day, window), for each match the best pair (by `score` sum)
    of two pool legs on different `distinct` values (and different subject+line+direction);
    the matches ranked by their best pair, top `per_window` taken, one builder per match.
    target: product must lie in [target(1-tol), target(1+2tol)]. Payout 0.90 x product
    (refund leg 1.00) when every non-refund leg won."""
    d = df[pool_mask].copy()
    d['_s'] = score[pool_mask].astype(float).values
    rows = []
    for (day, win), g in b._windows(d, windows):
        cands = []
        for eid, m in g.groupby('eid'):
            if len(m) < 2:
                continue
            m = m.sort_values('_s', ascending=False).head(top_k)
            s = m._s.values
            o = m.odds.values
            dv = pd.factorize(m[distinct].astype(str))[0]
            ss = s[:, None] + s[None, :]
            ok = np.triu(np.ones((len(m), len(m)), bool), 1) & (dv[:, None] != dv[None, :])
            if target is not None:
                pr = o[:, None] * o[None, :]
                ok &= (pr >= target * (1 - band_tol)) & (pr <= target * (1 + 2 * band_tol))
            if not ok.any():
                continue
            ss = np.where(ok, ss, -np.inf)
            i, j = np.unravel_index(np.argmax(ss), ss.shape)
            cands.append((ss[i, j], eid, m.iloc[i], m.iloc[j]))
        cands.sort(key=lambda x: -x[0])
        for k, (_, eid, x, y) in enumerate(cands[:per_window]):
            legs = [x, y]
            prod = float(x.odds * y.odds)
            eff = float(np.prod([1.0 if l.refund else l.odds for l in legs]))
            win_all = all(l.refund or l.won == 1 for l in legs)
            rows.append({'day': day, 'window': win, 'slip': k, 'n_legs': 2, 'product': prod,
                         'joint_inv': float(x.inv * y.inv), 'won': int(win_all),
                         'payout': 0.90 * eff if win_all else 0.0,
                         'legs': f'{x.key}|{y.key}'})
    return pd.DataFrame(rows)


def main():
    t0 = time.time()
    data = {s: b.load(s) for s in ('dev', 'val')}
    for d in data.values():
        d['_ev'] = b.evidence_score(d, EV_SIGNALS)
    cells = []  # (cell, dimension, definition, {split: dict})

    def add(cell, dim, definition, fn):
        res = {s: fn(d) for s, d in data.items()}
        cells.append((cell, dim, definition, res))
        print(f'{time.time() - t0:6.0f}s {cell}: dev {res["dev"]} | val {res["val"]}', flush=True)

    def legcell(mask_fn):
        def f(d):
            r = b.leg_cell(d, mask_fn(d))
            if r.get('n'):
                r['realisation'] = round(r['hit'] / r['inv'], 4)
            return r
        return f

    # (1) singles per pool x odds band
    for pn, (pdef, pf) in POOLS.items():
        for bn, (lo, hi) in BANDS.items():
            add(f'single|{pn}|{bn}', 'singles', f'pool[{pdef}] & odds>={lo} & odds<{hi}; n_legs=1',
                legcell(lambda d, pf=pf, lo=lo, hi=hi: pf(d) & (d.odds >= lo) & (d.odds < hi)))
    # (5) realisation per pool x sport
    for pn, (pdef, pf) in POOLS.items():
        for sp in SPORTS:
            add(f'realisation|{pn}|{sp}', 'realisation', f"pool[{pdef}] & sport=='{sp}'",
                legcell(lambda d, pf=pf, sp=sp: pf(d) & (d.sport == sp)))

    # (2) random slips
    for pn, (pdef, pf) in POOLS.items():
        for spw in (1, 3):
            for nl, tg in COMBOS:
                def f(d, pf=pf, nl=nl, tg=tg, spw=spw):
                    out = []
                    for sd in SEEDS:
                        rk = pd.Series(np.random.default_rng(1000 + sd).random(len(d)), index=d.index)
                        s = b.simulate_slips(d, pf(d), rk, nl, tg, slips_per_window=spw, seed=sd)
                        if len(s):
                            s['seed'] = sd
                            out.append(s)
                    return summarise(pd.concat(out) if out else None)
                add(f'random|{pn}|{nl}legs|t{tg:g}|spw{spw}', 'random',
                    f'pool[{pdef}]; rank=uniform random (seeds 1000..1019, tie seed 0..19); '
                    f'n_legs={nl}; target={tg}; slips_per_window={spw}; band_tol=0.15; all windows; '
                    f'20 seeds pooled', f)

    # (3) current /kupon and variants
    for pn, (pdef, pf) in POOLS.items():
        for nl, tg in COMBOS:
            def f(d, pf=pf, nl=nl, tg=tg):
                m = pf(d) & (d.odds >= 1.10) & (d.odds <= 2.00)
                return summarise(b.simulate_slips(d, m, pd.Series(kupon_rank(d), index=d.index),
                                                  nl, tg, slips_per_window=3, seed=0))
            add(f'kupon|{pn}|{nl}legs|t{tg:g}', 'kupon_current',
                f'pool[{pdef}] & 1.10<=odds<=2.00; rank=log(min(conf,inv))+log(1.0025)*(overround<0.08); '
                f'n_legs={nl}; target={tg}; slips_per_window=3; all windows', f)
    for nl, tg in COMBOS:
        def f(d, nl=nl, tg=tg):
            m = (d.odds >= 1.10) & (d.odds <= 2.00)
            return summarise(b.simulate_slips(d, m, np.log(d.conf.astype(float)), nl, tg,
                                              slips_per_window=3, seed=0))
        add(f'kupon_confrank|all|{nl}legs|t{tg:g}', 'kupon_current',
            f'1.10<=odds<=2.00; rank=log(conf) (no price cap, no margin tie); n_legs={nl}; '
            f'target={tg}; slips_per_window=3', f)

    # (4) builders
    def bscore(name, d, sd=0):
        if name == 'conf':
            return np.log(d.conf.astype(float))
        if name == 'kupon':
            return pd.Series(kupon_rank(d), index=d.index)
        if name == 'evidence':
            return d._ev.fillna(-1.0)
        return pd.Series(np.random.default_rng(2000 + sd).random(len(d)), index=d.index)

    for pn, (pdef, pf) in POOLS.items():
        for distinct in ('market', 'family'):
            for tg in (None, 2.0):
                for rk in ('conf', 'kupon', 'evidence', 'random'):
                    def f(d, pf=pf, distinct=distinct, tg=tg, rk=rk):
                        seeds = SEEDS if rk == 'random' else [0]
                        out = []
                        for sd in seeds:
                            s = builders(d, pf(d), bscore(rk, d, sd), distinct=distinct, target=tg)
                            if len(s):
                                s['seed'] = sd
                                out.append(s)
                        return summarise(pd.concat(out) if out else None)
                    rdef = {'conf': 'log(conf_i)+log(conf_j)',
                            'kupon': 'sum log(min(conf,inv))+margin tie',
                            'evidence': 'sum evidence_score(m_own,m_conc,m_a,m_b,m_lg,m_h2h,m_ref,m_sample), NaN=-1',
                            'random': 'uniform random, 20 seeds pooled'}[rk]
                    add(f'builder|{pn}|diff_{distinct}|{"t2" if tg else "notarget"}|{rk}', 'builder',
                        f'pool[{pdef}]; 2 legs of one match, different {distinct}; best pair per match '
                        f'by {rdef}; top 3 matches per (day, window); '
                        f'{"product in [1.70,2.60]" if tg else "no target"}; payout 0.90 x product', f)

    rows = []
    for cell, dim, definition, res in cells:
        row = {'batch': BATCH, 'cell': cell, 'dimension': dim, 'definition': definition}
        for s, r in res.items():
            for k, v in r.items():
                row[f'{s}_{k}'] = v
        rows.append(row)
    out = pd.DataFrame(rows)
    out.to_csv(f'{OUT}/cells.csv', index=False)
    print('cells', len(out), 'in', round(time.time() - t0), 's')


if __name__ == '__main__':
    main()
