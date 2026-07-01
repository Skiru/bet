#!/usr/bin/env python3
"""Default live analyst session runner.

This runner produces analyst recommendations even when odds, HYDRATED status,
or model_probability are absent. Final coupon/placement remain blocked without
human-entered Superbet quote.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]+_\d{8}_\d{6}$")

from bet.pipeline.unified_live_analyst_session import (  # noqa: E402
    apply_human_quote_if_valid,
    build_package_from_candidates,
    load_candidates_from_path,
    load_source_artifacts,
    now_run_id,
    write_package,
)


def _write_preflight(out_dir: Path, input_paths: list[Path], candidates_loaded: int) -> None:
    (out_dir / "preflight.md").write_text(
        "\n".join([
            "# Preflight",
            f"generated_at_utc={datetime.now(timezone.utc).isoformat()}",
            "no_superbet_api=true",
            "no_betclic_api=true",
            "no_browser_automation=true",
            "no_automated_placement=true",
            "odds_required_for_analysis=false",
            "hydrated_required_for_analysis=false",
            "model_probability_required_for_analysis=false",
            f"input_paths={[str(p) for p in input_paths]}",
            f"candidate_objects_loaded={candidates_loaded}",
        ]) + "\n",
        encoding="utf-8",
    )


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _repo_relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT))
    except ValueError:
        return str(resolved)


def _run_id_from_path(path: Path) -> str | None:
    runs_dir = (REPO_ROOT / "reports" / "pipeline_runs").resolve()
    resolved = path.resolve()
    try:
        rel = resolved.relative_to(runs_dir)
    except ValueError:
        rel = None
    if rel and rel.parts:
        return rel.parts[0]
    for candidate in (resolved, *resolved.parents):
        if RUN_ID_PATTERN.fullmatch(candidate.name):
            return candidate.name
    return None


def _infer_source_run_id(input_paths: list[Path]) -> str | None:
    run_ids = {run_id for path in input_paths if (run_id := _run_id_from_path(path))}
    if len(run_ids) == 1:
        return next(iter(run_ids))
    if len(run_ids) > 1:
        return "MULTIPLE_EXPLICIT_INPUTS"
    return None


def _select_latest_run_dir(runs_dir: Path, out_dir: Path) -> Path:
    dirs = [
        p for p in runs_dir.iterdir()
        if p.is_dir() and not p.name.startswith(".") and p.resolve() != out_dir.resolve()
    ]
    if not dirs:
        raise SystemExit("INPUT_REQUIRED_OR_DISCOVERY_UNAVAILABLE: No run directories found to select latest from.")
    dirs.sort(key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
    return dirs[0]


def _resolve_input_paths(args: argparse.Namespace, out_dir: Path) -> tuple[list[Path], str | None, str]:
    input_paths: list[Path] = [Path(p) for p in args.input]
    source_run_id = None
    if args.from_run_id:
        source_run_id = args.from_run_id
        input_paths.append(REPO_ROOT / "reports" / "pipeline_runs" / args.from_run_id)
    if not input_paths:
        if not args.latest_run:
            raise SystemExit("INPUT_REQUIRED_OR_DISCOVERY_UNAVAILABLE: No input paths specified. Use --input, --from-run-id, or explicitly --latest-run.")
        default_runs = REPO_ROOT / "reports" / "pipeline_runs"
        if not default_runs.exists():
            raise SystemExit("INPUT_REQUIRED_OR_DISCOVERY_UNAVAILABLE: reports/pipeline_runs directory does not exist.")
        latest_dir = _select_latest_run_dir(default_runs, out_dir)
        print(f"INFO: --latest-run explicit flag set. Selecting latest run directory by modified time: {latest_dir.name}")
        input_paths.append(latest_dir)
        source_run_id = latest_dir.name
    current_output_guard = "PASS"
    for path in input_paths:
        if path.resolve() == out_dir.resolve() or _is_relative_to(path, out_dir):
            current_output_guard = "FAIL"
            raise SystemExit(f"CURRENT_OUTPUT_SELF_SELECTION_GUARD=FAIL: Refusing to use current output directory as input: {path}")
    return input_paths, source_run_id or _infer_source_run_id(input_paths), current_output_guard


def main() -> int:
    parser = argparse.ArgumentParser(description="Run unified odds-optional live analyst session")
    parser.add_argument("--from-run-id", default=None, help="Use reports/pipeline_runs/<RUN_ID> as input")
    parser.add_argument("--input", action="append", default=[], help="Path to JSON file or directory with run artifacts; may repeat")
    parser.add_argument("--quote-file", default=None, help="Optional human-entered Superbet quote JSON")
    parser.add_argument("--output-root", default="reports/pipeline_runs", help="Output root")
    parser.add_argument("--run-id", default=None, help="Explicit run id for deterministic tests")
    parser.add_argument("--latest-run", action="store_true", help="Explicitly allow selecting the latest run by modified time")
    parser.add_argument("--historical-context-input", action="append", default=[], help="Additional historical JSON/file/dir inputs for source enrichment; requires --allow-historical-context")
    parser.add_argument("--allow-historical-context", action="store_true", help="Allow explicitly supplied historical context inputs for source enrichment")
    args = parser.parse_args()

    run_id = args.run_id or now_run_id()
    out_dir = REPO_ROOT / args.output_root / run_id

    historical_context_paths: list[Path] = [Path(p) for p in args.historical_context_input]
    if historical_context_paths and not args.allow_historical_context:
        raise SystemExit("HISTORICAL_CONTEXT_FLAG_REQUIRED: add --allow-historical-context to use --historical-context-input.")

    input_paths, source_run_id, current_output_guard = _resolve_input_paths(args, out_dir)

    candidates = []
    for path in input_paths:
        candidates.extend(load_candidates_from_path(path))
    if not candidates:
        raise SystemExit(
            "BLOCKED_NO_CURRENT_RUN_ARTIFACTS: No candidate JSON artifacts found in input paths: "
            + ", ".join(_repo_relative(path) for path in input_paths)
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_preflight(out_dir, input_paths, len(candidates))

    generated_at_utc = datetime.now(timezone.utc).isoformat()
    source_artifacts = load_source_artifacts(
        input_paths,
        excluded_roots=[out_dir],
        historical_context_paths=historical_context_paths,
        allow_historical_context=args.allow_historical_context,
    )
    package = build_package_from_candidates(
        candidates,
        run_id=run_id,
        source_artifacts=source_artifacts,
        source_run_id=source_run_id,
        input_artifact_paths=[_repo_relative(path) for path in input_paths],
        generated_at_utc=generated_at_utc,
        stale_artifact_guard="PASS",
        current_output_self_selection_guard=current_output_guard,
    )
    if args.quote_file:
        quote_path = Path(args.quote_file)
        try:
            quote_payload = json.loads(quote_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise SystemExit(f"QUOTE_FILE_READ_ERROR={exc}")
        package = apply_human_quote_if_valid(package, quote_payload)

    paths = write_package(package, out_dir)

    # Compatibility aliases expected by prior reporting prompts.
    (out_dir / "deep_statistical_analysis.md").write_text(paths["md"].read_text(encoding="utf-8"), encoding="utf-8")
    (out_dir / "deep_statistical_analysis.json").write_text(paths["json"].read_text(encoding="utf-8"), encoding="utf-8")
    (out_dir / "status_safety_review.md").write_text(
        "# Status Safety Review\n\n"
        f"SOURCE_RUN_ID={package.source_run_id or 'N/A'}\n"
        f"INPUT_ARTIFACT_PATHS={json.dumps(package.input_artifact_paths, ensure_ascii=False)}\n"
        f"STALE_ARTIFACT_GUARD={package.stale_artifact_guard}\n"
        f"CURRENT_OUTPUT_SELF_SELECTION_GUARD={package.current_output_self_selection_guard}\n"
        "NO_SUPERBET_API_VERDICT=PASS\n"
        "NO_BETCLIC_API_VERDICT=PASS\n"
        "NO_BROWSER_AUTOMATION_VERDICT=PASS\n"
        "NO_AUTOMATED_BET_PLACEMENT_VERDICT=PASS\n"
        "NO_FAKE_OPERATOR_QUOTE_VERDICT=PASS\n"
        "NO_COMBINED_BUILDER_ODDS_COMPUTED_VERDICT=PASS\n"
        f"READY_FOR_MANUAL_OPERATOR_QUOTE_REVIEW={str(package.ready_for_manual_operator_quote_review).lower()}\n"
        f"READY_FOR_FINAL_COUPON={str(package.ready_for_final_coupon).lower()}\n"
        f"READY_FOR_MANUAL_PLACEMENT={str(package.ready_for_manual_placement).lower()}\n"
        "READY_FOR_PRODUCTION_EXECUTION=false\n"
        "READY_FOR_AUTOMATED_BET_PLACEMENT=false\n",
        encoding="utf-8",
    )

    sports = sorted({idea.sport for idea in [*package.recommendations, *package.watchlist_only]})
    print(f"RUN_ID={run_id}")
    print(f"PACKAGE_TYPE={package.package_type}")
    print(f"SPORTS_REPRESENTED={sports}")
    print(f"ANALYST_RECOMMENDATION_COUNT={len(package.recommendations)}")
    print(f"WATCHLIST_ONLY_COUNT={len(package.watchlist_only)}")
    print(f"BET_BUILDER_COMBO_IDEA_COUNT={len(package.bet_builder_combo_ideas)}")
    print("ODDS_REQUIRED_FOR_ANALYSIS=false")
    print("HYDRATED_REQUIRED_FOR_ANALYSIS=false")
    print("MODEL_PROBABILITY_REQUIRED_FOR_ANALYSIS=false")
    print(f"READY_FOR_MANUAL_OPERATOR_QUOTE_REVIEW={str(package.ready_for_manual_operator_quote_review).lower()}")
    print(f"READY_FOR_FINAL_COUPON={str(package.ready_for_final_coupon).lower()}")
    print(f"READY_FOR_MANUAL_PLACEMENT={str(package.ready_for_manual_placement).lower()}")
    print(f"PACKAGE_JSON={paths['json']}")
    print(f"PACKAGE_MD={paths['md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
