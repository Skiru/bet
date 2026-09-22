"""Measure what the browser bridge can actually serve, by ramping the rate.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_bridge_capacity.py

Deliberately OUTSIDE `DEFAULT_SEQUENCE`. Run it when the number of tabs
changes, and set `SOFA_TARGET_RPS` from the plateau it reports - never above
it. Above the plateau the only thing that grows is the queue: measured
2026-09-22 with three tabs, asking for 14 req/s delivered the same 3.9 req/s
as asking for 4, and took the bridge round trip from 605 ms to 5,603 ms.

Result on 2026-09-22, three tabs, 360 requests, zero non-200 and no 403:

    target  achieved   bridge p50
         2     2.01/s        522ms
         4     3.78/s        605ms
         6     3.87/s       2797ms
         8     3.88/s       3581ms
        10     3.94/s       4920ms
        14     3.93/s       5603ms

Three tabs served 3.9 req/s, not the 8.6 the userscript floor allows, because
the browser throttles hidden tabs - see check_bridge.py. Sofascore refused
nothing.

Not the 2026-09-17 shape: that was ONE curl_cffi client, 100 workers, peaking
at 550 req/s. Here the per-connection pace stays at the userscript's 350 ms
floor and only the number of connections grows, so each tab still looks like a
person with a tab open.

Design constraints, on purpose:
  - distinct URLs throughout. The discredited 2026-09-17 test hit ONE url
    3,000 times, which measured Cloudflare's edge cache, not throttling.
  - 60 requests per step, six steps: 360 total, ~1.4% of a normal run.
  - hard abort on anything that is not 200/404, on a circuit-breaker open,
    or on latency blowing out - and the ramp stops, it does not "retry".
"""
import sqlite3
import statistics as st
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, "src")
from bet.sofa.client import SofascoreClient
from bet.sofa.config import SofaConfig
from bet.sofa.errors import CircuitOpenError, ProviderError

STEPS = [2, 4, 6, 8, 10, 14]
PER_STEP = 60

db = sqlite3.connect("data/sofa.db")
ids: list[int] = [int(r[0]) for r in db.execute(
    "select sofascore_event_id from sofa_event_stats "
    "where statistics_json is not null order by random() limit 600")]
print(f"pool of {len(ids)} distinct event ids\n")

cursor = 0
cursor_lock = threading.Lock()
def next_id() -> int:
    global cursor
    with cursor_lock:
        v: int = ids[cursor % len(ids)]
        cursor += 1
        return v

abort = threading.Event()
abort_reason = []

def run_step(rps: int) -> tuple[float, list[float], list[int], float]:
    cfg = SofaConfig(run_id=f"ramp{rps}", target_rps=rps)
    client = SofascoreClient(cfg)
    lat: list[float] = []
    statuses: list[int] = []
    lock = threading.Lock()

    def one(_: int) -> None:
        if abort.is_set():
            return
        t0 = time.monotonic()
        try:
            client.event_statistics(next_id())
            code = 200
        except CircuitOpenError:
            code = -1
            abort_reason.append("circuit breaker opened")
            abort.set()
        except ProviderError as e:
            code = -2
            abort_reason.append(f"provider refused: {e}")
            abort.set()
        with lock:
            lat.append((time.monotonic() - t0) * 1000)
            statuses.append(code)

    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=min(rps * 2, 24)) as pool:
        list(pool.map(one, range(PER_STEP)))
    el = time.monotonic() - t0
    done = len(statuses)
    return done / el if el else 0, lat, statuses, el

print(
    f"{'target':>7s} {'achieved':>9s} {'p50 lat':>9s} "
    f"{'n':>5s} {'non-200':>8s} {'wall':>7s}"
)
results = []
for rps in STEPS:
    achieved, lat, statuses, el = run_step(rps)
    bad = sum(1 for s in statuses if s != 200)
    p50 = st.median(lat) if lat else 0
    print(
        f"{rps:7d} {achieved:8.2f}/s {p50:8.0f}ms "
        f"{len(statuses):5d} {bad:8d} {el:6.1f}s"
    )
    results.append((rps, achieved))
    if abort.is_set():
        print(f"\nABORTED: {abort_reason[0]}")
        break
    time.sleep(2)

if not abort.is_set():
    peak = max(r[1] for r in results)
    print(f"\npeak sustained: {peak:.2f} req/s over {len(STEPS)} steps, "
          f"{sum(PER_STEP for _ in results)} requests, zero non-200")
