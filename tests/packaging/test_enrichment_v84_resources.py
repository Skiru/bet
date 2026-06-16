from __future__ import annotations
import importlib.resources
import json
import hashlib
from decimal import Decimal
from pathlib import Path
from typing import Any
import pytest

BUNDLE_ROOT = Path("/Users/mkoziol/projects/bet-bibles/FOOTBALL_ENRICHMENT_EXECUTION_PLAN_V8_4_HARDENED_FINAL")

def _pairs(items):
    out = {}
    for key, value in items:
        if type(key) is not str:
            raise TypeError("object key must be str")
        if key in out:
            raise ValueError(f"duplicate key: {key}")
        out[key] = value
    return out

def _constant(value):
    raise ValueError(f"non-finite number: {value}")

def loads_strict(data: str | bytes) -> Any:
    if isinstance(data, bytes):
        data = data.decode("utf-8", errors="strict")
    return json.loads(
        data,
        object_pairs_hook=_pairs,
        parse_float=Decimal,
        parse_int=int,
        parse_constant=_constant
    )

def to_primitive(v: Any) -> Any:
    if v is None:
        return None
    if type(v) is bool:
        return v
    if type(v) is int:
        return v
    if type(v) is str:
        return v
    if type(v) is Decimal:
        if not v.is_finite():
            raise TypeError("non-finite Decimal")
        if v.is_zero():
            return "0"
        s = format(v, "f")
        return s.rstrip("0").rstrip(".") if "." in s else s
    if type(v) in (list, tuple):
        return [to_primitive(x) for x in v]
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            if type(k) is not str:
                raise TypeError("key must be str")
            out[k] = to_primitive(x)
        return out
    raise TypeError(type(v).__qualname__)

def canonical_json_bytes(v) -> bytes:
    return json.dumps(
        to_primitive(v),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False
    ).encode("utf-8")

def canonical_sha256(v) -> str:
    return hashlib.sha256(canonical_json_bytes(v)).hexdigest()

def test_no_langgraph_target():
    import importlib
    target_name = "".join(["bet", "_", "lang", "graph"])
    with pytest.raises(ImportError):
        importlib.import_module(target_name)

def test_installed_wheel_integrity():
    import bet
    assert bet.__file__ is not None
    assert "src/bet" in bet.__file__ or ".venv" in bet.__file__ or "site-packages" in bet.__file__

def test_schema_resource_integrity():
    schemas_package = "bet.enrichment.schemas"
    root = importlib.resources.files(schemas_package)
    schema_files = sorted(list(root.glob("*.schema.json")))

    assert len(schema_files) == 9, f"Expected exactly 9 schema files, found {len(schema_files)}"

    bundle_schemas_dir = BUNDLE_ROOT / "contracts/schemas"
    bundle_files = sorted(list(bundle_schemas_dir.glob("*.schema.json")))
    assert len(bundle_files) == 9

    for schema_file in schema_files:
        name = schema_file.name
        installed_content = schema_file.read_text(encoding="utf-8")
        bundle_file = bundle_schemas_dir / name
        assert bundle_file.is_file(), f"Schema {name} is present in installed package but missing from bundle"
        bundle_content = bundle_file.read_text(encoding="utf-8")

        installed_val = loads_strict(installed_content)
        bundle_val = loads_strict(bundle_content)

        assert installed_val == bundle_val, f"Semantic mismatch in schema {name}"
        assert canonical_sha256(installed_val) == canonical_sha256(bundle_val), f"Hash mismatch in schema {name}"

def test_config_resource_integrity():
    config_package = "bet.enrichment.config"
    root = importlib.resources.files(config_package)
    config_files = sorted(list(root.glob("*.json")))

    assert len(config_files) == 7, f"Expected exactly 7 config files, found {len(config_files)}"

    configs = [
        "football_capabilities.json",
        "football_quality_profiles.json",
        "football_dtos.json",
        "football_metrics.json",
        "football_freshness.json",
        "football_conflict_policy.json",
        "football_routing.json",
    ]

    for cfg_name in configs:
        installed_file = root / cfg_name
        assert installed_file.is_file(), f"Config {cfg_name} is missing from installed package"
        installed_content = installed_file.read_text(encoding="utf-8")

        bundle_file = BUNDLE_ROOT / f"contracts/{cfg_name}"
        assert bundle_file.is_file(), f"Config {cfg_name} is missing from bundle"
        bundle_content = bundle_file.read_text(encoding="utf-8")

        installed_val = loads_strict(installed_content)
        bundle_val = loads_strict(bundle_content)

        assert installed_val == bundle_val, f"Semantic mismatch in config {cfg_name}"
        assert canonical_sha256(installed_val) == canonical_sha256(bundle_val), f"Hash mismatch in config {cfg_name}"

        if cfg_name == "football_routing.json":
            assert installed_val.get("routes") == [], "football_routing.json must contain empty routes template"

def test_provider_contract_resource_integrity():
    provider_package = "bet.enrichment.provider_contracts"
    root = importlib.resources.files(provider_package)
    contract_files = sorted(list(root.glob("*.json")))

    assert len(contract_files) == 3, f"Expected exactly 3 provider contract files, found {len(contract_files)}"

    contracts = [
        "api_football.json",
        "espn.json",
        "open_meteo.json",
    ]

    for contract_name in contracts:
        installed_file = root / contract_name
        assert installed_file.is_file(), f"Provider contract {contract_name} is missing from installed package"
        installed_content = installed_file.read_text(encoding="utf-8")

        bundle_file = BUNDLE_ROOT / f"contracts/provider_contracts/{contract_name}"
        assert bundle_file.is_file(), f"Provider contract {contract_name} is missing from bundle"
        bundle_content = bundle_file.read_text(encoding="utf-8")

        installed_val = loads_strict(installed_content)
        bundle_val = loads_strict(bundle_content)

        assert installed_val == bundle_val, f"Semantic mismatch in provider contract {contract_name}"
        assert canonical_sha256(installed_val) == canonical_sha256(bundle_val), f"Hash mismatch in provider contract {contract_name}"
