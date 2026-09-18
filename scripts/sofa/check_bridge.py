"""Is the browser bridge alive, and does it actually reach Sofascore?

    python scripts/sofa/check_bridge.py

Checks three things in order, and says which one broke:
  1. the bridge server is listening
  2. a browser tab is polling it
  3. a real /api/v1/ request comes back 200 with JSON
"""

from __future__ import annotations

import json
import sys
from urllib.error import URLError
from urllib.request import urlopen

sys.path.insert(0, "src")

from bet.sofa.bridge_transport import (  # noqa: E402
    DEFAULT_BRIDGE_URL,
    BrowserBridgeTransport,
)
from bet.sofa.errors import ProviderError  # noqa: E402

PROBE_URL = "https://api.sofascore.com/api/v1/sport/football/events/live"


def main() -> int:
    base = DEFAULT_BRIDGE_URL

    try:
        with urlopen(base + "/health", timeout=5) as r:
            health = json.loads(r.read().decode("utf-8"))
    except URLError as e:
        print(f"FAIL  bridge server not listening on {base} ({e})")
        print("      start it:  python scripts/sofa/bridge_server.py")
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
