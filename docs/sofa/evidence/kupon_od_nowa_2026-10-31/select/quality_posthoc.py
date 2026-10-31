"""Quality-filter cells for the implementation (after the one hold-out run: hold numbers POST HOC)."""
import sys; sys.path.insert(0, '.')
import bt_lib as L
for split in ('dev', 'val', 'hold'):
    d = L.load(split); ss = d.sample_size.fillna(0)
    cells = {
     'sample>=8': ss >= 8, 'sample 0': ss == 0, 'sample 1..7 (micro)': (ss >= 1) & (ss < 8),
     'sample>=8 & own rate>=1/odds': (ss >= 8) & (d.sample_hit_rate >= d.inv),
     'sample>=8 & own rate<1/odds': (ss >= 8) & (d.sample_hit_rate < d.inv),
     'fb count: both sides >= 1/odds (own&conc or a&b)': ((d.r_own >= d.inv) & (d.r_conc >= d.inv)) | ((d.r_a >= d.inv) & (d.r_b >= d.inv)),
     'fb count: a side below 1/odds': ((d.r_own < d.inv) | (d.r_conc < d.inv)) | ((d.r_a < d.inv) | (d.r_b < d.inv)),
     'player legs (subject person, one-sided)': (d.one_sided == 1) & d.market.str.startswith('player'),
    }
    for k, m in cells.items():
        x = L.leg_cell(d, m)
        print(f"{split:4} {k:50} n={x['n']:6} excess={x['excess_pp']:+.2f} [{x['excess_lo']:+.2f},{x['excess_hi']:+.2f}] roi_pre={x['roi_pre']:+.2f}")
