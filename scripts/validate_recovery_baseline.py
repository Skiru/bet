#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set, Tuple

RUN_ID = "20260611T062319Z_af9bc5a_RECOVERY"
REPO_ROOT = Path("/Users/mkoziol/projects/bet")
EXPECTED_BRANCH = "main"
EXPECTED_HEAD = "af9bc5a5f63f933670b931240aaae369cb8c0e03"
CONTROL_DIR = REPO_ROOT / "artifacts" / "control"
RECOVERY_DIR = REPO_ROOT / "artifacts" / "recovery" / RUN_ID
EVIDENCE_DIR = REPO_ROOT / "artifacts" / "evidence" / RUN_ID / "baseline_validation"
REPORTS_DIR = REPO_ROOT / "artifacts" / "reports" / RUN_ID
SECRET_VALUE_RE = re.compile(r"(?i)(api[_-]?key|token|secret|password|oauth)[^\n]{0,40}[:=][^\n]{1,200}")
HASH_LINE_RE = re.compile(r"^([0-9a-f]{64})  (.+)$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_status_sets() -> Dict[str, Set[str]]:
    raw = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=REPO_ROOT,
        text=False,
        capture_output=True,
        check=True,
    ).stdout
    entries = [e for e in raw.split(b"\0") if e]
    modified_paths: Set[str] = set()
    deleted_paths: Set[str] = set()
    untracked_paths: Set[str] = set()
    idx = 0
    while idx < len(entries):
        rec = entries[idx].decode("utf-8", "replace")
        x = rec[0]
        y = rec[1]
        path = rec[3:]
        if x == "?" and y == "?":
            untracked_paths.add(path)
            idx += 1
            continue
        if x in {"R", "C"} or y in {"R", "C"}:
            if idx + 1 < len(entries):
                path = entries[idx + 1].decode("utf-8", "replace")
                idx += 1
        modified_paths.add(path)
        if "D" in {x, y}:
            deleted_paths.add(path)
        idx += 1
    return {
        "modified": modified_paths,
        "deleted": deleted_paths,
        "untracked": untracked_paths,
    }


def allowed_dynamic_current_run(rel: str) -> bool:
    return rel.startswith(f"artifacts/evidence/{RUN_ID}/baseline_validation/")


def scan_secret_like_values(paths: List[Path]) -> List[str]:
    hits: List[str] = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for match in SECRET_VALUE_RE.finditer(text):
            snippet = match.group(0)
            if "environment_variable_names" in snippet:
                continue
            hits.append(f"{path.relative_to(REPO_ROOT).as_posix()}: {snippet[:160]}")
    return hits


def main() -> int:
    checks_executed: List[str] = []
    checks_passed: List[str] = []
    checks_failed: List[str] = []
    warnings: List[str] = []
    failed_invariants: List[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks_executed.append(name)
        if ok:
            checks_passed.append(name)
        else:
            checks_failed.append(name)
            failed_invariants.append(f"{name}:{detail}" if detail else name)

    required_files = [
        CONTROL_DIR / "controller_state.json",
        CONTROL_DIR / "phase_state.json",
        CONTROL_DIR / "progress.json",
        CONTROL_DIR / "SESSION_HANDOFF.md",
        CONTROL_DIR / "recovery_baseline_capture.py",
        CONTROL_DIR / "finalize_recovery_baseline.py",
        RECOVERY_DIR / "BASELINE.md",
        RECOVERY_DIR / "BASELINE_FILES.json",
        RECOVERY_DIR / "BASELINE_CONTENT.sha256",
        RECOVERY_DIR / "PRE_RECOVERY.diff",
        RECOVERY_DIR / "UNTRACKED_INVENTORY.json",
        RECOVERY_DIR / "REPOSITORY_STATE.json",
        RECOVERY_DIR / "WORKTREES.json",
        RECOVERY_DIR / "RAW_GIT_STATUS_Z.bin",
        RECOVERY_DIR / "PREVIOUS_AGENT_CHANGE_LEDGER.json",
        RECOVERY_DIR / "PREVIOUS_AGENT_CHANGE_LEDGER.md",
        RECOVERY_DIR / "DUPLICATE_ARTIFACT_GRAPH.json",
        RECOVERY_DIR / "STALE_ARTIFACT_REPORT.md",
        RECOVERY_DIR / "BASELINE_CAPTURE_PROVENANCE.json",
        RECOVERY_DIR / "BASELINE_DRIFT_REPORT.md",
        RECOVERY_DIR / "CURRENT_RUN_EXCLUSIONS.json",
        RECOVERY_DIR / "PRE_RECOVERY_PATH_INVENTORY.json",
        RECOVERY_DIR / "CURRENT_RUN_ARTIFACT_INVENTORY.json",
        REPO_ROOT / "scripts" / "validate_recovery_baseline.py",
    ]
    missing = [p.relative_to(REPO_ROOT).as_posix() for p in required_files if not p.exists()]
    check("required_files_exist", not missing, ",".join(missing))
    if missing:
        result = {
            "run_id": RUN_ID,
            "status": "FAIL",
            "validator_timestamp": now(),
            "checks_executed": checks_executed,
            "checks_passed": checks_passed,
            "checks_failed": checks_failed,
            "warnings": warnings,
            "failed_invariants": failed_invariants,
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1

    controller = load_json(CONTROL_DIR / "controller_state.json")
    phase_state = load_json(CONTROL_DIR / "phase_state.json")
    progress = load_json(CONTROL_DIR / "progress.json")
    repo_state = load_json(RECOVERY_DIR / "REPOSITORY_STATE.json")
    baseline_files = load_json(RECOVERY_DIR / "BASELINE_FILES.json")
    ledger = load_json(RECOVERY_DIR / "PREVIOUS_AGENT_CHANGE_LEDGER.json")
    duplicate_graph = load_json(RECOVERY_DIR / "DUPLICATE_ARTIFACT_GRAPH.json")
    exclusions = load_json(RECOVERY_DIR / "CURRENT_RUN_EXCLUSIONS.json")
    pre_inventory = load_json(RECOVERY_DIR / "PRE_RECOVERY_PATH_INVENTORY.json")
    current_inventory = load_json(RECOVERY_DIR / "CURRENT_RUN_ARTIFACT_INVENTORY.json")
    provenance = load_json(RECOVERY_DIR / "BASELINE_CAPTURE_PROVENANCE.json")

    run_ids = {
        controller.get("run_id"),
        phase_state.get("run_id"),
        progress.get("run_id"),
        repo_state.get("run_id"),
        baseline_files.get("run_id"),
        ledger.get("run_id"),
        exclusions.get("run_id"),
        pre_inventory.get("run_id"),
        current_inventory.get("run_id"),
        provenance.get("run_id"),
    }
    check("run_id_consistency", run_ids == {RUN_ID}, str(sorted(run_ids)))

    branch = subprocess.run(["git", "branch", "--show-current"], cwd=REPO_ROOT, text=True, capture_output=True, check=True).stdout.strip()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True, capture_output=True, check=True).stdout.strip()
    root = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=REPO_ROOT, text=True, capture_output=True, check=True).stdout.strip()
    check("live_git_identity", branch == EXPECTED_BRANCH and head == EXPECTED_HEAD and root == str(REPO_ROOT), f"{root}:{branch}:{head}")
    check("controller_identity", controller.get("branch") == EXPECTED_BRANCH and controller.get("head_sha") == EXPECTED_HEAD and controller.get("repository_root") == str(REPO_ROOT), json.dumps(controller, sort_keys=True))

    check("implementation_unauthorized", controller.get("implementation_authorized") is False, str(controller.get("implementation_authorized")))
    check("r2_not_started", phase_state.get("phases", {}).get("R2 claim/evidence reconciliation", {}).get("status") == "NOT_STARTED", json.dumps(phase_state.get("phases", {}).get("R2 claim/evidence reconciliation", {}), sort_keys=True))

    live = git_status_sets()
    pre_modified = set(pre_inventory["tracked_modified_paths"])
    pre_deleted = set(pre_inventory["tracked_deleted_paths"])
    pre_untracked = set(pre_inventory["untracked_file_paths"])
    current_artifacts = {item["path"] for item in current_inventory["artifacts"]}
    allowed_dynamic = {p for p in live["untracked"] if allowed_dynamic_current_run(p)}
    expected_untracked_live = pre_untracked | current_artifacts | allowed_dynamic

    check("pre_recovery_tracked_modified_match", live["modified"] == pre_modified, f"missing={sorted(pre_modified - live['modified'])};extra={sorted(live['modified'] - pre_modified)}")
    check("pre_recovery_tracked_deleted_match", live["deleted"] == pre_deleted, f"missing={sorted(pre_deleted - live['deleted'])};extra={sorted(live['deleted'] - pre_deleted)}")
    check("live_untracked_match", live["untracked"] == expected_untracked_live, f"missing={sorted(expected_untracked_live - live['untracked'])};extra={sorted(live['untracked'] - expected_untracked_live)}")

    ledger_paths = {entry["path"] for entry in ledger["entries"]}
    expected_ledger = pre_modified | pre_deleted | pre_untracked
    check("ledger_path_reconciliation", ledger_paths == expected_ledger, f"missing={sorted(expected_ledger - ledger_paths)};extra={sorted(ledger_paths - expected_ledger)}")
    counts = ledger.get("counts", {})
    check("ledger_count_reconciliation", counts.get("git_modified_tracked_count") == len(pre_modified) and counts.get("git_deleted_tracked_count") == len(pre_deleted) and counts.get("git_untracked_count") == len(pre_untracked) and counts.get("ledger_path_count") == len(expected_ledger), json.dumps(counts, sort_keys=True))

    current_run_paths_in_ledger = sorted([p for p in ledger_paths if p.startswith("artifacts/control/") or p.startswith(f"artifacts/recovery/{RUN_ID}/") or p.startswith(f"artifacts/evidence/{RUN_ID}/") or p.startswith(f"artifacts/reports/{RUN_ID}/") or p == "scripts/validate_recovery_baseline.py"])
    check("no_current_run_artifacts_in_pre_recovery_ledger", not current_run_paths_in_ledger, ",".join(current_run_paths_in_ledger))

    excluded = {item["path"] for item in exclusions["exclusions"]}
    check("exclusions_removed_from_pre_recovery_inventory", not (excluded & pre_untracked), str(sorted(excluded & pre_untracked)))

    manifest_lines = [line for line in (RECOVERY_DIR / "BASELINE_CONTENT.sha256").read_text(encoding="utf-8").splitlines() if line.strip()]
    seen_paths: Set[str] = set()
    manifest_ok = True
    manifest_detail: List[str] = []
    for line in manifest_lines:
        match = HASH_LINE_RE.match(line)
        if not match:
            manifest_ok = False
            manifest_detail.append(f"invalid:{line}")
            continue
        digest, rel = match.groups()
        if rel.endswith("BASELINE_CONTENT.sha256"):
            manifest_ok = False
            manifest_detail.append("self_hash_cycle")
            continue
        path = REPO_ROOT / rel
        if not path.exists() or not path.is_file():
            manifest_ok = False
            manifest_detail.append(f"missing:{rel}")
            continue
        if sha256_file(path) != digest:
            manifest_ok = False
            manifest_detail.append(f"mismatch:{rel}")
        if rel in seen_paths:
            manifest_ok = False
            manifest_detail.append(f"duplicate:{rel}")
        seen_paths.add(rel)
    check("hash_manifest_integrity", manifest_ok, ";".join(manifest_detail[:20]))

    inventory_ok = True
    inventory_detail: List[str] = []
    for item in current_inventory["artifacts"]:
        rel = item["path"]
        digest = item.get("sha256")
        path = REPO_ROOT / rel
        if not HEX64_RE.match(digest or ""):
            inventory_ok = False
            inventory_detail.append(f"invalid_sha:{rel}")
            continue
        if not path.exists() or not path.is_file():
            inventory_ok = False
            inventory_detail.append(f"missing:{rel}")
            continue
        if sha256_file(path) != digest:
            inventory_ok = False
            inventory_detail.append(f"mismatch:{rel}")
    check("current_run_artifact_inventory_integrity", inventory_ok, ";".join(inventory_detail[:20]))

    duplicate_ok = True
    duplicate_detail: List[str] = []
    for artifact in duplicate_graph.get("artifacts", []):
        if artifact.get("classification") == "current_run" and RUN_ID not in artifact.get("path", ""):
            duplicate_ok = False
            duplicate_detail.append(artifact.get("path", ""))
    check("historical_evidence_not_marked_current", duplicate_ok, ";".join(duplicate_detail[:20]))

    secret_paths = [REPO_ROOT / item["path"] for item in current_inventory["artifacts"]]
    secret_hits = scan_secret_like_values(secret_paths)
    check("no_secret_values_in_generated_artifacts", not secret_hits, ";".join(secret_hits[:10]))

    production_changed = sorted([p for p in pre_modified | pre_deleted | pre_untracked if p.startswith("src/") or p.startswith("tests/")])
    if production_changed:
        warnings.append(f"pre_existing_production_or_test_changes_present:{production_changed}")
    current_run_production = sorted([p for p in current_artifacts if p.startswith("src/") or p.startswith("tests/")])
    check("no_current_run_production_code_artifacts", not current_run_production, ";".join(current_run_production))

    result = {
        "run_id": RUN_ID,
        "status": "PASS" if not checks_failed else "FAIL",
        "validator_timestamp": now(),
        "checks_executed": checks_executed,
        "checks_passed": checks_passed,
        "checks_failed": checks_failed,
        "warnings": warnings,
        "failed_invariants": failed_invariants,
        "counts": {
            "tracked_modified": len(pre_modified),
            "tracked_deleted": len(pre_deleted),
            "untracked_top_level_entries": pre_inventory["counts"]["untracked_top_level_entries"],
            "untracked_file_entries_pre_recovery": len(pre_untracked),
            "current_run_artifact_count": len(current_artifacts),
            "baseline_ledger_path_count": len(expected_ledger),
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not checks_failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
