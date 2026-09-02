"""The Highlightly discovery adapter must pay for what it spends.

Found 2026-09-02 while checking readiness for that day's run: preflight
reported highlightly at 76 of 100 remaining and advised GO, and the adapter
that opens every run was invisible to that number entirely.

It calls ``requests.get`` directly rather than through the client -- deliberately,
because the client's own ``discover_matches_result`` is scoped to a single
``leagueId``/``season`` pair and would miss the fixtures outside the main
leagues this source exists to catch. But going around the client also went
around the three things the client's request path does:

1. ``can_request`` -- so a run with nothing left still fired five pages and
   collected five rejections.
2. ``record_request`` -- so ENRICH decided its budget against a count up to
   five requests optimistic.
3. ``reconcile_from_provider`` -- so ``x-ratelimit-day-remaining``, the one
   authoritative number on the page, was read and thrown away.

This provider is the one where that matters most: it drives *discovery*, so
running dry shrinks the whole slate by about 77% rather than merely costing
corroboration on events already found.
"""
from __future__ import annotations

import pytest

from bet.api_clients.rate_limiter import RateLimiter
from bet.simple_stats.discover import (
    _HIGHLIGHTLY_MAX_PAGES,
    HighlightlyDiscoveryAdapter,
)


class _Response:
    def __init__(self, rows: list[dict], headers: dict[str, str] | None = None):
        self._rows = rows
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"data": self._rows}


@pytest.fixture
def adapter(monkeypatch):
    """A real ``RateLimiter``, pointed at a temporary usage dir.

    The redirection is the root ``conftest.py``'s autouse fixture, not
    something this file does -- writing a *fake* request into the production
    counter is what this test did on its first run, and the fix belongs where
    every test gets it rather than where one test remembers it.
    """
    made = HighlightlyDiscoveryAdapter(RateLimiter())
    monkeypatch.setattr(made._client, "api_key", "k", raising=False)
    monkeypatch.setattr(made._client, "_build_headers", lambda: {}, raising=False)
    monkeypatch.setattr(made._client, "base_url", "https://example.invalid", raising=False)
    return made


def _row(match_id: str) -> dict:
    return {
        "id": match_id,
        "date": "2026-09-02T18:00:00Z",
        "homeTeam": {"id": "1", "name": "Home FC"},
        "awayTeam": {"id": "2", "name": "Away FC"},
        "league": {"name": "Test League"},
        "state": {"description": "scheduled"},
    }


def test_every_page_is_recorded_against_the_daily_quota(adapter, monkeypatch):
    calls: list[int] = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(params["offset"])
        # One full page then an empty one, so paging stops naturally.
        return _Response([_row("m1")] if params["offset"] == 0 else [])

    monkeypatch.setattr("bet.simple_stats.discover.requests.get", fake_get)
    before = adapter._client.rate_limiter.get_remaining("highlightly")
    adapter._fetch_events_impl("2026-09-02", "football")
    after = adapter._client.rate_limiter.get_remaining("highlightly")
    assert len(calls) >= 1
    assert before - after == len(calls), "discovery pages were not charged"


def test_an_exhausted_quota_stops_the_paging_instead_of_firing_it(adapter, monkeypatch):
    """The old behaviour fired all five pages into a provider that had already
    said no. Five rejections is not more information than one."""
    fired: list[int] = []

    def fake_get(url, params=None, headers=None, timeout=None):
        fired.append(params["offset"])
        return _Response([_row("m1")])

    monkeypatch.setattr("bet.simple_stats.discover.requests.get", fake_get)
    monkeypatch.setattr(
        adapter._client.rate_limiter, "can_request", lambda name, cost=1: False
    )
    events = adapter._fetch_events_impl("2026-09-02", "football")
    assert fired == []
    assert events == []
    assert any("quota exhausted" in str(e) for e in adapter.last_errors), adapter.last_errors


def test_the_providers_own_remaining_count_corrects_ours(adapter, monkeypatch):
    """The header was on every page and parsed nowhere. Reconciliation is
    one-way -- it can only ever raise our count -- so a provider that has spent
    budget this counter never saw (a second run, the MCP server, a manual
    probe) is believed."""
    limiter = adapter._client.rate_limiter

    def fake_get(url, params=None, headers=None, timeout=None):
        return _Response(
            [_row("m1")] if params["offset"] == 0 else [],
            headers={"x-ratelimit-day-limit": "100", "x-ratelimit-day-remaining": "3"},
        )

    monkeypatch.setattr("bet.simple_stats.discover.requests.get", fake_get)
    adapter._fetch_events_impl("2026-09-02", "football")
    remaining = limiter.get_remaining("highlightly")
    assert remaining is not None
    # The provider said three left; our count must not claim more than that.
    assert remaining <= 3, remaining


def test_a_page_that_errors_still_leaves_the_call_charged(adapter, monkeypatch):
    """A request that reached the provider cost quota whether or not we could
    parse the answer. Charging only successes is how a counter drifts
    optimistic in the exact circumstances that matter."""
    import requests as requests_module

    def fake_get(url, params=None, headers=None, timeout=None):
        class _Bad(_Response):
            def raise_for_status(self):
                raise requests_module.RequestException("500")

        return _Bad([])

    monkeypatch.setattr("bet.simple_stats.discover.requests.get", fake_get)
    limiter = adapter._client.rate_limiter
    before = limiter.get_remaining("highlightly")
    adapter._fetch_events_impl("2026-09-02", "football")
    assert limiter.get_remaining("highlightly") == before - 1


def test_the_page_cap_still_bounds_a_healthy_run(adapter, monkeypatch):
    """Paging stops at the cap, so a provider returning full pages forever
    cannot spend the whole budget in DISCOVER -- and the quota check added in
    front of each page must not change where that cap lands on a healthy run.

    ``_HIGHLIGHTLY_PAGE_SIZE`` full rows per page is what keeps the loop going;
    a short page ends it, which is the ordinary case and is covered by
    ``test_every_page_is_recorded_against_the_daily_quota``.
    """
    from bet.simple_stats.discover import _HIGHLIGHTLY_PAGE_SIZE

    fired: list[int] = []

    def fake_get(url, params=None, headers=None, timeout=None):
        fired.append(params["offset"])
        offset = params["offset"]
        return _Response([_row(f"m{offset}-{i}") for i in range(_HIGHLIGHTLY_PAGE_SIZE)])

    monkeypatch.setattr("bet.simple_stats.discover.requests.get", fake_get)
    adapter._fetch_events_impl("2026-09-02", "football")
    assert len(fired) == _HIGHLIGHTLY_MAX_PAGES
