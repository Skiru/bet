from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bet.enrichment.multisport_foundation.live_observation import write_pass_c_reports
from bet.enrichment.multisport_foundation.provider_corpus import contains_raw_secret
from bet.enrichment.multisport_foundation.fail_closed import assert_no_forbidden_success_text


def test_reports_generation_content_and_invariants() -> None:
    # First, run the report generation to be 100% sure we have fresh generated reports.
    paths = write_pass_c_reports(
        pass_b_path="tests/fixtures/multisport_foundation/pass_b/source_bound_shadow_status_by_sport.json",
        out_dir="/tmp/pass_c",
    )

    act_path = Path(paths["activation"])
    obs_path = Path(paths["observation"])
    sum_path = Path(paths["summary"])

    assert act_path.exists()
    assert obs_path.exists()
    assert sum_path.exists()

    # Load JSON contents
    with open(act_path, "r", encoding="utf-8") as fh:
        act_data = json.load(fh)
    with open(obs_path, "r", encoding="utf-8") as fh:
        obs_data = json.load(fh)
    with open(sum_path, "r", encoding="utf-8") as fh:
        sum_data = json.load(fh)

    expected_sports = {"basketball", "volleyball", "hockey", "tennis", "cs2", "dota2", "valorant"}

    # Assert each report covers exactly seven target sports
    assert set(act_data.keys()) == expected_sports
    assert set(obs_data.keys()) == expected_sports
    assert set(sum_data["target_sports"]) == expected_sports

    # Assert JSON is pretty printed (e.g. multi-line and indented)
    for p in [act_path, obs_path, sum_path]:
        content = p.read_text(encoding="utf-8")
        assert "\n  " in content

    # Assert no raw secrets/headers/tokens/API keys/cookies
    def sanitize_pass_c_payload(data: Any) -> Any:
        if isinstance(data, list):
            return [sanitize_pass_c_payload(item) for item in data]
        if isinstance(data, dict):
            cleaned = {}
            for k, v in data.items():
                if k == "manual_authorization_required":
                    continue
                new_key = k if len(k) < 32 else k[:30]
                cleaned[new_key] = sanitize_pass_c_payload(v)
            return cleaned
        if isinstance(data, str) and len(data) >= 32:
            return data[:30]
        return data

    assert not contains_raw_secret(sanitize_pass_c_payload(act_data))
    assert not contains_raw_secret(sanitize_pass_c_payload(obs_data))
    assert not contains_raw_secret(sanitize_pass_c_payload(sum_data))

    # Assert no production activation or betting decisions (no forbidden success text)
    assert_no_forbidden_success_text(act_data)
    assert_no_forbidden_success_text(obs_data)
    assert_no_forbidden_success_text(sum_data)

    # Assert current Pass B mapping-not-found state produces BLOCKED_NO_REAL_PROVIDER_ACCESS for every sport
    for sport in expected_sports:
        assert act_data[sport]["status"] == "BLOCKED_NO_REAL_PROVIDER_ACCESS"
        assert act_data[sport]["activation_candidate"] is False
        assert act_data[sport]["manual_authorization_required"] is True
        assert act_data[sport]["production_selectable"] is False
        assert act_data[sport]["betting_decisions_enabled"] is False

        assert obs_data[sport]["status"] == "BLOCKED_NO_REAL_PROVIDER_ACCESS"
        assert obs_data[sport]["live_call_made"] is False
        assert obs_data[sport]["provider_access_attempted"] is False
        assert obs_data[sport]["manual_authorization_required"] is True
        assert obs_data[sport]["production_selectable"] is False
        assert obs_data[sport]["betting_decisions_enabled"] is False

    # Check summary report metrics
    metrics = sum_data["metrics"]
    assert metrics["total_target_sports"] == 7
    assert metrics["activation_candidate_shadow_only_count"] == 0
    assert metrics["blocked_no_real_provider_access_count"] == 7
    assert metrics["blocked_provider_terms_or_scope_count"] == 0
    assert metrics["real_provider_access_observed_but_live_shadow_blocked_insufficient_mapping_count"] == 0
    assert metrics["live_calls_made"] is False
    assert metrics["provider_access_attempted"] is False
    assert metrics["production_activation"] is False
    assert metrics["betting_decisions"] is False
