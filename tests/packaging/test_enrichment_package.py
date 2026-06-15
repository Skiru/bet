from __future__ import annotations
import importlib.resources
import json
import pytest

def test_package_imports():
    # Verify that bet and its enrichment submodules can be imported
    import bet
    import bet.enrichment
    import bet.enrichment.kernel
    assert bet.__file__ is not None

def test_schema_resources():
    # Verify that schema resources are discoverable and valid JSON
    schemas_package = "bet.enrichment.schemas"
    root = importlib.resources.files(schemas_package)
    schema_files = list(root.glob("*.schema.json"))
    assert len(schema_files) >= 8, f"Expected at least 8 schema files, found {len(schema_files)}"

    for p in schema_files:
        content = p.read_text(encoding="utf-8")
        data = json.loads(content)
        assert "$schema" in data
        assert "$id" in data

def test_config_resources():
    # Verify that config resources are discoverable and valid JSON
    config_package = "bet.enrichment.config"
    root = importlib.resources.files(config_package)
    config_files = list(root.glob("*.json"))
    assert len(config_files) >= 7, f"Expected at least 7 config files, found {len(config_files)}"

    for p in config_files:
        content = p.read_text(encoding="utf-8")
        data = json.loads(content)
        assert isinstance(data, dict)
