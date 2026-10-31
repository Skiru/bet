"""Batch E_slips_rank: ranking x slip construction (dimensions 4 and 5).

Main grid: windows = all three, slips_per_window = 3, max_per_market None, one_sport False;
ranking (8) x pool (4) x (n_legs, target) (7). Then variants (each window alone,
slips_per_window 1, one_sport True, max_per_market 1) on the 10 best dev non-control
cells (>= 30 dev slips), and the same variants of the /kupon and random controls on the
distinct (pool, n_legs, target) of the 5 best. Every cell on dev and val.
Random = rank 0, seeds 0..19 (ties broken by the seeded shuffle); reported = mean of the
per-seed slip_summary numbers, plus roi seed sd / min / max.
"""
from __future__ import annotations

import os
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
import bt_lib as b  # noqa: E402

BATCH = 'E_slips_rank'
DATA = {}

AGREE_COLS = ['m_own', 'm_conc', 'm_a', 'm_b', 'm_lg', 'm_h2h', 'm_sample', 'm_conf', 'm_model']


def rankings(d: pd.DataFrame) -> dict[str, pd.Series]:
    side = d.m_own.notna() | d.m_conc.notna()
    ev_side = b.evidence_score(d, ['m_own', 'm_conc', 'm_lg', 'm_h2h'])
    ev_tot = b.evidence_score(d, ['m_a', 'm_b', 'm_lg', 'm_h2h'])
    ev = ev_side.where(side, ev_tot).fillna(d.m_conf)
    agree = (d[AGREE_COLS] >= 0).sum(1) + 0.001 * d.m_conf.fillna(0)
    low_margin = (d.one_sided == 0) & (d.overround < 0.08)
    kupon = np.log(np.minimum(d.conf.astype(float), d.inv)) + np.log(1.0025) * low_margin
    return {
        'evidence': ev,
        'margin_conf': d.conf.astype(float) - d.inv,
        'agreement': agree,
        'model_margin': (pd.to_numeric(d.forecast_p, errors='coerce') - d.inv).fillna(-9),
        'price_long': -d.inv,
        'price_short': d.inv,
        'kupon_current': kupon,
        'random': pd.Series(0.0, index=d.index),
    }


RANK_DEF = {
    'evidence': 'evidence_score(own,conc,lg,h2h) if own/conc available else evidence_score(a,b,lg,h2h); NaN -> m_conf',
    'margin_conf': 'conf - inv',
    'agreement': 'count(m_* >= 0 over own,conc,a,b,lg,h2h,sample,conf,model) + 0.001*m_conf (tie-break)',
    'model_margin': 'forecast_p - inv (NaN -> -9)',
    'price_long': '-inv (longest first)',
    'price_short': '+inv (shortest first)',
    'kupon_current': 'log(min(conf,inv)) + log(1.0025)*(one_sided==0 & overround<0.08)',
    'random': 'rank 0, seeds 0..19, mean of per-seed summaries',
}


def pools(d: pd.DataFrame) -> dict[str, pd.Series]:
    ss = pd.to_numeric(d.sample_size, errors='coerce')
    return {
        'all': pd.Series(True, index=d.index),
        'sample8_notlr': (ss >= 8) & (d.forecast_source != 'league_rate'),
        'fbcount_n8': d.count_leg & (np.minimum(d.n_home, d.n_away) >= 8),
        'conf_ge_inv': d.conf.astype(float) >= d.inv,
    }


POOL_DEF = {
    'all': 'all legs',
    'sample8_notlr': 'sample_size >= 8 & forecast_source != "league_rate"',
    'fbcount_n8': 'count_leg & min(n_home, n_away) >= 8',
    'conf_ge_inv': 'conf >= inv',
}

NT = [(1, 1.5), (1, 2.0), (2, 2.0), (2, 3.0), (3, 3.0), (3, 4.0), (4, 4.0)]
ALLW = ('afternoon', 'evening', 'night')
BASE = dict(windows=ALLW, spw=3, mpm=None, one_sport=False)
VARIANTS = {
    'w_afternoon': dict(windows=('afternoon',)),
    'w_evening': dict(windows=('evening',)),
    'w_night': dict(windows=('night',)),
    'spw1': dict(spw=1),
    'one_sport': dict(one_sport=True),
    'mpm1': dict(mpm=1),
}


def get(split):
    if split not in DATA:
        d = b.load(split)
        DATA[split] = (d, rankings(d), pools(d))
    return DATA[split]


def run_one(spec):
    rank, pool, n, t, cfg = spec
    out = {}
    for split in ('dev', 'val'):
        d, R, P = get(split)
        seeds = range(20) if rank == 'random' else [0]
        sums = []
        for sd in seeds:
            s = b.simulate_slips(d, P[pool], R[rank], n, t, windows=cfg['windows'],
                                 slips_per_window=cfg['spw'], max_per_market=cfg['mpm'],
                                 one_sport=cfg['one_sport'], seed=sd)
            sums.append(b.slip_summary(s, seed=sd))
        keys = ['slips', 'days', 'hit', 'mean_product', 'roi_after_tax', 'ci_day_lo', 'ci_day_hi',
                'ci_slip_lo', 'ci_slip_hi']
        res = {}
        for k in keys:
            v = [float(x.get(k, np.nan)) for x in sums]
            res[k] = round(float(np.nanmean(v)), 4) if not all(np.isnan(v)) else np.nan
        res['suspicion'] = (res['slips'] or 0) < 100
        rois = [float(x.get('roi_after_tax', np.nan)) for x in sums]
        if rank == 'random':
            res['roi_seed_sd'] = round(float(np.nanstd(rois)), 2)
            res['roi_seed_min'] = round(float(np.nanmin(rois)), 2)
            res['roi_seed_max'] = round(float(np.nanmax(rois)), 2)
        for k, v in res.items():
            out[f'{split}_{k}'] = v
    return out


def name(rank, pool, n, t, var):
    return f'{rank}|{pool}|n{n}|t{t:g}|{var}'


def row(rank, pool, n, t, var, cfg, res, dim):
    defn = (f'rank={RANK_DEF[rank]}; pool={POOL_DEF[pool]}; n_legs={n}; target={t}; '
            f'windows={list(cfg["windows"])}; slips_per_window={cfg["spw"]}; '
            f'max_per_market={cfg["mpm"]}; one_sport={cfg["one_sport"]}; band_tol=0.15')
    return {'batch': BATCH, 'cell': name(rank, pool, n, t, var), 'dimension': dim,
            'ranking': rank, 'pool': pool, 'n_legs': n, 'target': t, 'variant': var,
            'definition': defn, **res}


def main():
    specs, meta = [], []
    for rank in RANK_DEF:
        for pool in POOL_DEF:
            for n, t in NT:
                specs.append((rank, pool, n, t, BASE))
                meta.append((rank, pool, n, t, 'base', BASE, 'slip_main_grid'))
    with Pool(10) as p:
        res = p.map(run_one, specs, chunksize=1)
    rows = [row(*m[:6], r, m[6]) for m, r in zip(meta, res)]
    df = pd.DataFrame(rows)
    controls = {'random', 'kupon_current', 'price_long', 'price_short'}
    cand = df[~df.ranking.isin(controls) & (df.dev_slips >= 30)].sort_values(
        'dev_roi_after_tax', ascending=False)
    top10 = cand.head(10)
    specs2, meta2 = [], []
    for r in top10.itertuples():
        for vn, vv in VARIANTS.items():
            cfg = {**BASE, **vv}
            specs2.append((r.ranking, r.pool, r.n_legs, r.target, cfg))
            meta2.append((r.ranking, r.pool, r.n_legs, r.target, vn, cfg, 'slip_variant_top10'))
    seen = set()
    for r in top10.itertuples():
        k = (r.pool, r.n_legs, r.target)
        if k in seen:
            continue
        seen.add(k)
        if len(seen) > 5:
            break
        for ctl in ('kupon_current', 'random'):
            for vn, vv in VARIANTS.items():
                cfg = {**BASE, **vv}
                specs2.append((ctl, r.pool, r.n_legs, r.target, cfg))
                meta2.append((ctl, r.pool, r.n_legs, r.target, vn, cfg, 'slip_variant_control'))
    with Pool(10) as p:
        res2 = p.map(run_one, specs2, chunksize=1)
    df2 = pd.DataFrame([row(*m[:6], r, m[6]) for m, r in zip(meta2, res2)])
    out = pd.concat([df, df2], ignore_index=True)
    out = out.drop_duplicates('cell')
    out.to_csv(os.path.join(HERE, 'cells.csv'), index=False)
    print(len(out), 'cells')


if __name__ == '__main__':
    main()
