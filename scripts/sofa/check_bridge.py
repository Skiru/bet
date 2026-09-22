"""Is the browser bridge alive, and does it actually reach Sofascore?

    python scripts/sofa/check_bridge.py

Checks four things in order, and says which one broke:
  1. the bridge server is listening
  2. a browser tab is polling it
  3. a real /api/v1/ request comes back 200 with JSON
  4. the tab is answering at full speed, not throttled by the browser
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

sys.path.insert(0, "src")

from bet.sofa.bridge_transport import (  # noqa: E402
    DEFAULT_BRIDGE_URL,
    BrowserBridgeTransport,
)
from bet.sofa.errors import ProviderError  # noqa: E402

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
HEALTHY_ROUND_TRIP_MS = 600.0
LATENCY_SAMPLES = 3


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

    try:
        resp = BrowserBridgeTransport().get(PROBE_URL, timeout=30.0)
    except ProviderError as e:
        print(f"FAIL  bridge could not serve the request: {e}")
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

    # 4. Is the tab answering at full speed? The request count here is
    # deliberately tiny - this measures our own latency, it is not a
    # throughput test against someone else's production API.
    transport = BrowserBridgeTransport()
    samples = []
    for _ in range(LATENCY_SAMPLES):
        started = time.monotonic()
        try:
            transport.get(PROBE_URL, timeout=30.0)
        except ProviderError:
            break
        samples.append((time.monotonic() - started) * 1000.0)
    if not samples:
        print("WARN  could not measure round-trip latency")
        return 0

    median_ms = statistics.median(samples)
    if median_ms >= HEALTHY_ROUND_TRIP_MS:
        print(f"WARN  bridge round trip {median_ms:.0f} ms — the browser is "
              f"throttling the tab (healthy is ~175 ms)")
        print("      the run will take roughly "
              f"{median_ms / 175:.0f}x longer for no benefit to anyone.")
        print("      keep the sofascore.com tab visible and the machine awake:")
        print("      a backgrounded or occluded tab has its timers clamped, and")
        print("      one overnight run paid ~5.3 hours for exactly this.")
    else:
        print(f"OK    bridge round trip {median_ms:.0f} ms (tab not throttled)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
