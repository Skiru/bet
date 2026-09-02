"""No test may spend the production quota counter.

``RateLimiter()`` with no arguments writes to
``betting/data/.api_usage/<provider>_<date>.json``, and 33 places in this suite
construct one that way. The counter is what the morning's preflight decides GO
from, so a test that charges a request against it moves a production decision
hours later, from a different process, with nothing in the test output saying
so.

Not hypothetical. On 2026-09-02 a new test for the Highlightly discovery
adapter monkeypatched ``requests.get``, made no network call at all, and still
charged five requests -- and its fake ``x-ratelimit-day-remaining: 3`` header
went through the one-way reconciliation and drove the day's count from 24 to
100 of 100. Highlightly drives discovery, so a run started in that state loses
about 77% of the slate. The usage file had to be repaired by hand.

The root ``conftest.py`` redirects ``USAGE_DIR`` for every test. This file is
what notices if that fixture is ever removed or renamed.
"""
from __future__ import annotations

from pathlib import Path

from bet.api_clients import rate_limiter as rate_limiter_module
from bet.api_clients.rate_limiter import RateLimiter


def _production_usage_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "betting" / "data" / ".api_usage"


def test_the_usage_dir_is_redirected_away_from_production():
    assert rate_limiter_module.USAGE_DIR != _production_usage_dir()
    # And a bare limiter picks the redirection up, which is the whole point:
    # the 33 call sites do not pass a directory.
    assert RateLimiter().usage_dir == rate_limiter_module.USAGE_DIR


def test_recording_a_request_does_not_reach_the_production_counter():
    limiter = RateLimiter()
    before = limiter.get_remaining("highlightly")
    limiter.record_request("highlightly", "a-test-that-spent-nothing", 1)
    assert limiter.get_remaining("highlightly") == before - 1
    assert not (_production_usage_dir() / "highlightly_test_marker.json").exists()
    # Nothing this test wrote is anywhere near the real directory.
    assert str(_production_usage_dir()) not in str(limiter.usage_dir)


def test_reconciling_from_a_fake_header_does_not_reach_production_either():
    """The half that did the damage. ``record_request`` moves the count by one;
    ``reconcile_from_provider`` can move it to anything the header says, and it
    is one-way, so a fabricated "3 remaining" cannot be walked back."""
    limiter = RateLimiter()
    limiter.reconcile_from_provider(
        "highlightly", {"daily_limit": 100, "daily_remaining": 3}
    )
    assert limiter.get_remaining("highlightly") <= 3
    assert str(_production_usage_dir()) not in str(limiter.usage_dir)


def test_the_exhausted_marker_does_not_leak_between_tests():
    """``_PROVIDER_EXHAUSTED`` is module-level state: one test noting a
    provider dead would make every later test in the session see it that way,
    and the order tests run in is not fixed."""
    assert rate_limiter_module._PROVIDER_EXHAUSTED == {}
    RateLimiter().note_provider_exhausted("highlightly", "set by a test")
    assert "highlightly" in rate_limiter_module._PROVIDER_EXHAUSTED


def test_the_exhausted_marker_was_cleared_before_this_test():
    """Deliberately paired with the one above and named to sort after it, so
    the pair fails if the teardown stops clearing. Reading the two together is
    the assertion; neither alone says anything."""
    assert rate_limiter_module._PROVIDER_EXHAUSTED == {}
