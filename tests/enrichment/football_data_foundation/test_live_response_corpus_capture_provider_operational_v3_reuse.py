from __future__ import annotations

import pytest
from bet.api_clients.sportdb_mcp import SportDBMCPClient, SportDBMCPShadowAdapter
from bet.api_clients.highlightly import HighlightlyClient


def test_existing_client_reuse_and_import() -> None:
    """REQ-TEST-009: Existing sportdb_mcp.py and highlightly.py must be reused/repaired/wrapped."""
    # Ensure they can be imported and initialized
    assert SportDBMCPClient is not None
    assert SportDBMCPShadowAdapter is not None
    assert HighlightlyClient is not None

    # Check that they have the expected classes/attributes
    assert hasattr(SportDBMCPClient, "call_tool")
    assert hasattr(SportDBMCPClient, "list_tools")
    assert hasattr(HighlightlyClient, "get_statistics_result")
