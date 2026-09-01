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


# --- 402 is a purchase, not a spend -----------------------------------------
#
# Live on 2026-09-01, bzzoiro's tennis product answered
#
#     HTTP 402
#     {"error":"Sports Addon required","code":"addon_required",
#      "detail":"...require the Sports Addon ($5/mo)."}
#     ratelimit-policy: "tennis";q=100;w=86400
#     ratelimit:        "tennis";r=0;t=54274
#
# -- a billing refusal carrying a perfectly real ``r=0``. Believing that header
# wrote "100/95 used" into the day's counter, and preflight then told the
# operator to raise BET_LIMIT_BZZOIRO_TENNIS or reset the counter. Neither can
# buy an addon. These tests keep the two facts apart.


def test_an_entitlement_fault_does_not_move_the_counter(limiter):
    """Buy the addon and the provider works again -- with nothing to reset."""
    for _ in range(3):
        limiter.record_request("bzzoiro-tennis", "/matches/")

    limiter.note_entitlement_fault("bzzoiro-tennis", "HTTP 402: Sports Addon required")

    assert limiter.usage_snapshot("bzzoiro-tennis")["used"] == 3


def test_an_entitlement_fault_survives_the_process_that_saw_it(tmp_path):
    """Preflight runs in its own process. An in-memory flag would never reach it."""
    first = RateLimiter(usage_dir=tmp_path, limits={"bzzoiro-tennis": 100},
                        rate_limits={}, honor_env_overrides=False)
    first.note_entitlement_fault("bzzoiro-tennis", "HTTP 402: Sports Addon required")

    second = RateLimiter(usage_dir=tmp_path, limits={"bzzoiro-tennis": 100},
                         rate_limits={}, honor_env_overrides=False)

    assert "Sports Addon" in (second.entitlement_fault("bzzoiro-tennis") or "")
    assert second.usage_snapshot("bzzoiro-tennis")["entitlement_fault"]


def test_a_provider_with_no_fault_reports_none(limiter):
    assert limiter.entitlement_fault("bzzoiro-tennis") is None
    assert limiter.usage_snapshot("bzzoiro-tennis")["entitlement_fault"] is None


def test_preflight_names_the_purchase_instead_of_advising_a_reset(tmp_path, monkeypatch):
    """The whole point: the advice has to be one that can work."""
    from bet.simple_stats import preflight as pf

    limiter = RateLimiter(usage_dir=tmp_path, limits={"bzzoiro-tennis": 100},
                          rate_limits={}, honor_env_overrides=False)
    limiter.note_entitlement_fault("bzzoiro-tennis", "HTTP 402: Sports Addon required")
    monkeypatch.setattr(pf, "has_credentials", lambda _p: (True, "BZZORIO_KEY"))

    quota = pf.provider_quota(limiter, "bzzoiro-tennis")

    assert quota["available"] is False, "a 402'd provider must not read as usable"
    assert quota["entitlement_fault"]
    # And the counter is untouched, so nothing suggests spend.
    assert quota["used_hint"] == 0


def test_a_402_response_does_not_reconcile_the_counter_from_its_headers(tmp_path, monkeypatch):
    """The boundary test, with the exact live payload that caused this.

    Without the 402 branch, ``r=0`` on this response set ``count`` to 100 and
    the day was over for a provider that had spent nothing.
    """
    from bet.api_clients.bzzoiro_tennis import BzzoiroTennisClient
    from bet.integration import evidence as ev
    from bet.integration import telemetry_wrapper as tw

    limiter = RateLimiter(usage_dir=tmp_path, limits={"bzzoiro-tennis": 100},
                          rate_limits={}, honor_env_overrides=False)
    limiter.clear_provider_exhausted()

    class _Result:
        status_code = 402
        headers = {
            "ratelimit-policy": '"tennis";q=100;w=86400',
            "ratelimit": '"tennis";r=0;t=54274',
        }
        content = b'{"error":"Sports Addon required","code":"addon_required"}'
        text = content.decode()
        error_code = "payment_required"
        retryable = False
        error = None
        elapsed_ms = 1

        @staticmethod
        def json():
            return {"error": "Sports Addon required", "code": "addon_required"}

    # The imports are function-local, so the source modules are what must be
    # patched -- and bzzoiro goes through EvidenceRequestMixin, not
    # APISportsClient. Patching the wrong one is how a fix lands next to the
    # code path it was written for.
    monkeypatch.setattr(tw, "wrap_request", lambda **_kwargs: _Result())
    monkeypatch.setattr(ev, "persist_response_evidence", lambda *a, **k: None)

    client = BzzoiroTennisClient(limiter)
    monkeypatch.setattr(client, "api_key", "test-key", raising=False)
    # Keyword-only, and NOT wrapped in a bare except: a swallowed TypeError
    # here made this test pass against a call that never happened.
    result = client._request_with_evidence(
        endpoint="/matches/", params={}, operation="fixtures"
    )
    assert result is not None

    snapshot = limiter.usage_snapshot("bzzoiro-tennis")
    assert snapshot["used"] < 100, (
        "the 402's ratelimit header was believed as a spend tally: "
        f"count is {snapshot['used']}"
    )
    assert snapshot["entitlement_fault"], "the billing refusal was not recorded"
    limiter.clear_provider_exhausted()


def test_an_entitlement_fault_stops_the_run_from_asking_again(limiter):
    """A 402 consumes no quota, so nothing else would ever stop the loop."""
    assert limiter.can_request("bzzoiro-tennis", 1) is True

    limiter.note_entitlement_fault("bzzoiro-tennis", "HTTP 402: Sports Addon required")

    assert limiter.provider_says_exhausted("bzzoiro-tennis") is True
    assert limiter.can_request("bzzoiro-tennis", 1) is False
    limiter.clear_provider_exhausted()
