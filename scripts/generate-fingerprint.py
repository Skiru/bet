#!/usr/bin/env python3
"""
Phase 3 — Fingerprint Generator

Generates a comprehensive fingerprint for Phase 3 qualification.

Usage:
    python scripts/generate-fingerprint.py
"""

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


def file_hash(path: Path) -> str:
    """Generate SHA256 hash of a file."""
    if not path.exists():
        return "MISSING"
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        h.update(f.read())
    return h.hexdigest()[:16]


def main():
    """Generate fingerprint."""
    print("=" * 60)
    print("Phase 3 Fingerprint Generator")
    print("=" * 60)
    print()
    
    # Git HEAD
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    git_head = proc.stdout.strip()
    
    # Phase 2 fingerprint
    p2_state = PROJECT_ROOT / "reports" / "kilo-rapidmlx-baseline" / "STATE.md"
    p2_fingerprint = "UNKNOWN"
    if p2_state.exists():
        content = p2_state.read_text()
        for line in content.split('\n'):
            if 'Configuration fingerprint:' in line:
                p2_fingerprint = line.split(':')[1].strip()
                break
    
    # Kilo version
    proc = subprocess.run(
        ["kilo", "--version"],
        capture_output=True,
        text=True,
    )
    kilo_version = proc.stdout.strip()
    
    # Rapid-MLX fingerprint
    proc = subprocess.run(
        ["curl", "-s", "-H", f"Authorization: Bearer {subprocess.os.environ.get('RAPID_MLX_API_KEY', 'test')}",
         "http://127.0.0.1:8000/v1/models"],
        capture_output=True,
        text=True,
    )
    try:
        models_data = json.loads(proc.stdout)
        rapid_mlx_fingerprint = hashlib.sha256(proc.stdout.encode()).hexdigest()[:16]
    except:
        rapid_mlx_fingerprint = "ERROR"
    
    # File hashes
    kilo_jsonc_hash = file_hash(PROJECT_ROOT / "kilo.jsonc")
    tool_hash = file_hash(PROJECT_ROOT / ".kilo" / "tool" / "bet_script_run.ts")
    manifest_hash = file_hash(PROJECT_ROOT / "config" / "bet-script-operations.json")
    
    # Fixture hashes
    fixtures = [
        "scripts/fixtures/bet-script-success.py",
        "scripts/fixtures/bet-script-failure.py",
        "scripts/fixtures/bet-script-slow.py",
        "scripts/fixtures/bet-script-large-output.py",
        "scripts/fixtures/bet-script-injection.py",
    ]
    fixture_hashes = {f: file_hash(PROJECT_ROOT / f) for f in fixtures}
    
    # Test harness hash
    test_harness_hash = file_hash(PROJECT_ROOT / "scripts" / "test-bet-script-executor.py")
    
    # Resolved permissions
    proc = subprocess.run(
        ["kilo", "debug", "config"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    config = json.loads(proc.stdout)
    permissions = config.get("permission", {})
    bet_script_run_perm = permissions.get("bet_script_run", "NOT_FOUND")
    
    # Build fingerprint
    fingerprint = {
        "phase": "P3",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_head": git_head,
        "phase_2_fingerprint": p2_fingerprint,
        "kilo_version": kilo_version,
        "rapid_mlx_fingerprint": rapid_mlx_fingerprint,
        "kilo_jsonc_hash": kilo_jsonc_hash,
        "custom_tool_hash": tool_hash,
        "manifest_hash": manifest_hash,
        "fixture_hashes": fixture_hashes,
        "test_harness_hash": test_harness_hash,
        "resolved_permissions": {
            "bet_script_run": bet_script_run_perm,
            "bash": permissions.get("bash", "NOT_FOUND"),
            "edit": permissions.get("edit", "NOT_FOUND"),
            "write": permissions.get("write", "NOT_FOUND"),
        },
        "mcp_servers_disabled": sum(1 for s in config.get("mcp", {}).values() if not s.get("enabled", True)),
    }
    
    # Generate fingerprint hash
    fingerprint_json = json.dumps(fingerprint, sort_keys=True)
    fingerprint_hash = hashlib.sha256(fingerprint_json.encode()).hexdigest()[:16]
    fingerprint["fingerprint_hash"] = fingerprint_hash
    
    # Print fingerprint
    print("FINGERPRINT:")
    print("-" * 40)
    for key, value in fingerprint.items():
        if isinstance(value, dict):
            print(f"  {key}:")
            for k, v in value.items():
                print(f"    {k}: {v}")
        else:
            print(f"  {key}: {value}")
    
    # Save fingerprint
    report_dir = PROJECT_ROOT / "reports" / "bet-script-executor"
    report_dir.mkdir(parents=True, exist_ok=True)
    fingerprint_path = report_dir / "fingerprint.json"
    
    with open(fingerprint_path, 'w') as f:
        json.dump(fingerprint, f, indent=2)
    
    print()
    print(f"Fingerprint hash: {fingerprint_hash}")
    print(f"Saved to: {fingerprint_path}")


if __name__ == "__main__":
    main()
