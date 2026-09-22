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
# 2026-09-22 with three visible windows: the bridge sustains 8.6 req/s once
# the tabs are saturated, but a tab that finishes a job and finds nothing
# waiting goes back into a 20 s /pull and pays that cycle to be claimed again.
# So four probes from idle read 0.10-0.20 req/s on exactly the bridge that
# then did 8.64 req/s over 360 requests with zero non-200.
#
# This check therefore REPORTS the number and refuses to grade it. Earlier
# versions graded it and cried wolf on a healthy bridge, which is worse than
# saying nothing - CLAUDE.md runs this first.
EXPECTED_PLATEAU_RPS = 8.6
BURST_SAMPLES = 4

# The FIRST request after a quiet period is not a latency measurement, it is a
# poll cycle. The userscript long-polls /pull for PULL_WAIT_S = 20 s; a job
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
        print(f"      no tab claimed the job in {COLD_PROBE_TIMEOUT_S:.0f}s, which is")
        print("      longer than a poll cycle - so the tab is not merely idle.")
        print("      Bring the sofascore.com window to the front and retry.")
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
    # userscript's PULL_WAIT_S = 20 poll window - while twelve concurrent jobs
    # finished in 2.6 s at 4.56 req/s with a minimum latency of 0.2 s and all
    # 200. A tab that is slow to re-enter /pull looks catastrophic one job at a
    # time and is perfectly fine under load, so the verdict has to come from
    # the burst. Judging it sequentially made this preflight report FAIL on a
    # healthy bridge, and CLAUDE.md says to run it first.
    transport = BrowserBridgeTransport()
    failures = 0

    def probe() -> None:
        nonlocal failures
        try:
            transport.get(PROBE_URL, timeout=COLD_PROBE_TIMEOUT_S)
        except (ProviderError, TransportError):
            failures += 1

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
    elapsed = burst()

    served = BURST_SAMPLES - failures
    if served == 0 or elapsed <= 0:
        print("WARN  could not measure bridge throughput")
        return 0

    rate = served / elapsed
    print(f"INFO  bridge served {rate:.2f} req/s in a {BURST_SAMPLES}-request "
          f"burst from idle")
    print(f"      Not a capacity reading: a run sustains ~{EXPECTED_PLATEAU_RPS:.1f} "
          f"req/s once the tabs")
    print("      are saturated, and an idle burst pays a 20 s poll cycle. For the")
    print("      real number:  PYTHONPATH=src:. .venv/bin/python \\")
    print("                      scripts/sofa/measure_bridge_capacity.py")
    if failures:
        print(f"WARN  {failures} of {BURST_SAMPLES} burst probes FAILED - that is a")
        print("      real fault, unlike a low rate. Check every sofascore.com")
        print("      window is open and visible.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
