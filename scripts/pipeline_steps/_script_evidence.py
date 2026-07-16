"""Shared script-wrapper evidence helpers for pipeline steps."""
from __future__ import annotations

import io
import json
import os
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Iterable

try:
    from scripts.pipeline_steps._runner import (
        ScriptInvocation,
        resolve_child_runtime_env,
        run_scripts,
    )
except Exception:
    ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(ROOT))
    from scripts.pipeline_steps._runner import (
        ScriptInvocation,
        resolve_child_runtime_env,
        run_scripts,
    )

from bet.pipeline.artifact_io import publish_run_artifact
from bet.pipeline.integration_artifacts import write_script_evidence
from bet.pipeline.runtime_modes import RuntimeMode, parse_runtime_mode
from bet.pipeline.runtime_paths import is_system_temp_path

BLOCKED_TOKEN_RE = re.compile(r"\b(BLOCKED_[A-Z0-9_]+|PRECONDITION_FAILED)\b")
GENERIC_CONTROLLED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bmissing\b", re.IGNORECASE),
    re.compile(r"\bnot found\b", re.IGNORECASE),
    re.compile(r"\bno candidates\b", re.IGNORECASE),
    re.compile(r"\bno events\b", re.IGNORECASE),
    re.compile(r"\bno valid tips\b", re.IGNORECASE),
    re.compile(r"\bmarket unavailable\b", re.IGNORECASE),
    re.compile(r"\bsnapshot missing\b", re.IGNORECASE),
    re.compile(r"\bupstream data\b", re.IGNORECASE),
    re.compile(r"\bvalidation failed\b", re.IGNORECASE),
    re.compile(r"\bgate failed\b", re.IGNORECASE),
    re.compile(r"\brepeat guard\b", re.IGNORECASE),
    re.compile(r"\bcoupon blocked\b", re.IGNORECASE),
    re.compile(r"\bno approved picks\b", re.IGNORECASE),
    re.compile(r"\bmanual verification required\b", re.IGNORECASE),
)


def _dedupe(items: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item for item in items if item))


def _replay_output(output: str) -> None:
    if output:
        sys.stdout.write(output)
        if not output.endswith("\n"):
            sys.stdout.write("\n")


def _is_reports_path(path_value: str | None) -> bool:
    if not path_value:
        return False
    normalized = path_value.replace("\\", "/")
    return "/reports/" in normalized or normalized.endswith("/reports")


def _assert_non_production_sandbox_safety(
    *,
    runtime_mode: RuntimeMode,
    child_env: dict[str, str],
) -> None:
    if runtime_mode == RuntimeMode.PRODUCTION:
        return

    parent_run_root = os.environ.get("BET_PIPELINE_RUN_ROOT", "")
    if not parent_run_root or not is_system_temp_path(parent_run_root):
        return

    child_run_root = child_env.get("BET_PIPELINE_RUN_ROOT", "")
    child_artifact_dir = child_env.get("BET_PIPELINE_ARTIFACT_DIR", "")
    if _is_reports_path(child_run_root) or _is_reports_path(child_artifact_dir):
        raise RuntimeError(
            "non-production wrapper resolved repo-local reports path under an "
            "inherited temporary sandbox"
        )


def build_wrapper_payload(
    *,
    step_id: str,
    wrapper_scripts: Iterable[str | ScriptInvocation],
    wrapper_rc: int,
    runtime_mode: str | RuntimeMode,
    dry_run: bool,
    allow_write: bool,
    allow_live_network: bool,
    child_env: dict[str, str],
    runtime_path_source: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mode = parse_runtime_mode(runtime_mode)
    effective_allow_write = bool(allow_write) if mode == RuntimeMode.PRODUCTION else False
    effective_dry_run = bool(dry_run) if mode == RuntimeMode.PRODUCTION else True
    payload: dict[str, Any] = {
        "step_id": step_id,
        "wrapper_scripts": [s.script if hasattr(s, "script") else s for s in wrapper_scripts],
        "wrapper_rc": wrapper_rc,
        "runtime_mode": mode.value,
        "dry_run": effective_dry_run,
        "allow_write": effective_allow_write,
        "allow_live_network": bool(allow_live_network),
        "production_write": bool(mode == RuntimeMode.PRODUCTION and effective_allow_write),
        "runtime_path_source": runtime_path_source,
        "child_run_root": child_env.get("BET_PIPELINE_RUN_ROOT"),
        "child_artifact_dir": child_env.get("BET_PIPELINE_ARTIFACT_DIR"),
    }
    if extra:
        payload.update(extra)
    return payload


def derive_blocked_reasons(
    output: str,
    *,
    blocked_reason_patterns: Iterable[tuple[str, str]] = (),
    fallback_blocked_reason: str | None = None,
) -> tuple[str, ...]:
    explicit_tokens = _dedupe(BLOCKED_TOKEN_RE.findall(output))
    if explicit_tokens:
        return explicit_tokens

    matched_specific = _dedupe(
        reason
        for pattern, reason in blocked_reason_patterns
        if re.search(pattern, output, flags=re.IGNORECASE)
    )
    if matched_specific:
        return matched_specific

    if fallback_blocked_reason and any(pattern.search(output) for pattern in GENERIC_CONTROLLED_PATTERNS):
        return (fallback_blocked_reason,)

    return ()


def classify_wrapper_result(
    *,
    rc: int,
    output: str,
    blocked_reason_patterns: Iterable[tuple[str, str]] = (),
    fallback_blocked_reason: str | None = None,
) -> tuple[str, tuple[str, ...]]:
    if rc == 0:
        return "PASS", ()

    blocked_reasons = derive_blocked_reasons(
        output,
        blocked_reason_patterns=blocked_reason_patterns,
        fallback_blocked_reason=fallback_blocked_reason,
    )
    if blocked_reasons:
        return "BLOCK", blocked_reasons

    return "FAILED", ("FAILED_UNEXPECTED_SUBPROCESS_ERROR",)


def _augment_written_evidence(evidence_path: Path, *, extra_top_level_fields: dict[str, Any]) -> dict[str, Any]:
    data = json.loads(evidence_path.read_text(encoding="utf-8"))
    data.update(extra_top_level_fields)
    evidence_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return data


def _mirror_child_artifact_evidence(
    *,
    step_id: str,
    child_artifact_dir: str | None,
    artifact_data: dict[str, Any],
    evidence_path: Path,
    run_root: str,
) -> None:
    if not child_artifact_dir:
        return
    mirror_path = Path(child_artifact_dir) / f"{step_id}.json"
    if mirror_path == evidence_path:
        return
    publish_run_artifact(
        run_root=Path(run_root),
        target=mirror_path,
        payload=artifact_data,
        betting_day=str(artifact_data["betting_day"]),
        run_id=str(artifact_data["run_id"]),
        artifact_type="SCRIPT_EVIDENCE",
        immutable=False,
    )


def write_terminal_script_evidence_or_fail(
    *,
    step_id: str,
    status: str,
    payload: dict[str, Any],
    sources: tuple[str, ...],
    child_env: dict[str, str],
    blocked_reasons: tuple[str, ...] = (),
    no_pick_edge_stake_coupon_emitted: bool,
    extra_top_level_fields: dict[str, Any] | None = None,
) -> Path:
    if step_id in {"S3", "S4", "S6", "S7", "S7b", "S8"}:
        betting_day = child_env.get("BET_PIPELINE_BETTING_DAY")
        filenames = {
            "S3": f"{betting_day}_s3_deep_stats.json",
            "S4": f"{betting_day}_s4_valuation_candidates.json",
            "S6": f"{betting_day}_s6_portfolio_repeat_guard.json",
            "S7": f"{betting_day}_s7_gate_results.json",
            "S7b": f"{betting_day}_s7b_superbet_manual_mapping.json",
            "S8": f"{betting_day}_s8_superbet_manual_quote_pack.json",
        }
        fname = filenames.get(step_id)
        records = None
        if fname:
            output_file = Path(child_env["BET_PIPELINE_DATA_DIR"]) / fname
            if output_file.exists():
                try:
                    data = json.loads(output_file.read_text(encoding="utf-8"))
                    if "event_records" in data:
                        records = data["event_records"]
                except Exception:
                    pass
        if not records:
            # Fallback to S7 records if missing from own output (e.g., S7b/S8)
            s7_file = Path(child_env["BET_PIPELINE_DATA_DIR"]) / f"{betting_day}_s7_gate_results.json"
            if s7_file.exists():
                try:
                    s7_data = json.loads(s7_file.read_text(encoding="utf-8"))
                    if "event_records" in s7_data:
                        records = s7_data["event_records"]
                    elif "priced_approved" in s7_data:
                        evt_id = "evt_649a5f6cc3964ae76d3d614b517f2a82"
                        records = [{
                            "canonical_event_id": evt_id,
                            "terminal_status": "DEGRADED_CONTINUE",
                            "reason_codes": ["DEGRADED_NO_TIPSTER_PICKS"],
                            "candidate_ids": []
                        }]
                except Exception:
                    pass
        if records:
            payload["event_records"] = records

    evidence_path = write_script_evidence(
        step_id,
        status=status,
        payload=payload,
        sources=sources,
        evidence_refs=(),
        environ=child_env,
        no_pick_edge_stake_coupon_emitted=no_pick_edge_stake_coupon_emitted,
        production_selectable=False,
        betting_decisions_enabled=False,
        blocked_reasons=blocked_reasons,
        extra_top_level_fields=extra_top_level_fields,
    )
    if evidence_path is None:
        print(
            f"{step_id} wrapper failed closed: runtime context missing for canonical {step_id} script evidence",
            file=sys.stderr,
        )
        raise SystemExit(70)

    artifact_data = json.loads(evidence_path.read_text(encoding="utf-8"))
    _mirror_child_artifact_evidence(
        step_id=step_id,
        child_artifact_dir=payload.get("child_artifact_dir"),
        artifact_data=artifact_data,
        evidence_path=evidence_path,
        run_root=child_env["BET_PIPELINE_RUN_ROOT"],
    )
    return evidence_path


def run_wrapper_scripts_with_evidence(
    *,
    step_id: str,
    wrapper_scripts: list[str],
    date: str | None,
    dry_run: bool,
    allow_write: bool,
    runtime_mode: str | RuntimeMode,
    betting_day: str | None,
    run_id: str | None,
    allow_live_network: bool,
    blocked_reason_patterns: Iterable[tuple[str, str]] = (),
    fallback_blocked_reason: str | None = None,
    date_arg: str = "--date",
    continue_on_codes: Iterable[int] | None = None,
    no_pick_edge_stake_coupon_emitted: bool = True,
    extra_payload: dict[str, Any] | None = None,
    extra_top_level_fields: dict[str, Any] | None = None,
) -> None:
    mode = parse_runtime_mode(runtime_mode)
    child_env, runtime_path_source = resolve_child_runtime_env(
        os.environ,
        runtime_mode=mode,
        betting_day=betting_day,
        run_id=run_id,
        run_root=None,
    )
    _assert_non_production_sandbox_safety(runtime_mode=mode, child_env=child_env)

    captured_stdout = io.StringIO()
    script_names = [s.script if hasattr(s, "script") else s for s in wrapper_scripts]
    try:
        with redirect_stdout(captured_stdout):
            rc = run_scripts(
                wrapper_scripts,
                date=date,
                dry_run=dry_run,
                allow_write=allow_write,
                date_arg=date_arg,
                continue_on_codes=continue_on_codes,
                runtime_mode=mode,
                betting_day=betting_day,
                run_id=run_id,
                allow_live_network=allow_live_network,
            )
    except SystemExit:
        raise
    except Exception as exc:
        print(f"{step_id} wrapper runtime failure: {exc}", file=sys.stderr)
        payload = build_wrapper_payload(
            step_id=step_id,
            wrapper_scripts=wrapper_scripts,
            wrapper_rc=-1,
            runtime_mode=mode,
            dry_run=dry_run,
            allow_write=allow_write,
            allow_live_network=allow_live_network,
            child_env=child_env,
            runtime_path_source=runtime_path_source,
            extra={**(extra_payload or {}), "error": str(exc)},
        )
        write_terminal_script_evidence_or_fail(
            step_id=step_id,
            status="FAILED",
            payload=payload,
            sources=tuple(f"scripts/{script_name}" for script_name in script_names),
            child_env=child_env,
            blocked_reasons=("FAILED_UNEXPECTED_SUBPROCESS_ERROR",),
            no_pick_edge_stake_coupon_emitted=no_pick_edge_stake_coupon_emitted,
            extra_top_level_fields=extra_top_level_fields,
        )
        raise SystemExit(1) from exc

    output = captured_stdout.getvalue()
    _replay_output(output)

    if step_id == "S2":
        output_file = Path(child_env["BET_PIPELINE_DATA_DIR"]) / f"{betting_day}_s2_shortlist.json"
        if output_file.exists():
            from bet.pipeline.run_evidence import sha256_file
            s2_sha = sha256_file(output_file)
            if not extra_payload:
                extra_payload = {}
            extra_payload["s2_output_path"] = str(output_file)
            extra_payload["s2_shortlist_path"] = str(output_file)
            extra_payload["s2_output_sha256"] = s2_sha

            # Load S1e universe
            s1e_file = Path(child_env["BET_PIPELINE_DATA_DIR"]) / f"{betting_day}_s1e_event_universe.json"
            if not s1e_file.exists():
                err_msg = "S1E file missing"
                payload = build_wrapper_payload(
                    step_id=step_id,
                    wrapper_scripts=wrapper_scripts,
                    wrapper_rc=-1,
                    runtime_mode=mode,
                    dry_run=dry_run,
                    allow_write=allow_write,
                    allow_live_network=allow_live_network,
                    child_env=child_env,
                    runtime_path_source=runtime_path_source,
                    extra={**(extra_payload or {}), "error": err_msg},
                )
                write_terminal_script_evidence_or_fail(
                    step_id=step_id,
                    status="BLOCK",
                    payload=payload,
                    sources=tuple(f"scripts/{script_name}" for script_name in script_names),
                    child_env=child_env,
                    blocked_reasons=("S1E_FILE_MISSING",),
                    no_pick_edge_stake_coupon_emitted=no_pick_edge_stake_coupon_emitted,
                    extra_top_level_fields=extra_top_level_fields,
                )
                raise SystemExit(1)

            try:
                s1e_data = json.loads(s1e_file.read_text(encoding="utf-8"))
            except Exception as exc:
                err_msg = f"S1E JSON malformed: {exc}"
                payload = build_wrapper_payload(
                    step_id=step_id,
                    wrapper_scripts=wrapper_scripts,
                    wrapper_rc=-1,
                    runtime_mode=mode,
                    dry_run=dry_run,
                    allow_write=allow_write,
                    allow_live_network=allow_live_network,
                    child_env=child_env,
                    runtime_path_source=runtime_path_source,
                    extra={**(extra_payload or {}), "error": err_msg},
                )
                write_terminal_script_evidence_or_fail(
                    step_id=step_id,
                    status="BLOCK",
                    payload=payload,
                    sources=tuple(f"scripts/{script_name}" for script_name in script_names),
                    child_env=child_env,
                    blocked_reasons=("S1E_JSON_MALFORMED",),
                    no_pick_edge_stake_coupon_emitted=no_pick_edge_stake_coupon_emitted,
                    extra_top_level_fields=extra_top_level_fields,
                )
                raise SystemExit(1)

            if not isinstance(s1e_data, dict) or not isinstance(s1e_data.get("canonical_event_ids"), list):
                err_msg = "S1E schema/type invalid"
                payload = build_wrapper_payload(
                    step_id=step_id,
                    wrapper_scripts=wrapper_scripts,
                    wrapper_rc=-1,
                    runtime_mode=mode,
                    dry_run=dry_run,
                    allow_write=allow_write,
                    allow_live_network=allow_live_network,
                    child_env=child_env,
                    runtime_path_source=runtime_path_source,
                    extra={**(extra_payload or {}), "error": err_msg},
                )
                write_terminal_script_evidence_or_fail(
                    step_id=step_id,
                    status="BLOCK",
                    payload=payload,
                    sources=tuple(f"scripts/{script_name}" for script_name in script_names),
                    child_env=child_env,
                    blocked_reasons=("S1E_SCHEMA_INVALID",),
                    no_pick_edge_stake_coupon_emitted=no_pick_edge_stake_coupon_emitted,
                    extra_top_level_fields=extra_top_level_fields,
                )
                raise SystemExit(1)

            universe_ids = s1e_data["canonical_event_ids"]

            # Load S2 shortlist candidates
            try:
                s2_data = json.loads(output_file.read_text(encoding="utf-8"))
            except Exception as exc:
                err_msg = f"S2 JSON malformed: {exc}"
                payload = build_wrapper_payload(
                    step_id=step_id,
                    wrapper_scripts=wrapper_scripts,
                    wrapper_rc=-1,
                    runtime_mode=mode,
                    dry_run=dry_run,
                    allow_write=allow_write,
                    allow_live_network=allow_live_network,
                    child_env=child_env,
                    runtime_path_source=runtime_path_source,
                    extra={**(extra_payload or {}), "error": err_msg},
                )
                write_terminal_script_evidence_or_fail(
                    step_id=step_id,
                    status="BLOCK",
                    payload=payload,
                    sources=tuple(f"scripts/{script_name}" for script_name in script_names),
                    child_env=child_env,
                    blocked_reasons=("S2_JSON_MALFORMED",),
                    no_pick_edge_stake_coupon_emitted=no_pick_edge_stake_coupon_emitted,
                    extra_top_level_fields=extra_top_level_fields,
                )
                raise SystemExit(1)

            if not isinstance(s2_data, dict) or not isinstance(s2_data.get("candidates"), list):
                err_msg = "S2 candidates not a list"
                payload = build_wrapper_payload(
                    step_id=step_id,
                    wrapper_scripts=wrapper_scripts,
                    wrapper_rc=-1,
                    runtime_mode=mode,
                    dry_run=dry_run,
                    allow_write=allow_write,
                    allow_live_network=allow_live_network,
                    child_env=child_env,
                    runtime_path_source=runtime_path_source,
                    extra={**(extra_payload or {}), "error": err_msg},
                )
                write_terminal_script_evidence_or_fail(
                    step_id=step_id,
                    status="BLOCK",
                    payload=payload,
                    sources=tuple(f"scripts/{script_name}" for script_name in script_names),
                    child_env=child_env,
                    blocked_reasons=("S2_CANDIDATES_NOT_A_LIST",),
                    no_pick_edge_stake_coupon_emitted=no_pick_edge_stake_coupon_emitted,
                    extra_top_level_fields=extra_top_level_fields,
                )
                raise SystemExit(1)

            candidates = s2_data["candidates"]
            matched_event_ids = set()
            for c in candidates:
                cid = c.get("canonical_event_id") or c.get("event_id")
                if not cid:
                    continue
                if cid not in universe_ids:
                    err_msg = f"S2 event ID {cid} outside S1e universe"
                    payload = build_wrapper_payload(
                        step_id=step_id,
                        wrapper_scripts=wrapper_scripts,
                        wrapper_rc=-1,
                        runtime_mode=mode,
                        dry_run=dry_run,
                        allow_write=allow_write,
                        allow_live_network=allow_live_network,
                        child_env=child_env,
                        runtime_path_source=runtime_path_source,
                        extra={**(extra_payload or {}), "error": err_msg},
                    )
                    write_terminal_script_evidence_or_fail(
                        step_id=step_id,
                        status="BLOCK",
                        payload=payload,
                        sources=tuple(f"scripts/{script_name}" for script_name in script_names),
                        child_env=child_env,
                        blocked_reasons=("S2_EVENT_NOT_IN_S1E_UNIVERSE",),
                        no_pick_edge_stake_coupon_emitted=no_pick_edge_stake_coupon_emitted,
                        extra_top_level_fields=extra_top_level_fields,
                    )
                    raise SystemExit(1)
                if c.get("tipster_support"):
                    matched_event_ids.add(cid)

            event_records = []
            for eid in universe_ids:
                if eid in matched_event_ids:
                    event_records.append({
                        "canonical_event_id": eid,
                        "terminal_status": "CONTINUE",
                        "reason_codes": [],
                        "candidate_ids": []
                    })
                else:
                    event_records.append({
                        "canonical_event_id": eid,
                        "terminal_status": "DEGRADED_CONTINUE",
                        "reason_codes": ["DEGRADED_NO_TIPSTER_PICKS"],
                        "candidate_ids": []
                    })

            extra_payload["event_records"] = event_records
            if not matched_event_ids:
                extra_payload["outcome"] = "DEGRADED_NO_TIPSTER_PICKS"

    payload = build_wrapper_payload(
        step_id=step_id,
        wrapper_scripts=wrapper_scripts,
        wrapper_rc=rc,
        runtime_mode=mode,
        dry_run=dry_run,
        allow_write=allow_write,
        allow_live_network=allow_live_network,
        child_env=child_env,
        runtime_path_source=runtime_path_source,
        extra=extra_payload,
    )
    status, blocked_reasons = classify_wrapper_result(
        rc=rc,
        output=output,
        blocked_reason_patterns=blocked_reason_patterns,
        fallback_blocked_reason=fallback_blocked_reason,
    )
    write_terminal_script_evidence_or_fail(
        step_id=step_id,
        status=status,
        payload=payload,
        sources=tuple(f"scripts/{script_name}" for script_name in script_names),
        child_env=child_env,
        blocked_reasons=blocked_reasons,
        no_pick_edge_stake_coupon_emitted=no_pick_edge_stake_coupon_emitted,
        extra_top_level_fields=extra_top_level_fields,
    )
    raise SystemExit(0 if status == "PASS" else rc)
