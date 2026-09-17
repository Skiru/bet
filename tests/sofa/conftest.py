import pytest

@pytest.fixture(autouse=True)
def _guard_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Block network access in unit tests unless marked with @pytest.mark.sofa_live."""
    if "sofa_live" in request.node.keywords:
        return
        
    import socket
    import requests  # type: ignore
    from curl_cffi import requests as cffi_requests

    def guard(*args, **kwargs) -> None:  # type: ignore
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
