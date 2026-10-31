"""Batch B_evidence_fb: evidence rules for football count legs (metric not null).
Every number from bt_lib.leg_cell; reference pool = the whole split (all sports)."""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import bt_lib as b  # noqa: E402

BATCH = 'B_evidence_fb'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cells.csv')

FB = "count_leg & sport=='football'"


def prep(df):
    df = df.copy()
    df['fb'] = df.count_leg.astype(bool) & (df.sport == 'football')
    met = df.metric.fillna('')
    fam = met.str.replace(r'_(1h|2h)', '', regex=True).str.replace(r'_(for|total|against)$', '', regex=True)
    fam = fam.replace({'cards_points': 'cards', 'red_cards': 'cards', 'fouls': 'cards',
                       'shots_on_target': 'shots', 'penalties': 'other', 'offsides': 'other',
                       'goal_kicks': 'other'})
    df['fam'] = np.where(df.fb, fam, '')
    jt = df.joint.fillna(0).astype(float) == 1
    df['legtype'] = np.where(~df.fb, '', np.where(jt, 'joint', np.where(met.str.endswith('_for'), 'side', 'total')))
    df['half'] = np.where(~df.fb, '', np.where(met.str.contains('_1h|_2h'), 'half', 'full'))
    return df


SPLITS = {}


def data(split, msn=5):
    k = (split, msn)
    if k not in SPLITS:
        SPLITS[k] = prep(b.load(split, min_signal_n=msn))
    return SPLITS[k]


SETS = {
    'oc': ['m_own', 'm_conc'],
    'ocl': ['m_own', 'm_conc', 'm_lg'],
    'oclh': ['m_own', 'm_conc', 'm_lg', 'm_h2h'],
    'ab': ['m_a', 'm_b'],
    'abl': ['m_a', 'm_b', 'm_lg'],
    'ablh': ['m_a', 'm_b', 'm_lg', 'm_h2h'],
    'ablr': ['m_a', 'm_b', 'm_lg', 'm_ref'],          # cards / fouls only
    'cmocl': ['m_conf', 'm_model', 'm_own', 'm_conc', 'm_lg'],
    'indep': ['m_own', 'm_a', 'm_conc', 'm_b', 'm_lg', 'm_h2h', 'm_ref'],
}
SET_EXTRA = {'ablr': "fam=='cards'"}

cells = []  # (cell, dimension, definition, mask_fn(df)->Series, msn)


def add(cell, dim, definition, fn, msn=5):
    cells.append((cell, dim, definition, fn, msn))


def base(df, extra=None):
    m = df.fb
    if extra:
        m = m & df.eval(extra)
    return m


# ---- controls -------------------------------------------------------------
add('ctl_fb_count_all', 'control', FB, lambda d: base(d))
for dr in ('OVER', 'UNDER'):
    add(f'ctl_dir_{dr}', 'control', f"{FB} & direction=='{dr}'", lambda d, dr=dr: base(d) & (d.direction == dr))
for fam in ('goals', 'corners', 'cards', 'shots', 'saves', 'other'):
    add(f'ctl_fam_{fam}', 'control', f"{FB} & fam=='{fam}'", lambda d, f=fam: base(d) & (d.fam == f))
for lt in ('side', 'total', 'joint'):
    add(f'ctl_type_{lt}', 'control', f"{FB} & legtype=='{lt}'", lambda d, t=lt: base(d) & (d.legtype == t))
for h in ('full', 'half'):
    add(f'ctl_half_{h}', 'control', f"{FB} & half=='{h}'", lambda d, h=h: base(d) & (d.half == h))
add('ctl_conf_ge_inv', 'control', f"{FB} & m_conf>=0", lambda d: base(d) & (d.m_conf >= 0))
add('ctl_conf_lt_inv', 'control', f"{FB} & m_conf<0", lambda d: base(d) & (d.m_conf < 0))
add('ctl_low_overround', 'control', f"{FB} & overround<0.06", lambda d: base(d) & (pd.to_numeric(d.overround, errors='coerce') < 0.06))

# ---- single signals --------------------------------------------------------
for s in ('own', 'conc', 'a', 'b', 'lg', 'h2h', 'ref', 'sample', 'conf', 'model'):
    col = f'm_{s}'
    for mg in (0.0, 0.05, 0.10):
        add(f'single_{s}_ge{mg:.2f}', 'single', f"{FB} & {col}>={mg}", lambda d, c=col, mg=mg: base(d) & (d[c] >= mg))
    for mg in (0.0, -0.05, -0.10):
        add(f'single_{s}_lt{mg:+.2f}', 'single_below', f"{FB} & {col}<{mg}", lambda d, c=col, mg=mg: base(d) & (d[c] < mg))

# ---- evidence rules per signal set ----------------------------------------
def ev(sig, extra, **kw):
    return lambda d: base(d, extra) & b.evidence(d, sig, **kw)


for name, sig in SETS.items():
    extra = SET_EXTRA.get(name)
    pre = f"{FB}" + (f" & {extra}" if extra else '')
    size = len(sig)
    mins = [m for m in (2, 3, 4) if m <= size]
    for mg in (0.0, 0.02, 0.05, 0.10):
        for ma in mins:
            add(f'{name}_all_m{mg:.2f}_a{ma}', 'evidence_all',
                f"{pre} & evidence({sig}, rule='all', margin={mg}, min_avail={ma})", ev(sig, extra, rule='all', margin=mg, min_avail=ma))
    for k in (2, 3, 4):
        if k > size:
            continue
        for mg in (0.0, 0.05):
            add(f'{name}_k{k}_m{mg:.2f}', 'evidence_k',
                f"{pre} & evidence({sig}, rule='k', k={k}, margin={mg}, min_avail={k})", ev(sig, extra, rule='k', k=k, margin=mg, min_avail=k))
    for mg in (0.0, 0.02, 0.05, 0.10):
        add(f'{name}_mean_m{mg:.2f}', 'evidence_mean',
            f"{pre} & evidence({sig}, rule='mean', margin={mg}, min_avail=2)", ev(sig, extra, rule='mean', margin=mg, min_avail=2))
    for sp in (0.10, 0.15, 0.20):
        add(f'{name}_all0_sp{sp:.2f}', 'evidence_spread',
            f"{pre} & evidence({sig}, rule='all', margin=0, min_avail=2, max_spread={sp})", ev(sig, extra, rule='all', margin=0.0, min_avail=2, max_spread=sp))
    # opposite: evidence below the price
    add(f'{name}_allbelow', 'evidence_below',
        f"{pre} & every available of {sig} < 0, min_avail=2",
        lambda d, sig=sig, extra=extra: base(d, extra) & (d[sig].notna().sum(axis=1) >= 2) & ((d[sig] < 0) | d[sig].isna()).all(axis=1))
    for mg in (0.0, -0.05):
        add(f'{name}_meanbelow{mg:+.2f}', 'evidence_below',
            f"{pre} & mean({sig}) < {mg}, min_avail=2",
            lambda d, sig=sig, extra=extra, mg=mg: base(d, extra) & (d[sig].notna().sum(axis=1) >= 2) & (d[sig].mean(axis=1) < mg))

# ---- minimal signal sample size (subset) ------------------------------------
for msn in (8, 10):
    for name in ('oc', 'ocl', 'ab', 'abl', 'indep'):
        sig = SETS[name]
        for mg in (0.0, 0.05):
            add(f'n{msn}_{name}_all_m{mg:.2f}', 'min_signal_n',
                f"load(min_signal_n={msn}); {FB} & evidence({sig}, rule='all', margin={mg}, min_avail=2)",
                ev(sig, None, rule='all', margin=mg, min_avail=2), msn)
        add(f'n{msn}_{name}_mean_m0.05', 'min_signal_n',
            f"load(min_signal_n={msn}); {FB} & evidence({sig}, rule='mean', margin=0.05, min_avail=2)",
            ev(sig, None, rule='mean', margin=0.05, min_avail=2), msn)
    for s in ('own', 'conc', 'a', 'b', 'sample'):
        add(f'n{msn}_single_{s}_ge0.05', 'min_signal_n', f"load(min_signal_n={msn}); {FB} & m_{s}>=0.05",
            lambda d, c=f'm_{s}': base(d) & (d[c] >= 0.05), msn)


def evaluate(cell, dim, definition, fn, msn):
    row = {'batch': BATCH, 'cell': cell, 'dimension': dim, 'definition': definition}
    for split in ('dev', 'val'):
        d = data(split, msn)
        r = b.leg_cell(d, fn(d).fillna(False).astype(bool))
        for k, v in r.items():
            row[f'{split}_{k}'] = v
    return row


rows = [evaluate(*c) for c in cells]

# ---- crosses: best evidence rules by DEV excess (n >= 300) x direction / family / leg type
res = pd.DataFrame(rows)
ev_rows = res[res.dimension.str.startswith('evidence_') & (res.dimension != 'evidence_below') & (res.dev_n >= 300)]
top = ev_rows.sort_values('dev_excess_pp', ascending=False).head(5)
cmap = {c[0]: c for c in cells}
for cn in top.cell:
    _, _, definition, fn, msn = cmap[cn]
    subs = [(f'dir_{x}', f"direction=='{x}'", lambda d, x=x: d.direction == x) for x in ('OVER', 'UNDER')]
    subs += [(f'fam_{x}', f"fam=='{x}'", lambda d, x=x: d.fam == x) for x in ('goals', 'corners', 'cards', 'shots', 'saves', 'other')]
    subs += [(f'type_{x}', f"legtype=='{x}'", lambda d, x=x: d.legtype == x) for x in ('side', 'total', 'joint')]
    subs += [(f'half_{x}', f"half=='{x}'", lambda d, x=x: d.half == x) for x in ('full', 'half')]
    subs += [(f'{dr}_{fm}', f"direction=='{dr}' & fam=='{fm}'", lambda d, dr=dr, fm=fm: (d.direction == dr) & (d.fam == fm))
             for dr in ('OVER', 'UNDER') for fm in ('goals', 'corners')]
    for sn, sdef, sfn in subs:
        r = evaluate(f'x_{cn}__{sn}', 'cross', f'{definition} & {sdef}',
                     lambda d, fn=fn, sfn=sfn: fn(d) & sfn(d), msn)
        if r.get('dev_n', 0) > 0 or r.get('val_n', 0) > 0:  # empty by construction: dropped
            rows.append(r)

out = pd.DataFrame(rows)
out.to_csv(OUT, index=False)
print(len(out), 'cells ->', OUT)
