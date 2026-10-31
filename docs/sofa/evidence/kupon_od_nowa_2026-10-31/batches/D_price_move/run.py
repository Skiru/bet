"""Batch D_price_move: price movement (a) first print -> decision, (b) decision -> close re-ask."""
import os
import numpy as np
import pandas as pd
import bt_lib as b

OUT = os.path.dirname(os.path.abspath(__file__))
BATCH = 'D_price_move'
RESULTS = ['result_or_under', 'result_or_over', 'double_chance', 'result_handicap', 'btts_or_over',
           'draw_no_bet', 'result_or_btts', 'dc_and_over', 'result_or_clean_sheet', 'dc_and_under',
           'result_1x2', 'first_goal']

GROUPS = {  # name -> (definition text, function)
    'sport=football': ("sport=='football'", lambda d: d.sport == 'football'),
    'sport=tennis': ("sport=='tennis'", lambda d: d.sport == 'tennis'),
    'sport=hockey': ("sport=='hockey'", lambda d: d.sport == 'hockey'),
    'sport=bb/vb/cs2': ("sport in [basketball,volleyball,cs2]", lambda d: d.sport.isin(['basketball', 'volleyball', 'cs2'])),
    'band=inv<0.75': ("inv<0.75", lambda d: d.inv < 0.75),
    'band=0.75-0.85': ("0.75<=inv<0.85", lambda d: (d.inv >= 0.75) & (d.inv < 0.85)),
    'band=inv>=0.85': ("inv>=0.85", lambda d: d.inv >= 0.85),
    'fam=fb_count': ("count_leg (football metric not null)", lambda d: d.count_leg.astype(bool)),
    'fam=fb_result': ("football & ~count_leg & market in RESULTS", lambda d: (d.sport == 'football') & ~d.count_leg.astype(bool) & d.market.isin(RESULTS)),
    'fam=fb_other': ("football & ~count_leg & market not in RESULTS", lambda d: (d.sport == 'football') & ~d.count_leg.astype(bool) & ~d.market.isin(RESULTS)),
    'fam=tennis': ("sport=='tennis'", lambda d: d.sport == 'tennis'),
    'fam=other_sports': ("sport not in [football,tennis]", lambda d: ~d.sport.isin(['football', 'tennis'])),
    'dir=OVER': ("direction=='OVER'", lambda d: d.direction == 'OVER'),
    'dir=UNDER': ("direction=='UNDER'", lambda d: d.direction == 'UNDER'),
    'dir=other': ("direction not in [OVER,UNDER]", lambda d: ~d.direction.isin(['OVER', 'UNDER'])),
}
POOLS = {
    'Q1_conf>=inv': ("conf>=inv", lambda d: d.conf.astype(float) >= d.inv),
    'Q2_sample>=8': ("sample_size>=8", lambda d: pd.to_numeric(d.sample_size, errors='coerce') >= 8),
    'Q3_own&conc>=inv': ("count_leg & m_own>=0 & m_conc>=0", lambda d: d.count_leg.astype(bool) & (d.m_own >= 0) & (d.m_conc >= 0)),
    'Q4_notleague&sample>0': ("forecast_source!='league_rate' & sample_size>0", lambda d: (d.forecast_source != 'league_rate') & (pd.to_numeric(d.sample_size, errors='coerce') > 0)),
}
TS = [0, 0.01, 0.02, 0.03, 0.05, 0.08]

cells = []  # (cell, dimension, definition, kind, maskfn, kwargs)


def add(cell, dim, definition, fn, kind='leg', close=False, odds_col='odds', slip=None):
    cells.append(dict(cell=cell, dimension=dim, definition=definition, fn=fn, kind=kind,
                      close=close, odds_col=odds_col, slip=slip))


def mf(d):
    return d.move_first


def mc(d):
    return d.move_close


def hasc(d):
    return d.close_odds.notna()


# ---- controls
add('CTRL all', 'control', 'all legs', lambda d: pd.Series(True, index=d.index))
add('CTRL all with close @decision', 'control', 'close_odds notna, odds_col=odds', hasc, close=True)
add('CTRL all with close @close', 'control', 'close_odds notna, odds_col=close_odds', hasc, close=True, odds_col='close_odds')
add('CTRL no first move', 'control', 'move_first==0', lambda d: mf(d) == 0)
for g, (gd, gf) in GROUPS.items():
    add(f'CTRL {g}', 'control', gd, gf)
for p, (pd_, pf) in POOLS.items():
    add(f'CTRL {p}', 'control', pd_, pf)
    add(f'CTRL {p} with close @close', 'control', f'{pd_} & close_odds notna, odds_col=close_odds',
        (lambda pf: lambda d: pf(d) & hasc(d))(pf), close=True, odds_col='close_odds')

# ---- (a) first print -> decision
for t in TS:
    add(f'A keep move_first<={t}', 'a_first_keep', f'move_first<={t} (legs with move_first>{t} dropped)', (lambda t: lambda d: ~(mf(d) > t))(t))
    add(f'A dropped move_first>{t}', 'a_first_dropped', f'move_first>{t} (price rose = market against)', (lambda t: lambda d: mf(d) > t)(t))
    add(f'A shortened move_first<-{t}', 'a_first_shortened', f'move_first<-{t} (price shortened = market with us)', (lambda t: lambda d: mf(d) < -t)(t))
for t in (0, 0.02):
    for g, (gd, gf) in GROUPS.items():
        add(f'A dropped move_first>{t} | {g}', 'a_first_dropped_x', f'move_first>{t} & {gd}', (lambda t, gf: lambda d: (mf(d) > t) & gf(d))(t, gf))
        add(f'A shortened move_first<-{t} | {g}', 'a_first_shortened_x', f'move_first<-{t} & {gd}', (lambda t, gf: lambda d: (mf(d) < -t) & gf(d))(t, gf))
for p, (pd_, pf) in POOLS.items():
    for t in (0, 0.01, 0.02, 0.05):
        add(f'A keep move_first<={t} | {p}', 'a_first_keep_q', f'~(move_first>{t}) & {pd_}', (lambda t, pf: lambda d: ~(mf(d) > t) & pf(d))(t, pf))
        add(f'A dropped move_first>{t} | {p}', 'a_first_dropped_q', f'move_first>{t} & {pd_}', (lambda t, pf: lambda d: (mf(d) > t) & pf(d))(t, pf))

# ---- (b) decision -> close (re-ask before serving); kept legs at the CLOSE price
for t in TS:
    add(f'B keep move_close<={t} @close', 'b_close_keep', f'close_odds notna & move_close<={t}, odds_col=close_odds',
        (lambda t: lambda d: hasc(d) & (mc(d) <= t))(t), close=True, odds_col='close_odds')
    add(f'B dropped move_close>{t} @decision', 'b_close_dropped', f'move_close>{t}, odds_col=odds (what the dropped legs would have done)',
        (lambda t: lambda d: mc(d) > t)(t), close=True)
    add(f'B shortened move_close<-{t} @close', 'b_close_shortened', f'move_close<-{t}, odds_col=close_odds',
        (lambda t: lambda d: mc(d) < -t)(t), close=True, odds_col='close_odds')
for t in (0, 0.02):
    for g, (gd, gf) in GROUPS.items():
        add(f'B keep move_close<={t} @close | {g}', 'b_close_keep_x', f'close_odds notna & move_close<={t} & {gd}, odds_col=close_odds',
            (lambda t, gf: lambda d: hasc(d) & (mc(d) <= t) & gf(d))(t, gf), close=True, odds_col='close_odds')
        add(f'B dropped move_close>{t} @decision | {g}', 'b_close_dropped_x', f'move_close>{t} & {gd}, odds_col=odds',
            (lambda t, gf: lambda d: (mc(d) > t) & gf(d))(t, gf), close=True)
for p, (pd_, pf) in POOLS.items():
    for t in (0, 0.02):
        add(f'B keep move_close<={t} @close | {p}', 'b_close_keep_q', f'close_odds notna & move_close<={t} & {pd_}, odds_col=close_odds',
            (lambda t, pf: lambda d: hasc(d) & (mc(d) <= t) & pf(d))(t, pf), close=True, odds_col='close_odds')
        add(f'B dropped move_close>{t} @decision | {p}', 'b_close_dropped_q', f'move_close>{t} & {pd_}, odds_col=odds',
            (lambda t, pf: lambda d: (mc(d) > t) & pf(d))(t, pf), close=True)

# ---- (a)+(b) combined
for t in (0, 0.02):
    add(f'AB keep first<={t} & close<={t} @close', 'ab_keep', f'close_odds notna & ~(move_first>{t}) & move_close<={t}, odds_col=close_odds',
        (lambda t: lambda d: hasc(d) & ~(mf(d) > t) & (mc(d) <= t))(t), close=True, odds_col='close_odds')
    add(f'AB against both first>{t} & close>{t} @decision', 'ab_against', f'move_first>{t} & move_close>{t}, odds_col=odds',
        (lambda t: lambda d: (mf(d) > t) & (mc(d) > t))(t), close=True)

# ---- slips (2 legs, pool Q1 conf>=inv, rank conf-inv): no filter vs move filters
for tgt in (1.5, 2.0):
    add(f'SLIP 2leg t{tgt} Q1 nofilter @decision', 'slip', f'pool conf>=inv, rank conf-inv, n_legs=2, target={tgt}',
        POOLS['Q1_conf>=inv'][1], kind='slip', slip=dict(n_legs=2, target=tgt))
    add(f'SLIP 2leg t{tgt} Q1 first<=0 @decision', 'slip', f'pool conf>=inv & ~(move_first>0), rank conf-inv, n_legs=2, target={tgt}',
        lambda d: POOLS['Q1_conf>=inv'][1](d) & ~(mf(d) > 0), kind='slip', slip=dict(n_legs=2, target=tgt))
    add(f'SLIP 2leg t{tgt} Q1 with close @close', 'slip', f'pool conf>=inv & close notna, odds_col=close_odds, n_legs=2, target={tgt}',
        lambda d: POOLS['Q1_conf>=inv'][1](d) & hasc(d), kind='slip', slip=dict(n_legs=2, target=tgt), odds_col='close_odds')
    add(f'SLIP 2leg t{tgt} Q1 close<=0 @close', 'slip', f'pool conf>=inv & close notna & move_close<=0, odds_col=close_odds, n_legs=2, target={tgt}',
        lambda d: POOLS['Q1_conf>=inv'][1](d) & hasc(d) & (mc(d) <= 0), kind='slip', slip=dict(n_legs=2, target=tgt), odds_col='close_odds')


def run():
    rows = []
    data = {s: b.load(s) for s in ('dev', 'val')}
    for c in cells:
        row = dict(batch=BATCH, cell=c['cell'], dimension=c['dimension'], definition=c['definition'])
        for s, d in data.items():
            m = c['fn'](d).fillna(False).astype(bool)
            if c['kind'] == 'slip':
                rank = d.conf.astype(float) - 1.0 / d[c['odds_col']].astype(float)
                sl = b.simulate_slips(d, m, rank, odds_col=c['odds_col'], **c['slip'])
                res = b.slip_summary(sl)
            else:
                res = b.leg_cell(d, m, odds_col=c['odds_col'])
                if c['close']:
                    r2 = b.leg_cell(d, m, ref=d[d.close_odds.notna()], odds_col=c['odds_col'])
                    for k in ('excess_pp', 'excess_lo', 'excess_hi', 'p_excess'):
                        res[f'cref_{k}'] = r2.get(k)
            for k, v in res.items():
                row[f'{s}_{k}'] = v
        rows.append(row)
    out = pd.DataFrame(rows)
    out.to_csv(f'{OUT}/cells.csv', index=False)
    print(len(out))


if __name__ == '__main__':
    run()
