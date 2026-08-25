from __future__ import annotations

from scripts.validate_production_surface import validate


def test_production_surface_has_one_complete_betclic_free_graph():
    result = validate()
    assert result["status"] == "PASS", result
    assert result["active_graph_complete"] is True
    assert result["unknown_reachable_files"] == []
    assert result["legacy_active_references"] == []
    assert result["active_betclic_references"] == []
    assert result["alternate_production_entrypoints"] == []
    assert result["unsafe_deletions"] == []
