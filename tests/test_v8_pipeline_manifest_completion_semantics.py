from bet.pipeline.manifest import load_pipeline_manifest, validate_pipeline_manifest


def test_every_production_stage_has_explicit_completion_semantics():
    manifest = load_pipeline_manifest()
    for stage in manifest.steps:
        assert stage.stage_scope in {"event", "run", "human"}
        assert stage.completion_policy in {
            "required",
            "optional",
            "conditional",
            "human_only",
        }
        assert isinstance(stage.automated, bool)


def test_s9_is_human_only_and_non_automated():
    stage = load_pipeline_manifest().get_step("S9")
    assert stage.stage_scope == "human"
    assert stage.completion_policy == "human_only"
    assert stage.automated is False


def test_event_and_run_scopes_match_registered_output_contracts():
    manifest = load_pipeline_manifest()
    assert manifest.get_step("S3").stage_scope == "event"
    assert manifest.get_step("S6").stage_scope == "run"
    assert validate_pipeline_manifest(manifest) == []


def test_missing_scope_or_policy_is_rejected():
    manifest = load_pipeline_manifest()
    manifest.get_step("S3").stage_scope = None
    manifest.get_step("S4").completion_policy = None
    errors = validate_pipeline_manifest(manifest)
    assert any("S3 missing or invalid stage_scope" in error for error in errors)
    assert any("S4 missing or invalid completion_policy" in error for error in errors)


def test_scope_conflict_with_contract_registry_is_rejected():
    manifest = load_pipeline_manifest()
    manifest.get_step("S6").stage_scope = "event"
    errors = validate_pipeline_manifest(manifest)
    assert any("S6 scope event conflicts" in error for error in errors)


def test_human_dependency_for_automated_stage_is_rejected():
    manifest = load_pipeline_manifest()
    stage = manifest.get_step("S8")
    stage.depends_on = ["S9"]
    errors = validate_pipeline_manifest(manifest)
    assert any("cannot depend on human step S9" in error for error in errors)


def test_dependency_cycle_is_rejected():
    manifest = load_pipeline_manifest()
    manifest.get_step("S2").depends_on = ["S5"]
    assert any(
        "Dependency cycle" in error for error in validate_pipeline_manifest(manifest)
    )


def test_conditional_policy_shape_is_validated():
    manifest = load_pipeline_manifest()
    stage = manifest.get_step("S3")
    stage.completion_policy = "conditional"
    stage.condition_id = None
    assert any(
        "requires condition_id" in error
        for error in validate_pipeline_manifest(manifest)
    )
    stage.completion_policy = "required"
    stage.condition_id = "unexpected"
    assert any(
        "forbids condition_id" in error
        for error in validate_pipeline_manifest(manifest)
    )
