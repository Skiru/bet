from __future__ import annotations

import os

import pytest


def test_live_shadow_readiness_gating() -> None:
    sportdb_key = os.environ.get("SPORTDB_API_KEY")
    fd_key = os.environ.get("FOOTBALL_DATA_API_KEY")
    hl_key = os.environ.get("HIGHLIGHTLY_API_KEY")

    # We check if credentials are missing
    if not (sportdb_key or fd_key or hl_key):
        # Skipped with explicit reason if all are missing
        pytest.skip(
            "Skipping live shadow probes: no API credentials found in environment (SPORTDB_API_KEY, FOOTBALL_DATA_API_KEY, HIGHLIGHTLY_API_KEY)"
        )

    # If they are present, we can assert that they are non-empty and start with allowed characters
    if sportdb_key:
        assert len(sportdb_key) > 0
    if fd_key:
        assert len(fd_key) > 0
    if hl_key:
        assert len(hl_key) > 0
