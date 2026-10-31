"""Shared harness of the /kupon redesign backtest (2026-10-31). Read-only.

Every agent of the workflow evaluates its cells through THIS module, so every number
is computed one way:

  load(split)          legs.pkl + signals.pkl, settled-or-refund legs of the split's days,
                       derived columns (inv = 1/odds, signal rates and margins vs inv).
                       The hold-out days are refused unless HOLDOUT_TOKEN matches the hash
                       of frozen_rules.json (written before the one hold-out run).
  leg_cell(df, mask)   n, hit, mean 1/odds, lift = hit - mean(1/odds), band-matched EXCESS
                       (the cell's lift minus the whole split's lift in the same 1/odds
                       band, weighted by the cell's legs - "a good 1.20 vs a bad 1.20"),
                       pre-tax ROI, single after tax, match-bootstrap CIs, one-sided p of
                       excess <= 0.
  simulate_slips(...)  disjoint slips per (day, window) from a ranked pool; pays
                       0.88 x product of the legs' odds (refund leg = 1.00) when every leg
                       wins; ROI per slip with day-cluster bootstrap.

Splits: dev 2026-10-13..10-24, val 10-25..10-28, hold 10-29..10-30.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
TAX = 0.88
LOCAL = ZoneInfo('Europe/Warsaw')
SPLITS = {
    'dev': [f'2026-10-{d:02d}' for d in range(13, 25)],
    'val': [f'2026-10-{d:02d}' for d in range(25, 29)],
    'hold': [f'2026-10-{d:02d}' for d in range(29, 31)],
}
BAND_EDGES = np.arange(0.40, 1.0001, 0.05)  # 1/odds bands for band-matching
WINDOWS = {  # local kickoff hour windows (Europe/Warsaw), end exclusive; night wraps
    'afternoon': (12, 17), 'evening': (17, 21), 'night': (21, 26),
}
B = 1000

_CACHE: dict[str, pd.DataFrame] = {}


def frozen_hash() -> str | None:
    p = f'{HERE}/frozen_rules.json'
    if not os.path.exists(p):
        return None
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def _rate(k, n, min_n):
    k = pd.to_numeric(k, errors='coerce')
    n = pd.to_numeric(n, errors='coerce')
    r = k / n
    return r.where(n >= min_n)


def load(split: str, min_signal_n: int = 5) -> pd.DataFrame:
    """Legs of one split ('dev', 'val', 'hold', or 'devval'), settled (won / lost)
    or refunded, with derived columns."""
    token = frozen_hash()
    if split == 'hold' and (token is None or os.environ.get('HOLDOUT_TOKEN') != token):
        raise RuntimeError('hold-out is run once, after frozen_rules.json; token missing')
    key = f'{split}|{min_signal_n}'
    if key in _CACHE:
        return _CACHE[key].copy()
    days = SPLITS['dev'] + SPLITS['val'] if split == 'devval' else SPLITS[split]
    df = pd.read_pickle(f'{HERE}/legs.pkl')
    df = df[df.day.isin(days) & df.status.isin(['won', 'lost', 'refund'])].copy()
    df = df[df.dec_src == 'legs']  # a leg the reads removed is not on offer to /kupon
    sp = f'{HERE}/signals.pkl'
    if os.path.exists(sp):
        sig = pd.read_pickle(sp)
        df = df.merge(sig, on=['day', 'key'], how='left')
    df['odds'] = df.odds.astype(float)
    df['inv'] = 1.0 / df.odds
    df['won'] = (df.status == 'won').astype(float)
    df['refund'] = (df.status == 'refund')
    df['band'] = pd.cut(df.inv, BAND_EDGES, include_lowest=True).astype(str)
    # local kickoff hour (night window 21..02 -> 21..26)
    ko = pd.to_datetime(df.kickoff, unit='s', utc=True).dt.tz_convert(LOCAL)
    h = ko.dt.hour + ko.dt.minute / 60
    df['ko_local_h'] = np.where(h < 6, h + 24, h)
    # signal rates
    for col in ('own', 'conc', 'a', 'b', 'lg', 'h2h', 'ref'):
        kc, nc = f'{col}_k', f'{col}_n'
        if kc not in df:
            df[kc] = np.nan
            df[nc] = np.nan
    df['r_own'] = _rate(df.own_k, df.own_n, min_signal_n)
    df['r_conc'] = _rate(df.conc_k, df.conc_n, min_signal_n)
    df['r_a'] = _rate(df.a_k, df.a_n, min_signal_n)
    df['r_b'] = _rate(df.b_k, df.b_n, min_signal_n)
    df['r_lg'] = _rate(df.lg_k, df.lg_n, 30)
    df['r_h2h'] = _rate(df.h2h_k, df.h2h_n, 2)
    df['r_ref'] = _rate(df.ref_k, df.ref_n, 8)
    df['r_sample'] = pd.to_numeric(df.sample_hit_rate, errors='coerce').where(
        pd.to_numeric(df.sample_size, errors='coerce') >= min_signal_n)
    df['r_conf'] = df.conf.astype(float)
    df['r_model'] = pd.to_numeric(df.forecast_p, errors='coerce')
    for s in ('own', 'conc', 'a', 'b', 'lg', 'h2h', 'ref', 'sample', 'conf', 'model'):
        df[f'm_{s}'] = df[f'r_{s}'] - df.inv
    # price move: decision vs first print (market against = odds rose), close vs decision
    df['move_first'] = df.odds / pd.to_numeric(df.first_odds, errors='coerce') - 1
    df['move_close'] = pd.to_numeric(df.close_odds, errors='coerce') / df.odds - 1
    # ladder agreement: share of the same variable's rungs (same direction) with conf > inv
    var = ['day', 'eid', 'market', 'subject', 'direction']
    df['_above'] = (df.conf > df.inv).astype(float)
    df['ladder_agree'] = df.groupby(var, dropna=False)['_above'].transform('mean')
    df['ladder_n'] = df.groupby(var, dropna=False)['_above'].transform('size')
    df['count_leg'] = df.metric.notna() if 'metric' in df else False
    _CACHE[key] = df
    return df.copy()


SIGNAL_COLS = ['m_own', 'm_conc', 'm_a', 'm_b', 'm_lg', 'm_h2h', 'm_ref', 'm_sample', 'm_conf', 'm_model']


def evidence(df: pd.DataFrame, signals, rule: str = 'all', margin: float = 0.0, k: int = 1,
             min_avail: int = 1, max_spread: float | None = None) -> pd.Series:
    """Boolean mask of legs whose evidence passes. `signals` names of margin columns
    (m_*, rate - 1/odds). rule: 'all' (every available >= margin), 'k' (>= k available
    above margin), 'mean' (mean of available >= margin). Legs with fewer than
    `min_avail` available signals fail. max_spread: std of the available rates."""
    m = df[list(signals)]
    avail = m.notna().sum(1)
    above = (m >= margin).sum(1)
    if rule == 'all':
        ok = above == avail
    elif rule == 'k':
        ok = above >= k
    elif rule == 'mean':
        ok = m.mean(1) >= margin
    else:
        raise ValueError(rule)
    ok = ok & (avail >= max(min_avail, 1))
    if max_spread is not None:
        ok = ok & (m.std(1).fillna(0) <= max_spread)
    return ok.fillna(False)


def evidence_score(df: pd.DataFrame, signals) -> pd.Series:
    """Mean margin over the available signals (rate - 1/odds)."""
    return df[list(signals)].mean(1)


def _band_lift(df: pd.DataFrame) -> pd.Series:
    s = df[~df.refund]
    return (s.won - s.inv).groupby(s.band).mean()


def leg_cell(df: pd.DataFrame, mask, ref: pd.DataFrame | None = None, seed: int = 0,
             odds_col: str = 'odds') -> dict:
    """Leg metrics of the cell `df[mask]` (refunds out). `ref` = the comparison pool for
    the band-matched excess (default: the whole df)."""
    ref = df if ref is None else ref
    c = df[mask & ~df.refund]
    n = len(c)
    if n == 0:
        return {'n': 0}
    odds = c[odds_col].astype(float)
    inv = 1.0 / odds
    base = _band_lift(ref)
    exp = c.band.map(base).fillna(0.0)
    resid = (c.won - inv) - exp
    roi = c.won * odds - 1
    g = pd.DataFrame({'eid': c.eid.values, 'resid': resid.values, 'roi': roi.values,
                      'won': c.won.values, 'inv': inv.values})
    agg = g.groupby('eid').agg(resid=('resid', 'sum'), roi=('roi', 'sum'), won=('won', 'sum'),
                               inv=('inv', 'sum'), cnt=('won', 'size'))
    rng = np.random.default_rng(seed)
    m = len(agg)
    idx = rng.integers(0, m, (B, m))
    cnt = agg.cnt.values[idx].sum(1)
    bs_ex = agg.resid.values[idx].sum(1) / cnt
    bs_roi = agg.roi.values[idx].sum(1) / cnt
    bs_lift = (agg.won.values[idx].sum(1) - agg.inv.values[idx].sum(1)) / cnt
    ex = resid.mean()
    return {
        'n': n, 'matches': m, 'hit': round(c.won.mean(), 4), 'inv': round(inv.mean(), 4),
        'lift_pp': round((c.won.mean() - inv.mean()) * 100, 2),
        'lift_lo': round(np.percentile(bs_lift, 2.5) * 100, 2),
        'lift_hi': round(np.percentile(bs_lift, 97.5) * 100, 2),
        'excess_pp': round(ex * 100, 2),
        'excess_lo': round(np.percentile(bs_ex, 2.5) * 100, 2),
        'excess_hi': round(np.percentile(bs_ex, 97.5) * 100, 2),
        'p_excess': round(float((bs_ex <= 0).mean()), 4),
        'roi_pre': round(roi.mean() * 100, 2),
        'roi_lo': round(np.percentile(bs_roi, 2.5) * 100, 2),
        'roi_hi': round(np.percentile(bs_roi, 97.5) * 100, 2),
        'single_after_tax': round(((c.won * odds * TAX).mean() - 1) * 100, 2),
        'suspicion': n < 100,
    }


def bh(pvals, q: float = 0.10):
    """Benjamini-Hochberg: boolean list, True = discovery at FDR q."""
    p = np.asarray(pvals, float)
    order = np.argsort(p)
    m = len(p)
    thr = q * (np.arange(1, m + 1)) / m
    passed = p[order] <= thr
    k = np.max(np.nonzero(passed)[0]) + 1 if passed.any() else 0
    out = np.zeros(m, bool)
    out[order[:k]] = True
    return out


def simulate_slips(df: pd.DataFrame, pool_mask, rank: pd.Series, n_legs: int, target: float,
                   windows=('afternoon', 'evening', 'night'), slips_per_window: int = 1,
                   max_per_market: int | None = None, one_sport: bool = False,
                   band_tol: float = 0.15, odds_col: str = 'odds', seed: int = 0,
                   builder: bool = False) -> pd.DataFrame:
    """Disjoint slips: in each (day, window), legs of the pool whose odds lie within
    target**(1/n) x (1 +/- band_tol), one leg per match, taken in descending `rank`
    (ties broken by a seeded shuffle); the last leg must bring the product into
    [target x (1 - band_tol), target x (1 + 2 band_tol)]; up to `slips_per_window` slips of exactly n legs.
    max_per_market caps legs of one market key in a slip; one_sport keeps a slip in the
    sport of its first leg. Returns one row per slip: day, window, legs, product, won,
    payout (0.88 x product when every non-refund leg won, refund legs at 1.00;
    0.90 x product instead of 0.88 when builder=True - Bet Builder: 0.90 x product
    as the brief states)."""
    rng = np.random.default_rng(seed)
    per = target ** (1.0 / n_legs)
    lo, hi = per * (1 - band_tol), per * (1 + band_tol)
    d = df[pool_mask].copy()
    d['_rank'] = rank[pool_mask].astype(float)
    d['_tie'] = rng.random(len(d))
    d = d[(d[odds_col] >= max(lo, 1.01)) & (d[odds_col] <= hi)]
    rows = []
    for (day, win), g in _windows(d, windows):
        g = g.sort_values(['_rank', '_tie'], ascending=[False, False])
        used: set = set()
        for s in range(slips_per_window):
            legs, mk, sport = [], {}, None
            for r in g.itertuples():
                if r.eid in used or any(x.eid == r.eid for x in legs):
                    continue
                if len(legs) == n_legs - 1:
                    prod = float(np.prod([getattr(x, odds_col) for x in legs])) * getattr(r, odds_col)
                    if not target * (1 - band_tol) <= prod <= target * (1 + 2 * band_tol):
                        continue
                if one_sport and sport is not None and r.sport != sport:
                    continue
                if max_per_market is not None and mk.get(r.market, 0) >= max_per_market:
                    continue
                legs.append(r)
                mk[r.market] = mk.get(r.market, 0) + 1
                sport = sport or r.sport
                if len(legs) == n_legs:
                    break
            if len(legs) < n_legs:
                break
            for x in legs:
                used.add(x.eid)
            prod = float(np.prod([getattr(x, odds_col) for x in legs]))
            eff = float(np.prod([1.0 if x.refund else getattr(x, odds_col) for x in legs]))
            win_all = all(x.refund or x.won == 1 for x in legs)
            factor = 0.90 if builder else TAX
            rows.append({'day': day, 'window': win, 'slip': s, 'n_legs': n_legs, 'product': prod,
                         'won': int(win_all), 'payout': factor * eff if win_all else 0.0,
                         'legs': '|'.join(str(x.key) for x in legs)})
    return pd.DataFrame(rows)


def _windows(d: pd.DataFrame, windows):
    for w in windows:
        a, b = WINDOWS[w]
        g = d[(d.ko_local_h >= a) & (d.ko_local_h < b)]
        for day, gg in g.groupby('day'):
            yield (day, w), gg


def slip_summary(slips: pd.DataFrame, seed: int = 0) -> dict:
    if slips is None or len(slips) == 0:
        return {'slips': 0}
    r = slips.payout - 1
    rng = np.random.default_rng(seed)
    days = slips.day.unique()
    by = {dd: r[slips.day == dd].values for dd in days}
    bs = []
    for _ in range(B):
        pick = rng.choice(days, len(days))
        v = np.concatenate([by[x] for x in pick])
        bs.append(v.mean())
    idx = rng.integers(0, len(r), (B, len(r)))
    bs2 = r.values[idx].mean(1)
    return {'slips': len(slips), 'days': len(days), 'hit': round(slips.won.mean(), 4),
            'mean_product': round(slips['product'].mean(), 3),
            'roi_after_tax': round(r.mean() * 100, 2),
            'ci_day_lo': round(np.percentile(bs, 2.5) * 100, 2),
            'ci_day_hi': round(np.percentile(bs, 97.5) * 100, 2),
            'ci_slip_lo': round(np.percentile(bs2, 2.5) * 100, 2),
            'ci_slip_hi': round(np.percentile(bs2, 97.5) * 100, 2),
            'suspicion': len(slips) < 100}


def utc_day_start(day: str) -> float:
    return datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()
