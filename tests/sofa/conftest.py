"""Test harness for `sofa`. `pytest tests/sofa` is offline, always (PLAN §8)."""

from __future__ import annotations

import os
from typing import Any

import pytest


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Deselect `@pytest.mark.sofa_live` unless the operator opts in.

    `--strict-markers` alone registers the marker; it does not stop the test
    from running, and a live test in CI turns a provider's bad afternoon into a
    red build (L28). Opt in with `SOFA_LIVE=1` or `pytest --sofa-live`.
    """
    if config.getoption("--sofa-live") or os.environ.get("SOFA_LIVE") == "1":
        return
    skip = pytest.mark.skip(
        reason="live Sofascore test; opt in with SOFA_LIVE=1 or --sofa-live"
    )
    for item in items:
        if "sofa_live" in item.keywords:
            item.add_marker(skip)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--sofa-live",
        action="store_true",
        default=False,
        help="run the @sofa_live tests, which call Sofascore for real",
    )


@pytest.fixture(autouse=True)
def _guard_network(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No unit test reaches the network, and none spends provider budget (L28)."""
    if "sofa_live" in request.node.keywords:
        return

    import socket

    import requests
    from curl_cffi import requests as cffi_requests

    def guard(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("network access in unit test")

    monkeypatch.setattr(socket, "socket", guard)
    monkeypatch.setattr(cffi_requests, "get", guard)
    monkeypatch.setattr(cffi_requests, "post", guard)
    monkeypatch.setattr(cffi_requests, "request", guard)
    monkeypatch.setattr(cffi_requests.Session, "request", guard)
    monkeypatch.setattr(requests, "get", guard)
    monkeypatch.setattr(requests, "post", guard)
    monkeypatch.setattr(requests, "request", guard)
    monkeypatch.setattr(requests.Session, "request", guard)
