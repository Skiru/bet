"""Slip grid for the frozen-candidate choice (main session): candidate leg pools x slip
configs on dev and val, controls on the same days. Pools / rules named as in PROTOCOL.md."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, '..'); sys.path.insert(0, '.')
import bt_lib as L

def pools(d):
    lr = (d.forecast_source == 'league_rate')
    keep = ~(d.move_close > 0.02)  # NaN close = kept (no re-ask record)
    return {
        'ALL': d.sport.notna(),
        'ALL_move': keep,
        'L1_league_rate': lr,
        'L1_move': lr & keep,
        'L2_lr_conf_below': lr & (d.conf < d.inv),
        'Q2_sample8': d.sample_size >= 8,
        'Q2_move': (d.sample_size >= 8) & keep,
    }

def ranks(d):
    return {'current': np.log(np.minimum(d.conf, d.inv)) + np.where((d.one_sided == 0) & (d.overround < 0.08), np.log(1.0025), 0),
            'margin_conf': d.conf - d.inv, 'random': pd.Series(0.0, index=d.index)}

rows = []
for split in ('dev', 'val'):
    d = L.load(split)
    P, R = pools(d), ranks(d)
    for pn, pm in P.items():
        for rn, r in R.items():
            for n, t in ((1, 1.3), (1, 1.5), (2, 1.5), (2, 2.0), (3, 2.0), (3, 3.0)):
                seeds = range(20) if rn == 'random' else (0,)
                ss = [L.simulate_slips(d, pm, r, n, t, slips_per_window=3, seed=s) for s in seeds]
                s = pd.concat(ss) if rn == 'random' else ss[0]
                out = L.slip_summary(s)
                rows.append({'split': split, 'pool': pn, 'rank': rn, 'n_legs': n, 'target': t, **out})
g = pd.DataFrame(rows)
w = g.pivot_table(index=['pool', 'rank', 'n_legs', 'target'], columns='split',
                  values=['slips', 'hit', 'roi_after_tax', 'ci_day_lo', 'ci_day_hi'])
w.columns = [f'{b}_{a}' for a, b in w.columns]
w = w.reset_index()
w.to_csv('select/slip_grid.csv', index=False)
pd.set_option('display.width', 250)
print(w.sort_values('val_roi_after_tax', ascending=False).to_string())
