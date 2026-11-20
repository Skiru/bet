"""Step 4: the simulator's walk-forward over the history the sim curves used (2026-06-01 .. 2026-10-20,
data/football_sim_2026-11-06 minute_history.pkl + forecasts.pkl, as fit_football_sim_curves.py reads them),
p of every candidate selection and its outcome from the half-time / 90-minute score."""
import gzip, json, pickle, sys
from datetime import UTC, datetime
from multiprocessing import Pool
from pathlib import Path
sys.path[:0] = ["src", ".", str(Path(__file__).parent)]
from cands import parse

S = Path(sys.argv[1])
CACHE = Path("data/football_sim_2026-11-06")
lo = int(datetime(2026, 6, 1, tzinfo=UTC).timestamp()); hi = int(datetime(2026, 10, 20, tzinfo=UTC).timestamp())
SYN = []
def syn(mn, name, a="A", b="B"):
    got = parse({"marketName": mn, "name": name, "side_a": a, "side_b": b})
    assert got is not None, (mn, name)
    SYN.append(got)
for t in ("A", "B"):
    for s in ("tak", "nie"):
        syn(f"{t} wygra obie połowy", s); syn(f"{t} wygra przynajmniej jedną połowę", s)
for s in ("tak", "nie"):
    syn("Remis w obu połowach", s); syn("Gol w obu połowach", s)
    for L in ("2.5", "3.5", "4.5"):
        syn(f"Obie drużyny strzelą gola & powyżej {L} gola", s)
for h in ("1", "2"):
    for L in (0.5, 1.5, 2.5):
        for t in ("A", "B"):
            syn(f"{h}.połowa - handicap", f"{t} (-{L})"); syn(f"{h}.połowa - handicap", f"{t} ({L})")
    for t in ("A", "B"):
        syn(f"{h}.połowa - zakład bez remisu", t)

def job(item):
    from simcore import joint, p_of
    m, values = item
    j = joint(m.event_id, values)
    if j is None:
        return []
    h1, a1 = m.ht
    h2, a2 = m.ft[0] - h1, m.ft[1] - a1
    if min(h2, a2) < 0:
        return []
    out = []
    for cand, gk, label, held in SYN:
        p = p_of(j, held)
        v = held(h1, a1, h2, a2)
        if p is None or v is None:
            continue
        out.append((m.event_id, m.ts, int(bool(m.women)), cand, gk, label, round(p, 5), int(v)))
    return out

if __name__ == "__main__":
    minutes = pickle.load(open(CACHE / "minute_history.pkl", "rb"))
    fc = pickle.load(open(CACHE / "forecasts.pkl", "rb"))
    items = [(m, fc.get(m.event_id)) for m in minutes if lo <= m.ts < hi and m.ht is not None and fc.get(m.event_id)]
    del minutes, fc
    print("matches", len(items), flush=True)
    n = 0
    with Pool(int(sys.argv[2]) if len(sys.argv) > 2 else 4) as pool, gzip.open(S / "history_rows.jsonl.gz", "wt") as fh:
        for i, rows in enumerate(pool.imap(job, items, chunksize=32)):
            for r in rows:
                fh.write(json.dumps(r) + "\n")
            n += len(rows)
            if (i + 1) % 5000 == 0:
                print(i + 1, n, flush=True)
    print("done", n, flush=True)
