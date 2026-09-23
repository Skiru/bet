"""Measure what the browser bridge can actually serve, by ramping the rate.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_bridge_capacity.py

Deliberately OUTSIDE `DEFAULT_SEQUENCE`. Run it when the number of tabs
changes, and set `SOFA_TARGET_RPS` from the plateau it reports - never above
it. Above the plateau the only thing that grows is the queue: measured
2026-09-22 with three tabs, asking for 14 req/s delivered the same 3.9 req/s
as asking for 4, and took the bridge round trip from 605 ms to 5,603 ms.

Result on 2026-09-22 with three *visible* sofascore.com windows, 360
requests, zero non-200 and no 403, reproduced twice within 0.03 req/s:

    target  achieved
         2     2.01/s
         4     3.97/s
         6     2.00/s
         8     2.17/s
        10     2.23/s
        14     8.64/s

The shape is bimodal, not a plateau. Below the tabs' own capacity the bucket
starves them: a tab that finishes its job and finds no work goes back into a
/pull (20 s then; 1 s since 663e7102), and pays that cycle to be claimed again. Above
it they stay
saturated and deliver 3 x 2.86 = 8.6 req/s, which is exactly three tabs each
honouring MIN_INTERVAL_MS. So read the PEAK here, and set SOFA_TARGET_RPS
above the tabs' capacity rather than at it.

Worker count, measured separately at target 14: 3 workers 8.62 req/s at p50
357 ms, 6 workers 8.72 at 707 ms, 12 workers 8.59 at 1378 ms, 24 workers
1.88 at 2714 ms. One worker per tab is both the fastest and the cheapest.

Sofascore refused nothing in any of it.

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
import json
import pathlib
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, "src")
from bet.sofa.client import SofascoreClient
from bet.sofa.config import SofaConfig
from bet.sofa.errors import CircuitOpenError, ProviderError

# The steps have to straddle what the tabs can serve, or the ramp measures
# starvation and nothing else. Five windows at MIN_INTERVAL_MS = 350 is
# 5 x 2.86 = 14.3 req/s, so a ramp that stops at 14 sits entirely BELOW the
# ceiling: every step leaves tabs idle between jobs, paying a /pull (20 s then), and
# the run reports a "plateau" that is purely its own starvation. The old fixed
# [2, 4, 6, 8, 10, 14] was fitted to three windows and became misleading the
# moment a fourth was opened.
_TAB_CEILING = SofaConfig().max_concurrency * (1000.0 / 350.0)
# and the ramp starts AT the ceiling, never below it. Below it the tabs idle,
# a job outlives the client deadline, and the step dies on a 504 - so a ramp
# with sub-ceiling steps does not measure a slow bridge, it guarantees its own
# abort. That starvation is documented in CLAUDE.md and does not need
# re-measuring on every run.
STEPS = [max(2, round(_TAB_CEILING * f)) for f in (1.0, 1.4, 2.0, 3.0, 4.0)]
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
abort_reason: list[str] = []

def run_step(rps: int) -> tuple[float, list[float], list[int], float]:
    cfg = SofaConfig(run_id=f"ramp{rps}-{RAMP_STAMP}", target_rps=rps)
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
    # One worker per tab, matching SofaConfig.max_concurrency. More threads
    # than the client's semaphore allows do not add throughput - they queue
    # behind it, and a request that waits there long enough outlives the job
    # deadline and comes back 504, killing the whole step. The instrument was
    # breaking the same rule it exists to measure (min(rps*2, 24) meant 24
    # threads against a semaphore of 5).
    with ThreadPoolExecutor(max_workers=cfg.max_concurrency) as pool:
        list(pool.map(one, range(PER_STEP)))
    el = time.monotonic() - t0
    done = len(statuses)
    return done / el if el else 0, lat, statuses, el

# Every invocation gets its own run_id suffix. Without it a ramp reads back
# every previous ramp's rows too, and a step that ran in 216 ms reports a p90
# of 9,870 ms inherited from a run hours earlier.
RAMP_STAMP = time.strftime("%H%M%S")


def bridge_round_trip_ms(run_id: str) -> list[float]:
    """The browser's own latency, read back from the request log.

    The timer around `client.event_statistics()` spans the token bucket as
    well as the request, and with `max_workers` threads all starting at once
    the bucket wait dominates and is roughly constant. Reporting that as
    latency reads as "every step is equally slow" no matter what the browser
    is doing - on 2026-09-22 it showed a flat ~2,050 ms while the bridge was
    in fact answering in 216 ms, and sent a whole diagnosis the wrong way.

    The log records the round trip alone, which is the number that says
    whether a tab is throttled.
    """
    path = pathlib.Path("runs/sofa/run.log.jsonl")
    if not path.exists():
        return []
    out = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("run_id") == run_id and not row.get("cache_hit"):
                out.append(row["elapsed_ms"])
    return out


print(
    f"{'target':>7s} {'achieved':>9s} {'p50 net':>9s} {'p90 net':>9s} "
    f"{'n':>5s} {'non-200':>8s} {'wall':>7s}"
)
results = []
for rps in STEPS:
    achieved, lat, statuses, el = run_step(rps)
    bad = sum(1 for s in statuses if s != 200)
    net = sorted(bridge_round_trip_ms(f"ramp{rps}-{RAMP_STAMP}"))
    p50 = net[len(net) // 2] if net else 0
    p90 = net[int(len(net) * 0.9)] if net else 0
    print(
        f"{rps:7d} {achieved:8.2f}/s {p50:8.0f}ms {p90:8.0f}ms "
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
