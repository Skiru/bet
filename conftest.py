"""Pytest configuration — ensure scripts/ and src/ are importable.

The adapters use ``from adapters import dedup_results`` (absolute import within
``scripts/``).  When pytest runs from the project root, ``scripts/`` is not on
``sys.path`` by default, so we add it here.  ``src/`` is added so that
``from bet.…`` imports work without ``pip install -e .``.
"""
import sys
from pathlib import Path

import pytest

_root = Path(__file__).resolve().parent
for _subdir in ("scripts", "src"):
    _path = str(_root / _subdir)
    if _path not in sys.path:
        sys.path.insert(0, _path)


@pytest.fixture(autouse=True)
def _isolate_provider_quota_counters(tmp_path, monkeypatch):
    """No test may spend the production quota counter.

    ``RateLimiter()`` with no arguments writes to
    ``betting/data/.api_usage/<provider>_<date>.json``, and 33 places in this
    suite construct one that way. Any of them that reaches
    ``record_request`` or ``reconcile_from_provider`` moves the number the
    morning's preflight decides GO from.

    That is not hypothetical. On 2026-09-02 a new test for the Highlightly
    discovery adapter monkeypatched ``requests.get``, made no network call at
    all, and still charged five requests against the real counter -- and its
    fake ``x-ratelimit-day-remaining: 3`` header went through the one-way
    reconciliation and drove the day's count from 24 to 100. Highlightly is
    the provider that drives discovery, so a run started in that state would
    have lost about 77% of the slate. The file had to be repaired by hand.

    Redirected here rather than in each test, because the failure mode is a
    test that *forgets* to isolate itself and the cost lands on a different
    process hours later. ``_PROVIDER_EXHAUSTED`` is a module-level set with the
    same problem in miniature -- one test noting a provider dead would make
    every later test in the session see it that way -- so it is cleared too.
    """
    from bet.api_clients import rate_limiter as _rate_limiter

    monkeypatch.setattr(_rate_limiter, "USAGE_DIR", tmp_path / ".api_usage")
    with _rate_limiter._EXHAUSTED_LOCK:
        _rate_limiter._PROVIDER_EXHAUSTED.clear()
    yield
    with _rate_limiter._EXHAUSTED_LOCK:
        _rate_limiter._PROVIDER_EXHAUSTED.clear()
