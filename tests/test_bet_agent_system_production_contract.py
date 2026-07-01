from scripts.audit_bet_agent_system_production import audit


def test_bet_agent_system_production_contract_passes():
    payload = audit()
    assert payload["status"] == "PASS", payload["failures"]


def test_production_contract_enforces_core_summary_flags():
    payload = audit()
    summary = payload["summary"]
    assert summary["required_agent_files_exist"] is True
    assert summary["required_prompt_files_exist"] is True
    assert summary["required_docs_exist"] is True
    assert summary["required_betting_agents_do_not_pin_model_overrides"] is True
    assert summary["ui_runtime_inheritance_policy_exists"] is True
    assert summary["anti_loop_contract_exists"] is True
    assert summary["orchestrator_cannot_mutate_repo"] is True
    assert summary["engineer_can_mutate_repo"] is True
    assert summary["no_stale_policy_strings"] is True
    assert summary["no_stale_betclic_operator_flow"] is True
    assert summary["output_schemas_present"] is True
    assert summary["continuation_protocol_present"] is True
    assert summary["no_recursive_delegation"] is True
