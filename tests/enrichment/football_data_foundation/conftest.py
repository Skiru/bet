from __future__ import annotations

import socket
import urllib.request

import pytest


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise RuntimeError("network access disabled in football_data_foundation unit tests")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)

    try:
        import requests
    except ImportError:
        requests = None

    if requests is not None:
        monkeypatch.setattr(requests.sessions.Session, "request", blocked)
