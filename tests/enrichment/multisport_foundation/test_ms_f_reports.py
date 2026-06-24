from __future__ import annotations

import json
from pathlib import Path
from bet.enrichment.multisport_foundation.source_inventory import TARGET_SPORTS

def test_pass_f_reports_exist_and_are_valid() -> None:
    base_dir = Path("reports/multisport_foundation/pass_f")
    assert base_dir.exists()

    plan_path = base_dir / "provider_probe_plan.json"
    results_path = base_dir / "provider_probe_results_by_sport.json"
    summary_path = base_dir / "pass_f_summary.json"

    assert plan_path.exists()
    assert results_path.exists()
    assert summary_path.exists()

    for path in (plan_path, results_path, summary_path):
        content = path.read_text(encoding="utf-8")
        
        # 1. Must be pretty JSON with 2 spaces indent
        lines = content.splitlines()
        # Simple check: should be multi-line
        assert len(lines) > 5

        # 2. Parseable and sort-keys preserved (we can load and re-dump, check identical)
        data = json.loads(content)
        re_dumped = json.dumps(data, indent=2, sort_keys=True) + "\n"
        assert content == re_dumped

        # 3. No secrets / raw credentials / cookies / bearer keys / auth header names
        content_lower = content.lower()
        for forbidden in ("bearer", "authorization", "cookie", "x-api-key", "x-apisports-key", "x-rapidapi-key"):
            assert forbidden not in content_lower, f"Forbidden substring '{forbidden}' found in {path}"

        # No production activation or betting decisions enabled
        assert "production_selectable\": true" not in content_lower
        assert "betting_decisions_enabled\": true" not in content_lower
        assert "production_activation\": true" not in content_lower
        assert "betting_decisions\": true" not in content_lower

        # No odds, stakes, recommendations
        for forbidden_concept in ("stake", "edge", "recommendation", "pick"):
            assert forbidden_concept not in content_lower

def test_reports_cover_exactly_seven_sports() -> None:
    base_dir = Path("reports/multisport_foundation/pass_f")
    
    plan = json.loads((base_dir / "provider_probe_plan.json").read_text(encoding="utf-8"))
    assert set(plan.get("target_sports", [])) == set(TARGET_SPORTS)
    assert len(plan.get("provider_probe_policies_by_sport", {})) == 7

    results = json.loads((base_dir / "provider_probe_results_by_sport.json").read_text(encoding="utf-8"))
    assert set(results.get("target_sports", [])) == set(TARGET_SPORTS)
    assert len(results.get("provider_probe_results_by_sport", {})) == 7

    summary = json.loads((base_dir / "pass_f_summary.json").read_text(encoding="utf-8"))
    assert set(summary.get("target_sports", [])) == set(TARGET_SPORTS)
    assert len(summary.get("provider_probe_statuses", {})) == 7
