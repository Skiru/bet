"""The ONE hold-out run (10-29..10-30) of frozen_rules.json. Leg rules, P1, slips, controls."""
import json, sys, numpy as np, pandas as pd
sys.path.insert(0, '.')
import bt_lib as L
out = {}
for split in ('dev', 'val', 'hold'):
    d = L.load(split)
    lr = d.forecast_source == 'league_rate'
    keep = ~(d.move_close > 0.02)
    cl = d.close_odds.notna()
    r = {
      'ALL': L.leg_cell(d, d.sport.notna()),
      'L1_league_rate': L.leg_cell(d, lr),
      'L2_lr_conf_below': L.leg_cell(d, lr & (d.conf < d.inv)),
      'P1_dropped_at_coupon_price': L.leg_cell(d, d.move_close > 0.02),
      'P1_kept_at_close_price': L.leg_cell(d, cl & keep, ref=d[cl], odds_col='close_odds'),
      'P1_all_with_close_at_close_price': L.leg_cell(d, cl, ref=d[cl], odds_col='close_odds'),
    }
    cur = np.log(np.minimum(d.conf, d.inv)) + np.where((d.one_sided == 0) & (d.overround < 0.08), np.log(1.0025), 0)
    zero = pd.Series(0.0, index=d.index)
    def rnd(pool, n, t):
        return L.slip_summary(pd.concat([L.simulate_slips(d, pool, zero, n, t, slips_per_window=3, seed=s) for s in range(20)]))
    r['S1_protocol_pick'] = rnd(lr, 3, 3.0)
    r['S2_L1_two_legs'] = L.slip_summary(L.simulate_slips(d, lr & keep, cur, 2, 1.5, slips_per_window=3))
    r['C1_current_kupon'] = L.slip_summary(L.simulate_slips(d, d.sport.notna(), cur, 2, 2.0, slips_per_window=3))
    r['C2_random_two'] = rnd(d.sport.notna(), 2, 2.0)
    r['C3_random_single'] = rnd(d.sport.notna(), 1, 1.5)
    out[split] = r
def clean(o):
    if isinstance(o, dict): return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (np.floating, np.integer)): return o.item()
    if isinstance(o, np.bool_): return bool(o)
    return o
json.dump(clean(out), open('select/holdout_result.json', 'w'), indent=1)
for name in out['hold']:
    print(name)
    for s in ('dev', 'val', 'hold'):
        x = out[s][name]
        if 'excess_pp' in x:
            print(f"  {s:4} n={x['n']:6} hit={x['hit']:.3f} inv={x['inv']:.3f} excess={x['excess_pp']:+.2f} [{x['excess_lo']:+.2f},{x['excess_hi']:+.2f}] roi_pre={x['roi_pre']:+.2f} single_tax={x['single_after_tax']:+.2f}")
        else:
            print(f"  {s:4} slips={x.get('slips')} hit={x.get('hit')} roi_tax={x.get('roi_after_tax')} day[{x.get('ci_day_lo')},{x.get('ci_day_hi')}] slip[{x.get('ci_slip_lo')},{x.get('ci_slip_hi')}]")
