from bet.enrichment.football_data_foundation.source_bound_activation.verifier import verify_activation_candidate_payload


REQUIRED_PROVIDERS = ("api-football", "football-data-org", "espn-baseline", "sportdb", "highlightly")


def make_valid_payload():
    return {
        "fixture_slug": "worldcup2026-norway-senegal",
        "decision": {
            "status": "ACTIVATION_CANDIDATE_SHADOW_ONLY",
            "selectable_for_production": False,
            "manual_authorization_required": True,
            "production_db_write_allowed": False,
            "betting_decision_allowed": False,
            "live_network_allowed": False,
        },
        "provider_ids": {p: "mock_id" for p in REQUIRED_PROVIDERS},
        "provider_fact_counts": {p: 10 for p in REQUIRED_PROVIDERS},
        "sqlite_summary": {"provider_fact_rows": {p: 10 for p in REQUIRED_PROVIDERS}},
        "score": {"home": 3, "away": 2},
        "conflicts": [],
        "shadow_status": "SHADOW_ENRICHMENT_READY_FOR_MANUAL_REVIEW",
        "source_bound_verifier_verdict": "PASS",
    }


def test_verifier_passes_valid_activation_candidate() -> None:
    payload = make_valid_payload()
    result = verify_activation_candidate_payload(payload)
    assert result.verdict == "PASS"
    assert not result.failed_requirements


def test_verifier_fails_production_ready() -> None:
    payload = make_valid_payload()
    payload["decision"]["status"] = "PRODUCTION_READY"
    payload["decision"]["selectable_for_production"] = True
    result = verify_activation_candidate_payload(payload)
    assert result.verdict == "FAIL"
    assert any("activation_status_not_shadow_only" in f for f in result.failed_requirements) or any("forbidden_text" in f for f in result.failed_requirements)


def test_verifier_fails_betting_decision_text() -> None:
    payload = make_valid_payload()
    payload["conflicts"] = ["this is a betting decision recommendation for the match"]
    result = verify_activation_candidate_payload(payload)
    assert result.verdict == "FAIL"
    assert any("forbidden_text" in f for f in result.failed_requirements)


def test_verifier_fails_raw_headers_and_secrets() -> None:
    payload = make_valid_payload()
    payload["conflicts"] = ["secret x-api-key inside raw_headers"]
    result = verify_activation_candidate_payload(payload)
    assert result.verdict == "FAIL"
    assert any("forbidden_text" in f for f in result.failed_requirements)
