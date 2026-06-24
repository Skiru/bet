import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

@dataclass(frozen=True)
class ProviderEnvelope:
    provider: str
    path: Path
    status: str
    body: Any
    body_sha256: str
    source_url: Optional[str]

def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

def load_provider_envelopes(run_dirs: List[Path]) -> List[ProviderEnvelope]:
    envelopes: List[ProviderEnvelope] = []
    # Process run directories in a deterministic, stable order
    for run_dir in sorted(run_dirs):
        # Sort files to ensure stable, deterministic order
        for path in sorted(run_dir.rglob("*.json")):
            if path.name in {
                "manifest.json",
                "mapping_candidate.json",
                "capture_verifier_result.json",
                "README.md",
                "fixtures_discovered.json",
            }:
                continue
            try:
                data = load_json(path)
            except Exception as e:
                # If cannot parse json, fail
                raise ValueError(f"Failed to parse JSON file {path}: {e}")

            if not isinstance(data, dict):
                continue

            provider = str(data.get("provider") or path.parent.name)
            status = str(data.get("status") or "UNKNOWN")
            body_sha256 = data.get("body_sha256")

            # REQ-LOADER-005 Treat missing body_sha256 in an enrichment envelope as verifier failure
            success_statuses = {"SUCCESS", "DISCOVERY_FETCHED", "FETCHED", "RESCUE_FETCHED"}
            if status in success_statuses:
                if not body_sha256:
                    raise ValueError(f"Missing body_sha256 in enrichment envelope: {path}")

            envelopes.append(
                ProviderEnvelope(
                    provider=provider,
                    path=path,
                    status=status,
                    body=data.get("body"),
                    body_sha256=str(body_sha256 or ""),
                    source_url=data.get("source_url"),
                )
            )
    return envelopes

def load_mapping_metadata(run_dirs: List[Path]) -> List[Dict[str, Any]]:
    # Loads and normalizes mapping_candidate.json files from directories
    mappings: List[Dict[str, Any]] = []
    for run_dir in sorted(run_dirs):
        mapping_file = run_dir / "mapping_candidate.json"
        if mapping_file.exists():
            data = load_json(mapping_file)
            if isinstance(data, list):
                mappings.extend(data)
            elif isinstance(data, dict):
                mappings.append(data)
    return mappings
