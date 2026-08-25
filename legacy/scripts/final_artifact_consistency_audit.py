from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from bet.pipeline.final_artifact_consistency import (
    validate_analysis_first_consistency,
    scan_artifact_hygiene,
    validate_cross_artifact_consistency,
    validate_market_matrix_lineage,
    validate_test_manifest,
)


def load(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-root", required=True)
    ap.add_argument("--expected-run-id", default=None)
    ap.add_argument("--allowed-source-run-id", action="append", default=[])
    args = ap.parse_args()
    root = Path(args.run_root)
    expected_run_id = args.expected_run_id or root.name
    analysis_first = (root / "18B_analysis_first_candidate_board.json").exists() or (root / "12_analysis_portfolio_drafts.json").exists()

    final_report = load(root / "10_final_session_report.json", {})
    daily = load(root / "13_daily_session_certification.json", None)
    adversarial = load(root / "16D_final_adversarial_review.json", None)
    wimbledon = load(root / "16E_wimbledon_singles_classification_audit.json", None)
    manifest = load(root / "16F_final_evidence_export_manifest.json", None)
    quote_cards = (load(root / "09_manual_superbet_quote_cards.json", {}) or {}).get("quote_cards", [])
    groups = (load(root / "08_same_game_builder_idea_groups.json", {}) or {}).get("groups", [])
    drafts = (load(root / "12_coupon_drafts.json", {}) or {}).get("coupon_drafts", [])
    matrix = load(root / "05D_market_availability_matrix.json", {}) or {}
    board_rows = (load(root / "18B_analysis_first_candidate_board.json", {}) or {}).get("rows", [])
    concepts = (load(root / "18C_superbet_bet_builder_concepts.json", {}) or {}).get("concepts", [])
    portfolios = (load(root / "12_analysis_portfolio_drafts.json", {}) or {}).get("analysis_portfolios", [])
    shortlist = (load(root / "18D_optional_superbet_quote_check_shortlist.json", {}) or {}).get("rows", [])

    required_tests = {
        "tests/test_final_artifact_cross_consistency.py",
        "tests/test_builder_group_schema_quality.py",
        "tests/test_final_report_blocker_scoping.py",
        "tests/test_coupon_draft_multisport_diversification.py",
        "tests/test_artifact_hygiene_no_nested_absolute_paths.py",
        "tests/test_market_matrix_run_lineage.py",
        "tests/test_test_manifest_integrity.py",
    }
    if analysis_first:
        required_tests |= {
            "tests/test_odds_optional_analysis_contract.py",
            "tests/test_unpriced_candidates_not_rejected.py",
            "tests/test_pricing_tier_classification.py",
            "tests/test_bet_builder_concepts_operator_screen_only.py",
            "tests/test_analysis_first_board_sections.py",
            "tests/test_optional_quote_shortlist_not_required.py",
            "tests/test_analysis_portfolio_not_bettable.py",
            "tests/test_manual_quote_required_only_for_bettable.py",
            "tests/test_tipster_context_analysis_only.py",
            "tests/test_v17_to_v18_analysis_first_regression.py",
        }

    reports = [
        validate_analysis_first_consistency(
            final_report=final_report,
            daily_certification=daily,
            wimbledon_audit=wimbledon,
            candidate_board_rows=board_rows,
            bet_builder_concepts=concepts,
            analysis_portfolios=portfolios,
            optional_quote_shortlist=shortlist,
            builder_groups=groups,
        ) if analysis_first else validate_cross_artifact_consistency(
            final_report=final_report,
            daily_certification=daily,
            adversarial_review=adversarial,
            wimbledon_audit=wimbledon,
            export_manifest=manifest,
            quote_cards=quote_cards,
            builder_groups=groups,
            coupon_drafts=drafts,
        ),
        scan_artifact_hygiene(root),
        validate_market_matrix_lineage(
            matrix,
            expected_current_run_id=expected_run_id,
            allowed_source_run_ids=set(args.allowed_source_run_id),
        ),
        validate_test_manifest(
            manifest,
            required_test_files=required_tests,
        ),
    ]
    issues = [issue for report in reports for issue in report.issues]
    out = {
        "run_id": expected_run_id,
        "ok": not any(issue.severity == "BLOCK" for issue in issues),
        "blocker_count": sum(1 for issue in issues if issue.severity == "BLOCK"),
        "warning_count": sum(1 for issue in issues if issue.severity == "WARN"),
        "issues": [issue.__dict__ for issue in issues],
    }
    json_name = "18F_analysis_first_final_consistency_audit.json" if analysis_first else "17A_final_artifact_consistency_audit.json"
    md_name = "18F_analysis_first_final_consistency_audit.md" if analysis_first else "17A_final_artifact_consistency_audit.md"
    title = "# V18.1 analysis-first final consistency audit\n\n" if analysis_first else "# V17.1 final artifact consistency audit\n\n"
    (root / json_name).write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")
    (root / md_name).write_text(
        title
        +
        f"- run_id: `{out['run_id']}`\n"
        f"- ok: `{out['ok']}`\n"
        f"- blockers: `{out['blocker_count']}`\n"
        f"- warnings: `{out['warning_count']}`\n\n"
        + "\n".join(f"- {i['severity']} {i['code']}: {i['message']}" for i in out["issues"])
        + "\n",
        encoding="utf-8",
    )
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
