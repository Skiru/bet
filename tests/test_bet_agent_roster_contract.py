from scripts.audit_bet_agent_roster import (
    AGENT_DIR,
    AGENTS_MD_PATH,
    PROJECT_PROFILE_PATH,
    REQUIRED_AGENTS,
    REQUIRED_INHERITED_SUBAGENTS,
    SMOKE_REQUIRED,
    build_matrix,
    load_jsonc,
    normalize_smoke_results,
    read_frontmatter_model,
)


def build_smoke_payload(active_runtime_model: str, **overrides):
    result_defaults = {
        "launched": True,
        "verdict": "PASS",
        "inherited_parent_model": True,
        "explicit_override_used": False,
        "explicit_override_approved": False,
        "conflicting_explicit_override": False,
        "provider_model_not_found_error": False,
        "silent_fallback_detected": False,
        "active_runtime_model": active_runtime_model,
    }
    results = []
    per_agent = overrides.pop("per_agent", {})
    for agent_name in SMOKE_REQUIRED:
        result = dict(result_defaults)
        result.update(per_agent.get(agent_name, {}))
        result["subagent_name"] = agent_name
        results.append(result)
    payload = {
        "active_runtime_model": active_runtime_model,
        "provider_model_not_found_error": False,
        "silent_fallback_detected": False,
        "results": results,
    }
    payload.update(overrides)
    return payload


def test_required_agents_do_not_pin_model_overrides():
    profile = load_jsonc(PROJECT_PROFILE_PATH)
    for agent_name in REQUIRED_AGENTS:
        assert read_frontmatter_model(AGENT_DIR / f"{agent_name}.md") is None
        assert "model" not in profile["agent"][agent_name]


def test_required_subagent_agent_files_inherit_parent_model():
    for agent_name in REQUIRED_INHERITED_SUBAGENTS:
        assert read_frontmatter_model(AGENT_DIR / f"{agent_name}.md") is None


def test_openai_active_runtime_smoke_can_pass_when_user_selected():
    matrix, summary, failures = build_matrix(smoke_payload=build_smoke_payload("openai/gpt-5.4"))
    assert summary["active_runtime_model"] == "openai/gpt-5.4"
    assert summary["active_runtime_unknown"] is False
    assert summary["provider_model_not_found_error"] is False
    assert summary["subagents_inherit_active_runtime_model"] is True
    assert summary["verdict"] == "PASS"
    assert not failures
    assert {matrix[name]["smoke_verdict"] for name in SMOKE_REQUIRED} == {"PASS"}


def test_gemini_active_runtime_smoke_can_pass_when_user_selected():
    matrix, summary, failures = build_matrix(smoke_payload=build_smoke_payload("google-vertex/gemini-3.5-flash"))
    assert summary["active_runtime_model"] == "google-vertex/gemini-3.5-flash"
    assert summary["verdict"] == "PASS"
    assert not failures
    assert all(matrix[name]["inherited_parent_model"] is True for name in SMOKE_REQUIRED)


def test_unknown_active_runtime_blocks():
    _, summary, failures = build_matrix(smoke_payload=build_smoke_payload("unknown"))
    assert summary["active_runtime_unknown"] is True
    assert summary["verdict"] == "FAIL"
    assert any("active runtime model is unknown" in failure for failure in failures)


def test_provider_model_not_found_blocks():
    payload = build_smoke_payload("openai/gpt-5.4", provider_model_not_found_error=True)
    _, summary, failures = build_matrix(smoke_payload=payload)
    assert summary["provider_model_not_found_error"] is True
    assert summary["verdict"] == "FAIL"
    assert any("ProviderModelNotFoundError detected" in failure for failure in failures)


def test_conflicting_subagent_override_blocks():
    payload = build_smoke_payload(
        "openai/gpt-5.4",
        per_agent={
            "bet-valuator": {
                "explicit_override_used": True,
                "conflicting_explicit_override": True,
                "inherited_parent_model": False,
            }
        },
    )
    matrix, summary, failures = build_matrix(smoke_payload=payload)
    assert summary["verdict"] == "FAIL"
    assert matrix["bet-valuator"]["conflicting_explicit_override"] is True
    assert any("conflicting explicit override detected" in failure for failure in failures)


def test_no_hardcoded_gemini_only_gate():
    content = AGENTS_MD_PATH.read_text(encoding="utf-8")
    assert "must resolve to `google-vertex/gemini-3.5-flash-flex-high`" not in content
    assert "inherit that verified Gemini 3.5 Flash Flex model" not in content
    assert "The active model selected in Kilo UI is the source of truth" in content


def test_subagents_must_inherit_active_runtime_model():
    payload = build_smoke_payload(
        "openai/gpt-5.4",
        per_agent={
            "bet-enricher": {
                "inherited_parent_model": False,
            }
        },
    )
    normalized = normalize_smoke_results(payload)
    assert normalized["smoke_map"]["bet-enricher"]["inherited_parent_model"] is False
    _, summary, failures = build_matrix(smoke_payload=payload)
    assert summary["subagents_inherit_active_runtime_model"] is False
    assert summary["verdict"] == "FAIL"
    assert any("subagent did not inherit active parent runtime model" in failure for failure in failures)
