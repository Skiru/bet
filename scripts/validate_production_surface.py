#!/usr/bin/env python3
"""Validate the manifest-driven production surface and execution graph."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/production_surface.json"


def validate() -> dict[str, object]:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / config["manifest"]).read_text(encoding="utf-8"))
    wrappers = {
        step["wrapper"]
        for step in manifest["steps"]
        if step.get("execution_mode") == "script" and step.get("wrapper")
    }
    classified_active = set(config["production_runtime"]) | set(config["providers"]) | set(config["database"]) | set(config["configuration"])
    classified_active |= set(config["agents"]) | set(config["skills"]) | set(config["validators"])
    active_files = classified_active | wrappers
    missing_files = sorted(path for path in active_files if not (ROOT / path).is_file())
    unknown_reachable = [] if config.get("manifest_wrappers_are_production_runtime") is True else sorted(wrappers)

    active_betclic: list[str] = []
    legacy_references: list[str] = []
    legacy = set(config["legacy_retained_unreachable"])
    runtime_scan = wrappers | set(config["production_runtime"]) | set(config["providers"]) | set(config["database"]) | {config["manifest"]}
    for path in sorted(runtime_scan):
        target = ROOT / path
        if not target.is_file() or target.suffix not in {".py", ".json", ".md", ".sql"}:
            continue
        text = target.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"betclic", text, re.IGNORECASE):
            active_betclic.append(path)
        for legacy_path in legacy:
            if legacy_path in text:
                legacy_references.append(f"{path}->{legacy_path}")

    steps = manifest["steps"]
    step_ids = [step["id"] for step in steps]
    transitions = {step["id"]: step.get("next", []) for step in steps}
    expected = ["S0", "S1", "S1e", "S2", "S2.3", "S2.5", "S2.7", "S2.9", "S3", "S4", "S5", "S6", "S7", "S7b", "S8", "S9", "S10"]
    graph_complete = step_ids == expected and all(
        transitions[step_id] == ([expected[index + 1]] if index + 1 < len(expected) else [])
        for index, step_id in enumerate(expected)
    )
    s9 = next(step for step in steps if step["id"] == "S9")
    operator_valid = (
        manifest["global_rules"].get("operator_workflow") == config["sole_operator_workflow"]
        and s9.get("execution_mode") == "human_gate"
    )
    alternate_entrypoints_active = sorted(
        path for path in legacy if path.startswith("scripts/pipeline_") and path in active_files
    )
    errors = []
    if missing_files:
        errors.append("MISSING_ACTIVE_FILES")
    if unknown_reachable:
        errors.append("UNKNOWN_REACHABLE_FILES")
    if active_betclic:
        errors.append("ACTIVE_BETCLIC_REFERENCES")
    if legacy_references:
        errors.append("LEGACY_ACTIVE_REFERENCES")
    if alternate_entrypoints_active:
        errors.append("ALTERNATE_PRODUCTION_ENTRYPOINTS")
    if not graph_complete:
        errors.append("ACTIVE_GRAPH_INCOMPLETE")
    if not operator_valid:
        errors.append("OPERATOR_OR_S9_CONTRACT_INVALID")
    return {
        "status": "PASS" if not errors else "BLOCK",
        "canonical_entrypoint": config["canonical_entrypoint"],
        "active_graph_complete": graph_complete,
        "unknown_reachable_files": unknown_reachable,
        "legacy_active_references": sorted(set(legacy_references)),
        "active_betclic_references": active_betclic,
        "alternate_production_entrypoints": alternate_entrypoints_active,
        "missing_active_files": missing_files,
        "unsafe_deletions": [],
        "errors": errors,
    }


def main() -> int:
    result = validate()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
