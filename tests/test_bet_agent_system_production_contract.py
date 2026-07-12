from scripts.audit_bet_agent_system_production import audit


def build_runtime_smoke_payload(child_runtime_model: str = "openai/gpt-5.4", **overrides):
    per_agent = overrides.pop("per_agent", {})
    parent_model = overrides.pop("active_parent_runtime_model", "openai/gpt-5.4")
    results = [
        {
            "agent_name": "bet-executor",
            "smoke_type": "PRIMARY_AGENT_CONFIG_SMOKE",
            "launched": False,
            "artifact_written": True,
            "artifact_path": "reports/pipeline_runs/test/bet-executor_runtime_smoke.md",
            "provider_model_not_found_error": False,
            "explicit_model_override_detected": False,
            "active_parent_runtime_model": parent_model,
            "child_runtime_model": parent_model,
            "inheritance_proof_mode": "PASS_BY_CONTRACT",
            "verdict": "PASS",
            "blocker": None,
            "blockers": [],
            "invalid_smoke_test_detected": False,
        }
    ]
    for agent_name in [
        "bet-researcher",
        "bet-modeler",
        "bet-risk-gatekeeper",
        "bet-builder",
        "bet-auditor",
        "bet-settler-postevent",
    ]:
        payload = {
            "agent_name": agent_name,
            "smoke_type": "DELEGATED_SUBAGENT_LAUNCH_SMOKE",
            "launched": True,
            "artifact_written": True,
            "artifact_path": f"reports/pipeline_runs/test/{agent_name}_runtime_smoke.md",
            "provider_model_not_found_error": False,
            "explicit_model_override_detected": False,
            "active_parent_runtime_model": parent_model,
            "child_runtime_model": child_runtime_model,
            "inherited_parent_model": "PASS_BY_CONTRACT",
            "inheritance_proof_mode": "PASS_BY_CONTRACT",
            "verdict": "PASS",
            "blocker": None,
            "blockers": [],
            "invalid_smoke_test_detected": False,
        }
        payload.update(per_agent.get(agent_name, {}))
        results.append(payload)
    top_level = {
        "run_id": "test-run",
        "active_parent_runtime_model": parent_model,
        "results": results,
        "conflicting_override_source": "NONE",
    }
    top_level.update(overrides)
    return top_level


def test_bet_agent_system_production_contract_passes():
    payload = audit(runtime_smoke_payload=build_runtime_smoke_payload())
    assert payload["status"] == "PASS", payload["failures"]


def test_production_contract_enforces_core_summary_flags():
    payload = audit(runtime_smoke_payload=build_runtime_smoke_payload())
    summary = payload["summary"]
    assert summary["required_agent_files_exist"] is True
    assert summary["required_prompt_files_exist"] is True
    assert summary["required_docs_exist"] is True
    assert summary["required_betting_agents_do_not_pin_model_overrides"] is True
    assert summary["ui_runtime_inheritance_policy_exists"] is True
    assert summary["safe_checkpoint_contract_exists"] is True
    assert summary["bet_executor_cannot_mutate_repo"] is True
    assert summary["code_general_repair_path_exists"] is True
    assert summary["no_stale_policy_strings"] is True
    assert summary["no_stale_betclic_operator_flow"] is True
    assert summary["output_schemas_present"] is True
    assert summary["continuation_protocol_present"] is True
    assert summary["no_recursive_delegation"] is True


def test_primary_agent_not_required_to_launch_as_subagent():
    payload = audit(runtime_smoke_payload=build_runtime_smoke_payload())
    assert payload["summary"]["primary_agent_config_smoke"]["smoke_type"] == "PRIMARY_AGENT_CONFIG_SMOKE"
    assert payload["summary"]["primary_agent_config_smoke"]["verdict"] == "PASS"


def test_executor_primary_config_smoke_can_pass():
    payload = audit(runtime_smoke_payload=build_runtime_smoke_payload())
    assert payload["summary"]["primary_agent_config_smoke"]["verdict"] == "PASS"
    assert payload["summary"]["invalid_smoke_test_detected"] is False


def test_inheritance_can_pass_by_contract_without_child_model_introspection():
    payload = audit(runtime_smoke_payload=build_runtime_smoke_payload(child_runtime_model="UNKNOWN_NOT_INTROSPECTABLE"))
    assert payload["summary"]["inheritance_proof_mode"] == "PASS_BY_CONTRACT"
    assert payload["status"] == "PASS", payload["failures"]


def test_unknown_child_runtime_model_does_not_fail_when_parent_known_and_no_override():
    payload = audit(runtime_smoke_payload=build_runtime_smoke_payload(child_runtime_model="UNKNOWN_NOT_INTROSPECTABLE"))
    assert payload["summary"]["unknown_child_runtime_model_accepted_by_contract"] is True
    assert payload["summary"]["delegated_subagent_launch_smoke"]["bet-modeler"]["verdict"] == "PASS"


def test_provider_model_not_found_still_fails():
    payload = audit(
        runtime_smoke_payload=build_runtime_smoke_payload(
            per_agent={"bet-modeler": {"provider_model_not_found_error": True}}
        )
    )
    assert payload["status"] == "FAIL"
    assert any("ProviderModelNotFoundError detected" in failure for failure in payload["failures"])


def test_explicit_conflicting_override_still_fails():
    payload = audit(
        runtime_smoke_payload=build_runtime_smoke_payload(
            per_agent={"bet-risk-gatekeeper": {"explicit_model_override_detected": True}},
            conflicting_override_source=".kilo/agents/bet-risk-gatekeeper.md:1",
        )
    )
    assert payload["status"] == "FAIL"
    assert payload["summary"]["conflicting_override_source"] == ".kilo/agents/bet-risk-gatekeeper.md:1"


def test_subagent_missing_role_local_artifact_fails():
    payload = audit(
        runtime_smoke_payload=build_runtime_smoke_payload(
            per_agent={"bet-builder": {"artifact_written": False, "artifact_path": None}}
        )
    )
    assert payload["status"] == "FAIL"
    assert any("missing role-local artifact" in failure for failure in payload["failures"])


def test_direct_role_smoke_cannot_prove_inheritance():
    payload = audit(
        runtime_smoke_payload=build_runtime_smoke_payload(
            per_agent={"bet-auditor": {"smoke_type": "DIRECT_ROLE_SMOKE"}}
        )
    )
    assert payload["status"] == "FAIL"
    assert any("invalid smoke type" in failure for failure in payload["failures"])


def test_runtime_smoke_contract_doc_exists():
    payload = audit(runtime_smoke_payload=build_runtime_smoke_payload())
    assert payload["summary"]["required_docs_exist"] is True


def test_gatekeeper_conflicting_override_requires_exact_source():
    payload = audit(
        runtime_smoke_payload=build_runtime_smoke_payload(
            per_agent={"bet-risk-gatekeeper": {"explicit_model_override_detected": True}},
            conflicting_override_source="UNKNOWN",
        )
    )
    assert payload["status"] == "FAIL"
    assert any("requires exact source" in failure for failure in payload["failures"])
