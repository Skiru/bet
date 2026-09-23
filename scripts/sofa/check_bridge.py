"""Is the browser bridge alive, and does it actually reach Sofascore?

    python scripts/sofa/check_bridge.py

Checks four things in order, and says which one broke:
  1. the bridge server is listening
  2. a browser tab is polling it
  3. a real /api/v1/ request comes back 200 with JSON
  4. the bridge serves a concurrent burst at a usable rate
"""

from __future__ import annotations

import json
import sys
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen

sys.path.insert(0, "src")

from bet.sofa.bridge_transport import (  # noqa: E402
    DEFAULT_BRIDGE_URL,
    BrowserBridgeTransport,
)
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.errors import ProviderError, TransportError  # noqa: E402

PROBE_URL = "https://api.sofascore.com/api/v1/sport/football/events/live"

# A healthy bridge round trip is ~175 ms, measured over 15,949 requests. A tab
# the browser has throttled answers the *same routes* in ~1,997 ms, and the
# only signal today is that the run takes four times as long for no stated
# reason. Confirmed not to be Sofascore and not to be the clock: hour 21 UTC
# contains both modes on different runs (161 ms vs 1,997 ms), and one overnight
# run paid the slow mode on 10,544 requests - about 5.3 hours.
#
# The threshold sits well above the fast mode's p99 and well below the slow
# mode's p10 (1,889 ms), so it cannot fire on ordinary variance.
# This is CONNECTIVITY, not capacity, and the distinction is load-bearing.
#
# A short burst from idle cannot reach the regime a run works in. Measured
# 2026-09-22 with three visible windows and PULL_WAIT_S = 20 s: the bridge
# sustained 8.64 req/s over 360 requests once the tabs were saturated, but a
# tab that finished a job and found nothing waiting went back into a 20 s
# /pull and paid that cycle to be claimed again, so four probes from idle read
# 0.10-0.20 req/s. PULL_WAIT_S is 1 s since 663e7102, which shortens the cycle
# but does not make an idle burst a capacity reading.
#
# This check therefore REPORTS the number and refuses to grade it. Earlier
# versions graded it and cried wolf on a healthy bridge, which is worse than
# saying nothing - CLAUDE.md runs this first.
# A saturated tab serves one request per MIN_INTERVAL_MS = 350 ms, and
# capacity comes from windows, never from a faster tab (CLAUDE.md). Measured:
# 3 windows 8.64 req/s (2026-09-22), 5 windows 11.67 (2026-09-22) and
# 14.4-14.8 (2026-09-23, after PULL_WAIT_S 20 -> 1).
PER_WINDOW_RPS = 1000.0 / 350.0
BURST_SAMPLES = 4
# The fast/slow split, measured over 80,964 live requests (740b5d3f): fast mode
# p50 175 ms, slow mode p10 1,889 / p50 1,997 ms. 600 ms sits above the
# userscript's own 350 ms pacing floor - so a healthy back-to-back tab is never
# called throttled - and far below the slow mode's p10.
#
# This is graded on the MINIMUM round trip inside the concurrent burst, and
# both halves of that matter. Sequentially, a probe from idle pays the /pull
# cycle to be claimed (20 s when this was written, 1 s since 663e7102), so it
# measures the poll window and not the tab; grading that is what made this
# preflight FAIL on a healthy bridge and got the whole check deleted in
# 7318e08a. Inside the burst the tabs are already
# awake, and the minimum drops the probe that queued behind a busy tab
# (BURST_SAMPLES exceeds max_concurrency, so one always does).
HEALTHY_ROUND_TRIP_MS = 600.0

# The FIRST request after a quiet period is not a latency measurement, it is a
# poll cycle. The userscript long-polls /pull for PULL_WAIT_S (20 s until
# 2026-09-23, 1 s since - see bridge_server.py); a job
# submitted while every tab sits between polls waits for the next one. Measured
# 2026-09-22 on a bridge that was provably healthy: single requests from idle
# took 20.1 s, 20.1 s and 40.1 s - exact multiples of the poll window - while
# twelve concurrent jobs finished in 2.6 s at 4.56 req/s, minimum latency
# 0.2 s, all 200.
#
# So this preflight must wake the loop before it measures, and must allow a
# cold first request more than one poll cycle before calling the bridge dead.
# It did neither, which made a healthy-but-idle bridge report FAIL - and
# CLAUDE.md says to run this first, so that FAIL would stop a day that had
# nothing wrong with it.
COLD_PROBE_TIMEOUT_S = 60.0


def main() -> int:
    base = DEFAULT_BRIDGE_URL

    try:
        with urlopen(base + "/health", timeout=5) as r:
            health = json.loads(r.read().decode("utf-8"))
    except URLError as e:
        print(f"FAIL  bridge server not listening on {base} ({e})")
        print("      start it:  python scripts/sofa/bridge_server.py")
        print("      it dies with the terminal that launched it, so for a")
        print("      long run detach it:  nohup ... &")
        return 1
    print(f"OK    bridge server listening on {base}")

    age = health.get("last_pull_age_s")
    if age is None:
        print("FAIL  no browser tab has ever polled the bridge")
        print("      open https://www.sofascore.com/ with the userscript installed")
        return 1
    if age > 30:
        print(f"WARN  last browser poll was {age}s ago — tab may be closed or asleep")
    else:
        print(f"OK    browser tab polling (last poll {age}s ago)")

    # This one doubles as the warm-up, so it gets the cold timeout.
    try:
        resp = BrowserBridgeTransport().get(PROBE_URL, timeout=COLD_PROBE_TIMEOUT_S)
    except (ProviderError, TransportError) as e:
        # TransportError, not just ProviderError. The bridge answers 504 when
        # no tab claims the job, and `bridge_transport.get` raises
        # TransportError for that - which is not a ProviderError, so this
        # preflight used to die with a traceback instead of the diagnosis it
        # exists to print.
        print(f"FAIL  bridge could not serve the request: {e}")
        print(f"      no answer in {COLD_PROBE_TIMEOUT_S:.0f}s. Either no tab")
        print("      claimed the job, or a tab claimed it and its /push is stuck")
        print("      (health 'pending: 0' after this means it WAS claimed). A stuck")
        print("      /push was a long /pull holding the only connection to")
        print("      127.0.0.1 (2026-09-23) - is bridge_server.py's PULL_WAIT_S short?")
        return 1

    if resp.status_code != 200:
        print(f"FAIL  Sofascore answered {resp.status_code}: {resp.text[:120]}")
        if resp.status_code == 403:
            print("      the tab's x-captcha is stale — reload sofascore.com")
        return 1

    try:
        data = resp.json()
    except Exception:
        print(f"FAIL  200 but not JSON: {resp.text[:120]}")
        return 1

    events = data.get("events", []) if isinstance(data, dict) else []
    print(f"OK    Sofascore returned 200 with {len(events)} live football events")

    # 4. Will today's run actually move? Measured as a small CONCURRENT burst,
    # because that is how SAMPLES drives the bridge (max_concurrency tabs at
    # once) and because a sequential probe measures something else entirely.
    #
    # On 2026-09-22, on a bridge that was provably healthy, single requests
    # from idle took 20.1 s / 20.1 s / 40.1 s - exact multiples of the
    # then-20 s PULL_WAIT_S poll window (1 s since 663e7102) - while twelve
    # concurrent jobs finished in 2.6 s at 4.56 req/s with a minimum latency
    # of 0.2 s and all 200. A tab that is slow to re-enter /pull looks
    # catastrophic one job at a time and is perfectly fine under load, so the verdict
    # has to come from
    # the burst. Judging it sequentially made this preflight report FAIL on a
    # healthy bridge, and CLAUDE.md says to run it first.
    transport = BrowserBridgeTransport()
    failures = 0
    latencies_ms: list[float] = []
    latency_lock = threading.Lock()

    def probe() -> None:
        nonlocal failures
        started = time.monotonic()
        try:
            transport.get(PROBE_URL, timeout=COLD_PROBE_TIMEOUT_S)
        except (ProviderError, TransportError):
            failures += 1
            return
        elapsed_ms = (time.monotonic() - started) * 1000.0
        with latency_lock:
            latencies_ms.append(elapsed_ms)

    def burst() -> float:
        started = time.monotonic()
        threads = [threading.Thread(target=probe) for _ in range(BURST_SAMPLES)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        return time.monotonic() - started

    # The first burst is the wake-up, not the measurement: every tab is sitting
    # in a /pull that has to return before it can take work, so a cold burst
    # reports one poll cycle no matter how healthy the bridge is. A real run
    # pays this once at the start of a stage and then flows.
    burst()
    failures = 0
    latencies_ms.clear()
    elapsed = burst()

    served = BURST_SAMPLES - failures
    if served == 0 or elapsed <= 0:
        print("WARN  could not measure bridge throughput")
        return 0

    rate = served / elapsed
    print(f"INFO  bridge served {rate:.2f} req/s in a {BURST_SAMPLES}-request "
          f"burst from idle")
    windows = SofaConfig.from_env().max_concurrency
    print(f"      Not a capacity reading: {windows} window(s) sustain "
          f"~{windows * PER_WINDOW_RPS:.1f} req/s once saturated")
    print("      (2.86 per window), and an idle burst pays a poll cycle. For the")
    print("      real number:  PYTHONPATH=src:. .venv/bin/python \\")
    print("                      scripts/sofa/measure_bridge_capacity.py")
    if failures:
        print(f"WARN  {failures} of {BURST_SAMPLES} burst probes FAILED - that is a")
        print("      real fault, unlike a low rate. Check every sofascore.com")
        print("      window is open and visible.")

    # 5. Is the browser clamping our own pacing timer? This is the one number
    # in this preflight that IS graded, and it is graded on the minimum.
    if latencies_ms:
        fastest_ms = min(latencies_ms)
        if fastest_ms >= HEALTHY_ROUND_TRIP_MS:
            print(f"WARN  fastest round trip {fastest_ms:.0f} ms — the browser is "
                  f"throttling")
            print("      the tab's timer (healthy is ~175 ms). The run will take "
                  "roughly")
            print(f"      {fastest_ms / 175:.0f}x longer for no benefit to anyone. "
                  "Launch the")
            print("      windows with:  scripts/sofa/launch_bridge_browser.py")
        else:
            print(f"OK    fastest round trip {fastest_ms:.0f} ms (timer not clamped)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
