"""The provider's own quota headers outrank our tally of what we spent.

Every counter above this file counts *our* requests against a limit *we* wrote
down. The number that actually decides whether a request will be served is the
provider's, and the two drift: the key is used from more than one place, a
usage file gets cleared, or the configured limit was simply guessed. Bzzoiro
states the truth on every response --

    ratelimit-policy: "tennis";q=100;w=86400
    ratelimit:        "tennis";r=81;t=41561      # live, 2026-08-28

-- and until now the pipeline parsed that, reported it to preflight, and then
went on deciding from its own count anyway. On a 100-a-day bucket at roughly
sixteen calls an event, being six events out of step is the difference between
a clean run and one that 429s halfway through and leaves the artifact lopsided,
which is the exact outcome preflight exists to prevent.
"""
import pytest

from bet.api_clients.base_client import _EXHAUSTION_HORIZON_SECONDS
from bet.api_clients.rate_limiter import RateLimiter


@pytest.fixture
def limiter(tmp_path):
    """A limiter with a closed world: 100/day for tennis, nothing ambient."""
    rl = RateLimiter(
        usage_dir=tmp_path,
        limits={"bzzoiro-tennis": 100},
        rate_limits={},
        honor_env_overrides=False,
    )
    rl.clear_provider_exhausted()
    yield rl
    rl.clear_provider_exhausted()


def test_provider_report_raises_a_counter_that_is_behind(limiter):
    """The headline case: the key was used somewhere we cannot see.

    We think we have spent 5. The provider says 40 are gone. Continuing to
    plan against 95 remaining is how a run commits to a slate it cannot finish.
    """
    for _ in range(5):
        limiter.record_request("bzzoiro-tennis", "/matches/")
    assert limiter.get_remaining("bzzoiro-tennis") == 95

    limiter.reconcile_from_provider(
        "bzzoiro-tennis", {"daily_limit": 100, "daily_remaining": 60}
    )

    assert limiter.get_remaining("bzzoiro-tennis") == 60


def test_provider_report_never_lowers_a_counter(limiter):
    """One-way on purpose.

    The provider's window is a rolling 86400s from its own first request while
    ours is a calendar day, so a *more generous* r is usually the two windows
    disagreeing about when the day started -- not budget coming back. Believing
    it would let a shared key's spending vanish from the record.
    """
    for _ in range(40):
        limiter.record_request("bzzoiro-tennis", "/matches/")

    limiter.reconcile_from_provider(
        "bzzoiro-tennis", {"daily_limit": 100, "daily_remaining": 95}
    )

    assert limiter.get_remaining("bzzoiro-tennis") == 60


def test_silence_is_an_answer_not_a_gap(limiter):
    """Bzzoiro's football product stops sending these headers on the PRO plan.

    Reconciling from nothing must leave the counter alone: inferring a limit
    for the uncapped product from its capped sibling is how football would
    inherit a 100-a-day ceiling it does not have.
    """
    for _ in range(5):
        limiter.record_request("bzzoiro-tennis", "/matches/")

    assert limiter.reconcile_from_provider("bzzoiro-tennis", {}) is None
    assert limiter.reconcile_from_provider("bzzoiro-tennis", None) is None
    assert limiter.reconcile_from_provider(
        "bzzoiro-tennis", {"daily_limit": None, "daily_remaining": None}
    ) is None
    assert limiter.get_remaining("bzzoiro-tennis") == 95


def test_provider_reporting_zero_stops_the_run_asking(limiter):
    limiter.note_provider_exhausted("bzzoiro-tennis", "ratelimit header reports 0")

    assert limiter.provider_says_exhausted("bzzoiro-tennis")
    assert not limiter.can_request("bzzoiro-tennis")


def test_exhaustion_outranks_having_no_configured_limit(tmp_path):
    """An unlimited provider that just answered 429 is not unlimited today.

    The old ordering returned True the moment no local limit was configured,
    so the one provider whose real ceiling we can see was the one whose word
    could not stop a request.
    """
    rl = RateLimiter(usage_dir=tmp_path, limits={}, rate_limits={}, honor_env_overrides=False)
    rl.clear_provider_exhausted()
    try:
        assert rl.can_request("bzzoiro")
        rl.note_provider_exhausted("bzzoiro", "HTTP 429")
        assert not rl.can_request("bzzoiro")
    finally:
        rl.clear_provider_exhausted()


def test_exhaustion_is_shared_across_limiter_instances(tmp_path):
    """get_client() builds a fresh RateLimiter whenever it is not handed one,
    but the quota belongs to the *key* every one of them shares. A per-instance
    flag would be forgotten by the very next request."""
    first = RateLimiter(usage_dir=tmp_path, limits={}, rate_limits={}, honor_env_overrides=False)
    second = RateLimiter(usage_dir=tmp_path, limits={}, rate_limits={}, honor_env_overrides=False)
    first.clear_provider_exhausted()
    try:
        first.note_provider_exhausted("bzzoiro-tennis", "HTTP 429")
        assert second.provider_says_exhausted("bzzoiro-tennis")
        assert not second.can_request("bzzoiro-tennis")
    finally:
        first.clear_provider_exhausted()


def test_horizon_separates_back_pressure_from_exhaustion():
    """A burst throttle clears inside a run; a daily window does not.

    Bzzoiro's tennis window is 86400s, so its Retry-After is measured in hours.
    Retrying into that spends the rest of the slate rediscovering the same wall.
    """
    assert 60 <= _EXHAUSTION_HORIZON_SECONDS <= 3600
    assert _EXHAUSTION_HORIZON_SECONDS < 86400


def test_a_nonsense_quota_report_is_ignored(limiter):
    """A malformed or absurd header must not be able to zero the budget."""
    for _ in range(5):
        limiter.record_request("bzzoiro-tennis", "/matches/")
    for bad in (
        {"daily_limit": 0, "daily_remaining": 0},
        {"daily_limit": -1, "daily_remaining": 5},
        {"daily_limit": 100, "daily_remaining": -3},
        {"daily_limit": "100", "daily_remaining": "60"},
    ):
        assert limiter.reconcile_from_provider("bzzoiro-tennis", bad) is None
    assert limiter.get_remaining("bzzoiro-tennis") == 95


def test_reconciliation_leaves_a_trace_an_operator_can_read(limiter, tmp_path):
    """A corrected count must be distinguishable from a counted one, or the
    next person to read the usage file cannot tell why it jumped."""
    limiter.record_request("bzzoiro-tennis", "/matches/")
    limiter.reconcile_from_provider(
        "bzzoiro-tennis", {"daily_limit": 100, "daily_remaining": 60}
    )
    usage = limiter._read_usage("bzzoiro-tennis", window_type="daily")
    assert usage["count"] == 40
    assert usage["provider_reported"]["remaining"] == 60
    assert usage["provider_reported"]["limit"] == 100
    assert usage["provider_reported"]["observed_at"]
