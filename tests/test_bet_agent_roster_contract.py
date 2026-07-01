from pathlib import Path

from scripts.audit_bet_agent_roster import (
    AGENT_DIR,
    AGENTS_MD_PATH,
    ORCHESTRATOR,
    PROJECT_PROFILE_PATH,
    REQUIRED_INHERITED_SUBAGENTS,
    TARGET_ALIAS,
    TARGET_MODEL_KEY,
    TARGET_PROVIDER,
    build_matrix,
    load_global_provider_config,
    load_jsonc,
    read_frontmatter_model,
)


def test_orchestrator_stays_explicit_gemini_flex_high():
    assert read_frontmatter_model(AGENT_DIR / f"{ORCHESTRATOR}.md") == TARGET_ALIAS
    profile = load_jsonc(PROJECT_PROFILE_PATH)
    assert profile["agent"][ORCHESTRATOR]["model"] == TARGET_ALIAS


def test_required_subagent_agent_files_inherit_parent_model():
    for agent_name in REQUIRED_INHERITED_SUBAGENTS:
        assert read_frontmatter_model(AGENT_DIR / f"{agent_name}.md") is None


def test_required_subagent_profile_entries_inherit_parent_model():
    profile = load_jsonc(PROJECT_PROFILE_PATH)
    for agent_name in REQUIRED_INHERITED_SUBAGENTS:
        assert "model" not in profile["agent"][agent_name]


def test_global_vertex_catalog_contains_target_alias():
    global_config, _ = load_global_provider_config()
    vertex_models = global_config["provider"][TARGET_PROVIDER]["models"]
    assert TARGET_MODEL_KEY in vertex_models
    assert vertex_models[TARGET_MODEL_KEY]["id"] == "gemini-3.5-flash"


def test_agents_md_documents_inheritance_contract():
    content = AGENTS_MD_PATH.read_text(encoding="utf-8")
    assert "`bet-orchestrator` must resolve to `google-vertex/gemini-3.5-flash-flex-high`" in content
    assert "inherit that verified Gemini 3.5 Flash Flex model from `bet-orchestrator`" in content
    assert "explicit override that passes a live subagent launch smoke test" in content


def test_audit_matrix_accepts_inherited_parent_model_contract():
    matrix, summary, failures = build_matrix()
    assert summary["orchestrator_model_resolvable"] is True
    assert summary["explicit_subagent_model_overrides_removed"] is True
    assert summary["forbidden_model_routing_detected"] is False
    inherited_sources = {matrix[name]["model_source"] for name in REQUIRED_INHERITED_SUBAGENTS}
    assert inherited_sources == {"inherited_parent"}
    assert not [failure for failure in failures if "explicit model override remains present" in failure]
