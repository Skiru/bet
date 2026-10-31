"""Independent recompute of B_evidence_fb top cells (no bt_lib import)."""
import numpy as np, pandas as pd
H = '/Users/mkoziol/projects/bet/data/kupon_redesign_2026-10-31'
DEV = [f'2026-10-{d:02d}' for d in range(13, 25)]
VAL = [f'2026-10-{d:02d}' for d in range(25, 29)]
legs = pd.read_pickle(f'{H}/legs.pkl')
legs = legs[legs.day.isin(DEV + VAL)].copy()  # hold-out rows dropped immediately, never used
sig = pd.read_pickle(f'{H}/signals.pkl')
sig = sig[sig.day.isin(DEV + VAL)]
assert not sig.duplicated(['day', 'key']).any()
legs = legs[legs.status.isin(['won', 'lost', 'refund']) & (legs.dec_src == 'legs')]
df = legs.merge(sig, on=['day', 'key'], how='left')
df['odds'] = df.odds.astype(float); df['inv'] = 1 / df.odds
df['W'] = (df.status == 'won').astype(float); df['R'] = df.status == 'refund'
def rate(k, n, mn):
    k = pd.to_numeric(df[k], errors='coerce'); n = pd.to_numeric(df[n], errors='coerce')
    return (k / n).where(n >= mn)
for c, mn in [('own', 5), ('conc', 5), ('a', 5), ('b', 5), ('lg', 30), ('h2h', 2), ('ref', 8)]:
    if f'{c}_k' not in df: df[f'{c}_k'] = np.nan; df[f'{c}_n'] = np.nan
    df['m_' + c] = rate(f'{c}_k', f'{c}_n', mn) - df.inv
fb = df.metric.notna() & (df.sport == 'football')
met = df.metric.fillna('')
fam = met.str.replace(r'_(1h|2h)', '', regex=True).str.replace(r'_(for|total|against)$', '', regex=True)
fam = fam.replace({'cards_points': 'cards', 'red_cards': 'cards', 'fouls': 'cards', 'shots_on_target': 'shots',
                   'penalties': 'other', 'offsides': 'other', 'goal_kicks': 'other'})
df['fam'] = np.where(fb, fam, ''); df['half'] = np.where(fb & met.str.contains('_1h|_2h'), 'half', 'full')
df['fb'] = fb
# bands: edges 0.40..1.00 step .05, include_lowest; outside -> NaN band -> expectation 0
edges = np.round(np.arange(0.40, 1.0001, 0.05), 10)
df['band'] = pd.cut(df.inv, edges, include_lowest=True).astype(str)

def ev(d, cols, rule, margin, k=1, min_avail=1):
    m = d[cols]; avail = m.notna().sum(1); above = (m >= margin).sum(1)
    ok = (above == avail) if rule == 'all' else (above >= k)
    return ok & (avail >= min_avail)

CELLS = {
    'x_oclh_k3_m0.05__half_half': lambda d: d.fb & ev(d, ['m_own', 'm_conc', 'm_lg', 'm_h2h'], 'k', 0.05, k=3, min_avail=3) & (d.half == 'half'),
    'x_ablh_all_m0.05_a2__fam_corners': lambda d: d.fb & ev(d, ['m_a', 'm_b', 'm_lg', 'm_h2h'], 'all', 0.05, min_avail=2) & (d.fam == 'corners'),
    'x_indep_all_m0.05_a3__fam_corners': lambda d: d.fb & ev(d, ['m_own', 'm_a', 'm_conc', 'm_b', 'm_lg', 'm_h2h', 'm_ref'], 'all', 0.05, min_avail=3) & (d.fam == 'corners'),
}
out = []
for split, days in (('dev', DEV), ('val', VAL)):
    d = df[df.day.isin(days)]
    s = d[~d.R]
    base = (s.W - s.inv).groupby(s.band).mean()
    for name, fn in CELLS.items():
        c = d[fn(d) & ~d.R]
        exp = c.band.map(base).fillna(0)
        resid = c.W - c.inv - exp
        out.append(dict(cell=name, split=split, n=len(c), matches=c.eid.nunique(), hit=round(c.W.mean(), 4),
                        inv=round(c.inv.mean(), 4), lift_pp=round((c.W.mean() - c.inv.mean()) * 100, 2),
                        excess_pp=round(resid.mean() * 100, 2), roi_pre=round((c.W * c.odds - 1).mean() * 100, 2),
                        single_after_tax=round((c.W * c.odds * 0.88 - 1).mean() * 100, 2),
                        n_days=c.day.nunique(), max_day_share=round(c.day.value_counts(normalize=True).max(), 3),
                        max_match_legs=int(c.eid.value_counts().max())))
r = pd.DataFrame(out)
r.to_csv(f'{H}/batches/B_evidence_fb/verify/recomputed.csv', index=False)
pd.set_option('display.width', 250); print(r.to_string())
