"""A job the client gave up on is never run later (review 2026-10-01)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

SCRIPT = Path(__file__).parents[2] / "scripts" / "sofa" / "bridge_server.py"


def _module() -> Any:
    spec = importlib.util.spec_from_file_location("bridge_server_forget", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_forgotten_job_is_never_claimed() -> None:
    q = _module().JobQueue()
    dead = q.submit("https://api.sofascore.com/api/v1/event/1")
    live = q.submit("https://api.sofascore.com/api/v1/event/2")
    q.forget(dead.id)
    assert q.claim(0) is live
    assert q.claim(0) is None
    stats = q.stats()
    assert stats["pending"] == 0
    assert stats["in_flight"] == 1  # the live one, claimed and not pushed
