"""Batch C_evidence_other: dimension 2 (evidence) for every leg NOT covered by football
count signals (~count_leg): tennis, hockey, basketball, volleyball, CS2, football
results / score / player legs. Every number from bt_lib.leg_cell / simulate_slips /
slip_summary. Reference for the excess = the whole split (bt_lib default)."""
import os
import numpy as np
import pandas as pd
import bt_lib as bt

OUT = os.path.dirname(os.path.abspath(__file__))
BATCH = 'C_evidence_other'
D = {s: bt.load(s) for s in ('dev', 'val')}

FB_RESULT = ['result_or_under', 'result_or_over', 'double_chance', 'result_handicap',
             'btts_or_over', 'draw_no_bet', 'result_or_btts', 'dc_and_over',
             'result_or_clean_sheet', 'dc_and_under', 'result_1x2']

# universes: name -> expression on df (string, evaluated as python with df=x)
UNI = {
    'pooled': "~x.count_leg",
    'fb_noncount': "~x.count_leg & (x.sport=='football')",
    'fb_result': "~x.count_leg & (x.sport=='football') & x.market.isin(FB_RESULT)",
    'fb_player': "~x.count_leg & (x.sport=='football') & x.market.str.startswith('player_')",
    'fb_other': "~x.count_leg & (x.sport=='football') & ~x.market.isin(FB_RESULT) & ~x.market.str.startswith('player_')",
    'tennis': "~x.count_leg & (x.sport=='tennis')",
    'hockey': "~x.count_leg & (x.sport=='hockey')",
    'basketball': "~x.count_leg & (x.sport=='basketball')",
    'volleyball': "~x.count_leg & (x.sport=='volleyball')",
    'cs2': "~x.count_leg & (x.sport=='cs2')",
}
SRC = ['league_rate']  # football_rating ~ fb_noncount, score_model ~ hockey+bb+vb, tennis_rating ~ tennis, cs2_engine = cs2
FULL_UNI = {'pooled', 'fb_noncount', 'tennis', 'hockey'}
for s in SRC:
    UNI[f'src_{s}'] = f"~x.count_leg & (x.forecast_source=='{s}')"

AGREE = ['m_conf', 'm_model', 'm_sample']

# signals: name -> (dimension, expression)
SIG = {
    'all': ('control', "True"),
    'conf_ge_0': ('conf_vs_inv', "x.m_conf>=0"),
    'conf_ge_05': ('conf_vs_inv', "x.m_conf>=0.05"),
    'conf_ge_10': ('conf_vs_inv', "x.m_conf>=0.10"),
    'conf_below': ('conf_vs_inv', "x.m_conf<0"),
    'conf_below_05': ('conf_vs_inv', "x.m_conf<-0.05"),
    'fp_ge_0': ('forecast_p_vs_inv', "x.m_model>=0"),
    'fp_ge_05': ('forecast_p_vs_inv', "x.m_model>=0.05"),
    'fp_ge_10': ('forecast_p_vs_inv', "x.m_model>=0.10"),
    'fp_below': ('forecast_p_vs_inv', "x.m_model<0"),
    'mp_ge_0': ('model_p_vs_inv', "(pd.to_numeric(x.model_p,errors='coerce')-x.inv)>=0"),
    'mp_ge_05': ('model_p_vs_inv', "(pd.to_numeric(x.model_p,errors='coerce')-x.inv)>=0.05"),
    'mp_below': ('model_p_vs_inv', "(pd.to_numeric(x.model_p,errors='coerce')-x.inv)<0"),
    'samp8_ge_0': ('sample_vs_inv', "(x.sample_size>=8)&((x.sample_hit_rate-x.inv)>=0)"),
    'samp10_ge_0': ('sample_vs_inv', "(x.sample_size>=10)&((x.sample_hit_rate-x.inv)>=0)"),
    'samp15_ge_0': ('sample_vs_inv', "(x.sample_size>=15)&((x.sample_hit_rate-x.inv)>=0)"),
    'samp10_ge_05': ('sample_vs_inv', "(x.sample_size>=10)&((x.sample_hit_rate-x.inv)>=0.05)"),
    'samp10_ge_10': ('sample_vs_inv', "(x.sample_size>=10)&((x.sample_hit_rate-x.inv)>=0.10)"),
    'samp10_below': ('sample_vs_inv', "(x.sample_size>=10)&((x.sample_hit_rate-x.inv)<0)"),
    'agree_all3': ('agreement', "bt.evidence(x, AGREE, 'all', 0.0, min_avail=3)"),
    'agree_2of3': ('agreement', "bt.evidence(x, AGREE, 'k', 0.0, k=2, min_avail=3)"),
    'agree_mean_ge_0': ('agreement', "bt.evidence(x, AGREE, 'mean', 0.0, min_avail=2)"),
    'agree_mean_ge_05': ('agreement', "bt.evidence(x, AGREE, 'mean', 0.05, min_avail=2)"),
    'agree_none_above': ('agreement', "bt.evidence(x, AGREE, 'all', -9, min_avail=2) & ~bt.evidence(x, AGREE, 'k', 0.0, k=1, min_avail=2)"),
    'ladder_ge50_n2': ('ladder', "(x.ladder_agree>=0.5)&(x.ladder_n>=2)"),
    'ladder_ge75_n2': ('ladder', "(x.ladder_agree>=0.75)&(x.ladder_n>=2)"),
    'ladder_eq1_n2': ('ladder', "(x.ladder_agree>=1.0)&(x.ladder_n>=2)"),
    'ladder_eq1_n3': ('ladder', "(x.ladder_agree>=1.0)&(x.ladder_n>=3)"),
    'ladder_eq0_n2': ('ladder', "(x.ladder_agree==0)&(x.ladder_n>=2)"),
    'caln_lt300': ('calibration_n', "x.calibration_n<300"),
    'caln_ge1000': ('calibration_n', "x.calibration_n>=1000"),
    'caln_ge5000': ('calibration_n', "x.calibration_n>=5000"),
    'lineoff_set': ('line_evidence', "x.line_offset.notna()"),
    'lineoff_null': ('line_evidence', "x.line_offset.isna()"),
    'bandcap_set': ('line_evidence', "x.price_band_cap.notna()"),
    'one_sided': ('one_sided', "x.one_sided.astype(int)==1"),
    'two_sided': ('one_sided', "x.one_sided.astype(int)==0"),
    'ctx_none': ('context', "x.context_flags.fillna('')==''"),
    'ctx_congested': ('context', "x.context_flags.fillna('').str.contains('CONGESTED')"),
    'ctx_layoff': ('context', "x.context_flags.fillna('').str.contains('LONG_LAYOFF')"),
    'ctx_makeup': ('context', "x.context_flags.fillna('').str.contains('MAKEUP_FIXTURE')"),
    'price_gap_flag': ('price_gap', "x.price_gap.astype(float)>0"),
    'peer_pref': ('peer', "x.peer_pref.astype(float)>0"),
}
# signals that are meaningless in some universes (empty by construction) are skipped
SPORT_SKIP = {
    'mp_ge_0', 'mp_ge_05', 'mp_below',  # model_p only football / tennis
}
CORE_SRC = ['all', 'conf_ge_0', 'conf_ge_05', 'conf_ge_10', 'conf_below', 'fp_ge_0', 'fp_ge_05',
            'fp_below', 'mp_ge_0', 'samp10_ge_0', 'samp10_ge_05', 'agree_2of3', 'agree_mean_ge_0',
            'ladder_ge75_n2', 'ladder_eq0_n2', 'caln_ge1000', 'lineoff_set', 'lineoff_null',
            'one_sided']
POOLED_ONLY = {'price_gap_flag', 'peer_pref'}
CTX = {'ctx_none', 'ctx_congested', 'ctx_layoff', 'ctx_makeup'}


def mask(x, uexpr, sexpr):
    m = eval(uexpr, {'x': x, 'pd': pd, 'bt': bt, 'FB_RESULT': FB_RESULT, 'AGREE': AGREE})
    s = eval(sexpr, {'x': x, 'pd': pd, 'bt': bt, 'np': np, 'AGREE': AGREE})
    if s is True:
        return pd.Series(m, index=x.index).fillna(False).astype(bool)
    return (m & s).fillna(False).astype(bool)


rows = []


def add(cell, dim, definition, uexpr, sexpr, extra_dev=None, extra_val=None):
    r = {'batch': BATCH, 'cell': cell, 'dimension': dim,
         'definition': f'universe: {uexpr} ; signal: {sexpr}'}
    for sp, x in D.items():
        res = bt.leg_cell(x, mask(x, uexpr, sexpr))
        for k, v in res.items():
            r[f'{sp}_{k}'] = v
    if r.get('dev_n', 0) == 0 and r.get('val_n', 0) == 0:
        return None
    rows.append(r)
    return r


for u, ue in UNI.items():
    is_src = u.startswith('src_')
    for s, (dim, se) in SIG.items():
        if (is_src or u not in FULL_UNI) and s not in CORE_SRC:
            continue
        if s in POOLED_ONLY and u != 'pooled':
            continue
        if s == 'bandcap_set' and u not in ('pooled', 'fb_noncount'):
            continue
        if s in CTX and u not in ('pooled', 'fb_noncount'):
            continue
        if s in SPORT_SKIP and u in ('hockey', 'basketball', 'volleyball', 'cs2', 'meas_sports'):
            continue
        if s.startswith('samp') and u in ('fb_noncount', 'fb_result', 'fb_other', 'fb_player', 'cs2'):
            continue  # football non-count / CS2 legs carry no sample (median size 0)
        if s.startswith('agree') and u in ('fb_result', 'fb_other', 'cs2'):
            continue
        add(f'{u}|{s}', dim if s != 'all' else 'control', se, ue, se)

# crosses: the best dev cells (n >= 300, signal cells only) x price band and direction
base = pd.DataFrame(rows)
cand = base[(base.dimension != 'control') & (base.dev_n >= 300)].sort_values('dev_excess_pp', ascending=False)
BANDS = {'inv_lt75': "(x.inv<0.75)", 'inv_75_85': "(x.inv>=0.75)&(x.inv<0.85)",
         'inv_85_90': "(x.inv>=0.85)&(x.inv<0.90)", 'inv_ge90': "(x.inv>=0.90)"}
DIRS = {'OVER': "(x.direction=='OVER')", 'UNDER': "(x.direction=='UNDER')",
        'other_dir': "~x.direction.isin(['OVER','UNDER'])"}
seen = set()
top = []
for c in cand.itertuples():
    if c.cell in seen:
        continue
    top.append(c)
    seen.add(c.cell)
    if len(top) == 5:
        break
for c in top:
    u, s = c.cell.split('|')
    ue, se = UNI[u], SIG[s][1]
    for bn, be in BANDS.items():
        add(f'{c.cell}|{bn}', 'cross_band', se, ue, f'({se})&{be}' if se != 'True' else be)
        add(f'{u}|all|{bn}', 'control', be, ue, be) if not any(r['cell'] == f'{u}|all|{bn}' for r in rows) else None
    for dn, de in DIRS.items():
        add(f'{c.cell}|{dn}', 'cross_dir', se, ue, f'({se})&{de}')
        add(f'{u}|all|{dn}', 'control', de, ue, de) if not any(r['cell'] == f'{u}|all|{dn}' for r in rows) else None

# random control: a seeded 50% of pooled non-count legs
for sp, x in D.items():
    x['_rand'] = np.random.default_rng(7).random(len(x)) < 0.5
add('pooled|random50', 'control', 'random 50% (seed 7)', UNI['pooled'], "x._rand")

# slip cells: 2-leg slips, rank by conf margin, pool = best 3 dev cells vs pooled baseline / conf
SLIPS = [(2, 1.8), (2, 3.0), (3, 3.0)]
slip_pools = [('pooled|all', UNI['pooled'], 'True')] + [(c.cell, UNI[c.cell.split('|')[0]], SIG[c.cell.split('|')[1]][1]) for c in top[:3]]
for name, ue, se in slip_pools:
    for nl, tg in SLIPS:
        for rk in (('m_conf', 'random') if name == 'pooled|all' else ('m_conf',)):
            r = {'batch': BATCH, 'cell': f'slip|{name}|{nl}legs@{tg}|rank_{rk}', 'dimension': 'slip',
                 'definition': f'simulate_slips(pool=universe {ue} & signal {se}, rank={rk}, n_legs={nl}, target={tg}, windows all, 1 slip/window)'}
            for sp, x in D.items():
                m = mask(x, ue, se)
                rank = x.m_conf if rk == 'm_conf' else pd.Series(0.0, index=x.index)
                sl = bt.simulate_slips(x, m, rank, nl, tg)
                for k, v in bt.slip_summary(sl).items():
                    r[f'{sp}_{k}'] = v
            rows.append(r)

out = pd.DataFrame(rows)
out.to_csv(f'{OUT}/cells.csv', index=False)
print(len(out), 'cells;', (out.dimension != 'slip').sum(), 'leg cells')
