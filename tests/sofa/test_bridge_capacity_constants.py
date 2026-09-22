"""max_concurrency is the window count, and the bucket must sit above it.

Measured 2026-09-22 against five windows launched by launch_bridge_browser.py,
60 requests a step, zero non-200:

    conc  achieved   p50 net   p90 net
       3    0.15/s   20138 ms  20162 ms   two tabs idle, paying the poll cycle
       5   11.67/s     354 ms    620 ms   354 ms IS MIN_INTERVAL_MS
       8   11.72/s     668 ms    704 ms
      12   11.66/s    1010 ms   1056 ms

Two things this pins, both of which were wrong that morning:

1. max_concurrency sat at 3 while five windows were open, so two tabs had
   nothing in flight, went back into a 20 s /pull, and the whole bridge ran at
   0.15 req/s. Below the window count the failure is not gradual - it is 78x.

2. The bucket has to sit above the tabs' own ceiling (5 x 2.86 = 14.3 req/s)
   or it becomes the limiter and starves them into the same idle cycle.
"""

import importlib.util
from pathlib import Path

import pytest

from bet.sofa.config import SofaConfig

SCRIPTS = Path(__file__).parent.parent.parent / "scripts" / "sofa"
LAUNCHER = SCRIPTS / "launch_bridge_browser.py"

# The userscript's per-connection pacing floor. Never lowered - capacity comes
# from opening more windows, never from making one window faster.
MIN_INTERVAL_MS = 350.0
PER_WINDOW_RPS = 1000.0 / MIN_INTERVAL_MS


@pytest.fixture(scope="module")
def launcher():
    spec = importlib.util.spec_from_file_location("launch_bridge_browser", LAUNCHER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_concurrency_matches_the_number_of_windows_we_launch(launcher):
    """One in-flight job per tab. A tab with nothing queued for it goes back
    into a 20 s /pull, and at conc=3 against five windows that measured
    0.15 req/s against 11.67."""
    assert SofaConfig().max_concurrency == launcher.DEFAULT_WINDOWS


def test_the_bucket_sits_above_what_the_tabs_can_serve(launcher):
    """If the bucket is the limiter the tabs idle between jobs and pay the
    poll cycle, which is the same collapse from the other direction."""
    tab_ceiling = launcher.DEFAULT_WINDOWS * PER_WINDOW_RPS
    assert SofaConfig().target_rps > tab_ceiling


def test_the_bucket_is_not_set_so_high_it_stops_being_a_gate():
    """It is still a gate in front of someone else's production API. Above
    roughly twice the tabs' ceiling it is decoration."""
    assert SofaConfig().target_rps <= 2 * SofaConfig().max_concurrency * PER_WINDOW_RPS


def test_env_overrides_still_win():
    """Tuning on a machine with a different window count must not require a
    code change."""
    cfg = SofaConfig(max_concurrency=8, target_rps=30)
    assert cfg.max_concurrency == 8
    assert cfg.target_rps == 30
