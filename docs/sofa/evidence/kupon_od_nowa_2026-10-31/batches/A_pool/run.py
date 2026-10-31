"""Batch A_pool: leg cells by the POOL dimension (source, sample, sport, family,
direction, main/side rung, price band, ladder margin) and two-way crossings.
Every number from bt_lib.leg_cell. Re-run:
PYTHONPATH=<repo>/src:<redesign dir> .venv/bin/python batches/A_pool/run.py"""
import os
import re
import numpy as np
import pandas as pd
import bt_lib as bt

OUT = os.path.dirname(os.path.abspath(__file__))
BATCH = 'A_pool'

FAMILY_DOC = (
    "football: goals=goals_*|both_over_goals*|first_goal; corners=corners_*|both_over_corners|most_corners; "
    "shots_on_target=shots_on_target_*|both_over_shots_on_target|most_shots_on_target; shots=shots_*|both_over_shots; "
    "fouls=fouls_*|both_over_fouls; cards=cards_points*|both_over_cards_points|handicap_cards_points|red_cards*; "
    "penalties=penalties_*; offsides=offsides_*; throw_ins=*throw_ins*; goal_kicks=*goal_kicks*; tackles=*tackles* (non-player); "
    "saves=saves_*|both_over_saves; results=result_*|double_chance|draw_no_bet|btts*|dc_and_*|winner|match_won_for|*handicap (non-cards); "
    "player=player_*; tennis: tennis_games=games_*|tiebreaks_total; tennis_sets=set*|sets_total|match_won_for; tennis_serve=aces_for|double_faults_for; "
    "hockey: player=player_*; hockey_periods=period_*; hockey_game=other; basketball: basketball_points=all; "
    "volleyball: volleyball_sets=all; cs2: cs2_rounds=map_rounds_*|map_team_rounds; cs2_maps=maps_handicap|team_maps|match_winner; cs2_kills=*kills*")


def family(market: str, sport: str) -> str:
    m = market or ''
    if m.startswith('player_'):
        return 'player'
    if sport == 'tennis':
        if m in ('aces_for', 'double_faults_for'):
            return 'tennis_serve'
        if m.startswith('games_') or m == 'tiebreaks_total':
            return 'tennis_games'
        return 'tennis_sets'
    if sport == 'hockey':
        return 'hockey_periods' if m.startswith('period_') else 'hockey_game'
    if sport == 'basketball':
        return 'basketball_points'
    if sport == 'volleyball':
        return 'volleyball_sets'
    if sport == 'cs2':
        if 'kills' in m:
            return 'cs2_kills'
        return 'cs2_rounds' if 'rounds' in m else 'cs2_maps'
    # football
    if 'cards' in m:
        return 'cards'
    for k in ('shots_on_target', 'corners', 'goals', 'penalties', 'offsides', 'throw_ins',
              'goal_kicks', 'tackles', 'saves', 'fouls'):
        if k in m:
            return k
    if 'shots' in m:
        return 'shots'
    if m == 'first_goal':
        return 'goals'
    if (m.startswith('result') or m in ('double_chance', 'draw_no_bet', 'winner', 'match_won_for')
            or m.startswith('btts') or m.startswith('dc_and') or 'handicap' in m):
        return 'results'
    return 'other'


def prep(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['fam'] = [family(m, s) for m, s in zip(df.market, df.sport)]
    df['src'] = df.forecast_source.fillna('null')
    var = ['day', 'eid', 'market', 'subject']
    d = (df.inv - 0.5).abs()
    df['_d'] = d
    imin = df.groupby(var, dropna=False)['_d'].transform('min')
    df['is_main'] = df._d == imin
    omin = df.groupby(var, dropna=False)['odds'].transform('min')
    df['is_shortest'] = df.odds == omin
    df['var_n'] = df.groupby(var, dropna=False)['odds'].transform('size')
    df['ss'] = pd.to_numeric(df.sample_size, errors='coerce').fillna(0)
    df['nmin'] = df[['n_home', 'n_away']].min(axis=1)
    df['pband'] = pd.cut(df.odds, [1.0, 1.20, 1.35, 1.55, 1.80, 2.20, 99],
                         labels=['1.10-1.20', '1.20-1.35', '1.35-1.55', '1.55-1.80', '1.80-2.20', '>2.20'],
                         right=False).astype(str)
    df['mband'] = np.select(
        [df.one_sided == 1, df.overround < 0.05, df.overround < 0.08, df.overround < 0.12, df.overround <= 0.15],
        ['one_sided', '<0.05', '0.05-0.08', '0.08-0.12', '0.12-0.15'], 'other')
    df['dir2'] = np.where(df.direction.isin(['OVER', 'UNDER']), df.direction, 'other')
    df['rnd'] = (pd.util.hash_pandas_object(df.key.astype(str), index=False) % 1000).astype(int)
    df['rnd_m'] = (pd.util.hash_pandas_object(df.eid.astype(str), index=False) % 1000).astype(int)
    return df


def cells(df):
    """(name, dimension, definition, mask-fn) list."""
    C = []

    def add(name, dim, defin, fn):
        C.append((name, dim, defin, fn))

    # controls
    add('ctrl:all', 'control', 'all legs (excess 0 by construction)', lambda x: pd.Series(True, x.index))
    for k in (500, 250, 100):
        add(f'ctrl:rand_leg_{k/10:.0f}pct', 'control', f'hash(key)%1000 < {k}', lambda x, k=k: x.rnd < k)
        add(f'ctrl:rand_match_{k/10:.0f}pct', 'control', f'hash(eid)%1000 < {k}', lambda x, k=k: x.rnd_m < k)
    add('ctrl:conf_above_inv', 'control', 'conf > inv', lambda x: x.conf > x.inv)
    add('ctrl:conf_below_inv', 'control', 'conf <= inv', lambda x: x.conf <= x.inv)

    srcs = ['football_rating', 'tennis_rating', 'score_model', 'cs2_engine', 'player_model', 'league_rate', 'null']
    sports = ['football', 'tennis', 'hockey', 'basketball', 'volleyball', 'cs2']
    fams = ['goals', 'corners', 'shots', 'shots_on_target', 'fouls', 'cards', 'penalties', 'offsides', 'throw_ins',
            'goal_kicks', 'tackles', 'saves', 'results', 'player', 'tennis_games', 'tennis_sets', 'tennis_serve',
            'hockey_periods', 'hockey_game', 'basketball_points', 'volleyball_sets', 'cs2_maps', 'cs2_rounds', 'cs2_kills']
    pbands = ['1.10-1.20', '1.20-1.35', '1.35-1.55', '1.55-1.80', '1.80-2.20', '>2.20']
    mbands = ['<0.05', '0.05-0.08', '0.08-0.12', '0.12-0.15', 'one_sided']
    sizes = [5, 8, 10, 15]
    nmins = [5, 8, 10]

    # singles
    for s in srcs:
        add(f'src={s}', 'forecast_source', f"forecast_source.fillna('null')=='{s}'", lambda x, s=s: x.src == s)
    add('ss==0', 'min_sample', 'sample_size==0', lambda x: x.ss == 0)
    add('ss>0', 'min_sample', 'sample_size>0', lambda x: x.ss > 0)
    for k in sizes:
        add(f'ss>={k}', 'min_sample', f'sample_size>={k}', lambda x, k=k: x.ss >= k)
        add(f'ss<{k}', 'min_sample', f'sample_size<{k}', lambda x, k=k: x.ss < k)
    add('ss==20', 'min_sample', 'sample_size==20', lambda x: x.ss == 20)
    add('count_leg', 'min_sample', 'football count leg (metric notna)', lambda x: x.count_leg)
    for k in nmins:
        add(f'count&nmin>={k}', 'min_sample', f'count_leg & min(n_home,n_away)>={k}', lambda x, k=k: x.count_leg & (x.nmin >= k))
        add(f'count&nmin<{k}', 'min_sample', f'count_leg & min(n_home,n_away)<{k}', lambda x, k=k: x.count_leg & (x.nmin < k))
    for s in sports:
        add(f'sport={s}', 'sport', f"sport=='{s}'", lambda x, s=s: x.sport == s)
    for f in fams:
        add(f'fam={f}', 'family', f"fam=='{f}' [{'mapping in run.py family()'}]", lambda x, f=f: x.fam == f)
    add('fam=results_combo', 'family', "market.str.startswith('result_or_')|market.str.startswith('dc_and_')|btts_or_over",
        lambda x: x.market.str.startswith('result_or_') | x.market.str.startswith('dc_and_') | (x.market == 'btts_or_over'))
    add('fam=results_pure', 'family', "fam=='results' & not combo",
        lambda x: (x.fam == 'results') & ~(x.market.str.startswith('result_or_') | x.market.str.startswith('dc_and_') | (x.market == 'btts_or_over')))
    add('fam=joint_both_over', 'family', "market.str.startswith('both_over_')", lambda x: x.market.str.startswith('both_over_'))
    add('fam=half_markets', 'family', "football & market matches _1h_|_2h_", lambda x: (x.sport == 'football') & x.market.str.contains('_1h|_2h', regex=True))
    for dname in ('OVER', 'UNDER', 'other'):
        add(f'dir={dname}', 'direction', f"direction=='{dname}' (other = T1/T2/1X/X2/YES/NO)", lambda x, d=dname: x.dir2 == d)
    add('rung=main', 'rung', 'inv closest to 0.5 within (day,eid,market,subject)', lambda x: x.is_main)
    add('rung=side', 'rung', 'not main', lambda x: ~x.is_main)
    add('rung=shortest', 'rung', 'lowest odds within (day,eid,market,subject)', lambda x: x.is_shortest)
    add('rung=not_shortest', 'rung', 'not shortest', lambda x: ~x.is_shortest)
    add('rung=single_rung_var', 'rung', 'variable has 1 printed rung', lambda x: x.var_n == 1)
    add('rung=multi_rung_var', 'rung', 'variable has >=3 printed rungs', lambda x: x.var_n >= 3)
    for p in pbands:
        add(f'odds={p}', 'price_band', f'odds in [{p}) (1.10-1.20 includes <1.10)', lambda x, p=p: x.pband == p)
    for mb in mbands:
        add(f'margin={mb}', 'ladder_margin', f"overround bin {mb} (one_sided==1 separately)", lambda x, mb=mb: x.mband == mb)

    # operator's micro-sample cases
    add('micro:league_rate', 'micro_sample', "forecast_source=='league_rate'", lambda x: x.src == 'league_rate')
    add('micro:player&ss==0', 'micro_sample', "fam=='player' & sample_size==0", lambda x: (x.fam == 'player') & (x.ss == 0))
    add('micro:player&ss>0', 'micro_sample', "fam=='player' & sample_size>0", lambda x: (x.fam == 'player') & (x.ss > 0))
    add('micro:player&ss>=10', 'micro_sample', "fam=='player' & sample_size>=10", lambda x: (x.fam == 'player') & (x.ss >= 10))
    add('micro:football_player&ss==0', 'micro_sample', "sport=='football' & fam=='player' & ss==0",
        lambda x: (x.sport == 'football') & (x.fam == 'player') & (x.ss == 0))
    add('micro:hockey_player&ss==0', 'micro_sample', "sport=='hockey' & fam=='player' & ss==0",
        lambda x: (x.sport == 'hockey') & (x.fam == 'player') & (x.ss == 0))
    add('micro:fb_rating&ss==0', 'micro_sample', "src=='football_rating' & ss==0", lambda x: (x.src == 'football_rating') & (x.ss == 0))
    add('micro:fb_rating&ss>0', 'micro_sample', "src=='football_rating' & ss>0", lambda x: (x.src == 'football_rating') & (x.ss > 0))
    add('micro:ss in 1..7', 'micro_sample', 'sample_size between 1 and 7', lambda x: (x.ss >= 1) & (x.ss <= 7))
    add('micro:league_rate&odds<1.35', 'micro_sample', "league_rate & odds<1.35", lambda x: (x.src == 'league_rate') & (x.odds < 1.35))
    add('micro:league_rate&UNDER', 'micro_sample', "league_rate & UNDER", lambda x: (x.src == 'league_rate') & (x.dir2 == 'UNDER'))

    # crossings
    for f in fams + ['results_combo']:
        fm = (lambda x, f=f: x.fam == f) if f != 'results_combo' else \
            (lambda x: x.market.str.startswith('result_or_') | x.market.str.startswith('dc_and_') | (x.market == 'btts_or_over'))
        for dname in ('OVER', 'UNDER'):
            add(f'fam={f}&dir={dname}', 'family x direction', f"fam=='{f}' & direction=='{dname}'",
                lambda x, fm=fm, d=dname: fm(x) & (x.dir2 == d))
        for k in (0, 5, 10, 15):
            if k == 0:
                add(f'fam={f}&ss==0', 'family x min_sample', f"fam=='{f}' & sample_size==0", lambda x, fm=fm: fm(x) & (x.ss == 0))
            else:
                add(f'fam={f}&ss>={k}', 'family x min_sample', f"fam=='{f}' & sample_size>={k}", lambda x, fm=fm, k=k: fm(x) & (x.ss >= k))
        add(f'fam={f}&main', 'family x rung', f"fam=='{f}' & is_main", lambda x, fm=fm: fm(x) & x.is_main)
        add(f'fam={f}&side', 'family x rung', f"fam=='{f}' & ~is_main", lambda x, fm=fm: fm(x) & ~x.is_main)
        add(f'fam={f}&one_sided', 'family x margin', f"fam=='{f}' & one_sided==1", lambda x, fm=fm: fm(x) & (x.one_sided == 1))
        add(f'fam={f}&margin<0.08', 'family x margin', f"fam=='{f}' & one_sided==0 & overround<0.08",
            lambda x, fm=fm: fm(x) & (x.one_sided == 0) & (x.overround < 0.08))
        add(f'fam={f}&margin>=0.08', 'family x margin', f"fam=='{f}' & one_sided==0 & overround>=0.08",
            lambda x, fm=fm: fm(x) & (x.one_sided == 0) & (x.overround >= 0.08))
    for f in ('goals', 'corners', 'shots', 'shots_on_target', 'fouls', 'cards', 'offsides', 'saves'):
        for k in nmins:
            add(f'fam={f}&count&nmin>={k}', 'family x min_sample', f"fam=='{f}' & count_leg & min(n_home,n_away)>={k}",
                lambda x, f=f, k=k: (x.fam == f) & x.count_leg & (x.nmin >= k))
    for s in srcs:
        for p in pbands:
            add(f'src={s}&odds={p}', 'source x price_band', f"src=='{s}' & pband=='{p}'", lambda x, s=s, p=p: (x.src == s) & (x.pband == p))
    for s in sports:
        for p in pbands:
            add(f'sport={s}&odds={p}', 'sport x price_band', f"sport=='{s}' & pband=='{p}'", lambda x, s=s, p=p: (x.sport == s) & (x.pband == p))
    for dname in ('OVER', 'UNDER'):
        for p in pbands:
            add(f'dir={dname}&odds={p}', 'direction x price_band', f"direction=='{dname}' & pband=='{p}'",
                lambda x, d=dname, p=p: (x.dir2 == d) & (x.pband == p))
        add(f'dir={dname}&main', 'direction x rung', f"direction=='{dname}' & is_main", lambda x, d=dname: (x.dir2 == d) & x.is_main)
        add(f'dir={dname}&side', 'direction x rung', f"direction=='{dname}' & ~is_main", lambda x, d=dname: (x.dir2 == d) & ~x.is_main)
    for mb in mbands:
        for p in pbands:
            add(f'margin={mb}&odds={p}', 'margin x price_band', f"mband=='{mb}' & pband=='{p}'",
                lambda x, mb=mb, p=p: (x.mband == mb) & (x.pband == p))
    for k in sizes:
        for s in ('football_rating', 'tennis_rating', 'score_model', 'null'):
            add(f'src={s}&ss>={k}', 'source x min_sample', f"src=='{s}' & sample_size>={k}", lambda x, s=s, k=k: (x.src == s) & (x.ss >= k))
    return C


def main():
    data = {sp: prep(bt.load(sp)) for sp in ('dev', 'val')}
    rows = []
    for name, dim, defin, fn in cells(data['dev']):
        row = {'batch': BATCH, 'cell': name, 'dimension': dim, 'definition': defin}
        tot = 0
        for sp, df in data.items():
            r = bt.leg_cell(df, fn(df).fillna(False).astype(bool))
            tot += r.get('n', 0)
            for k, v in r.items():
                row[f'{sp}_{k}'] = v
        if tot == 0:
            continue
        rows.append(row)
    out = pd.DataFrame(rows)
    out.loc[out.dimension == 'family', 'definition'] += ' | ' + FAMILY_DOC
    thin = (out.dev_n.fillna(0) < 30) & (out.val_n.fillna(0) < 30)
    out[thin].to_csv(f'{OUT}/thin_cells.csv', index=False)  # both splits n<30: kept apart, not in cells.csv
    out[~thin].to_csv(f'{OUT}/cells.csv', index=False)
    print(len(out[~thin]), 'cells;', int(thin.sum()), 'thin cells apart')


if __name__ == '__main__':
    main()
