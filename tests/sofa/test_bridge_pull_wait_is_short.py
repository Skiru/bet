"""A /pull long-poll must not be able to starve a /push.

On 2026-09-23 the browser sent every tab's request to 127.0.0.1 over one
connection, one at a time. With PULL_WAIT_S = 20 a tab's /push queued behind
the other tabs' 20 s /pulls, so a job the tab had already fetched came back
after 60-80 s - past the pipeline's 60 s deadline - and every request was a
504 on a bridge with nothing wrong with it. At 1.0 the same browser sustained
14.4-14.8 req/s.

The bound: with every window's /pull ahead of it, a /push must still land
well inside one job deadline.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from bet.sofa.config import SofaConfig

BRIDGE_SERVER = (
    Path(__file__).parent.parent.parent / "scripts" / "sofa" / "bridge_server.py"
)


@pytest.fixture(scope="module")
def bridge_server():
    spec = importlib.util.spec_from_file_location("bridge_server", BRIDGE_SERVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_push_behind_every_window_pull_still_beats_the_deadline(bridge_server):
    windows = SofaConfig().max_concurrency
    worst_queue_s = windows * bridge_server.PULL_WAIT_S
    assert worst_queue_s * 4 <= bridge_server.JOB_TIMEOUT_S


def test_an_empty_pull_answers_after_the_wait(bridge_server):
    queue = bridge_server.JobQueue()
    assert queue.claim(0.01) is None


def test_a_pull_does_not_hold_the_connection_while_a_push_is_owed(bridge_server):
    # 2026-09-29: one shared connection, so a claimed job's /push waited
    # behind the other tabs' 1 s /pulls - a lone request took 2-4 s.
    import time

    queue = bridge_server.JobQueue()
    job = queue.submit("https://api.sofascore.com/api/v1/event/1")
    assert queue.claim(1.0, bridge_server.BUSY_PULL_WAIT_S) is job  # out in a tab
    start = time.monotonic()
    assert queue.claim(1.0, bridge_server.BUSY_PULL_WAIT_S) is None
    assert time.monotonic() - start < 0.5
    # Once it is pushed back, an idle /pull long-polls again.
    assert queue.complete(job.id, 200, "{}", None)
    start = time.monotonic()
    assert queue.claim(0.3, bridge_server.BUSY_PULL_WAIT_S) is None
    assert time.monotonic() - start >= 0.29


def test_a_busy_pull_still_takes_new_work_at_once(bridge_server):
    import threading
    import time

    queue = bridge_server.JobQueue()
    queue.claim(1.0, 0.05) if queue.submit("u1") else None
    got: list[object] = []
    t = threading.Thread(target=lambda: got.append(queue.claim(1.0, 0.5)))
    t.start()
    time.sleep(0.05)
    second = queue.submit("u2")
    t.join()
    assert got == [second]


def test_the_busy_wait_is_short_against_the_window_count(bridge_server):
    windows = SofaConfig().max_concurrency
    assert windows * bridge_server.BUSY_PULL_WAIT_S <= 0.5
