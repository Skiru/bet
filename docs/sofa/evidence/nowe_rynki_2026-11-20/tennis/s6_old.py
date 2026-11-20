"""Step 6: the same keys on the OLD (two-sided) format: settled Superbet lines
(sofa_settled_row, run_date 10-17..11-19) with the point model's p - backfill
(data/line_evidence/tennis_point_model_p.json.gz) for days before 11-06, the
row's p_central from 11-06 (SHEET under TENNIS_POINT_MODEL). Output
old_pairs.jsonl: one row per OVER line with both prices."""
import json, sqlite3, sys, gzip, collections
sys.path.insert(0, 'src')
from bet.sofa.tennis_point_curves import backfill_key
from bet.sofa.tennis_point_model import SERVE_MARKETS
D = sys.argv[1]
bf = json.load(gzip.open('data/line_evidence/tennis_point_model_p.json.gz', 'rt'))
conn = sqlite3.connect('file:data/sofa.db?mode=ro', uri=True)
rows = conn.execute(
    "SELECT run_date, sofascore_event_id, market, subject, line, direction, p_central, offered_odds, outcome, actual_value "
    "FROM sofa_settled_row WHERE run_date >= '2026-10-17' AND run_date <= '2026-11-19' AND sport='tennis'").fetchall()
by = {}
for rd, sid, m, subj, line, d, pc, odds, out, val in rows:
    if m not in SERVE_MARKETS or out not in ('WIN', 'LOSS'):
        continue
    by[(rd, sid, m, subj, line, d)] = (pc, odds, out, val)
n_src = collections.Counter()
outf = open(f'{D}/old_pairs.jsonl', 'w')
for (rd, sid, m, subj, line, d), (pc, odds, out, val) in by.items():
    if d != 'OVER':
        continue
    u = by.get((rd, sid, m, subj, line, 'UNDER'))
    if rd < '2026-11-06':
        p = bf.get(backfill_key(rd, sid, m, subj, line, 'OVER')); src = 'backfill'
    else:
        p = pc; src = 'p_central'
    if p is None:
        n_src['no_p'] += 1; continue
    n_src[src] += 1
    outf.write(json.dumps(dict(day=rd, sid=sid, metric=m, subject=subj, line=line, p=p, over_odds=odds,
                               under_odds=u[1] if u else None, y=1 if out == 'WIN' else 0, value=val)) + '\n')
print(n_src)
